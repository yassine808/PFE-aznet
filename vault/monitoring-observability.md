---
tags: [pfe, monitoring, observability, alerting, prometheus, grafana, sentry, uptime]
type: technical
priority: high
status: current
---

# Monitoring & Observability Stack

## Overview

Complete observability for the PFE system across all layers:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        OBSERVABILITY LAYERS                         │
├──────────────┬──────────────┬──────────────┬───────────────────────┤
│  INFRA       │  PLATFORM    │  APPLICATION │  BUSINESS             │
│  (VPS, Net)  │  (n8n, Vercel)│  (API)       │  (Reports, SLA)       │
├──────────────┼──────────────┼──────────────┼───────────────────────┤
│  • CPU/MEM   │  • Exec rate │  • Latency   │  • Reports/day        │
│  • Disk      │  • Queue     │  • Errors    │  • STT accuracy       │
│  • Network   │  • Errors    │  • Cold start│  • Extraction conf.   │
│  • SSL expiry│  • Webhooks  │  • Throughput│  • End-to-end latency │
└──────────────┴──────────────┴──────────────┴───────────────────────┘
```

---

## Tool Stack (All Free Tier Compatible)

| Layer | Tool | Cost | Purpose |
|-------|------|------|---------|
| **Metrics** | Prometheus + Grafana | Free (self-hosted) | Time-series, dashboards, alerts |
| **Logs** | Loki + Grafana | Free (self-hosted) | Log aggregation, query |
| **Traces** | Jaeger | Free (self-hosted) | Distributed tracing |
| **Errors** | Sentry | Free (5k events/mo) | Error tracking, alerting |
| **Uptime** | UptimeRobot / Better Uptime | Free (50/10 monitors) | External availability |
| **Heartbeat** | GitHub Actions + cron | Free | Keep-warm, synthetic checks |

---

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   API       │     │   n8n       │     │   VPS       │
│  (Vercel)   │     │  (VPS)      │     │  (System)   │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌────────────────────────────────────────────────────────────┐
│                    PROMETHEUS (VPS)                        │
│  Scrapes: /metrics from API, n8n, Node Exporter, Caddy    │
└──────────────────────────┬─────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         ┌─────────┐ ┌──────────┐ ┌───────────┐
         │ GRAFANA │ │ ALERT-   │ │   LOKI    │
         │ DASH-   │ │ MANAGER  │ │  (Logs)   │
         │ BOARDS  │ │          │ │           │
         └─────────┘ └──────────┘ └───────────┘
              │            │            │
              └────────────┼────────────┘
                           ▼
                    ┌──────────────┐
                    │ NOTIFICATION │
                    │  (Email,     │
                    │  Slack,      │
                    │  Telegram)   │
                    └──────────────┘
```

---

## Prometheus Setup (VPS)

### Docker Compose (Complete Stack)

```yaml
# /opt/monitoring/docker-compose.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:v2.48.0
    restart: unless-stopped
    ports:
      - "127.0.0.1:9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - ./rules:/etc/prometheus/rules
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
      - '--storage.tsdb.retention.size=10GB'
      - '--web.enable-lifecycle'
    networks:
      - monitoring

  alertmanager:
    image: prom/alertmanager:v0.26.0
    restart: unless-stopped
    ports:
      - "127.0.0.1:9093:9093"
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml
      - alertmanager_data:/alertmanager
    networks:
      - monitoring

  grafana:
    image: grafana/grafana:10.2.0
    restart: unless-stopped
    ports:
      - "127.0.0.1:3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
      - GF_INSTALL_PLUGINS=grafana-piechart-panel,grafana-worldmap-panel
      - GF_SERVER_ROOT_URL=https://monitor.aznet.ma/
      - GF_SERVER_SERVE_FROM_SUB_PATH=true
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./grafana/datasources:/etc/grafana/provisioning/datasources
    networks:
      - monitoring

  loki:
    image: grafana/loki:2.9.0
    restart: unless-stopped
    ports:
      - "127.0.0.1:3100:3100"
    volumes:
      - ./loki-config.yml:/etc/loki/local-config.yaml
      - loki_data:/loki
    command: -config.file=/etc/loki/local-config.yaml
    networks:
      - monitoring

  promtail:
    image: grafana/promtail:2.9.0
    restart: unless-stopped
    volumes:
      - /var/log:/var/log:ro
      - /opt/n8n/data:/opt/n8n/data:ro
      - ./promtail-config.yml:/etc/promtail/config.yml
    command: -config.file=/etc/promtail/config.yml
    networks:
      - monitoring

  node-exporter:
    image: prom/node-exporter:v1.7.0
    restart: unless-stopped
    ports:
      - "127.0.0.1:9100:9100"
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
    networks:
      - monitoring

  caddy:
    image: caddy:2.7
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - monitoring

networks:
  monitoring:
    driver: bridge

volumes:
  prometheus_data:
  alertmanager_data:
  grafana_data:
  loki_data:
  caddy_data:
  caddy_config:
```

