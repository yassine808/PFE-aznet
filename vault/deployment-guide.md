---
tags: [pfe, deployment, vercel, n8n, vps, docker, ci-cd]
type: technical
priority: high
status: partial
---

> **Reality check (2026-07-23):** substantial parts of this doc describe an API contract, file layout, or tooling that was never built (e.g. JSON+base64 `/process` body with metadata in the request, `ExtractedReport` fields like `technicien`/`type_travail`/`cables_tires`, ngrok, CI workflows, `requirements-dev.txt`, `.vscode/` configs). The real `/process` contract is multipart file upload (`audio`/`text` form fields), metadata is added by n8n *after* the API responds, and the real schema is in `api/app/schemas.py`. Treat concrete claims here as aspirational/unverified unless they match the real source files in `api/app/`, `api/tests/`, and `n8n/`.

# Deployment Guide

## Overview

| Environment | API | n8n | Database | Domain |
|-------------|-----|-----|----------|--------|
| **Dev** | Local (`uvicorn :8000`) | Docker (`localhost:5678`) | Local Sheets | ngrok tunnel |
| **Pilot** | Vercel (serverless) | VPS (Docker) | Google Sheets | `pilot.aznet.ma` |
| **Prod** | Vercel (serverless) | VPS (Docker) | Google Sheets | `app.aznet.ma` |

---

## API Deployment (Vercel)

### Project Structure for Vercel

```
api/
├── app/
│   ├── main.py          # FastAPI app (entry point)
│   ├── config.py        # Pydantic Settings
│   ├── schemas.py       # Pydantic models
│   ├── extraction.py    # LLM extraction
│   └── providers/       # STT providers
├── requirements.txt     # Python deps
├── vercel.json          # Vercel config
└── .vercelignore        # Exclude venv, tests, etc.
```

### vercel.json

```json
{
  "buildCommand": "pip install -r requirements.txt",
  "outputDirectory": ".",
  "devCommand": "uvicorn app.main:app --reload",
  "installCommand": "pip install -r requirements.txt",
  "framework": null,
  "functions": {
    "api/app/main.py": {
      "maxDuration": 30,
      "memory": 1024
    }
  },
  "routes": [
    { "src": "/(.*)", "dest": "api/app/main.py" }
  ],
  "env": {
    "PYTHON_VERSION": "3.9"
  }
}
```

### .vercelignore

```
.venv/
venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
tests/
benchmark/
docs/
.vscode/
.obsidian/
.git/
.gitignore
README.md
*.md
.env
.env.local
*.log
```

### Environment Variables (Vercel Dashboard)

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Google AI Studio key |
| `GROQ_API_KEY` | Yes | Groq Cloud key |
| `HF_API_KEY` | No | Hugging Face Inference API |
| `DEFAULT_STT_PROVIDER` | No | Default: `groq` |
| `STT_TIMEOUT_SECONDS` | No | Default: `30` |
| `EXTRACTION_TIMEOUT` | No | Default: `30` |
| `CORS_ORIGINS` | No | Comma-separated, e.g. `https://n8n.aznet.ma` |

### Deploy Commands

```bash
# Install Vercel CLI
npm i -g vercel

# Login
vercel login

# Deploy from api/ directory
cd api
vercel --prod

# Or link existing project
vercel link
vercel --prod
```

### Vercel Limitations & Workarounds

| Limitation | Workaround |
|------------|------------|
| 30s max function duration | Optimize STT calls, use streaming if needed |
| 1024MB memory | Whisper fits; avoid large model loads |
| No persistent storage | Use external services (Sheets, Redis) |
| Cold starts | Keep-alive cron (GitHub Actions) |
| 50MB payload limit | Telegram audio < 20MB (voice messages) |

---

## n8n Deployment (VPS)

### Server Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 1 vCPU | 2 vCPU |
| RAM | 2 GB | 4 GB |
| Disk | 20 GB | 50 GB |
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |

### Initial Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Install Caddy (reverse proxy + HTTPS)
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy -y
```

### Directory Structure

```
/opt/n8n/
├── docker-compose.yml
├── .env
├── data/              # n8n persistent data (workflows, credentials)
├── workflows/         # Exported workflows (git-tracked)
├── credentials/       # Credential files (NOT in git)
└── backups/           # Daily backups
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  n8n:
    image: n8nio/n8n:latest
    restart: unless-stopped
    ports:
      - "127.0.0.1:5678:5678"
    environment:
      # Basic auth
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=${N8N_USER}
      - N8N_BASIC_AUTH_PASSWORD=${N8N_PASSWORD}
      
      # Webhook URL (production domain)
      - WEBHOOK_URL=https://n8n.aznet.ma/
      
      # Timezone
      - GENERIC_TIMEZONE=Africa/Casablanca
      - TZ=Africa/Casablanca
      
      # Database (SQLite by default, can use Postgres)
      - DB_TYPE=sqlite
      - DB_SQLITE_DATABASE=/home/node/.n8n/database.sqlite
      
      # Execution settings
      - EXECUTIONS_MODE=regular
      - EXECUTIONS_TIMEOUT=3600
      - EXECUTIONS_TIMEOUT_MAX=7200
      
      # Logging
      - N8N_LOG_LEVEL=info
      - N8N_LOG_OUTPUT=console
      
      # Security
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
      
    volumes:
      - ./data:/home/node/.n8n
      - ./workflows:/home/node/.n8n/workflows
      - ./credentials:/home/node/.n8n/credentials
      
    networks:
      - n8n-network

  # Optional: Postgres for production scale
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
#   postgres_data:
```

### .env (Production)

```bash
# n8n Auth
N8N_USER=admin
N8N_PASSWORD=changeme-strong-password

