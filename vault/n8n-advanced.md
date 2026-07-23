---
tags: [pfe, deployment, n8n, advanced, workflows, patterns, queue, scaling]
type: technical
priority: high
status: partial
---

> **Reality check (2026-07-23):** substantial parts of this doc describe an API contract, file layout, or tooling that was never built (e.g. JSON+base64 `/process` body with metadata in the request, `ExtractedReport` fields like `technicien`/`type_travail`/`cables_tires`, ngrok, CI workflows, `requirements-dev.txt`, `.vscode/` configs). The real `/process` contract is multipart file upload (`audio`/`text` form fields), metadata is added by n8n *after* the API responds, and the real schema is in `api/app/schemas.py`. Treat concrete claims here as aspirational/unverified unless they match the real source files in `api/app/`, `api/tests/`, and `n8n/`.

# n8n Advanced Deployment & Workflow Patterns

## Production-Grade n8n Architecture

### Scaling Strategies

```
┌─────────────────────────────────────────────────────────────────┐
│                    n8n SCALING TIERS                            │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   TIER 1        │   TIER 2        │   TIER 3                    │
│   (Current)     │   (Growth)      │   (Scale)                   │
├─────────────────┼─────────────────┼─────────────────────────────┤
│ Single Instance │ Main + Workers  │ Queue Mode + Redis          │
│ SQLite          │ PostgreSQL      │ PostgreSQL + Redis          │
│ ~100 exec/min   │ ~500 exec/min   │ ~5000 exec/min              │
│ $5-10/mo VPS    │ $20-50/mo       │ $100+/mo                    │
└─────────────────┴─────────────────┴─────────────────────────────┘
```

### Tier 1: Single Instance (Current - PFE Scope)

```yaml
# docker-compose.yml (Production Hardened)
version: '3.8'

services:
  n8n:
    image: n8nio/n8n:latest
    restart: unless-stopped
    ports:
      - "127.0.0.1:5678:5678"  # Localhost only - Caddy proxies
    environment:
      # Core
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=${N8N_USER}
      - N8N_BASIC_AUTH_PASSWORD=${N8N_PASSWORD}
      - WEBHOOK_URL=https://n8n.aznet.ma/
      - GENERIC_TIMEZONE=Africa/Casablanca
      - TZ=Africa/Casablanca
      
      # Database
      - DB_TYPE=sqlite
      - DB_SQLITE_DATABASE=/home/node/.n8n/database.sqlite
      - DB_SQLITE_POOL_SIZE=5
      
      # Execution
      - EXECUTIONS_MODE=regular
      - EXECUTIONS_TIMEOUT=3600
      - EXECUTIONS_TIMEOUT_MAX=7200
      - N8N_PAYLOAD_SIZE_MAX=50
      
      # Security
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
      - N8N_USER_FOLDER=/home/node/.n8n
      
      # Logging
      - N8N_LOG_LEVEL=info
      - N8N_LOG_OUTPUT=console
      - N8N_METRICS=true
      
      # Performance
      - NODE_FUNCTION_ALLOW_EXTERNAL=axios,lodash,moment,uuid,cheerio
      
    volumes:
      - ./data:/home/node/.n8n
      - ./workflows:/home/node/.n8n/workflows
      - ./credentials:/home/node/.n8n/credentials
      - ./custom:/home/node/.n8n/custom
      
    networks:
      - n8n-network
      
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:5678/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
      
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.5'
        reservations:
          memory: 1G
          cpus: '0.5'

  # Optional: Redis for future queue mode
  # redis:
  #   image: redis:7-alpine
  #   restart: unless-stopped
  #   volumes:
  #     - redis_data:/data
  #   networks:
  #     - n8n-network

  # Optional: PostgreSQL for Tier 2
  # postgres:
  #   image: postgres:15-alpine
  #   restart: unless-stopped
  #   environment:
  #     - POSTGRES_DB=n8n
  #     - POSTGRES_USER=n8n
  #     - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
  #   volumes:
  #     - postgres_data:/var/lib/postgresql/data
  #   networks:
  #     - n8n-network

networks:
  n8n-network:
    driver: bridge

# volumes:
#   redis_data:
#   postgres_data:
```

---

## Advanced Workflow Patterns

### Pattern 1: Idempotent Processing (Critical for Telegram)

