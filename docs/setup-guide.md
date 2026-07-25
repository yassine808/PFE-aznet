# Setup Guide — Telegram + WhatsApp + n8n + API + Sheets

End-to-end configuration of the reception pipeline, as actually done on 2026-07-23.
Audience: future me / anyone redeploying from zero. Every secret location is explicit.

```
Telegram (polling) ─┐
                    ├→ n8n "Reception unified" → FastAPI /process → Google Sheets → reply (same channel)
WhatsApp (webhook) ─┘
```

---

## 0. Prerequisites

- Docker Desktop running
- Python 3.9 venv in `api/` (`api/.venv`)
- `.env` at repo root (never committed) — holds: `TELEGRAM_BOT_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_BUSINESS_ACCOUNT_ID`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `WEBHOOK_URL`

## 1. Start the stack

```bash
docker compose up -d                                   # n8n → http://localhost:5678
cd api && .venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/health                      # {"status":"ok",...}
```

`docker-compose.yml` passes into the n8n container: `WEBHOOK_URL`, `WHATSAPP_PHONE_NUMBER_ID`, `TELEGRAM_BOT_TOKEN`, and `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` (required — without it Code nodes get "access to env vars denied" when reading `$env.*`).

## 2. Telegram bot

1. Telegram → **@BotFather** → `/newbot` → name + username ending in `bot` → copy token.
2. Token goes in `.env` as `TELEGRAM_BOT_TOKEN=...` (the workflow's *Offset + token* Code node reads `$env.TELEGRAM_BOT_TOKEN` — never hardcode it in the workflow JSON).
3. n8n → Credentials → Add → **Telegram API** → paste same token. Used by all `TG *` nodes (file download + replies).
4. Find your numeric user ID: message **@userinfobot** → it replies with your ID → goes in the workflow ALLOWLIST.
5. Polling note: only ONE active workflow may call `getUpdates` per token — two pollers steal each other's messages. If Telegram returns 409: `https://api.telegram.org/bot<TOKEN>/deleteWebhook` once.

## 3. WhatsApp (Meta Cloud API)

Meta side (developers.facebook.com → your app, new use-case UI):

| Item | Where |
|---|---|
| App ID + App Secret | App settings → Basic (Secret behind "Show") |
| Phone number ID + WABA ID | WhatsApp use case → **Step 1. Try it out** (old "API Setup") |
| Access token (temp, 24h) | same page |
| Durable token | business.facebook.com → Business settings → System users → create Admin → assign app + WABA → Generate token, scopes `whatsapp_business_messaging` + `whatsapp_business_management` |

n8n side — TWO credentials:

1. **WhatsApp OAuth** (used by *WhatsApp Trigger* node): Client ID = App ID, Client Secret = App Secret.
2. **WhatsApp API** (used by send/media nodes): Access Token + Business Account ID (WABA).

`.env`: `WHATSAPP_PHONE_NUMBER_ID=...` (send nodes read `$env.WHATSAPP_PHONE_NUMBER_ID`).

Webhook registration (needed before the trigger can receive):

```bash
tailscale funnel --bg 5678       # once; survives reboots
tailscale funnel status          # → https://<machine>.<tailnet>.ts.net
```
The hostname is **stable** (currently `https://<TAILSCALE_HOSTNAME>`), so Meta is configured once and never again — unlike a cloudflared quick tunnel, whose URL changes on every run.

→ `.env` `WEBHOOK_URL=https://<TAILSCALE_HOSTNAME>/` (trailing slash) → `docker compose up -d` → activate workflow → open WhatsApp Trigger node, copy its production webhook URL + verify token → Meta dashboard → WhatsApp → Configuration → Webhook → paste both → Verify and save → subscribe to **messages** field.

Test-mode limits: 5 recipient numbers max, each must message the test number first or be added in Step 1 page. Temp tokens die in 24h.

**Until the tunnel is up:** keep the WhatsApp Trigger node deactivated (right-click → Deactivate node), otherwise workflow activation fails with "Bad request / Invalid parameter" (Meta rejects a localhost callback).

## 4. Google Sheets (service account)

1. Sheet: <https://docs.google.com/spreadsheets/d/<GOOGLE_SHEET_ID>> — tab **`Rapports`**, header row =
   `date, heure, canal, technicien, role, chantier, client, type_activite, goulottes_m, cables_m, bureaux_termines, panneaux_raccordes, autres_travaux, observations, resume, rapport_complet, confidence, flag_review, lien_audio`
   (paste comma string in A1 → Data → Split text to columns). An `Errors` tab serves the error workflow: `timestamp, workflow, node, message, execution_url`.
2. console.cloud.google.com → project `pfe-aznet` → enable **Google Sheets API** → IAM → Service Accounts → `n8n-sheets` → Keys → new JSON key.
3. **Share the Sheet** with `<SERVICE_ACCOUNT_EMAIL>` as **Editor** (skipping this = 403 on every append).
4. n8n → Credentials → **Google Service Account API** → Service Account Email + full `private_key` value (with the `\n`s, pasted as-is, Fixed not Expression).

## 5. The unified workflow

`n8n/reception-unified.json` = source of truth, import via Workflows → ⋯ → Import from File.

Already baked into the file (patched via scripts, re-import = zero manual wiring):
- credential IDs for Telegram / WhatsApp API / WhatsApp OAuth / Google service account
- spreadsheet ID, 19-column schema on *Append Sheet row* (n8n v4 Sheets node requires `columns.schema` when mapping is `defineBelow`)
- ALLOWLIST in *Access control*: Telegram `<TELEGRAM_USER_ID>` + WhatsApp `<WHATSAPP_NUMBER>` (both `directeur`)
- bot token + phone number ID via `$env.*`

Behavior:
- voice notes, forwarded audio, AND typed text reports (both channels; `/commands` ignored)
- allowlist gate; outsiders get exactly one HR reply per chat, then silence
- ⏳ ack after authorization; ✅ résumé reply (or ❌ error reply) always on the originating channel
- dedupe via static data keys (`tg:<chat>:<msgid>` / `wa:<wamid>`)
- Sheet row includes `canal`, `confidence`, `flag_review`

Credential/ID changes later: edit the JSON (or re-run the patch scripts) and re-import — n8n binds credentials by ID.

## 6. Companion workflows

- `n8n/error-workflow.json` — Error Trigger → `Errors` tab. Import, then set as Error Workflow in the unified workflow's settings.
- `n8n/daily-report-cron.json` — Mon–Sat 18:30 → today's rows → `POST /daily-report` → Gmail. Needs Gmail credential + manager address.
- `n8n/telegram-reception*.json`, `n8n/whatsapp-reception.json` — single-channel variants, superseded by unified; keep as reference.

## 7. Smoke test

1. API health: `curl http://localhost:8000/health`
2. Workflow Active (WhatsApp Trigger deactivated unless tunnel registered)
3. Telegram: voice note to bot → ⏳ within 15s → ✅ résumé → row in Sheet
4. Telegram: typed text report → same, no confidence value
5. Non-allowlisted account: one HR reply, nothing in Sheet
6. WhatsApp (post-registration): voice note from an allowlisted test number → same flow, reply on WhatsApp

## 8. Troubleshooting (all hit for real on 2026-07-23)

| Symptom | Cause → fix |
|---|---|
| "access to env vars denied" in Code node | add `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` to compose, restart |
| "Node does not have any credentials set" after import | JSON credential IDs don't match instance → patch real IDs (credential ID = string in URL when credential open) |
| "`columns.schema` is required…" on Sheets node | populate `schema` in JSON, or open node and re-select the Sheet so n8n refetches columns |
| Activation fails on WhatsApp Trigger "Invalid parameter" | no public `WEBHOOK_URL` yet → deactivate node until tunnel registered |
| Sheets append 403 | Sheet not shared with the service-account email |
| Telegram voice notes vanish randomly | second active workflow polling same token → keep one |
| getUpdates 409 | stale webhook → `deleteWebhook` once |
