---
tags: [pfe, deployment, devops, guide]
type: guide
priority: high
status: current
---

# Deployment Guide

## Architecture (containerized)

Three compose services defined in `docker-compose.yml` at repo root:

| Service | Image/Config | Port | Persistence |
|---|---|---|---|
| `api` | `api/Dockerfile` (Python 3.9-slim) | 8000:8000 | stateless (env+credentials via compose) |
| `n8n` | `n8nio/n8n:latest` | 5678:5678 | `n8n_data` named volume (SQLite DB, files) |
| `postgres` | `postgres:15-alpine` | 5432:5432 | `pgdata` named volume |

All three `restart: unless-stopped` — the pipeline comes back on its own after a reboot.

### API Image (`api/Dockerfile`)

```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Compose overrides two env values:
- `DATABASE_URL=postgresql://...@postgres:5432/...` (host = compose service name)
- `GOOGLE_SERVICE_ACCOUNT_JSON=/app/credentials/service-account.json` (absolute path, because `sheets.py` anchors relative paths to `__file__.parents[2]`, which is `/` in the image)

For API work, run `uvicorn --reload` on the host instead and set `API_BASE_URL=http://host.docker.internal:8000` so n8n reaches the host-process API.

## Provisioning Checklist

### Required credentials (`.env` at repo root)

```dotenv
# Telegram
TELEGRAM_BOT_TOKEN=...

# WhatsApp (webhook — no single env var, config in n8n)
WHATSAPP_VERIFY_TOKEN=...

# STT
GROQ_API_KEY=...
GEMINI_API_KEY=...            # Used for extraction, image generation, and as STT fallback
# HF_API_KEY=...              # Only if using hf-darija provider (benchmark pending)

# Google (all from the same service account)
GOOGLE_SERVICE_ACCOUNT_JSON=credentials/service-account.json
GOOGLE_SHEET_ID=...           # From the sheet URL
GOOGLE_DRIVE_REFRESH_TOKEN=... # For audio file upload to Dropbox equivalent

# Database (optional — logs/auth disabled if unset)
DATABASE_URL=postgresql://aznet:aznet@localhost:5432/aznet_pfe

# Auth
INTERNAL_API_KEY=...          # Shared secret for n8n → API calls
SECRET_KEY=...                # Cookie signing key (openssl rand -hex 32)

# SMTP
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...             # Gmail App Password

# Dashboard
VITE_API_BASE_URL=http://localhost:8000
```

### Google Cloud Platform

1. Create a Google Cloud Project
2. Enable the **Google Sheets API** and **Google Drive API**
3. Create a service account → download JSON key → save as `credentials/service-account.json`
4. Create a Google Sheet → share with the service account email (Editor)
5. Sheet ID = the long string in the URL between `/d/` and `/edit`

### Auth keys

```bash
openssl rand -hex 32         # for SECRET_KEY
openssl rand -hex 32         # for INTERNAL_API_KEY (shared with n8n)
```

### WhatsApp Cloud API

1. Create/use a Meta Business account
2. Create a System User with `whatsapp_business_messaging` and `whatsapp_business_media` permissions → generate a permanent token (never expires)
3. Create (or use existing) WhatsApp Business App
4. Configure the webhook handler URL: `https://<TAILSCALE_HOSTNAME>/webhook/whatsapp/receive`
5. Verify token: `WHATSAPP_VERIFY_TOKEN`
6. Call the WABA `subscribed_apps` API to subscribe the app to the business account's webhook events
7. Subscribe to `messages` and `message_template_status_update` fields

### Hosting Options

All three services **must run on the same machine** (n8n calls the API at `http://localhost:8000`). The public face is a **Tailscale Funnel** (`https://<TAILSCALE_HOSTNAME>` → `127.0.0.1:5678`) — a stable hostname so Meta's webhook URL is configured once and survives reboots.

#### Full `docker compose up -d`

For production/pilot:
```bash
docker compose up -d
```

#### Hybrid: API on host, n8n in container

For active development:
```bash
# Terminal 1
cd api && .venv/Scripts/python.exe -m uvicorn app.main:app --reload

# Terminal 2 — n8n configured to reach API at host.docker.internal:8000
docker compose up -d n8n postgres
```

### Free Tier Constraints / Budget

| Service | Free tier limit | Our usage |
|---|---|---|
| Groq API | 30 RPM / 14,000 RPD / 6 concurrent | <10/day |
| Google Gemini | 1,500 RPM (free tier) | <10 calls/day |
| HF Inference API | varies by model | only if hf-darija is the chosen STT |
| Telegram Bot API | unlimited | one bot, polling every 15s |
| WhatsApp Cloud API | 1,000 messages/day (free tier) | <20/day |
| n8n | unlimited (self-hosted) | one workflow, 2 active bands (reception + error handler) |
| Postgres 15 | unlimited (self-hosted) | <100 MB |
| Tailscale Funnel | 1 tunnel (free) | 1 HTTPS tunnel |
| Gmail SMTP | 500/day | 1 email/day |

## Related
- [[Project Overview]]
- [[n8n Workflows]]
- [[Google Sheets Integration]]
- [[security-secrets]]