```javascript
// Function Node: Check & Set Idempotency Key
// Place BEFORE any external API calls

const msgId = $json.metadata.telegram_message_id;
const key = `processed:${msgId}`;

// Check Redis (or use n8n's built-in workflow static data)
// For SQLite mode, use a simple file-based approach

const fs = require('fs');
const path = '/home/node/.n8n/idempotency';
const file = `${path}/${key}`;

if (fs.existsSync(file)) {
  // Already processed
  return [{ json: { skipped: true, reason: 'duplicate', messageId: msgId } }];
}

// Create marker
if (!fs.existsSync(path)) fs.mkdirSync(path, { recursive: true });
fs.writeFileSync(file, Date.now().toString());

// Cleanup old markers (>7 days)
const now = Date.now();
fs.readdirSync(path).forEach(f => {
  const age = now - parseInt(fs.readFileSync(`${path}/${f}`, 'utf8'));
  if (age > 7 * 24 * 60 * 60 * 1000) fs.unlinkSync(`${path}/${f}`);
});

return [{ json: { ...$json, idempotencyChecked: true } }];
```

### Pattern 2: Circuit Breaker for External APIs

```javascript
// Function Node: Circuit Breaker Wrapper
// Wraps any HTTP Request node

const circuitState = $getWorkflowStaticData('global').circuitBreakers || {};
const serviceName = $parameter.serviceName; // e.g., 'api', 'sheets', 'email'
const threshold = 5; // failures before open
const timeout = 60000; // 1 min before half-open

const state = circuitState[serviceName] || { failures: 0, lastFailure: 0, open: false };

// Check if circuit is open
if (state.open) {
  if (Date.now() - state.lastFailure > timeout) {
    // Half-open: allow one request
    state.open = false;
  } else {
    throw new Error(`Circuit breaker OPEN for ${serviceName}. Retry later.`);
  }
}

try {
  // Execute the actual HTTP request (this node's output)
  const result = $json; // Input from previous node
  
  // Success: reset failures
  state.failures = 0;
  circuitState[serviceName] = state;
  $getWorkflowStaticData('global').circuitBreakers = circuitState;
  
  return result;
} catch (error) {
  // Failure: increment
  state.failures++;
  state.lastFailure = Date.now();
  
  if (state.failures >= threshold) {
    state.open = true;
    console.warn(`Circuit breaker OPENED for ${serviceName}`);
  }
  
  circuitState[serviceName] = state;
  $getWorkflowStaticData('global').circuitBreakers = circuitState;
  
  throw error;
}
```

### Pattern 3: Retry with Exponential Backoff (Custom)

```javascript
// Function Node: Retry Logic
// Place BEFORE HTTP Request node

const maxRetries = 3;
const baseDelay = 1000; // 1s

const attempt = ($json.retryAttempt || 0) + 1;

if (attempt > maxRetries) {
  throw new Error(`Max retries (${maxRetries}) exceeded`);
}

const delay = baseDelay * Math.pow(2, attempt - 1) + Math.random() * 1000;

// Add retry metadata
return [{
  json: {
    ...$json,
    retryAttempt: attempt,
    retryDelay: delay
  }
}];
```

```yaml
# In workflow: Connect retry function → HTTP Request → IF (success?) → Retry Function
# On error: HTTP Request Error Trigger → Retry Function
```

### Pattern 4: Dead Letter Queue (DLQ) for Failed Executions

```javascript
// Error Trigger Workflow: dlq-handler
// Trigger: Error Trigger (catches all workflow errors)

const error = $json.error;
const workflow = $json.workflow;
const execution = $json.execution;

// Classify error
const classification = classifyError(error);

function classifyError(err) {
  const msg = err.message || String(err);
  
  if (msg.includes('timeout') || msg.includes('ETIMEDOUT')) return 'transient';
  if (msg.includes('429') || msg.includes('rate limit')) return 'rate_limit';
  if (msg.includes('502') || msg.includes('503') || msg.includes('504')) return 'transient';
  if (msg.includes('401') || msg.includes('403')) return 'auth';
  if (msg.includes('422') || msg.includes('validation')) return 'data';
  return 'unknown';
}

// Route based on classification
switch (classification) {
  case 'transient':
    // Schedule retry in 5 minutes
    return [{ 
      json: { 
        action: 'retry_later', 
        delay: 300000,
        originalExecution: execution.id 
      } 
    }];
    
  case 'rate_limit':
    // Schedule retry in 15 minutes
    return [{ 
      json: { 
        action: 'retry_later', 
        delay: 900000,
        originalExecution: execution.id 
      } 
    }];
    
  case 'auth':
    // Alert immediately - credentials issue
    return [{ 
      json: { 
        action: 'alert', 
        severity: 'critical',
        message: `Auth failure in ${workflow.name}: ${error.message}` 
      } 
    }];
    
  case 'data':
    // Log to error sheet, don't retry
    return [{ 
      json: { 
        action: 'log_error', 
        severity: 'warning',
        message: `Data error in ${workflow.name}: ${error.message}` 
      } 
    }];
    
  default:
    // Alert for manual review
    return [{ 
      json: { 
        action: 'alert', 
        severity: 'error',
        message: `Unknown error in ${workflow.name}: ${error.message}` 
      } 
    }];
}
```

