---
tags: [pfe, troubleshooting, runbook, debugging]
type: technical
priority: medium
status: partial
---

> **Note on status:** this is scoped to what actually exists — local dev only (Docker n8n + local uvicorn API, Telegram polling). There is no production deployment, no Vercel, no VPS, no Sentry, no Sheets integration to troubleshoot yet. A prior version of this doc described incident severities, on-call escalation, and production runbooks for infrastructure that was never built; it has been removed.

# Troubleshooting (Current Dev Setup)

## Read the asymmetry first

When one channel misbehaves and the other doesn't, the *difference* is the diagnosis:

- **Telegram works, WhatsApp silent** → almost always the tunnel. Telegram polls (outbound, no tunnel needed); WhatsApp needs Meta to reach in.
- **Both fail with an error reply** → downstream of reception: API down, or an STT/LLM engine failing.
- **Both silent** → n8n itself is down, or the workflow is deactivated.

An error reply is *better news* than silence: it proves the message reached the pipeline and the failure branch fired.


## Quick reference

| Symptom | Likely cause | Fix |
|---|---|---|
| **Telegram replies "❌ Erreur lors du traitement"** | The API is not running (`/process` refused) | `curl localhost:8000/health`; start uvicorn. The error reply means the pipeline caught the failure correctly |
| **WhatsApp does not reply at all** | Webhook tunnel dead — Meta cannot reach n8n, so *no node runs* | `curl <WEBHOOK_URL>`; restart the tunnel, then re-point Meta's webhook. See [[deployment-guide]] |
| **Logs panel empty while reports still work** | `API_BASE_URL` missing from the n8n container (started before the compose change) | `docker exec pfe-n8n printenv \| grep API_BASE_URL`; `docker compose up -d` to recreate |
| API logs `[logs] DISABLED — …` at startup | `DATABASE_URL` unset or Postgres not running | `docker compose up -d postgres`, set `DATABASE_URL` in `.env` |
| Reports reply fine but no Sheet rows | Sheet writes failing into the retry queue | `curl localhost:8000/sheet-queue`; check the `sheet_failed` rows in the Logs panel |
| Same report appears twice | Dedup claim unavailable, so it failed open | Confirm Postgres is up; the claim deliberately treats an unreachable store as "fresh" |
| n8n `getUpdates` returns 409 | Leftover webhook registered from a previous test | `curl https://api.telegram.org/bot<TOKEN>/deleteWebhook` |
| Bot never sees voice notes | Bot added to a group (privacy mode restricts groups) | Talk to the bot in a 1:1 chat |
| API returns 422 on `/process` | Both or neither of `audio`/`text` provided, or empty | Send exactly one, multipart form, non-empty |
| API returns 502 | STT or extraction engine failed (missing key, provider outage) | Check the specific error message — it names the engine and reason |
| `pytest` fails locally | Wrong venv/interpreter | Use `api/.venv/Scripts/python.exe`, not system Python |
| Pyright flags real code as broken | IDE not pointed at `api/.venv` | `api/pyrightconfig.json` already points at the venv; re-select interpreter |

## Diagnosing API errors

```bash
# Health check
curl http://localhost:8000/health

# Manual reproduction (multipart, not JSON+base64)
curl -X POST http://localhost:8000/process -F "text=test report"
curl -X POST http://localhost:8000/process -F "audio=@sample.ogg;type=audio/ogg"
```

`/health` returns `{"status": "ok", "stt_providers": [...], "stt_default": "..."}` — useful to confirm which STT adapters are registered and which one is the active default.

502 errors carry the real exception message from `TranscriptionError`/`ExtractionError`, e.g. `"transcription failed: groq: ..."` or `"extraction failed: extraction failed on both engines — gemini: ... | groq: ..."` — read the message, it names the failing provider(s).

## Diagnosing n8n issues

```bash
# n8n container running?
docker compose ps

# n8n logs
docker compose logs -f n8n
```

n8n's own execution list (UI, `http://localhost:5678`) shows each polling cycle's result — check there before assuming a bug in the API.

## Diagnosing Telegram reception

```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```
For the **polling** workflow this should show no webhook set (or you'll get 409s). For the **webhook** variant, confirm the URL matches your current `cloudflared` tunnel — it changes every run, so update `.env`'s `WEBHOOK_URL` and reactivate the workflow when it does.

## What doesn't apply yet

Vercel function logs, Sentry error tracking, Prometheus alerts, VPS SSH/firewall debugging, Sheets 403/429 errors, Gmail SMTP failures — none of these systems exist yet, so there's nothing to troubleshoot there. See [[Deployment Guide]], [[Google Sheets Integration]], and [[Monitoring Observability]] for the honest state of each.

## Related Notes

- [[Local Development]]
- [[Architecture]]
- [[n8n Workflows]]
