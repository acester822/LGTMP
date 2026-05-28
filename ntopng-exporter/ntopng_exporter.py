#!/usr/bin/env python3
"""
ntopng Prometheus Exporter
Polls the ntopng REST API and exposes metrics in Prometheus format.
"""

import os
import re
import logging
import sys

import requests
from requests.auth import HTTPBasicAuth
from prometheus_client import start_http_server, REGISTRY
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily

# ---------------------------------------------------------------------------
# Configuration (all overridable via environment variables)
# ---------------------------------------------------------------------------
NTOPNG_URL       = os.environ.get("NTOPNG_URL",       "http://10.10.10.2:3002")
NTOPNG_USER      = os.environ.get("NTOPNG_USER",      "admin")
NTOPNG_PASSWORD  = os.environ.get("NTOPNG_PASSWORD",  "admin")
EXPORTER_PORT    = int(os.environ.get("EXPORTER_PORT",    "9101"))
REQUEST_TIMEOUT  = int(os.environ.get("REQUEST_TIMEOUT",  "10"))
LOG_LEVEL        = os.environ.get("LOG_LEVEL",        "INFO").upper()
# Maximum hosts to track individually — limits label cardinality
TOP_HOSTS_LIMIT  = int(os.environ.get("TOP_HOSTS_LIMIT", "25"))

logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.INFO),
)
log = logging.getLogger("ntopng_exporter")

# L4 protocol number → human-readable name
L4_PROTO_MAP = {
    0: "HOPOPT",
    1: "ICMP",
    2: "IGMP",
    6: "TCP",
    17: "UDP",
    41: "IPv6",
    47: "GRE",
    50: "ESP",
    58: "ICMPv6",
    89: "OSPF",
    132: "SCTP",
}

_LABEL_SAFE = re.compile(r"[^a-zA-Z0-9_]")


def _sanitize(name: str) -> str:
    """Replace Prometheus-unsafe characters in label values."""
    return _LABEL_SAFE.sub("_", name)


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