### Prometheus Config (`prometheus.yml`)

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    environment: 'production'
    project: 'pfe-aznet'

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']

rule_files:
  - '/etc/prometheus/rules/*.yml'

scrape_configs:
  # Prometheus self-monitoring
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  # Node Exporter (System metrics)
  - job_name: 'node-exporter'
    static_configs:
      - targets: ['node-exporter:9100']

  # n8n Application Metrics
  - job_name: 'n8n'
    static_configs:
      - targets: ['host.docker.internal:5678']
    metrics_path: '/metrics'
    basic_auth:
      username: ${N8N_USER}
      password: ${N8N_PASSWORD}

  # Vercel API (via custom exporter or Vercel integration)
  # Option A: Vercel Analytics API (requires Pro)
  # Option B: Custom /metrics endpoint in API
  - job_name: 'pfe-api'
    static_configs:
      - targets: ['api.aznet.ma']
    metrics_path: '/metrics'
    scheme: https
    # Add auth if needed

  # Caddy (Web server metrics)
  - job_name: 'caddy'
    static_configs:
      - targets: ['caddy:2019']
    metrics_path: '/metrics'

  # Blackbox Exporter (External endpoint checks)
  - job_name: 'blackbox-http'
    metrics_path: /probe
    params:
      module: [http_2xx]
    static_configs:
      - targets:
        - https://api.aznet.ma/health
        - https://n8n.aznet.ma/healthz
        - https://api.telegram.org
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: blackbox-exporter:9115

  # Blackbox Exporter (TCP checks)
  - job_name: 'blackbox-tcp'
    metrics_path: /probe
    params:
      module: [tcp_connect]
    static_configs:
      - targets:
        - api.aznet.ma:443
        - n8n.aznet.ma:443
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: blackbox-exporter:9115

