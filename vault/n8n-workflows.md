---
tags: [pfe, n8n, workflows, telegram, google-sheets, email]
type: technical
priority: high
status: partial
---

> **Note on status:** Telegram reception (polling + webhook variants) is built and smoke-tested. Google Sheets append, email notification, and the manager dashboard read path are **not built yet** (PLAN.md Sprint 2). Treat those sections below as the plan, not current behavior.

# n8n Workflows

## Overview

Two workflow files live in `n8n/`, both exported JSON, both covering the *same* reception job with different transport:

- `n8n/telegram-reception-polling.json` — **current dev approach.** Polls Telegram's `getUpdates` every 15s. Outbound-only, so plain `localhost` works — no tunnel needed.
- `n8n/telegram-reception.json` — webhook variant, needs a public HTTPS tunnel (Cloudflare's `cloudflared`, not ngrok — n8n's built-in tunnel is dead in n8n 2.x). Targets the pilot.

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
cloudflared tunnel --url http://localhost:5678
```
Put the printed `https://<words>.trycloudflare.com` URL in `.env` as `WEBHOOK_URL`, then `docker compose up -d` to restart. Activating the workflow makes n8n call Telegram's `setWebhook` pointing at that URL — set it *before* activating.

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