### Pattern 5: Batch Processing for High Volume

```javascript
// Function Node: Batch Accumulator
// Use when: Multiple webhook calls arrive rapidly, batch to API

const batchKey = $parameter.batchKey || 'default';
const batchSize = $parameter.batchSize || 10;
const batchTimeout = $parameter.batchTimeout || 5000; // ms

const batches = $getWorkflowStaticData('global').batches || {};
const batch = batches[batchKey] || { items: [], timer: null };

batch.items.push($json);

if (batch.items.length >= batchSize) {
  // Flush immediately
  if (batch.timer) clearTimeout(batch.timer);
  const items = batch.items;
  batches[batchKey] = { items: [], timer: null };
  $getWorkflowStaticData('global').batches = batches;
  
  return items.map(item => ({ json: item }));
}

// Set flush timer
if (!batch.timer) {
  batch.timer = setTimeout(() => {
    const items = batch.items;
    batches[batchKey] = { items: [], timer: null };
    $getWorkflowStaticData('global').batches = batches;
    
    // Emit via internal webhook to self
    $executeWorkflow('batch-flush', { items, batchKey });
  }, batchTimeout);
}

batches[batchKey] = batch;
$getWorkflowStaticData('global').batches = batches;

// Return empty - wait for batch
return [];
```

---

## Workflow Templates (Reusable)

### Template: Standard API Call with Full Resilience

```json
{
  "name": "Template: Resilient API Call",
  "nodes": [
    {
      "name": "Prepare Request",
      "type": "n8n-nodes-base.function",
      "parameters": {
        "functionCode": "// Build request\nreturn [{\n  json: {\n    url: $parameter.apiUrl,\n    method: $parameter.method || 'POST',\n    headers: {\n      'Content-Type': 'application/json',\n      ...$parameter.headers\n    },\n    body: $json,\n    timeout: $parameter.timeout || 30000\n  }\n}]"
      }
    },
    {
      "name": "Circuit Breaker Check",
      "type": "n8n-nodes-base.function",
      "parameters": {
        "functionCode": "// Circuit breaker logic (see Pattern 2)\nconst service = $parameter.serviceName;\n// ... implementation\nreturn [$json];"
      }
    },
    {
      "name": "HTTP Request",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "url": "={{$json.url}}",
        "method": "={{$json.method}}",
        "headers": "={{$json.headers}}",
        "body": "={{$json.body}}",
        "timeout": "={{$json.timeout}}",
        "options": {
          "maxRetries": 0  // We handle retries ourselves
        }
      }
    },
    {
      "name": "Check Response",
      "type": "n8n-nodes-base.if",
      "parameters": {
        "conditions": {
          "string": [
            { "value1": "={{$json.statusCode}}", "operation": "between", "value2": "200,299" }
          ]
        }
      }
    },
    {
      "name": "Success Path",
      "type": "n8n-nodes-base.function",
      "parameters": {
        "functionCode": "// Reset circuit breaker on success\nreturn [{ json: { ...$json, success: true }}];"
      }
    },
    {
      "name": "Retry Logic",
      "type": "n8n-nodes-base.function",
      "parameters": {
        "functionCode": "// Exponential backoff (see Pattern 3)\nreturn [{ json: { ...$json, retryAttempt: ($json.retryAttempt || 0) + 1 }}];"
      }
    },
    {
      "name": "Error Classification",
      "type": "n8n-nodes-base.function",
      "parameters": {
        "functionCode": "// Classify and route error (see Pattern 4)\nreturn [{ json: { error: $json.error, classification: classify($json.error) }}];"
      }
    }
  ],
  "connections": {
    "Prepare Request": { "main": [["Circuit Breaker Check"]] },
    "Circuit Breaker Check": { "main": [["HTTP Request"]] },
    "HTTP Request": { 
      "main": [["Check Response"]],
      "error": [["Error Classification"]]
    },
    "Check Response": { 
      "main": [
        ["Success Path"],  // true
        ["Retry Logic"]    // false
      ]
    },
    "Retry Logic": { "main": [["Circuit Breaker Check"]] },
    "Error Classification": { "main": [["DLQ Handler"]] }
  }
}
```

