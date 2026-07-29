---
tags: [pfe, development, setup, guide]
type: guide
priority: high
status: current
---

# Local Development

## Prerequisites

- Python 3.9 (not 3.10+)
- Node.js 18+
- Docker Desktop (optional — for n8n + Postgres)
- A `.env` file at repo root (see `.env.example` for template)

## API Setup

```bash
# Navigate to the api directory
cd api

# Create virtual environment (Python 3.9)
py -3.9 -m venv .venv

# Activate
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run dev server with hot reload
uvicorn app.main:app --reload
```

The API runs on `http://localhost:8000`. Test it:

```bash
curl http://localhost:8000/health
```

### Running tests

```bash
# From api/ directory, with venv active
pytest                          # all 53 tests
pytest tests/test_process_endpoint.py -k test_voice_mode   # single test
```

Tests must pass **without API keys** — external SDKs are lazy-imported and mocked at test boundaries. No database required.

## Dashboard Setup

```bash
cd Dashboard
npm install
npm run dev          # Vite dev server on :5173
```

The Vite dev proxy routes `/n8n` → n8n API (with `X-N8N-API-KEY` from `Dashboard/.env`, **not** `VITE_`-prefixed, so it never reaches client JS). This is the only way n8n panels work in dev.

## Docker Compose (full stack)

From repo root:

```bash
docker compose up -d
```

Three services:
| Service | Port | Notes |
|---|---|---|
| api | 8000 | `restart: unless-stopped` |
| n8n | 5678 | `restart: unless-stopped`, `n8n_data` volume |
| postgres | 5432 | `restart: unless-stopped`, `pgdata` volume |

In compose mode, `DATABASE_URL` points to `postgres` host (compose service name).  
`GOOGLE_SERVICE_ACCOUNT_JSON` must be an absolute path inside the image.

### Hybrid mode (n8n+DB in Docker, API on host)

```bash
# Start n8n + postgres
docker compose up -d n8n postgres

# In .env, ensure DATABASE_URL=postgresql://aznet:aznet@localhost:5432/aznet_pfe
# Then run API on host
cd api && uvicorn app.main:app --reload

# Set API_BASE_URL=http://host.docker.internal:8000 in n8n env so the workflow
# reaches the host API from within the container
```

## Telegram setup (local dev)

For local development, use Telegram polling mode (no public URL needed):

```bash
# n8n does this for you — no open ports required
# The workflow uses the Telegram node in polling mode (getUpdates)
```

## Telegram setup (production/webhook)

```bash
# Set the webhook URL in n8n (not directly on Telegram API)
# n8n's Telegram Trigger handles this when switching to webhook mode
# Your bot has only one webhook at a time — don't point it at the API
```

## WhatsApp setup

WhatsApp needs a public HTTPS URL. Use **Tailscale Funnel**:

```bash
# On the machine running n8n (with Tailscale connected)
# A funnel route is configured: https://<TAILSCALE_HOSTNAME> → 127.0.0.1:5678
# Meta's webhook verification is a manual GET-echo step (n8n's WhatsApp Trigger fails it)
```

Full WhatsApp walkthrough: `docs/setup-guide.md`

## File Structure

```
PFE-aznet/
├── api/                  # Python FastAPI microservice
│   ├── app/
│   │   ├── main.py       # FastAPI app & all endpoints
│   │   ├── config.py     # pydantic-settings, env-driven
│   │   ├── schemas.py    # Pydantic models (ExtractedReport etc.)
│   │   ├── extraction.py # LLM extraction orchestration
│   │   ├── sheets.py     # Google Sheets read/write
│   │   ├── mailer.py     # SMTP email sending
│   │   ├── imagegen.py   # Summary card image generation
│   │   ├── memory.py     # Technician profiles
│   │   ├── daily_report.py       # Daily/weekly email logic
│   │   ├── auth.py              # Session-based auth
│   │   ├── prompt_loader.py     # Markdown prompt loader
│   │   ├── providers/           # STT strategy pattern
│   │   │   ├── base.py          # TranscriptionProvider ABC
│   │   │   └── groq.py, gemini.py, hf_darija.py
│   │   └── prompts/             # Versioned Markdown prompts
│   ├── tests/            # pytest test suite (53 tests)
│   └── Dockerfile
├── Dashboard/            # React/Vite frontend
│   ├── src/
│   │   ├── pages/       # overview, inbox, reports, daily, weekly, automation, access, logs, team, login
│   │   ├── lib/         # api.ts, auth.tsx, ops-context.tsx
│   │   └── locales/     # fr.json, en.json, ar.json
│   └── .env             # VITE_API_BASE_URL + N8N_API_KEY (non-VITE_)
├── n8n/
│   ├── aznet-complete.json   # Unified workflow (single source of truth)
│   ├── legacy-*.json         # Pre-unification workflows (reference only)
│   └── README.md
├── docs/
│   ├── cahier-des-charges.md # Original spec
│   └── setup-guide.md        # Full WhatsApp + Telegram walkthrough
├── docker-compose.yml   # 3 services: api, n8n, postgres
├── .env.example         # Environment variable template
├── PLAN.md              # Sprint timeline, architecture decisions
└── BUGS-TO-FIX.md       # Known bugs from code review
```

## Related
- [[Deployment Guide]]
- [[security-secrets]]
- [[n8n Workflows]]
