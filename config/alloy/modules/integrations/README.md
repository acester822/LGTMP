# Alloy Integrations Modules

This directory contains optional integrations loaded from `config/alloy/master.alloy`.

## Included modules

- `ntopng.alloy`  
  Scrapes ntopng Prometheus metrics (defaults to `ntopng:3000/metrics`).
- `ai-monitoring.alloy`  
  Scrapes AI workload metrics (GPU via DCGM exporter, inference latency, token generation, LLM API endpoints).
- `opnsense.alloy`  
  Scrapes OPNsense metrics endpoint when enabled.

## Enable AI / OPNsense modules

Both are disabled by default for backward compatibility:

- `AI_MONITORING_ENABLED=true`
- `OPNSENSE_MONITORING_ENABLED=true`

## Example configs

- `config/alloy/modules/integrations/examples/ai-monitoring-example.alloy`
- `config/alloy/modules/integrations/examples/opnsense-example.alloy`