---

## Monitoring & Alerting for n8n

### Built-in Metrics Endpoint

```bash
# Enable in environment
N8N_METRICS=true

# Scrape
curl http://localhost:5678/metrics

# Key metrics:
# n8n_workflow_executions_total{status="success|error"}
# n8n_workflow_execution_duration_seconds
# n8n_active_workflows
# n8n_queue_size (queue mode)
```

### Prometheus + Grafana (Free on VPS)

```yaml
# docker-compose.monitoring.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    restart: unless-stopped
    ports:
      - "127.0.0.1:9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
    networks:
      - monitoring

  grafana:
    image: grafana/grafana:latest
    restart: unless-stopped
    ports:
      - "127.0.0.1:3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
      - GF_INSTALL_PLUGINS=grafana-piechart-panel
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./grafana/datasources:/etc/grafana/provisioning/datasources
    networks:
      - monitoring

  alertmanager:
    image: prom/alertmanager:latest
    restart: unless-stopped
    ports:
      - "127.0.0.1:9093:9093"
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml
    networks:
      - monitoring

networks:
  monitoring:
    driver: bridge

volumes:
  prometheus_data:
  grafana_data:
```

### Prometheus Config (`prometheus.yml`)

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']

rule_files:
  - '/etc/prometheus/rules/*.yml'

scrape_configs:
  - job_name: 'n8n'
    static_configs:
      - targets: ['host.docker.internal:5678']
    metrics_path: '/metrics'

  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['host.docker.internal:9100']