# Remote write (optional - for long-term storage)
# remote_write:
#   - url: https://prometheus-prod.example.com/api/v1/write
```

### Alert Rules (`rules/pfe-alerts.yml`)

```yaml
groups:
  # ─── API Alerts ──────────────────────────────────────────────
  - name: pfe-api
    interval: 30s
    rules:
      - alert: APIHighErrorRate
        expr: |
          sum(rate(http_requests_total{job="pfe-api",status=~"5.."}[5m]))
          /
          sum(rate(http_requests_total{job="pfe-api"}[5m])) > 0.05
        for: 2m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "API error rate > 5%"
          description: "5xx errors exceed 5% of requests for 2 minutes"
          runbook: "https://github.com/aznet/pfe-aznet/wiki/Runbook-API-High-Error-Rate"

      - alert: APIHighLatency
        expr: |
          histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="pfe-api"}[5m])) by (le)) > 15
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "API p95 latency > 15s"
          description: "95th percentile response time exceeds 15 seconds"

      - alert: APIColdStartSpike
        expr: |
          rate(cold_starts_total{job="pfe-api"}[5m]) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High cold start rate"
          description: "More than 0.5 cold starts per second"

      - alert: APIDown
        expr: up{job="pfe-api"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "API is down"
          description: "API health endpoint unreachable for 1 minute"

  # ─── n8n Alerts ──────────────────────────────────────────────
  - name: pfe-n8n
    interval: 30s
    rules:
      - alert: N8NWorkflowFailureRate
        expr: |
          sum(rate(n8n_workflow_executions_total{status="error"}[5m]))
          /
          sum(rate(n8n_workflow_executions_total[5m])) > 0.1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "n8n workflow failure rate > 10%"

      - alert: N8NExecutionTimeout
        expr: |
          rate(n8n_workflow_executions_total{status="timeout"}[5m]) > 0.01
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "n8n executions timing out"

      - alert: N8NQueueBacklog
        expr: n8n_queue_size > 50
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "n8n queue backlog > 50"

      - alert: N8NDown
        expr: up{job="n8n"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "n8n is down"

  # ─── System Alerts ───────────────────────────────────────────
  - name: pfe-system
    interval: 30s
    rules:
      - alert: HighCPUUsage
        expr: 100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "CPU usage > 85%"

      - alert: HighMemoryUsage
        expr: (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100 > 85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Memory usage > 85%"

      - alert: DiskSpaceLow
        expr: (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100 < 15
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Disk space < 15%"

      - alert: SSLCertificateExpiring
        expr: ssl_certificate_expiration_timestamp_seconds - time() < 86400 * 30
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "SSL certificate expires in < 30 days"

  # ─── Business Alerts ─────────────────────────────────────────
  - name: pfe-business
    interval: 60s
    rules:
      - alert: NoReportsReceived
        expr: |
          increase(reports_received_total[1h]) == 0
        for: 2h
        labels:
          severity: warning
        annotations:
          summary: "No reports received in 2 hours"
          description: "Expected reports from technicians but none received"

      - alert: LowExtractionConfidence
        expr: |
          avg(extraction_confidence_score) < 0.6
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Average extraction confidence low"
          description: "Average confidence score below 0.6 over 1 hour"
```

---

## Grafana Dashboards

### Dashboard 1: System Overview

```json
{
  "dashboard": {
    "title": "PFE System Overview",
    "uid": "pfe-overview",
    "tags": ["pfe", "overview"],
    "timezone": "Africa/Casablanca",
    "panels": [
      {
        "id": 1,
        "title": "System Health",
        "type": "stat",
        "gridPos": {"x": 0, "y": 0, "w": 6, "h": 4},
        "targets": [
          {"expr": "up{job=\"pfe-api\"}", "legendFormat": "API"},
          {"expr": "up{job=\"n8n\"}", "legendFormat": "n8n"},
          {"expr": "up{job=\"node-exporter\"}", "legendFormat": "VPS"}
        ],
        "fieldConfig": {
          "defaults": {
            "mappings": [
              {"type": "value", "options": {"1": {"text": "UP", "color": "green"}}, "result": {"text": "DOWN", "color": "red"}}
            ]
          }
        }
      },
      {
        "id": 2,
        "title": "Reports Processed (Last 24h)",
        "type": "stat",
        "gridPos": {"x": 6, "y": 0, "w": 6, "h": 4},
        "targets": [
          {"expr": "increase(reports_received_total[24h])", "legendFormat": "Count"}
        ]
      },
      {
        "id": 3,
        "title": "End-to-End Latency (p50/p95/p99)",
        "type": "graph",
        "gridPos": {"x": 0, "y": 4, "w": 12, "h": 8},
        "targets": [
          {"expr": "histogram_quantile(0.50, rate(e2e_latency_seconds_bucket[5m]))", "legendFormat": "p50"},
          {"expr": "histogram_quantile(0.95, rate(e2e_latency_seconds_bucket[5m]))", "legendFormat": "p95"},
          {"expr": "histogram_quantile(0.99, rate(e2e_latency_seconds_bucket[5m]))", "legendFormat": "p99"}
        ]
      },
      {
        "id": 4,
        "title": "Error Rate by Component",
        "type": "graph",
        "gridPos": {"x": 12, "y": 4, "w": 12, "h": 8},
        "targets": [
          {"expr": "rate(http_requests_total{job=\"pfe-api\",status=~\"5..\"}[5m])", "legendFormat": "API 5xx"},
          {"expr": "rate(n8n_workflow_executions_total{status=\"error\"}[5m])", "legendFormat": "n8n Errors"}
        ]
      }
    ]
  }
}
```

### Dashboard 2: API Deep Dive

```json
{
  "dashboard": {
    "title": "PFE API Metrics",
    "uid": "pfe-api",
    "panels": [
      {
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {"expr": "sum(rate(http_requests_total{job=\"pfe-api\"}[1m])) by (method, path)", "legendFormat": "{{method}} {{path}}"}
        ]
      },
      {
        "title": "Latency Distribution",
        "type": "heatmap",
        "targets": [
          {"expr": "sum(rate(http_request_duration_seconds_bucket{job=\"pfe-api\"}[5m])) by (le)"}
        ]
      },
      {
        "title": "STT Provider Performance",
        "type": "graph",
        "targets": [
          {"expr": "sum(rate(stt_duration_seconds_bucket{job=\"pfe-api\"}[5m])) by (provider, le)", "legendFormat": "{{provider}}"}
        ]
      },
      {
        "title": "Extraction Confidence",
        "type": "graph",
        "targets": [
          {"expr": "rate(extraction_confidence_total{job=\"pfe-api\",confidence=\"high\"}[5m])", "legendFormat": "High"},
          {"expr": "rate(extraction_confidence_total{job=\"pfe-api\",confidence=\"medium\"}[5m])", "legendFormat": "Medium"},
          {"expr": "rate(extraction_confidence_total{job=\"pfe-api\",confidence=\"low\"}[5m])", "legendFormat": "Low"}
        ]
      },
      {
        "title": "Cold Starts",
        "type": "graph",
        "targets": [
          {"expr": "rate(cold_starts_total{job=\"pfe-api\"}[5m])", "legendFormat": "Cold Starts/sec"}
        ]
      }
    ]
  }
}
```

### Dashboard 3: Business KPIs

```json
{
  "dashboard": {
    "title": "PFE Business KPIs",
    "uid": "pfe-business",
    "panels": [
      {
        "title": "Daily Reports Volume",
        "type": "graph",
        "targets": [
          {"expr": "sum(increase(reports_received_total[1d])) by (date)", "legendFormat": "{{date}}"}
        ]
      },
      {
        "title": "Reports by Technician",
        "type": "piechart",
        "targets": [
          {"expr": "sum(increase(reports_received_total[7d])) by (technicien)", "legendFormat": "{{technicien}}"}
        ]
      },
      {
        "title": "Reports by Chantier",
        "type": "table",
        "targets": [
          {"expr": "sum(increase(reports_received_total[7d])) by (chantier, type_travail)", "format": "table"}
        ]
      },
      {
        "title": "STT Confidence Low Rate",
        "type": "graph",
        "targets": [
          {"expr": "sum(increase(reports_stt_confidence_low_total[1d])) / sum(increase(reports_received_total[1d]))", "legendFormat": "Low STT Confidence Rate"}
        ]
      },
      {
        "title": "Audio Duration Distribution",
        "type": "heatmap",
        "targets": [
          {"expr": "sum(rate(audio_duration_seconds_bucket[5m])) by (le)"}
        ]
      }
    ]
  }
}
```

---

## Alertmanager Configuration (`alertmanager.yml`)

```yaml
global:
  resolve_timeout: 5m
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'alerts@aznet.ma'
  smtp_auth_username: 'alerts@aznet.ma'
  smtp_auth_password: '${GMAIL_APP_PASSWORD}'
  smtp_require_tls: true

route:
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: 'critical-alerts'
      continue: true
    - match:
        team: platform
      receiver: 'platform-team'

receivers:
  - name: 'default'
    email_configs:
      - to: 'manager@aznet.ma'
        send_resolved: true
        headers:
          Subject: '[PFE] {{ .GroupLabels.alertname }} - {{ .Status }}'
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL}'
        channel: '#pfe-alerts'
        send_resolved: true
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}\n{{ .Annotations.description }}{{ end }}'

  - name: 'critical-alerts'
    email_configs:
      - to: 'oncall@aznet.ma,manager@aznet.ma'
        send_resolved: true
        headers:
          Subject: '[PFE CRITICAL] {{ .GroupLabels.alertname }}'
    telegram_configs:
      - bot_token: '${TELEGRAM_ALERT_BOT_TOKEN}'
        chat_id: '${TELEGRAM_ALERT_CHAT_ID}'
        message: '🚨 *CRITICAL*: {{ .GroupLabels.alertname }}\n{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
        send_resolved: true

  - name: 'platform-team'
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL}'
        channel: '#platform-alerts'
        send_resolved: true

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'instance']
```

---

## Log Aggregation (Loki + Promtail)

### Loki Config (`loki-config.yml`)

```yaml
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    instance_addr: 127.0.0.1
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2024-01-01
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