class NtopngCollector:
    def __init__(self, url: str, user: str, password: str, timeout: int):
        self._url     = url.rstrip("/")
        self._auth    = HTTPBasicAuth(user, password)
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None):
        """Make an authenticated GET request and return the 'rsp' payload."""
        url = f"{self._url}{path}"
        try:
            resp = requests.get(url, auth=self._auth, params=params,
                                timeout=self._timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"HTTP error for {path}: {exc}") from exc
        data = resp.json()
        if data.get("rc") != 0:
            raise RuntimeError(
                f"API error for {path}: rc={data.get('rc')} "
                f"msg={data.get('rc_str_hr', data.get('rc_str'))}"
            )
        return data["rsp"]

    # ------------------------------------------------------------------
    # Top-level collect (called by prometheus_client on each scrape)
    # ------------------------------------------------------------------

    def collect(self):
        yield from self._collect_system()
        yield from self._collect_interfaces()

    # ------------------------------------------------------------------
    # System-level metrics
    # ------------------------------------------------------------------

    def _collect_system(self):
        try:
            data = self._get("/lua/rest/v2/get/system/health/stats.lua")
        except RuntimeError as exc:
            log.warning("system/health/stats: %s", exc)
            return

        # --- CPU load ---
        m = GaugeMetricFamily(
            "ntopng_cpu_load_percent",
            "Current overall CPU load percentage",
        )
        m.add_metric([], float(data.get("cpu_load", 0)))
        yield m

        # --- CPU state breakdown ---
        cpu_states = data.get("cpu_states", {})
        if cpu_states:
            m = GaugeMetricFamily(
                "ntopng_cpu_state_percent",
                "CPU time percentage per state",
                labels=["state"],
            )
            for state, val in cpu_states.items():
                m.add_metric([state], float(val))
            yield m

        # --- Memory ---
        mem_fields = {
            "mem_total":            ("ntopng_memory_total_kilobytes",            "Total system memory (KB)"),
            "mem_free":             ("ntopng_memory_free_kilobytes",             "Free system memory (KB)"),
            "mem_used":             ("ntopng_memory_used_kilobytes",             "Used system memory (KB)"),
            "mem_cached":           ("ntopng_memory_cached_kilobytes",           "Cached system memory (KB)"),
            "mem_sreclaimable":     ("ntopng_memory_sreclaimable_kilobytes",     "Slab reclaimable memory (KB)"),
            "mem_ntopng_resident":  ("ntopng_memory_ntopng_resident_kilobytes",  "ntopng resident set size (KB)"),
            "mem_ntopng_virtual":   ("ntopng_memory_ntopng_virtual_kilobytes",   "ntopng virtual memory size (KB)"),
        }
        for key, (metric_name, help_text) in mem_fields.items():
            if key in data:
                m = GaugeMetricFamily(metric_name, help_text)
                m.add_metric([], float(data[key]))
                yield m

        # --- Storage ---
        storage = data.get("storage", {})
        if storage:
            m = GaugeMetricFamily(
                "ntopng_storage_used_bytes",
                "Disk storage used by ntopng (bytes)",
            )
            m.add_metric([], float(storage.get("total", 0)) * 1024)
            yield m

        # --- Uptime & PID ---
        if "pid" in data:
            m = GaugeMetricFamily("ntopng_pid", "ntopng process ID")
            m.add_metric([], float(data["pid"]))
            yield m

        if "epoch" in data:
            m = GaugeMetricFamily("ntopng_last_update_timestamp_seconds",
                                  "Unix timestamp of last ntopng stats update")
            m.add_metric([], float(data["epoch"]))
            yield m

    # ------------------------------------------------------------------
    # Interface discovery + per-interface metrics
    # ------------------------------------------------------------------

    def _collect_interfaces(self):
        try:
            interfaces = self._get("/lua/rest/v2/get/ntopng/interfaces.lua")
        except RuntimeError as exc:
            log.error("interfaces: %s", exc)
            return

        if not isinstance(interfaces, list):
            log.warning("Unexpected interfaces response type: %s", type(interfaces))
            return

        for iface in interfaces:
            ifid   = iface.get("ifid")
            ifname = iface.get("ifname", str(ifid))
            yield from self._collect_iface_data(ifid, ifname)
            yield from self._collect_flow_traffic(ifid, ifname)
            yield from self._collect_l4_counters(ifid, ifname)
            yield from self._collect_l7_counters(ifid, ifname)
            yield from self._collect_dscp_stats(ifid, ifname)
            yield from self._collect_top_hosts(ifid, ifname)

    def _collect_iface_data(self, ifid, ifname):
        try:
            d = self._get("/lua/rest/v2/get/interface/data.lua",
                          params={"ifid": ifid})
        except RuntimeError as exc:
            log.warning("interface/data ifid=%s: %s", ifid, exc)
            return

        lbl  = [ifname]
        lbln = ["interface"]

        # Throughput
        yield self._gauge("ntopng_interface_throughput_bps",
                          "Interface throughput (bits/s)", lbln, lbl,
                          d.get("throughput_bps", 0))
        yield self._gauge("ntopng_interface_throughput_pps",
                          "Interface throughput (packets/s)", lbln, lbl,
                          d.get("throughput_pps", 0))

        # Download/upload throughput breakdown
        tput = d.get("throughput", {})
        if tput:
            m = GaugeMetricFamily(
                "ntopng_interface_direction_throughput_bps",
                "Interface directional throughput (bits/s)",
                labels=["interface", "direction"],
            )
            m.add_metric([ifname, "download"],
                         float(tput.get("download", {}).get("bps", 0)))
            m.add_metric([ifname, "upload"],
                         float(tput.get("upload", {}).get("bps", 0)))
            yield m

            m = GaugeMetricFamily(
                "ntopng_interface_direction_throughput_pps",
                "Interface directional throughput (packets/s)",
                labels=["interface", "direction"],
            )
            m.add_metric([ifname, "download"],
                         float(tput.get("download", {}).get("pps", 0)))
            m.add_metric([ifname, "upload"],
                         float(tput.get("upload", {}).get("pps", 0)))
            yield m

        # Active entities
        yield self._gauge("ntopng_interface_active_flows",
                          "Number of active flows on interface", lbln, lbl,
                          d.get("num_flows", 0))
        yield self._gauge("ntopng_interface_active_hosts",
                          "Number of active hosts on interface", lbln, lbl,
                          d.get("num_hosts", 0))
        yield self._gauge("ntopng_interface_active_local_hosts",
                          "Number of active local hosts on interface", lbln, lbl,
                          d.get("num_local_hosts", 0))
        yield self._gauge("ntopng_interface_active_devices",
                          "Number of active devices on interface", lbln, lbl,
                          d.get("num_devices", 0))

        # Alerted flows (gauges – current snapshot)
        yield self._gauge("ntopng_interface_alerted_flows",
                          "Number of alerted flows (total)", lbln, lbl,
                          d.get("alerted_flows", 0))

        alerted_fields = {
            "alerted_flows_error":   "error",
            "alerted_flows_warning": "warning",
            "alerted_flows_notice":  "notice",
        }
        m = GaugeMetricFamily(
            "ntopng_interface_alerted_flows_by_severity",
            "Alerted flows broken down by severity",
            labels=["interface", "severity"],
        )
        for key, sev in alerted_fields.items():
            if key in d:
                m.add_metric([ifname, sev], float(d[key]))
        yield m

        # Cumulative byte/packet counters — prefer *_since_reset variants
        bytes_dl = d.get("bytes_download_since_reset",  d.get("bytes_download",  0))
        bytes_ul = d.get("bytes_upload_since_reset",    d.get("bytes_upload",    0))
        pkts_dl  = d.get("packets_download_since_reset", d.get("packets_download", 0))
        pkts_ul  = d.get("packets_upload_since_reset",   d.get("packets_upload",  0))

        m = CounterMetricFamily(
            "ntopng_interface_bytes",
            "Total bytes on interface since stats reset",
            labels=["interface", "direction"],
        )
        m.add_metric([ifname, "download"], float(bytes_dl))
        m.add_metric([ifname, "upload"],   float(bytes_ul))
        yield m

        m = CounterMetricFamily(
            "ntopng_interface_packets",
            "Total packets on interface since stats reset",
            labels=["interface", "direction"],
        )
        m.add_metric([ifname, "download"], float(pkts_dl))
        m.add_metric([ifname, "upload"],   float(pkts_ul))
        yield m

        # Dropped packets
        yield self._counter("ntopng_interface_drops",
                            "Total dropped packets on interface", lbln, lbl,
                            d.get("tot_pkt_drops", d.get("drops", 0)))

        # TCP stats
        tcp = d.get("tcpPacketStats", {})
        if tcp:
            m = CounterMetricFamily(
                "ntopng_interface_tcp_anomalies",
                "TCP packet anomalies on interface",
                labels=["interface", "type"],
            )
            m.add_metric([ifname, "retransmissions"],
                         float(tcp.get("retransmissions", 0)))
            m.add_metric([ifname, "lost"],
                         float(tcp.get("lost", 0)))
            m.add_metric([ifname, "out_of_order"],
                         float(tcp.get("out_of_order", 0)))
            yield m

        # Uptime
        yield self._gauge("ntopng_interface_uptime_seconds",
                          "Interface monitoring uptime (seconds)", lbln, lbl,
                          d.get("uptime_sec", 0))

    def _collect_flow_traffic(self, ifid, ifname):
        try:
            d = self._get("/lua/rest/v2/get/flow/traffic_stats.lua",
                          params={"ifid": ifid})
        except RuntimeError as exc:
            log.warning("flow/traffic_stats ifid=%s: %s", ifid, exc)
            return

        m = CounterMetricFamily(
            "ntopng_flow_bytes",
            "Total bytes in flows on interface",
            labels=["interface", "direction"],
        )
        m.add_metric([ifname, "sent"],     float(d.get("totBytesSent",  0)))
        m.add_metric([ifname, "received"], float(d.get("totBytesRcvd",  0)))
        yield m

    def _collect_l4_counters(self, ifid, ifname):
        try:
            entries = self._get("/lua/rest/v2/get/flow/l4/counters.lua",
                                params={"ifid": ifid})
        except RuntimeError as exc:
            log.warning("flow/l4/counters ifid=%s: %s", ifid, exc)
            return

        if not entries:
            return

        m = GaugeMetricFamily(
            "ntopng_flow_l4_active_flows",
            "Active flows by L4 protocol on interface",
            labels=["interface", "protocol"],
        )
        for entry in entries:
            proto_id   = entry.get("id", 0)
            proto_name = L4_PROTO_MAP.get(proto_id, f"proto_{proto_id}")
            m.add_metric([ifname, proto_name], float(entry.get("count", 0)))
        yield m

    def _collect_l7_counters(self, ifid, ifname):
        try:
            entries = self._get("/lua/rest/v2/get/flow/l7/counters.lua",
                                params={"ifid": ifid})
        except RuntimeError as exc:
            log.warning("flow/l7/counters ifid=%s: %s", ifid, exc)
            return

        if not entries:
            return

        m = GaugeMetricFamily(
            "ntopng_flow_l7_active_flows",
            "Active flows by L7 application on interface",
            labels=["interface", "application"],
        )
        for entry in entries:
            app_name = _sanitize(entry.get("name", "unknown"))
            m.add_metric([ifname, app_name], float(entry.get("count", 0)))
        yield m

    def _collect_dscp_stats(self, ifid, ifname):
        try:
            entries = self._get("/lua/rest/v2/get/interface/dscp/stats.lua",
                                params={"ifid": ifid})
        except RuntimeError as exc:
            log.warning("interface/dscp/stats ifid=%s: %s", ifid, exc)
            return

        if not entries:
            return

        m = GaugeMetricFamily(
            "ntopng_interface_dscp_flows",
            "Flow count by DSCP class on interface",
            labels=["interface", "dscp_class"],
        )
        for entry in entries:
            label = _sanitize(entry.get("label", "unknown"))
            m.add_metric([ifname, label], float(entry.get("value", 0)))
        yield m

    # ------------------------------------------------------------------
    # Per-host timeseries (top N hosts by total bytes)
    # ------------------------------------------------------------------

    def _collect_top_hosts(self, ifid, ifname):
        try:
            rsp = self._get(
                "/lua/rest/v2/get/host/active.lua",
                params={
                    "ifid":        ifid,
                    "sortColumn":  "column_thpt",
                    "sortOrder":   "desc",
                    "currentPage": 1,
                    "perPage":     TOP_HOSTS_LIMIT,
                },
            )
        except RuntimeError as exc:
            log.warning("host/active ifid=%s: %s", ifid, exc)
            return

        hosts = rsp.get("data") if isinstance(rsp, dict) else rsp
        if not hosts:
            return

        # --- per-host gauges/counters ---
        thpt_bps = GaugeMetricFamily(
            "ntopng_host_throughput_bps",
            "Current throughput for host (bits/s)",
            labels=["interface", "host", "name", "country"],
        )
        thpt_pps = GaugeMetricFamily(
            "ntopng_host_throughput_pps",
            "Current throughput for host (packets/s)",
            labels=["interface", "host", "name", "country"],
        )
        active_flows = GaugeMetricFamily(
            "ntopng_host_active_flows",
            "Active flow count for host",
            labels=["interface", "host", "name", "country", "role"],
        )
        bytes_m = CounterMetricFamily(
            "ntopng_host_bytes",
            "Total bytes for host since first seen",
            labels=["interface", "host", "name", "country", "direction"],
        )
        score_m = GaugeMetricFamily(
            "ntopng_host_score",
            "Security score for host (higher = more anomalous)",
            labels=["interface", "host", "name", "country"],
        )

        for h in hosts:
            ip      = h.get("ip", h.get("name", "unknown"))
            name    = h.get("name", ip)
            country = h.get("country", "")
            lbl     = [ifname, ip, name, country]

            tput = h.get("thpt", {})
            thpt_bps.add_metric(lbl, float(tput.get("bps", 0)))
            thpt_pps.add_metric(lbl, float(tput.get("pps", 0)))

            flows = h.get("num_flows", {})
            if isinstance(flows, dict):
                active_flows.add_metric(lbl + ["client"],
                                        float(flows.get("as_client", 0)))
                active_flows.add_metric(lbl + ["server"],
                                        float(flows.get("as_server", 0)))
            else:
                active_flows.add_metric(lbl + ["total"], float(flows))

            b = h.get("bytes", {})
            if isinstance(b, dict):
                bytes_m.add_metric(lbl + ["sent"],     float(b.get("sent", 0)))
                bytes_m.add_metric(lbl + ["received"], float(b.get("recvd", 0)))

            sc = h.get("score", {})
            if isinstance(sc, dict):
                score_m.add_metric(lbl, float(sc.get("total", 0)))

        yield thpt_bps
        yield thpt_pps
        yield active_flows
        yield bytes_m
        yield score_m

    # ------------------------------------------------------------------
    # Metric family helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _gauge(name, help_text, label_names, label_values, value):
        m = GaugeMetricFamily(name, help_text, labels=label_names)
        m.add_metric(label_values, float(value))
        return m

    @staticmethod
    def _counter(name, help_text, label_names, label_values, value):
        m = CounterMetricFamily(name, help_text, labels=label_names)
        m.add_metric(label_values, float(value))
        return m


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    log.info("Starting ntopng exporter on port %d", EXPORTER_PORT)
    log.info("Targeting ntopng at: %s (user=%s)", NTOPNG_URL, NTOPNG_USER)

    collector = NtopngCollector(
        url      = NTOPNG_URL,
        user     = NTOPNG_USER,
        password = NTOPNG_PASSWORD,
        timeout  = REQUEST_TIMEOUT,
    )
    REGISTRY.register(collector)

    start_http_server(EXPORTER_PORT)
    log.info("Exporter ready — scrape http://0.0.0.0:%d/metrics", EXPORTER_PORT)

    # Block forever; prometheus_client handles scrape requests in background threads
    import signal
    signal.pause()


if __name__ == "__main__":
    main()
