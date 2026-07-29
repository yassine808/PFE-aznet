---
tags: [pfe, n8n, workflows, telegram, google-sheets, email]
type: technical
priority: high
status: partial
---

> **Status 2026-07-29:** n8n now carries **reception + the error handler only** — `n8n/aznet-complete.json`, 52 nodes in two labelled bands (réception, erreurs). The maintenance, daily-report and (new) weekly-report schedules moved into the API's own scheduler, `api/app/jobs.py`, driven from the dashboard's **Automation** page: a cron node could not show what a run produced or let an operator re-run it. The error band stayed because it catches n8n's own execution failures, which the API cannot see. **The reply now happens BEFORE the Sheet append** — a Google outage can no longer swallow a report; failed writes park in a Postgres retry queue drained every 5 min. Added: durable WhatsApp idempotency (was in-memory, wiped on restart), retries + timeouts on `/process`, and per-stage logging to `POST /logs` joined by `correlation_id`. The error workflow posts to `/logs` instead of an `Errors` sheet tab. `legacy-*.json` are the superseded single-channel flows — **never activate one alongside the unified flow** (double processing). **Full setup doc: `docs/setup-guide.md`.**

# n8n Workflows

## Overview

Workflow files in `n8n/` (exported JSON):

- `n8n/aznet-complete.json` — **the one to import.** Merges everything below. Reception band: Telegram polling + WhatsApp webhook into one pipeline: extract (audio OR typed text, dedupe) → shared allowlist w/ roles (outsiders: one HR reply) → ⏳ ack → download per channel → `POST /process` (audio or text mode, error → ❌ reply) → ✅ résumé reply on the originating channel → **then** Sheets append (`canal`, `confidence`, `flag_review`); on write failure the report is queued for retry instead of lost. Seven `Log *` leaf nodes record each stage.
- Band 2 of `aznet-complete.json` — Error Trigger → `POST /logs` (`stage: workflow_error`); set the workflow as its own Error Workflow after import. No longer writes to an `Errors` sheet tab: an error handler that reports through Google cannot report Google failing.
- `api/app/jobs.py` — five scheduled jobs: `sheet_queue` (5 min, drains the retry queue), `prune_logs` + `profiles` (03:00), `daily_report` (Mon–Sat) and `weekly_report`. Times read from `app_settings` on every check.
- The per-concern workflow files (`reception-unified`, `maintenance-cron`, `daily-report-cron`, `error-workflow`) and the `legacy-*` single-channel flows were deleted on 2026-07-29 — git history has them.

```
Telegram (voice note / forwarded audio)
      │
      ▼
Telegram Trigger / getUpdates polling
      │
      ▼
Get File (binary audio, property `data`)
      │
      ▼
HTTP Request → POST /process (multipart, field `audio`)
      │
      ▼
[n8n adds metadata: date, technicien, lien_audio]
      │
      ▼
(planned) Sheets append ─┬─ (planned) Email to manager
                          └─ Telegram confirmation reply (built)
```

## Manual node recipe (per `n8n/README.md`)

| # | Node | Key config |
|---|---|---|
| 1 | **Telegram Trigger** | Updates = `message` |
| 2 | **Telegram** (Resource *File*, Op *Get File*) | File ID = `{{ $json.message.voice.file_id }}` → binary property `data` |
| 3 | **HTTP Request** | `POST http://host.docker.internal:8000/process` (dev), multipart-form-data, one binary field `audio` bound to `data` |

Forwarded audio (`message.audio`) is treated identically to native voice notes (`message.voice`) — both go through the same path.

Metadata added by n8n **after** the API responds (not sent to it): `date`/`heure` = now; `technicien` = `message.from.first_name` or a chat_id→name map; `lien_audio` — Telegram's file URL embeds the bot token and isn't durable, so the plan is to upload the audio to Google Drive and store that link, or fall back to storing the raw `file_id`.

## Confirmation reply (built)

A **Telegram → Send Message** node replies to the technician, tagged as a reply to the original voice message (`reply_to_message_id`). When the STT provider exposes a confidence score (Groq only today), the reply includes a `🎙️ Confiance transcription: NN%` line; reports below 50% get flagged with `low_confidence_transcription` in `warnings`.

## Webhook variant setup (pilot)

```bash
tailscale funnel --bg 5678
```
Put the resulting `https://<TAILSCALE_HOSTNAME>` in `.env` as `WEBHOOK_URL`, then `docker compose up -d` to restart. The hostname is stable, so this is a one-time step. Activating the workflow makes n8n call Telegram's `setWebhook` pointing at that URL — set it *before* activating.

## Google Sheets integration — planned

No sheet has been created, no service account provisioned, no n8n Sheets node exists. When built (Sprint 2), it will append one row per report with `ExtractedReport` fields + n8n's own metadata columns. Don't treat any column layout as decided — see [[Google Sheets Integration]] for the honest state.

## Email notification — planned

Gmail SMTP is the intended channel (PLAN.md), not yet wired into any workflow.

## Web form path — planned

The React web form (text mode) exists in PLAN.md's scope but as of Jul 23 the form itself and its n8n-facing webhook are not built.

## Testing

Smoke test (passed Jul 17, per PLAN.md): send a voice note to the bot → an execution appears in n8n → the *Get Voice File* node outputs binary audio. That's the whole integration risk killed for reception; Sheets/email/dashboard steps remain untested because unbuilt.

## Related Notes

- [[Project Overview]]
- [[Architecture]]
- [[Google Sheets Integration]]
- [[Deployment Guide]]