limits_config:
  reject_old_samples: true
  reject_old_samples_max_age: 168h
  ingestion_rate_mb: 10
  ingestion_burst_size_mb: 20

chunk_store_config:
  max_look_back_period: 30d

table_manager:
  retention_deletes_enabled: true
  retention_period: 30d
```

### Promtail Config (`promtail-config.yml`)

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 9081

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: system
    static_configs:
      - targets:
          - localhost
        labels:
          job: varlogs
          __path__: /var/log/*log

  - job_name: n8n
    static_configs:
      - targets:
          - localhost
        labels:
          job: n8n
          __path__: /opt/n8n/data/*.log

  - job_name: caddy
    static_configs:
      - targets:
          - localhost
        labels:
          job: caddy
          __path__: /var/log/caddy/*.log

  - job_name: docker
    static_configs:
      - targets:
          - localhost
        labels:
          job: docker
          __path__: /var/lib/docker/containers/*/*-json.log
    pipeline_stages:
      - json:
          expressions:
            container: container_name
            level: level
            message: log
      - labels:
          container:
      - output:
          source: message
```

---

## Sentry Error Tracking (API)

### Setup

```bash
# Add to requirements.txt
sentry-sdk[fastapi]==1.39.1
```

```python
# api/app/main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from app.config import settings

if settings.SENTRY_DSN:
    sentry_logging = LoggingIntegration(
        level=logging.INFO,
        event_level=logging.ERROR
    )
    
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[FastApiIntegration(), sentry_logging],
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        environment=settings.ENVIRONMENT,
        release=f"pfe-api@{settings.VERSION}",
        # Filter sensitive data
        before_send=lambda event, hint: filter_sensitive_data(event)
    )

def filter_sensitive_data(event):
    """Remove PII and secrets from error reports"""
    if 'request' in event and 'data' in event['request']:
        data = event['request']['data']
        # Remove audio data
        if 'audio' in data:
            data['audio'] = '[REDACTED]'
        # Remove API keys
        for key in list(data.keys()):
            if 'key' in key.lower() or 'token' in key.lower() or 'secret' in key.lower():
                data[key] = '[REDACTED]'
    return event
```

