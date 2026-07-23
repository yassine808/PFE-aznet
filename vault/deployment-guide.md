---
tags: [pfe, deployment, vercel, n8n, vps, docker]
type: technical
priority: high
status: partial
---

> **Note on status:** this is a **plan**, not a description of running infrastructure. As of Jul 23 2026 (Week 1) nothing described below is deployed — the API runs locally via `uvicorn`, n8n runs locally via Docker Compose. No Vercel project, no VPS, no CI/CD pipeline exists. See PLAN.md §4 (timeline) and §1 (locked decisions) for what's actually planned and when.

# Deployment Guide (Plan)

## Target environments (per PLAN.md)

| Environment | API | n8n | Notes |
|---|---|---|---|
| **Dev (current)** | Local `uvicorn --reload`, :8000 | Docker Compose, `localhost:5678` | Telegram polling — no tunnel needed |
| **Pilot (Sprint 3)** | Same Docker Compose stack on the aznet server if available, else Oracle Always Free VM | Same host | Telegram webhook + `cloudflared` tunnel if no fixed public IP |
| **Front (if built)** | Vercel free tier (React dashboard) | — | Dashboard reads Google Sheets API directly, not the FastAPI service |

The FastAPI service itself is not currently planned to run on Vercel — PLAN.md targets it running alongside n8n on the same host (Docker Compose, `api:` service already stubbed out commented-in `docker-compose.yml`). Any prior version of this doc describing a `vercel.json`, Vercel serverless functions for the API, or a `n8n.aznet.ma` domain was aspirational and has been removed — do not treat it as decided.

## What's real today

- `docker-compose.yml` (repo root) runs n8n only, mapped to `5678:5678`, with a commented-out `api:` service block reserved for Sprint 1.
- The API has no containerization yet — it's run directly via the venv.
- No domain, no reverse proxy, no TLS termination is configured anywhere.

## Telegram bot setup (real, dev)

Per `n8n/README.md`:
1. **@BotFather** → `/newbot` → get a token.
2. n8n → Credentials → Telegram API → paste the token.
3. Import `n8n/telegram-reception-polling.json`, toggle Active.

No webhook, no `setWebhook` call, no secret token verification is needed for the polling variant used in dev.

## Pilot deployment (planned, Sprint 3 per PLAN.md)

- Deploy the same Docker Compose stack (n8n + containerized API) to the aznet server or an Oracle Always Free VM.
- Switch to `n8n/telegram-reception.json` (webhook), tunneled via `cloudflared` if the host has no fixed public IP/HTTPS.
- Register 2-3 real phone numbers for the pilot.

None of this exists yet. Do not follow any prior version of this document that specified `vercel.json`, Caddy, Prometheus, or GitHub Actions CI — those tools are not part of the current plan; see [[Monitoring Observability]] and [[n8n Advanced]] for the honest state of those areas.

## Google Sheets / Gmail / dashboard

Not provisioned. See [[Google Sheets Integration]].

## Related Notes

- [[Project Overview]]
- [[Architecture]]
- [[n8n Workflows]]
- [[Local Development]]