```

### Alert Rules (`rules/n8n.yml`)

```yaml
groups:
  - name: n8n-alerts
    interval: 30s
    rules:
      - alert: N8NWorkflowHighErrorRate
        expr: |
          rate(n8n_workflow_executions_total{status="error"}[5m]) 
          / rate(n8n_workflow_executions_total[5m]) > 0.1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "High error rate in n8n workflows"
          description: "Error rate > 10% for 2 minutes"

      - alert: N8NExecutionDurationHigh
        expr: |
          histogram_quantile(0.95, rate(n8n_workflow_execution_duration_seconds_bucket[5m])) > 60
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "n8n execution duration high"
          description: "p95 execution time > 60s"

      - alert: N8NQueueBacklog
        expr: n8n_queue_size > 100
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "n8n queue backlog"
          description: "Queue size > 100 for 5 minutes"

      - alert: N8NDown
        expr: up{job="n8n"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "n8n is down"
          description: "n8n has been unreachable for 1 minute"
```

### Grafana Dashboard (Key Panels)

```json
{
  "dashboard": {
    "title": "n8n PFE Monitoring",
    "panels": [
      {
        "title": "Executions/min (Success vs Error)",
        "type": "graph",
        "targets": [
          { "expr": "rate(n8n_workflow_executions_total{status=\"success\"}[1m])", "legendFormat": "Success" },
          { "expr": "rate(n8n_workflow_executions_total{status=\"error\"}[1m])", "legendFormat": "Error" }
        ]
      },
      {
        "title": "Execution Duration (p50, p95, p99)",
        "type": "graph",
        "targets": [
          { "expr": "histogram_quantile(0.50, rate(n8n_workflow_execution_duration_seconds_bucket[5m]))", "legendFormat": "p50" },
          { "expr": "histogram_quantile(0.95, rate(n8n_workflow_execution_duration_seconds_bucket[5m]))", "legendFormat": "p95" },
          { "expr": "histogram_quantile(0.99, rate(n8n_workflow_execution_duration_seconds_bucket[5m]))", "legendFormat": "p99" }
        ]
      },
      {
        "title": "Active Workflows",
        "type": "stat",
        "targets": [{ "expr": "n8n_active_workflows" }]
      },
      {
        "title": "Error Rate by Workflow",
        "type": "table",
        "targets": [
          { "expr": "sum by (workflow) (rate(n8n_workflow_executions_total{status=\"error\"}[5m])) / sum by (workflow) (rate(n8n_workflow_executions_total[5m]))" }
        ]
      }
    ]
  }
}
```

---

## Backup & Disaster Recovery

### Automated Daily Backup

```bash
#!/bin/bash
# /opt/n8n/backup.sh

set -euo pipefail

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/n8n/backups"
RETENTION_DAYS=30

# Create backup directory
mkdir -p "$BACKUP_DIR"

# 1. Backup n8n data (SQLite + workflows + credentials)
echo "Backing up n8n data..."
docker run --rm \
  -v /opt/n8n/data:/data \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf "/backup/n8n_data_$DATE.tar.gz" -C /data .

# 2. Export workflows via n8n CLI (if running)
if docker ps | grep -q n8n; then
  echo "Exporting workflows..."
  docker exec n8n n8n export:workflow --all --output=/tmp/workflows_$DATE.json 2>/dev/null || true
  docker cp n8n:/tmp/workflows_$DATE.json "$BACKUP_DIR/" 2>/dev/null || true
fi

# 3. Backup credentials (encrypted)
echo "Backing up credentials..."
docker run --rm \
  -v /opt/n8n/credentials:/data \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf "/backup/n8n_credentials_$DATE.tar.gz" -C /data .

# 4. Cleanup old backups
echo "Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "n8n_*.tar.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "workflows_*.json" -mtime +$RETENTION_DAYS -delete

echo "Backup complete: $BACKUP_DIR"
ls -lh "$BACKUP_DIR"/*_$DATE*
```

### Restore Procedure

```bash
#!/bin/bash
# /opt/n8n/restore.sh <backup_date>
# Usage: ./restore.sh 20260723_020000

BACKUP_DATE=$1
BACKUP_DIR="/opt/n8n/backups"

if [ -z "$BACKUP_DATE" ]; then
  echo "Usage: $0 <backup_date>"
  echo "Available backups:"
  ls -1 "$BACKUP_DIR"/n8n_data_*.tar.gz | sed 's/.*n8n_data_\(.*\)\.tar\.gz/\1/'
  exit 1
fi

echo "Restoring from $BACKUP_DATE..."

# 1. Stop n8n
docker compose down

# 2. Restore data
docker run --rm \
  -v /opt/n8n/data:/data \
  -v "$BACKUP_DIR":/backup \
  alpine sh -c "rm -rf /data/* && tar xzf /backup/n8n_data_$BACKUP_DATE.tar.gz -C /data"

# 3. Restore credentials
docker run --rm \
  -v /opt/n8n/credentials:/data \
  -v "$BACKUP_DIR":/backup \
  alpine sh -c "rm -rf /data/* && tar xzf /backup/n8n_credentials_$BACKUP_DATE.tar.gz -C /data"

# 4. Start n8n
docker compose up -d

# 5. Verify
sleep 10
curl -f http://localhost:5678/healthz

echo "Restore complete. Verify workflows in n8n UI."
```

---

## Security Hardening Checklist

### n8n Configuration

- [ ] `N8N_ENCRYPTION_KEY` set (32-char hex, generated once: `openssl rand -hex 32`)
- [ ] Basic auth enabled with strong password
- [ ] `WEBHOOK_URL` set to HTTPS production domain
- [ ] `EXECUTIONS_TIMEOUT` set (prevent runaway workflows)
- [ ] `N8N_PAYLOAD_SIZE_MAX` limited (50MB default)
- [ ] `NODE_FUNCTION_ALLOW_EXTERNAL` minimal (only needed packages)
- [ ] `N8N_LOG_LEVEL=warn` in production (reduce log volume)

### Network Security

- [ ] n8n binds to `127.0.0.1:5678` only (not 0.0.0.0)
- [ ] Caddy reverse proxy with HTTPS
- [ ] Caddy: Rate limiting on webhook endpoints
- [ ] Caddy: IP allowlist for n8n editor (admin access)
- [ ] VPS firewall: Only 22 (SSH), 80, 443 open
- [ ] SSH: Key-only auth, disable password, fail2ban

### Credentials Management

- [ ] No credentials in workflow JSON (use n8n credential nodes)
- [ ] Service account keys in `/opt/n8n/credentials/` (not git)
- [ ] Telegram webhook secret token verified in workflow
- [ ] API keys in n8n credentials, not hardcoded
- [ ] Regular credential rotation (quarterly)

### Data Protection

- [ ] SQLite database encrypted at rest (via `N8N_ENCRYPTION_KEY`)
- [ ] Backups encrypted (GPG) before offsite storage
- [ ] Google Sheets: Service account with minimal scope
- [ ] Email: App password, not main password
- [ ] No PII in workflow names/logs (technicien names OK per spec)

---

## Related Notes

- [[Deployment Guide]]
- [[Vercel Advanced]]
- [[n8n Workflows]]
- [[Security Secrets]]
- [[Google Sheets Integration]]