### Sentry Alerts

Configure in Sentry UI:
- **Alert**: API error rate > 1% for 5min → Email + Slack
- **Alert**: New error type detected → Slack
- **Alert**: ExtractionError spike → PagerDuty/Telegram

---

## Uptime Monitoring (External)

### UptimeRobot (Free: 50 monitors, 5-min interval)

```bash
# Monitors to create:
# 1. API Health: https://api.aznet.ma/health (expect 200, keyword "healthy")
# 2. n8n Health: https://n8n.aznet.ma/healthz (expect 200)
# 3. API Process: https://api.aznet.ma/process (POST, expect 422 for missing auth)
# 4. Telegram API: https://api.telegram.org (expect 200)
# 5. Google Sheets: https://sheets.googleapis.com (expect 200/401)
```

### Better Uptime (Free: 10 monitors, 3-min interval)

More features: status page, incident management, on-call scheduling.

### GitHub Actions Synthetic Monitoring

```yaml
# .github/workflows/synthetic-monitoring.yml
name: Synthetic Monitoring

on:
  schedule:
    - cron: '*/5 * * * *'  # Every 5 minutes
  workflow_dispatch:

jobs:
  synthetic-checks:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Check API Health
        run: |
          curl -f -s -o /dev/null -w "%{http_code}" https://api.aznet.ma/health | grep -q 200
      
      - name: Check n8n Health
        run: |
          curl -f -s -o /dev/null -w "%{http_code}" https://n8n.aznet.ma/healthz | grep -q 200
      
      - name: Check API Process Endpoint
        run: |
          response=$(curl -s -w "\n%{http_code}" -X POST https://api.aznet.ma/process \
            -H "Content-Type: application/json" \
            -d '{"text": "synthetic test", "metadata": {"date": "2026-01-01", "technicien": "synthetic"}}')
          http_code=$(echo "$response" | tail -n1)
          # Expect 422 (validation) or 502 (no keys) but NOT 500/timeout
          if [[ "$http_code" == "500" ]] || [[ "$http_code" == "000" ]]; then
            exit 1
          fi
      
      - name: Check SSL Certificates
        run: |
          for domain in api.aznet.ma n8n.aznet.ma; do
            expiry=$(echo | openssl s_client -servername $domain -connect $domain:443 2>/dev/null | openssl x509 -noout -enddate | cut -d= -f2)
            expiry_epoch=$(date -d "$expiry" +%s)
            now_epoch=$(date +%s)
            days_left=$(( (expiry_epoch - now_epoch) / 86400 ))
            if [ $days_left -lt 30 ]; then
              echo "Certificate for $domain expires in $days_left days"
              exit 1
            fi
          done
      
      - name: Notify on Failure
        if: failure()
        run: |
          curl -X POST "${{ secrets.SLACK_WEBHOOK_URL }}" \
            -H 'Content-Type: application/json' \
            -d '{"text": "🚨 Synthetic check failed for PFE system"}'
```

