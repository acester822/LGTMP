# Complete Utilities Setup

> **NOTE**:
> As of 4/15/2024


- [ ] Create #Github-Exporter  Docker Compose File
- [ ] Create #All-In-One-compose-yaml  Docker Compose File
- [ ] Create #Compose-Includes-Needed  referenced in #All-In-One-compose-yaml  
- [ ] Create #Config files needed for all programs

##  #Github-Exporter

Step 1: Create Github Exporter compose.yaml

```yaml
# ============================================================================ #
#                           Github Exporter
# ============================================================================ #

# Usage:
#   COMPOSE_EXPERIMENTAL_GIT_REMOTE=true docker compose up -d --remove-orphans
#   COMPOSE_EXPERIMENTAL_GIT_REMOTE=true docker compose down


# Note:

# include is available in Docker Compose version 2.20 and later, and Docker Desktop version 4.22 and later.

# docs: https://docs.docker.com/compose/multiple-compose-files/include/#include-and-overrides

# Note:
# include is available in Docker Compose version 2.20 and later, and Docker Desktop version 4.22 and later.
# docs: https://docs.docker.com/compose/multiple-compose-files/include/#include-and-overrides
include:
# # use git remote
# - path: https://github.com/qclaogui/codelab-monitoring.git#main:docker-compose/monolithic-mode/all-in-one/compose.yaml  # All in one(Logs Traces Metrics Profiles)
# - path: https://github.com/qclaogui/codelab-monitoring.git#main:docker-compose/monolithic-mode/metrics/compose.yaml     # Metrics
# - path: https://github.com/qclaogui/codelab-monitoring.git#main:docker-compose/monolithic-mode/logs/compose.yaml        # Metrics and Logs
# - path: https://github.com/qclaogui/codelab-monitoring.git#main:docker-compose/monolithic-mode/traces/compose.yaml      # Metrics and Traces
# - path: https://github.com/qclaogui/codelab-monitoring.git#main:docker-compose/monolithic-mode/profiles/compose.yaml    # Metrics and Profiles

# # use local path
- path: ../../docker-compose/monolithic-mode/all-in-one/compose.yaml

services:
  github-exporter:
    labels:
      metrics.grafana.com/scrape: true
    image: githubexporter/github-exporter:1.1.0
    environment:
    - REPOS=grafana/alloy

```

## #All-In-One-compose-yaml

Step 2: Create the compose.yaml that you referenced above