# Encryption key (generate once: openssl rand -hex 32)
N8N_ENCRYPTION_KEY=your-32-char-hex-key-here

# Webhook domain
WEBHOOK_URL=https://n8n.aznet.ma/

# Optional Postgres
# POSTGRES_PASSWORD=secure-password
```

### Caddy Configuration (/etc/caddy/Caddyfile)

```caddyfile
n8n.aznet.ma {
    reverse_proxy localhost:5678 {
        header_up Host {host}
        header_up X-Real-IP {remote}
        header_up X-Forwarded-For {remote}
        header_up X-Forwarded-Proto {scheme}
    }
    
    # Increase body size for webhooks
    max_body_size 50MB
    
    # WebSocket support for n8n editor
    header {
        Access-Control-Allow-Origin *
        Access-Control-Allow-Methods "GET, POST, OPTIONS, PUT, DELETE"
        Access-Control-Allow-Headers "Content-Type, Authorization"
    }
}

# API proxy (if hosting API on same VPS)
api.aznet.ma {
    reverse_proxy localhost:8000
}
```

### Start Services

```bash
cd /opt/n8n
docker compose up -d

# Check logs
docker compose logs -f n8n

# Verify
curl https://n8n.aznet.ma/healthz
```

---

## Google Sheets Service Account

### Create Service Account

1. Google Cloud Console → IAM → Service Accounts
2. Create: `pfe-sheets-writer`
3. Grant: **No IAM roles** (minimal)
4. Enable **Google Sheets API** in project
5. Create key → JSON → Save as `credentials/sheets-service-account.json`

### Share Spreadsheet

1. Open target spreadsheet
2. Share with service account email: `pfe-sheets-writer@my-project.iam.gserviceaccount.com`
3. Permission: **Editor**

### n8n Credential Setup

1. n8n → Credentials → New → Google Sheets OAuth2 API
2. Or: Google Sheets Service Account (preferred)
3. Paste JSON key content
4. Test connection

---

## Telegram Bot Setup

### Create Bot

1. Message @BotFather
2. `/newbot` → Name: `PFE Aznet Bot` → Username: `pfe_aznet_bot`
3. Save token: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

### Set Webhook (Production)

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://n8n.aznet.ma/webhook/telegram",
    "secret_token": "your-secure-random-token",
    "allowed_updates": ["message", "edited_message"]
  }'
```

### Verify Webhook

```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

### Development (ngrok)

```bash
# Terminal 1: ngrok
ngrok http 5678

# Terminal 2: Set webhook to ngrok URL
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -d "url=https://abc123.ngrok-free.app/webhook/telegram" \
  -d "secret_token=dev-secret"
```

---

## Email Notifications (Gmail)

### Create App Password

1. Google Account → Security → 2-Step Verification → App Passwords
2. App: `n8n PFE Reports` → Generate
3. Save 16-char password

### n8n Email Credential

- **SMTP Host:** `smtp.gmail.com`
- **SMTP Port:** `587`
- **Security:** `STARTTLS`
- **User:** `your-email@gmail.com`
- **Password:** `app-password-16-chars`

---

## SSL/TLS (Automatic via Caddy)

Caddy automatically:
- Obtains Let's Encrypt certificates
- Renews before expiry
- Enforces HTTPS
- Adds security headers

No manual cert management needed.

---

## Backup Strategy

### n8n Data Backup (Daily Cron)

```bash
#!/bin/bash
# /opt/n8n/backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/n8n/backups"

# Backup n8n data
docker run --rm \
  -v /opt/n8n/data:/data \
  -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/n8n_data_$DATE.tar.gz -C /data .

# Backup workflows (git)
cd /opt/n8n/workflows && git add . && git commit -m "Auto backup $DATE" && git push

# Keep last 30 days
find $BACKUP_DIR -name "n8n_data_*.tar.gz" -mtime +30 -delete
```

```bash
chmod +x /opt/n8n/backup.sh
# Add to crontab
crontab -e
# 0 2 * * * /opt/n8n/backup.sh >> /var/log/n8n_backup.log 2>&1
```

### Restore

```bash
# Stop n8n
docker compose down

# Restore data
docker run --rm \
  -v /opt/n8n/data:/data \
  -v /opt/n8n/backups:/backup \
  alpine tar xzf /backup/n8n_data_20260723_020000.tar.gz -C /data