---

## Custom Application Metrics (API)

### Add to FastAPI App

```python
# api/app/metrics.py
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import Response

# Request metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'path', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'path'],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 15, 30, 60]
)

# Business metrics
reports_received_total = Counter(
    'reports_received_total',
    'Total reports received',
    ['source', 'technicien', 'chantier', 'type_travail']
)

reports_stt_confidence_low_total = Counter(
    'reports_stt_confidence_low_total',
    'Reports with low STT confidence'
)

extraction_confidence_total = Counter(
    'extraction_confidence_total',
    'Extraction confidence distribution',
    ['confidence']
)

# STT metrics
stt_duration_seconds = Histogram(
    'stt_duration_seconds',
    'STT processing duration',
    ['provider'],
    buckets=[0.5, 1, 2, 5, 10, 20, 30]
)

stt_success_total = Counter(
    'stt_success_total',
    'STT success count',
    ['provider']
)

stt_failure_total = Counter(
    'stt_failure_total',
    'STT failure count',
    ['provider', 'error_type']
)

# Extraction metrics
extraction_duration_seconds = Histogram(
    'extraction_duration_seconds',
    'Extraction processing duration',
    ['provider'],
    buckets=[0.5, 1, 2, 5, 10, 20, 30]
)

extraction_success_total = Counter(
    'extraction_success_total',
    'Extraction success count',
    ['provider']
)

extraction_failure_total = Counter(
    'extraction_failure_total',
    'Extraction failure count',
    ['provider', 'error_type']
)

# Cold start tracking
cold_starts_total = Counter(
    'cold_starts_total',
    'Cold start count'
)

# Audio metrics
audio_duration_seconds = Histogram(
    'audio_duration_seconds',
    'Audio file duration',
    buckets=[5, 10, 15, 20, 30, 45, 60, 120, 180]
)

# E2E latency
e2e_latency_seconds = Histogram(
    'e2e_latency_seconds',
    'End-to-end latency (Telegram → Sheets)',
    buckets=[1, 2, 5, 10, 15, 20, 30, 45, 60, 120]
)

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type="text/plain")
```

