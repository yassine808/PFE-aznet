---
tags: [pfe, development, local, setup, docker, debugging]
type: technical
priority: high
status: current
---

# Local Development Environment Setup

## Overview

```
Telegram (phone) ──polling (getUpdates every 15s)──▶ n8n (Docker, localhost:5678)
                                                          │ HTTP multipart
                                                          ▼
                                              FastAPI (uvicorn --reload, :8000)
```

No tunnel is needed for Telegram in dev: the polling workflow only makes outbound calls, so plain `localhost` works. A public URL is needed for WhatsApp (webhook-driven) and for the webhook Telegram variant — that's **Tailscale Funnel**, `https://<TAILSCALE_HOSTNAME>` → `127.0.0.1:5678`. See `n8n/README.md`.

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Git | any recent | |
| Python | 3.9.x | pinned — `Optional[X]`, never `X \| None` in `api/` |
| Docker | Desktop or Engine | for n8n |
| Tailscale | latest | provides the public HTTPS URL (Funnel) for WhatsApp + webhook-mode Telegram |

There is no Node.js, VS Code extension list, `.vscode/` config, or `requirements-dev.txt` checked into this repo — those don't exist. Dev dependencies (if any) live alongside runtime deps in `api/requirements.txt`.

## Quick start

```bash
# 1. n8n
docker compose up -d              # from repo root → http://localhost:5678

# 2. API
cd api
python -m venv .venv
.venv/Scripts/activate            # or `source .venv/Scripts/activate` in Git Bash
pip install -r requirements.txt
.venv/Scripts/python.exe -m uvicorn app.main:app --reload   # :8000

# 3. Tests (no API keys needed)
.venv/Scripts/python.exe -m pytest
```

## `docker-compose.yml` (actual, repo root)

```yaml
services:
  n8n:
    image: docker.n8n.io/n8nio/n8n:latest
    container_name: pfe-n8n
    restart: unless-stopped
    ports:
      - "5678:5678"
    environment:
      - GENERIC_TIMEZONE=Africa/Casablanca
      - TZ=Africa/Casablanca
      - N8N_DIAGNOSTICS_ENABLED=false
      - WEBHOOK_URL=${WEBHOOK_URL:-http://localhost:5678/}
    volumes:
      - n8n_data:/home/node/.n8n

  # api:  # Sprint 1 placeholder — uncomment once containerized; today the API runs
          # locally via uvicorn, not in this compose file
volumes:
  n8n_data:
```

No basic auth, no SQLite tuning, no queue mode, no healthcheck block, no `docker-compose.dev.yml` overlay — this is the whole file.

## `api/requirements.txt` (actual)

```
fastapi>=0.110,<1
uvicorn[standard]>=0.29
pydantic>=2.7,<3
pydantic-settings>=2.2
python-multipart>=0.0.9
groq>=0.11
google-genai>=1.0
httpx>=0.27
```
No `sentry-sdk`, `slowapi`, `soundfile`, `resampy`, `locust`, `black`, `ruff` — none of that is a dependency today.

## Environment configuration

Config is read by `api/app/config.py` (pydantic-settings) from a `.env` at the **repo root** (shared with docker-compose), not `api/.env`:

```bash
groq_api_key=...
gemini_api_key=...
hf_token=...
```
All optional at import time — a missing key only fails the specific call that needs it, with a clear error message (e.g. `"GEMINI_API_KEY not configured"`). No `.env.example` file exists in the repo yet.

## Telegram reception (dev)

See `n8n/README.md` for the full recipe. Summary:
1. Create a bot via **@BotFather**, paste the token into an n8n Telegram credential.
2. Import `n8n/telegram-reception-polling.json`.
3. Toggle the workflow **Active**.
4. Send a voice note to the bot from your own Telegram account — the *Get Voice File* node should output binary audio. That's the Week-0 smoke test (already passed, per PLAN.md).

For webhook-mode dev (only needed to exercise `telegram-reception.json`):
```bash
tailscale funnel --bg 5678     # once; persists across reboots
tailscale funnel status        # → https://<TAILSCALE_HOSTNAME>
# put that URL in .env as WEBHOOK_URL (trailing slash), then:
docker compose up -d
```

## Testing locally

```bash
cd api
.venv/Scripts/python.exe -m pytest                      # all 33 tests
.venv/Scripts/python.exe -m pytest tests/test_process_endpoint.py -v
.venv/Scripts/python.exe -m pytest -k test_voice_mode -v
```

### Manual API testing (multipart, not JSON)

```bash
# Text mode
curl -X POST http://localhost:8000/process -F "text=Bonjour c'est Ahmed, chantier Hay Riad..."

# Voice mode
curl -X POST http://localhost:8000/process -F "audio=@sample.ogg;type=audio/ogg"

# Health check
curl http://localhost:8000/health
```
There is no JSON+base64 request format and no `metadata` field sent to the API — see [[API Schemas]].

## Common issues

| Symptom | Cause | Fix |
|---|---|---|
| Telegram polling gets 409 | Leftover webhook registered | `curl https://api.telegram.org/bot<TOKEN>/deleteWebhook` |
| `getUpdates` never returns voice | Bot in a group, privacy mode on | Use a 1:1 chat, or disable group privacy |
| Import errors in editor | Wrong interpreter | Point your editor at `api/.venv/Scripts/python.exe` (see `api/pyrightconfig.json`) |
| Pyright false positives | Not using the repo venv | pytest is ground truth per CLAUDE.md |

## Related Notes

- [[Deployment Guide]]
- [[n8n Advanced]]
- [[Testing Strategy]]
- [[Architecture]]