```yaml
version: '3.9'

# ============================================================================ #
#                  Monolithic Mode - All in one
# ============================================================================ #

# Note:
# include is available in Docker Compose version 2.20 and later, and Docker Desktop version 4.22 and later.
# docs: https://docs.docker.com/compose/multiple-compose-files/include/#include-and-overrides
include:
  - path: ../../common/compose-include/minio.yaml
  - path: ../../common/compose-include/memcached.yaml
  - path: ../../common/compose-include/grafana.yaml
  - path: ../../common/compose-include/alloy.yaml

# https://github.com/qclaogui/codelab-monitoring/blob/main/docker-compose/common/config/alloy/modules/compose/README.md
x-labels: &profiles-labels
  profiles.grafana.com/cpu.scrape: true
  profiles.grafana.com/memory.scrape: true
  profiles.grafana.com/goroutine.scrape: true

x-environment: &jaeger-environment
  JAEGER_AGENT_HOST: alloy
  JAEGER_AGENT_PORT: 6831
  JAEGER_SAMPLER_TYPE: const
  JAEGER_SAMPLER_PARAM: 1

# Configure a check that's run to determine whether or not containers for this service are "healthy".
# docs: https://docs.docker.com/compose/compose-file/compose-file-v3/#healthcheck
x-healthcheck: &status-healthcheck
  interval: 3s
  timeout: 2s
  retries: 10

configs:
  alloy_config_file:
    file: ../../common/config/alloy/all-in-one.alloy

services:
  gateway:
    labels:
      metrics.grafana.com/scrape: false
    depends_on: { loki: { condition: service_healthy }, tempo: { condition: service_healthy }, mimir: { condition: service_healthy }, pyroscope: { condition: service_healthy } }
    image: ${NGINX_IMAGE:-docker.io/nginxinc/nginx-unprivileged:1.25-alpine}
    restart: always
    volumes:
      - ../../common/config/nginx/10-default-lgtmp.envsh:/docker-entrypoint.d/10-default-lgtmp.envsh
      - ../../common/config/nginx/nginx.conf:/etc/nginx/templates/nginx.conf.template
      - ../../common/config/loki/gateway_loki.conf:/etc/nginx/templates/gateway_loki.conf.template
      - ../../common/config/tempo/gateway_tempo.conf:/etc/nginx/templates/gateway_tempo.conf.template
      - ../../common/config/mimir/gateway_mimir.conf:/etc/nginx/templates/gateway_mimir.conf.template
      - ../../common/config/pyroscope/gateway_pyroscope.conf:/etc/nginx/templates/gateway_pyroscope.conf.template
    healthcheck:
      test: [ "CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:8080/ || exit 1" ]
      interval: 3s
      timeout: 1s
      retries: 20

  loki:
    labels:
      <<: *profiles-labels
      metrics.grafana.com/scrape: false
      profiles.grafana.com/service_name: loki
    depends_on: { minio: { condition: service_healthy } }
    image: ${LOKI_IMAGE:-docker.io/grafana/loki:3.0.0}
    volumes:
      - ../../common/config/loki:/etc/loki
    command:
      - -config.file=/etc/loki/monolithic-mode-logs.yaml
      - -target=all
      - -config.expand-env=true
    environment:
      <<: *jaeger-environment
      JAEGER_TAGS: app=loki
    healthcheck:
      test: [ "CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:3100/ready || exit 1" ]
      <<: *status-healthcheck
    # expose 33100 port so we can directly access loki inside container
    ports:
      - "33100:3100"
    networks:
      default:
        aliases:
          - loki-memberlist

  tempo:
    labels:
      <<: *profiles-labels
      metrics.grafana.com/scrape: false
      profiles.grafana.com/service_name: tempo
    depends_on: { minio: { condition: service_healthy }, mimir: { condition: service_healthy } }
    image: ${TEMPO_IMAGE:-docker.io/grafana/tempo:2.4.1}
    volumes:
      - ../../common/config/tempo:/etc/tempo
    command:
      - -config.file=/etc/tempo/monolithic-mode-traces.yaml
      - -target=all
      - -config.expand-env=true
    environment:
      <<: *jaeger-environment
      JAEGER_TAGS: app=tempo
    healthcheck:
      test: [ "CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:3200/ready || exit 1" ]
      <<: *status-healthcheck
      start_period: 10s
    # expose 33200 port so we can directly access tempo inside container
    ports:
      - "33200:3200"

  mimir:
    labels:
      <<: *profiles-labels
      metrics.grafana.com/scrape: false
      profiles.grafana.com/service_name: mimir
    depends_on: { minio: { condition: service_healthy } }
    image: ${MIMIR_IMAGE:-docker.io/grafana/mimir:2.12.0}
    volumes:
      - ../../common/config/mimir:/etc/mimir
    command:
      - -config.file=/etc/mimir/monolithic-mode-metrics.yaml
      - -target=all
      - -config.expand-env=true
      - -ruler.max-rules-per-rule-group=50
    environment:
      <<: *jaeger-environment
      JAEGER_TAGS: app=mimir
    healthcheck:
      test: [ "CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:8080/ready || exit 1" ]
      <<: *status-healthcheck
    # expose 38080 port so we can directly access mimir inside container
    ports:
      - "38080:8080"
    networks:
      default:
        aliases:
          - mimir-memberlist

  mimirtool:
    # https://github.com/qclaogui/codelab-monitoring/blob/main/docker-compose/common/config/alloy/modules/compose/README.md
    labels:
      metrics.grafana.com/scrape: false
    image: ${MIMIRTOOL_IMAGE:-docker.io/grafana/mimirtool:2.12.0}
    volumes:
      # - ../../monitoring-mixins/github-mixin/deploy/github-mixin-rules.yaml:/rules/github-mixin-rules.yaml
      # - ../../monitoring-mixins/github-mixin/deploy/github-mixin-alerts.yaml:/rules/github-mixin-alerts.yaml
      - ../../../monitoring-mixins/crontab:/etc/crontabs/root
      - ../../../monitoring-mixins/alloy-mixin/deploy/alloy-mixin-alerts.yaml:/rules/alloy-mixin-alerts.yaml
      - ../../../monitoring-mixins/memcached-mixin/deploy/memcached-mixin-alerts.yaml:/rules/memcached-mixin-alerts.yaml
      - ../../../monitoring-mixins/mimir-mixin/deploy/mimir-mixin-rules.yaml:/rules/mimir-mixin-rules.yaml
      - ../../../monitoring-mixins/mimir-mixin/deploy/mimir-mixin-alerts.yaml:/rules/mimir-mixin-alerts.yaml
      - ../../../monitoring-mixins/loki-mixin/deploy/loki-mixin-rules.yaml:/rules/loki-mixin-rules.yaml
      - ../../../monitoring-mixins/loki-mixin/deploy/loki-mixin-alerts.yaml:/rules/loki-mixin-alerts.yaml
      - ../../../monitoring-mixins/pyroscope-mixin/deploy/pyroscope-mixin-rules.yaml:/rules/pyroscope-mixin-rules.yaml
      - ../../../monitoring-mixins/tempo-mixin/deploy/tempo-mixin-rules.yaml:/rules/tempo-mixin-rules.yaml
      - ../../../monitoring-mixins/tempo-mixin/deploy/tempo-mixin-alerts.yaml:/rules/tempo-mixin-alerts.yaml
    environment:
      - MIMIR_ADDRESS=http://gateway:8080
      - MIMIR_TENANT_ID=anonymous
    command: >-
      rules load /rules/alloy-mixin-alerts.yaml /rules/mimir-mixin-rules.yaml /rules/mimir-mixin-alerts.yaml /rules/tempo-mixin-alerts.yaml /rules/tempo-mixin-rules.yaml /rules/loki-mixin-rules.yaml /rules/loki-mixin-alerts.yaml /rules/memcached-mixin-alerts.yaml /rules/pyroscope-mixin-rules.yaml



  pyroscope:
    labels:
      metrics.grafana.com/scrape: false
      profiles.grafana.com/service_name: pyroscope
    depends_on: { minio: { condition: service_healthy } }
    image: ${PYROSCOPE_IMAGE:-docker.io/grafana/pyroscope:1.5.0}
    volumes:
      - ../../common/config/pyroscope:/etc/pyroscope
      - pyroscope_data:/data
    command:
      - -config.file=/etc/pyroscope/monolithic-mode-profiles.yaml
      - -config.expand-env=true
    environment:
      <<: *jaeger-environment
      JAEGER_TAGS: app=pyroscope
    healthcheck:
      test: [ "CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:4040/ready || exit 1" ]
      <<: *status-healthcheck
    # expose 34040 port so we can directly access pyroscope inside container
    ports:
      - "34040:4040"

volumes:
  pyroscope_data:

```