### Instrument Endpoints

```python
# api/app/main.py
import time
from app.metrics import *

@app.metrics import *

@app.post("/process")
async def process(request: Request, body: ProcessRequest):
    start_time = time.time()
    cold_start = _groq_client is None  # Check if just initialized
    
    if cold_start:
        cold_starts_total.inc()
    
    try:
        # Track audio duration
        if body.audio:
            import base64
            audio_bytes = base64.b64decode(body.audio)
            audio_duration_seconds.observe(len(audio_bytes) / 32000)  # Rough estimate
        
        # Process...
        result = await process_report(body)
        
        # Record business metrics
        reports_received_total.labels(
            source=body.metadata.source,
            technicien=body.metadata.technicien or "unknown",
            chantier=result.extracted_report.chantier or "unknown",
            type_travail=result.extracted_report.type_travail or "unknown"
        ).inc()
        
        if result.extracted_report.stt_confidence_low:
            reports_stt_confidence_low_total.inc()
        
        extraction_confidence_total.labels(
            confidence=result.extracted_report.extraction_confidence
        ).inc()
        
        # E2E latency
        e2e_latency_seconds.observe(time.time() - start_time)
        
        # HTTP metrics
        http_requests_total.labels(
            method="POST", path="/process", status=200
        ).inc()
        http_request_duration_seconds.labels(
            method="POST", path="/process"
        ).observe(time.time() - start_time)
        
        return result
        
    except Exception as e:
        http_requests_total.labels(
            method="POST", path="/process", status=500
        ).inc()
        raise
```

---

## Runbooks (Incident Response)

### Runbook: API High Error Rate

```markdown
# Runbook: API High Error Rate

## Alert: APIHighErrorRate

### Symptoms
- >5% 5xx errors for 2+ minutes
- Sentry spike in errors
- n8n workflows failing at API call step

### Diagnosis
1. Check Sentry for error patterns
2. Check Vercel function logs: `vercel logs api.aznet.ma --follow`
3. Check n8n execution logs for API failures
4. Check external dependencies (Groq, Gemini, HF)

### Common Causes & Fixes

| Cause | Diagnosis | Fix |
|-------|-----------|-----|
| Groq API down | Sentry: Groq timeout/502 | Switch DEFAULT_STT_PROVIDER to gemini |
| Gemini quota exceeded | Sentry: 429 from Gemini | Wait/reset, or switch to Groq |
| Vercel timeout | Logs: Function exceeded 30s | Optimize audio processing, reduce quality |
| Memory limit | Logs: OOM kill | Reduce memory usage, stream processing |

### Escalation
- If unresolved in 15min → Page on-call
- If external API down → Monitor status page, switch provider
```

### Runbook: No Reports Received

```markdown
# Runbook: No Reports Received

## Alert: NoReportsReceived

### Symptoms
- 0 reports in 2+ hours during business hours
- Telegram bot not receiving messages
- n8n polling/webhook not triggering

### Diagnosis
1. Check Telegram bot status: `@BotFather` → bot info
2. Check n8n workflow executions (last run time)
3. Check webhook: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
4. Check n8n logs for Telegram API errors

### Common Causes & Fixes

| Cause | Diagnosis | Fix |
|-------|-----------|-----|
| Webhook URL changed | getWebhookInfo shows wrong URL | Reset webhook with correct URL |
| Bot token revoked | BotFather shows "token revoked" | Generate new token, update n8n |
| n8n down | n8n health check fails | Restart n8n container |
| Telegram API issues | Telegram status page | Wait, check webhook connectivity |

### Escalation
- If n8n down → Restart, check logs
- If Telegram issue → Check status, consider polling fallback
```

---

## Related Notes

- [[Deployment Guide]]
- [[Vercel Advanced]]
- [[n8n Advanced]]
- [[Security Secrets]]
- [[Architecture]]