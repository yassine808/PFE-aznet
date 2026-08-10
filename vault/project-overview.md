---
tags: [pfe, project, overview]
type: overview
priority: high
status: current
---

# Project Overview

## What This Is

**Subject:** End-of-studies project (PFE) at Aznet.ma  
**Deadline:** August 31, 2026  
**Current date:** July 31, 2026  
**Source of truth:** `PLAN.md` and `docs/cahier-des-charges.md`

A pipeline that takes voice notes in Moroccan Darija from cabling technicians (via Telegram or WhatsApp), transcribes them, extracts structured data using LLMs, writes to Google Sheets, and emails a professional French summary to managers.

## Architecture (Hybrid)

- **n8n** (self-hosted) = orchestration & glue: message reception, media download, HTTP calls, Sheets append, error handling
- **API** (Python/FastAPI) = AI microservice: STT, LLM extraction, scheduled jobs, dashboard backend
- **PostgreSQL** = observability, auth, queue, settings
- **Dashboard** (React/Vite/TypeScript/Tailwind v4) = web UI on top of the API

## Key Design Decisions

1. **n8n does the reply before the Sheet append** — a failed write must never cost the technician their summary. Failed writes go to a Postgres retry queue drained every 5 minutes.
2. **Darija STT** uses a strategy pattern (Groq Whisper primary, Gemini Audio fallback, HF Darija fine-tune pending benchmark).
3. **Two extraction fallback chains** (ranked 2026-07-27): text chain alternates vendors (Groq gpt-oss-120b → Gemini flash-lite → Gemini 3.6-flash); image chain is Google-only (no free Groq vision model).
4. **No silent fallbacks** — if all engines in a chain fail, the API returns 502 so n8n can flag the row. Never invented data.
5. **Image input**: vision model reads the photo and fills the schema directly (no intermediate transcription). Always `flag_review=true`.
6. **Technician profiles**: one French paragraph per technician, rebuilt nightly at 03:00 from their past reports, injected into extraction prompts as labelled context.
7. **Reply-first ordering**: n8n replies to the technician *before* appending to the Sheet. The user gets their confirmation even if Sheets is down.
8. **Auth**: session cookies (Postgres-backed) for humans, `X-API-Key` for n8n — two separate gates (`require_user` accepts either, `require_human` rejects machines, `require_director` narrows further).

## Tech Stack

- **Backend API**: Python 3.11, FastAPI, pydantic-settings, uvicorn
- **STT**: Groq Whisper-large-v3 (default), Gemini (flash-lite native audio), HF Darija fine-tune (benchmark pending)
- **LLM**: ranked chains (`extraction_text_chain` / `extraction_image_chain` in `config.py`) — text: Groq gpt-oss-120b → Gemini flash-lite → Gemini 3.6-flash; image: Google-only 3.6-flash chain
- **Image generation**: Google `gemini-3.1-flash-image` → `nano-banana-pro` → `3-pro-image` (click-only, never a cron)
- **Email**: smtplib + Gmail SMTP App Password
- **Database**: PostgreSQL 15 (optional — logs/auth disabled if `DATABASE_URL` unset)
- **Orchestration**: n8n (self-hosted, single unified workflow)
- **Dashboard**: React 19, Vite, TypeScript, Tailwind v4, `motion/react`, Phosphor icons
- **Deployment**: Docker Compose (3 services: api, n8n, postgres)
- **Public URL**: Tailscale Funnel → n8n (for WhatsApp webhooks)

## Feature Status

| Feature | Status | Notes |
|---|---|---|
| Telegram voice → STT → Sheet | ✅ Built | Live since 2026-03 |
| WhatsApp voice → STT → Sheet | ✅ Built | Live since 2026-07-23 |
| Text (typed report) mode | ✅ Built | `/process` accepts `text` field |
| Image/photo input | ✅ Built | Vision model, no transcription, `flag_review=true` |
| LLM extraction (ranked chains) | ✅ Built | Text alternates Groq/Gemini; image is Google-only |
| Technician profiles | ✅ Built | `api/app/memory.py`, rebuilt at 03:00 |
| Google Sheets append | ✅ Built | Done by n8n, retry queue for failures |
| Google Sheets read/write (dashboard) | ✅ Built | `GET|PATCH /reports` |
| PDF report generation | ✅ Built | `api/app/imagegen.py` (illustrated summary card) |
| Daily report email | ✅ Built | `api/app/daily_report.py`, triggered by scheduler |
| Weekly report email | ✅ Built | Reuses daily report with date-range label |
| Dashboard (React) | ✅ Built | `Dashboard/`, live on port 5173 (dev) |
| Dashboard auth (sessions) | ✅ Built | `POST /auth/login`, Postgres-backed |
| Access control (technicians) | ✅ Built | `GET|POST|DELETE /technicians` |
| STT benchmark | 🟡 Pending | Dataset `benchmark/dataset/audio/` still empty |
| n8n dashboards | 🟡 N/A | Dashboard has its own panel; n8n UI is admin only |
| AI search on reports | ❌ Not planned | Sheets search is sufficient |
| Automated testing on CI | 🟡 Blocked | `.github/workflows/ci.yml` exists but every job reports a GitHub Actions **billing block** ("recent account payments have failed") — fix billing or make the repo public |
| Public deployment | 🟡 Pilot | Docker Compose on local machine, Tailscale Funnel |

## Channels

Two active reception channels:

- **Telegram**: Polling (outbound only), no open ports needed. Technicians send voice notes to the bot. The bot uses `getUpdates` every 15s.
- **WhatsApp**: Webhook-driven via Tailscale Funnel (`https://<TAILSCALE_HOSTNAME>` → n8n). Needs a public HTTPS URL.

Both feed the same `/process` endpoint and append to the same Sheet. The reply returns on the originating channel.

## Data Flow (simplified)

```
Technician (TG/WA) → n8n → POST /process (API) → JSON → n8n reply → n8n Sheet append
                                                              → (on failure) Postgres queue → drain → Sheet
```

Scheduled jobs (API internal): daily email → SMTP, weekly email → SMTP, profile rebuild → persons.profile → no n8n involvement.

## Related

- [[architecture]] — detailed system boundaries
- [[Extraction Pipeline]] — LLM prompt flow
- [[n8n Workflows]] — orchestration details
- [[Google Sheets Integration]]
- [[Deployment Guide]]
- [[Local Development]]
- [[STT Benchmark]]
- [[TO-DO]]