```shell
COMPOSE_EXPERIMENTAL_GIT_REMOTE=true docker compose up -d --remove-orphans
```

## #Compose-Includes-Needed

Step 3: These compose.yaml files are also needed and referenced in step 2

### #Minio:

```yaml
services:
  minio:
    # https://github.com/qclaogui/codelab-monitoring/blob/main/docker-compose/common/config/alloy/modules/compose/README.md
    labels:
      logs.grafana.com/scrape: false
      metrics.grafana.com/scrape: true
      metrics.grafana.com/job: minio-job
      metrics.grafana.com/path: /minio/v2/metrics/cluster
      metrics.grafana.com/port: 9000
      metrics.grafana.com/interval: 15s
      metrics.grafana.com/timeout: 10s
    image: ${MINIO_IMAGE:-docker.io/minio/minio:RELEASE.2024-03-15T01-07-19Z}
    entrypoint:
      - sh
      - -euc
      - |
        mkdir -p /data/mimir-blocks /data/mimir-ruler /data/mimir-alertmanager && \
        mkdir -p /data/loki-data /data/loki-ruler && \
        mkdir -p /data/tempo-data  && \
        mkdir -p /data/pyroscope-data && \
        minio server /data --console-address ':9001'
    environment:
      - MINIO_ROOT_USER=lgtmp
      - MINIO_ROOT_PASSWORD=supersecret
      - MINIO_PROMETHEUS_AUTH_TYPE=public
      - MINIO_UPDATE=off
      # # https://github.com/minio/console/issues/3237#issuecomment-1947485286
      # - MINIO_PROMETHEUS_URL="http://gateway:8080/prometheus"
      # - MINIO_PROMETHEUS_JOB_ID="minio-job"
    volumes:
      - minio_data:/data:delegated
    healthcheck:
      test: ["CMD-SHELL", "mc ready local"]
      interval: 2s
      timeout: 1s
      retries: 15
    ports:
      - "9001:9001"

volumes:
  minio_data:

```

### #Memcached / Memcached Exporter:

