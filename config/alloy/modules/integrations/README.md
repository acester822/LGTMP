# Alloy Integrations Modules

This directory contains optional integrations loaded from `config/alloy/master.alloy`.

## Included modules

- `ntopng.alloy`  
  Scrapes ntopng Prometheus metrics (defaults to `ntopng:3000/metrics`).
- `ai-monitoring.alloy`  
  Scrapes AI workload metrics (GPU via DCGM exporter, inference latency, token generation, LLM API endpoints).
- `llama-server.alloy`  
  Receives `prometheus.remote_write` from the LLM server's local Alloy agent (which scrapes
  llama-server instances on `localhost:10001-10011`) and forwards to configured destinations.
- `opnsense.alloy`  
  Scrapes OPNsense metrics endpoint when enabled.

## Enable AI / OPNsense / llama-server modules

Both AI monitoring and OPNsense are disabled by default for backward compatibility:

- `AI_MONITORING_ENABLED=true`
- `OPNSENSE_MONITORING_ENABLED=true`

The llama-server receiver is always-on (no enable guard); just expose the port and configure the
LLM server's Alloy to `remote_write` to `http://<this-host>:9999/api/v1/push`.

- `LLAMA_SERVER_METRICS_PORT=9999`  (optional, default: 9999)