# Start n8n
docker compose up -d
```

---

## Monitoring & Health Checks

### n8n Health Endpoint

```bash
# Basic health
curl https://n8n.aznet.ma/healthz

# Detailed (requires auth)
curl -u admin:password https://n8n.aznet.ma/rest/health
```

### API Health (Vercel)

```bash
curl https://api.aznet.ma/health
```

### Uptime Monitoring (Free Options)

| Tool | Setup | Features |
|------|-------|----------|
| **UptimeRobot** | Web UI | 50 monitors free, 5-min interval |
| **Better Uptime** | Web UI | 10 monitors free, 3-min interval |
| **GitHub Actions** | YAML | Custom, free tier generous |

#### GitHub Actions Uptime Check

```yaml
# .github/workflows/uptime.yml
name: Uptime Check

on:
  schedule:
    - cron: '*/5 * * * *'  # Every 5 minutes

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - name: Check API
        run: |
          curl -f https://api.aznet.ma/health || exit 1
      - name: Check n8n
        run: |
          curl -f https://n8n.aznet.ma/healthz || exit 1
```

---

## CI/CD Pipeline

### GitHub Actions (API Deploy)

```yaml
# .github/workflows/deploy-api.yml
name: Deploy API to Vercel

on:
  push:
    branches: [main]
    paths:
      - 'api/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install Vercel CLI
        run: npm i -g vercel@latest
      - name: Deploy to Vercel
        run: |
          cd api
          vercel --prod --token=${{ secrets.VERCEL_TOKEN }}
        env:
          VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}
          VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}
```

### GitHub Actions (n8n Workflow Sync)

```yaml
# .github/workflows/sync-workflows.yml
name: Sync n8n Workflows

on:
  push:
    branches: [main]
    paths:
      - 'n8n/workflows/**'

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy workflows to n8n
        run: |
          # Use n8n CLI or API to import workflows
          # Requires n8n CLI or custom script
```

---

## Scaling Considerations

### API (Vercel)
- **Concurrency:** Auto-scales (1000+ concurrent)
- **Cost:** Free tier generous (100GB-hours/month)
- **Bottleneck:** External API latency (STT/LLM)

### n8n (VPS)
- **Current:** Single instance, SQLite
- **Scale triggers:**
  - >100 executions/minute → Add Postgres
  - >500 executions/minute → Queue mode (Redis + workers)
  - High memory → Increase VPS RAM

### Queue Mode (Future)

```yaml
# docker-compose.queue.yml
services:
  n8n-main:
    image: n8nio/n8n:latest
    command: start
    environment:
      - EXECUTIONS_MODE=queue
      - QUEUE_BULL_REDIS_HOST=redis
      - DB_TYPE=postgresdb
      # ... postgres config

  n8n-worker:
    image: n8nio/n8n:latest
    command: worker
    environment:
      - EXECUTIONS_MODE=queue
      - QUEUE_BULL_REDIS_HOST=redis
      - DB_TYPE=postgresdb
      # ... postgres config
    deploy:
      replicas: 2

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=n8n
      - POSTGRES_USER=n8n
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  redis_data:
  postgres_data:
```

---

## Security Checklist

- [ ] n8n basic auth enabled
- [ ] n8n encryption key set (32-char hex)
- [ ] Caddy HTTPS enforced
- [ ] Telegram webhook secret token verified
- [ ] Google Sheets service account minimal permissions
- [ ] Gmail app password (not main password)
- [ ] API keys in Vercel env vars (not code)
- [ ] `.env` files in `.gitignore`
- [ ] Credentials folder not in git
- [ ] VPS firewall: only 80, 443, 22 open
- [ ] SSH key-only auth (disable password)
- [ ] Fail2ban installed
- [ ] Automatic security updates enabled

---

## Troubleshooting

### n8n Won't Start

```bash
# Check logs
docker compose logs n8n

# Common issues:
# - Port 5678 in use: check `ss -tlnp | grep 5678`
# - Permission denied on data/: `sudo chown -R 1000:1000 /opt/n8n/data`
# - Encryption key mismatch: must be same across restarts
```

### API Returns 502 on Vercel

```bash
# Check Vercel function logs
vercel logs https://api.aznet.ma --follow

# Common issues:
# - Timeout (>30s): optimize STT calls
# - Memory limit: reduce audio processing
# - Missing env vars: check Vercel dashboard
```

### Telegram Webhook Fails

```bash
# Check webhook info
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"

# Common issues:
# - URL not HTTPS: Caddy required
# - Secret token mismatch: verify in n8n workflow
# - 404: webhook path wrong in n8n trigger
```

### Google Sheets Append Fails

```bash
# Check n8n execution logs
# Common issues:
# - Service account not shared on sheet
# - Sheet ID wrong in n8n node
# - Column range mismatch (A:R vs A:Z)
# - Rate limit: batch requests or add delay
```

---

## Related Notes

- [[Project Overview]]
- [[Architecture]]
- [[n8n Workflows]]
- [[API Schemas]]
- [[Google Sheets Integration]]