```yaml
services:
  memcached:
    labels:
      metrics.grafana.com/scrape: false
    image: ${MEMCACHED_IMAGE:-docker.io/memcached:1.6.24-alpine}

  # Use Alloy prometheus.exporter.memcached component instead of memcached-exporter
  # https://github.com/qclaogui/codelab-monitoring/pull/98
  memcached-exporter:
    labels:
      - logs.grafana.com/scrape=false
      - metrics.grafana.com/scrape=false
      - metrics.grafana.com/job=memcached
      - metrics.grafana.com/port=9150
      - metrics.grafana.com/interval=15s
    image: ${MEMCACHED_EXPORTER_IMAGE:-prom/memcached-exporter:v0.14.2}
    command:
      - --memcached.address=memcached:11211
      - --web.listen-address=0.0.0.0:9150

```

### #Grafana / Inbucket

```yaml
services:
  # Inbucket is an email testing service; it will accept email for any email
  # address and make it available to view without a password
  #
  # https://inbucket.org/packages/docker.html
  # https://github.com/inbucket/inbucket/blob/main/doc/config.md
  inbucket:
    labels:
      metrics.grafana.com/scrape: false
    image: ${INBUCKET_IMAGE:-inbucket/inbucket:3.0.4}
    ports:
      - 2500 # SMTP
      - "39000:9000" # HTTP
      - 1100 # POP3
    volumes:
      - inbucket_data:/storage
      - inbucket_data:/config

  grafana:
    labels:
      metrics.grafana.com/scrape: false
    image: ${GRAFANA_IMAGE:-docker.io/grafana/grafana:10.4.1}
    command:
      - --config=/etc/grafana-config/grafana.ini
    volumes:
      - ../config/grafana/grafana.ini:/etc/grafana-config/grafana.ini
      - ../config/grafana/dashboards:/var/lib/grafana/dashboards
      - ../config/grafana/provisioning:/etc/grafana/provisioning
      - ../../../monitoring-mixins/github-mixin/deploy/dashboards_out:/var/lib/grafana/dashboards/github-mixin
      - ../../../monitoring-mixins/alloy-mixin/deploy/dashboards_out:/var/lib/grafana/dashboards/alloy-mixin
      - ../../../monitoring-mixins/memcached-mixin/deploy/dashboards_out:/var/lib/grafana/dashboards/memcached-mixin
      - ../../../monitoring-mixins/go-runtime-mixin/deploy/dashboards_out:/var/lib/grafana/dashboards/go-runtime-mixin
      - ../../../monitoring-mixins/mimir-mixin/deploy/dashboards_out:/var/lib/grafana/dashboards/mimir-mixin
      - ../../../monitoring-mixins/memcached-mixin/deploy/dashboards_out:/var/lib/grafana/dashboards/memcached-mixin
      - ../../../monitoring-mixins/pyroscope-mixin/deploy/dashboards_out:/var/lib/grafana/dashboards/pyroscope-mixin
      - ../../../monitoring-mixins/loki-mixin/deploy/dashboards_out:/var/lib/grafana/dashboards/loki-mixin
      - ../../../monitoring-mixins/tempo-mixin/deploy/dashboards_out:/var/lib/grafana/dashboards/tempo-mixin
    environment:
      GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH: /var/lib/grafana/dashboards/github-mixin/api-usage.json
      GF_FEATURE_TOGGLES_ENABLE: traceqlEditor tracesEmbeddedFlameGraph traceqlSearch correlations metricsSummary traceToMetrics traceToProfiles
      GF_SMTP_ENABLED: true
      GF_SMTP_HOST: inbucket:2500
    ports:
      - "3000:3000"

volumes:
  inbucket_data:

```

### #Alloy

```yaml
services:
  alloy:
    depends_on: { gateway: { condition: service_healthy } }
    image: ${ALLOY_IMAGE:-docker.io/grafana/alloy:v1.0.0}
    configs:
      - source: alloy_config_file
        target: /etc/alloy/config.alloy
    volumes:
      - ../config/alloy/modules:/etc/alloy/modules
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /var/lib/docker:/var/lib/docker:ro
      - /:/rootfs:ro
      - /sys:/sys:ro
    entrypoint:
      - /bin/alloy
      - run
      - /etc/alloy/config.alloy
      - --server.http.listen-addr=0.0.0.0:12345
      - --cluster.enabled=true
      - --cluster.join-addresses=alloy-cluster:12345
      - --disable-reporting=true
      - --stability.level=experimental
      - --storage.path=/var/lib/alloy/data
    environment:
      - ALLOY_MODULES_FOLDER=/etc/alloy/modules
      - ALLOY_LOG_LEVEL=warn
    ports:
      - "12345:12345"
      # - "12345-12348:12345" # Note: max replicas num is 3.
    deploy:
      replicas: 1
    networks:
      default:
        aliases:
          - alloy-cluster

```
