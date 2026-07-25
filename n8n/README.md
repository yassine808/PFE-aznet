# n8n — orchestration layer

Role (per PLAN.md): **Telegram** reception → voice download → call FastAPI `/process` → append Google Sheets row → email notification → Telegram confirmation reply.

> Channel note: reception is channel-agnostic. The API (`/process`) only ever sees an audio blob — it has no idea the channel is Telegram. WhatsApp Business API is the documented production-evolution path; Telegram carries the pilot + defense demo (free, no approval, no recipient cap, no token expiry). See PLAN.md §1.

Workflow exports (`*.json`) live here — export after every meaningful change (n8n UI → workflow menu → Download).

Two import-ready variants:
- [`telegram-reception-polling.json`](./telegram-reception-polling.json) — **current dev approach.** Polls `getUpdates` every 15s; outbound-only so plain `localhost` works — no tunnel, no public URL. Paste the bot token in the "Offset + token" Code node + a Telegram credential on "Get Voice File", toggle Active. If `getUpdates` returns 409, clear a leftover webhook once via `https://api.telegram.org/bot<TOKEN>/deleteWebhook`.
- [`telegram-reception.json`](./telegram-reception.json) — webhook variant (needs the public HTTPS URL below; n8n's built-in `start --tunnel` is dead in n8n 2.x — use Tailscale Funnel). Pilot/server target.

## Import (one file)

**Import [`aznet-complete.json`](./aznet-complete.json) — that's it.** It merges all four production workflows into a single n8n workflow with independent trigger branches, laid out in four labelled bands:

| Band | Triggers | Role |
|---|---|---|
| 1 — Réception | `Every 15s` (TG poll), 2 WA webhooks | voice/text → `/process` → reply → Sheet |
| 2 — Maintenance | `Every 5 min`, `Daily 03:00` | drain the Sheet retry queue, prune logs >30 d |
| 3 — Rapport quotidien | `18:30 Mon-Sat` | day's rows → manager email |
| 4 — Gestionnaire d'erreurs | `Error Trigger` | any crash → `POST /logs` |

After import: **Settings → Error Workflow → this same workflow** (a workflow can be its own error handler; the field ships empty because it needs the ID n8n assigns at import). Then attach credentials once — one Google service account, one Telegram, one WhatsApp, one Gmail — and activate.

The individual files (`reception-unified.json`, `maintenance-cron.json`, `daily-report-cron.json`, `error-workflow.json`) remain as the per-concern sources; `aznet-complete.json` is generated from them. Edit the sources, then re-merge.

⚠️ `legacy-*.json` are the pre-unification single-channel flows, kept for reference only. **Never activate one alongside the unified flow** — they poll the same bot token and subscribe to the same Meta webhook, so you would get double processing: two Sheet rows, two replies, doubled free-tier quota burn. They also predate the reply-first fix, the durable dedup and all logging.

## Run

```bash
docker compose up -d     # from repo root → http://localhost:5678
```

## 1. Create the Telegram bot (replaces the whole Meta app setup)

1. In Telegram, open a chat with **@BotFather**.
2. Send `/newbot` → give it a display name and a username ending in `bot` (e.g. `aznet_rapports_bot`).
3. BotFather returns a **bot token** like `123456789:AAF...`. This single token is your entire credential — no app review, no phone registration, no expiry.
4. n8n → **Credentials** → *New* → **Telegram API** → paste the token.

## 2. Expose n8n's webhook (Telegram needs public HTTPS)

Telegram only delivers updates to a **public HTTPS** URL with a valid certificate (ports 443/80/88/8443). `localhost` is unreachable to it — the tunnel is still required.

**Tailscale Funnel (current setup)**
```bash
tailscale funnel --bg 5678     # once; persists across reboots
tailscale funnel status        # → https://<machine>.<tailnet>.ts.net → 127.0.0.1:5678
```
Gives a **stable** `https://<TAILSCALE_HOSTNAME>`. Put it in `.env` as `WEBHOOK_URL` (with trailing `/`), then `docker compose up -d` so n8n adopts it. Because the hostname never changes, Meta and Telegram are pointed at it once — no reconfiguration after a reboot.

> Why WEBHOOK_URL matters: when you **activate** a workflow, n8n calls Telegram's `setWebhook` for you, pointing Telegram at `WEBHOOK_URL` + the trigger's path. Set it *before* activating, or Telegram is told to deliver to `localhost` and nothing arrives.

**Alternative — cloudflared quick tunnel:** `cloudflared tunnel --url http://localhost:5678` gives a throwaway `*.trycloudflare.com` URL. Works, but the URL changes every run, so Meta must be reconfigured each time. Fallback only.

## 3. Telegram voice smoke test (Week 0 exit criterion)

1. n8n → new workflow → import `telegram-reception.json` (or add nodes manually, see below) → attach your Telegram API credential to both Telegram nodes.
2. Ensure `WEBHOOK_URL` = your live tunnel URL, then **toggle the workflow Active** (this is what registers the webhook with Telegram).
3. From your own Telegram account, open the bot chat and **send a voice note** (hold mic, speak, release).
4. **PASS** = an execution appears in n8n and the *Get Voice File* node outputs binary audio (the `.oga`/OPUS file). That's the whole integration risk killed.

### Manual node recipe (if not importing the JSON)

| # | Node | Key config |
|---|------|-----------|
| 1 | **Telegram Trigger** | Updates = `message`. Emits `message.voice.file_id` for voice notes. |
| 2 | **Telegram** → Resource *File*, Operation *Get File* | File ID = `={{ $json.message.voice.file_id }}` → downloads audio into binary property `data`. |
| 3 | **HTTP Request** | `POST` `http://host.docker.internal:8000/process` (dev; becomes `http://api:8000/process` once `api/` is in compose). Body = *multipart-form-data*, one **binary** field named `audio`, input data field `data`. |

Metadata n8n adds later (not the API's job): `date`/`heure` = now; `technicien` = `message.from.first_name` or a `chat_id`→name map; `lien_audio` (cahier marks it *optional*) — Telegram's file URL embeds the bot token and isn't durable, so upload the audio to Google Drive (you already hold Google creds for Sheets) and store that link, or store the raw `file_id` as a quick fallback.

> Bot privacy: a bot in a **1:1 chat** receives everything, including voice notes — no config needed. Privacy mode only restricts what a bot sees inside *groups*, which this flow doesn't use.

## 4. Confirmation reply (no 24h window)

To close the loop, add a **Telegram → Send Message** node after the pipeline, Chat ID = `={{ $json.message.chat.id }}`. Unlike WhatsApp's 24h session-window rule, Telegram bots can reply to a user any time.

The polling workflow tags the confirmation as a **reply** to the original voice/audio message (`additionalFields.reply_to_message_id`), so the technician can see which report a confirmation belongs to in the chat thread. When the STT provider exposes a confidence score (currently Groq only — see `TranscriptionInfo.confidence` in `api/`), the reply also shows a `🎙️ Confiance transcription: NN%` line, and reports below 50% get flagged with `low_confidence_transcription` in `warnings` for manual review.

Forwarded audio files (`message.audio`) are treated identically to native voice notes (`message.voice`) — both go through the same extraction + reply path.

## 5. Access control (allowlist + roles)

Both reception workflows now carry an **Access control** Code node: an `ALLOWLIST` map of Telegram user IDs → `{ name, role }` (`technicien` | `directeur`). Edit the map directly in the node (a settings panel replaces this post-PFE). To find someone's user ID, have them message the bot once and read `message.from.id` in the execution data.

- Allowlisted senders proceed; `technicien` is taken from the allowlist name (stable, not the free-form Telegram first name) and `role` is written to the Sheet so boss-specific behavior can branch on it later.
- Unknown senders get **exactly one** automated HR-contact reply per chat (tracked in workflow static data), then are dropped silently.

## 6. Sheets append + flag_review

The reception workflows append the full row to the `Rapports` tab (date, heure, technicien, role, all extracted fields, rapport_complet, confidence, `flag_review`, lien_audio). `flag_review` is `true` when the API returned `low_confidence_transcription` or `short_transcription` — the dashboard's review queue filters on it. Replace `REPLACE_WITH_SPREADSHEET_ID` and attach a Google Sheets credential.

## 7. Error workflow

Import [`error-workflow.json`](./error-workflow.json), then in each production workflow: **Settings → Error Workflow → "Error handler -> POST /logs"**. Any failed execution posts `stage: workflow_error` to the API with the workflow name, failing node and execution URL, and shows up in the dashboard's **Logs n8n** panel.

It writes to Postgres, **not** the Sheet: an error handler that reports through Google Sheets cannot report the failure of writing to Google Sheets.

## 7b. Pipeline logs (dashboard "Logs n8n" panel)

`docker compose up -d postgres` starts the log store. The API creates its tables at startup; if `DATABASE_URL` is unset the API still runs and prints `[logs] DISABLED — ...` (the pipeline never stops because observability is down).

Add to `.env` at the repo root:

```bash
DATABASE_URL=postgresql://pfe:pfe@localhost:5432/pfe_logs
API_BASE_URL=http://host.docker.internal:8000   # how the n8n container reaches the host API
# optional overrides, must match DATABASE_URL
POSTGRES_USER=pfe
POSTGRES_PASSWORD=pfe
POSTGRES_DB=pfe_logs
```

The unified workflow posts one row per stage (`received → authorized → transcribed → extracted → replied → sheet_written`), plus `denied`, `duplicate`, `sheet_failed` and `api`. Every row carries a `correlation_id` minted by the **Correlate** node, so the n8n stages and the API's own errors — two separate processes — join into one timeline in the dashboard.

Retention is 30 days, swept by the maintenance workflow.

## 7c. Reply-first + Sheet retry queue

**The Sheet write no longer blocks the technician's reply.** The chain is now `Process output → reply → Log replied → Append Sheet row`. When the append fails, the report is parked in the `failed_writes` table (`POST /sheet-queue`) instead of being lost, and the technician still receives their summary.

Import [`maintenance-cron.json`](./maintenance-cron.json): every 5 min it drains the retry queue back into the `Rapports` tab, and daily at 03:00 it prunes logs older than 30 days. Replace `REPLACE_WITH_SPREADSHEET_ID` and attach the Google credential, same as the reception workflow.

Idempotency: **Claim message (dedup)** calls `POST /logs/claim` before processing. Meta retries the WhatsApp webhook when it does not get a fast 200 — without the claim that means duplicate Sheet rows, duplicate replies and duplicate free-tier quota burn. If the claim store is unreachable the message is treated as fresh (a rare duplicate beats a silently dropped report).

## 8. WhatsApp reception (second input channel)

[`whatsapp-reception.json`](./whatsapp-reception.json) mirrors the Telegram pipeline on the WhatsApp Cloud API — same access control, same `/process` call, same Sheet row, so both channels coexist. Setup:

Uses n8n's **native WhatsApp nodes** — two credentials:

1. **WhatsApp OAuth** (for the *WhatsApp Trigger* node): App ID + App Secret — developers.facebook.com → your app → *App settings → Basic*. The trigger handles the webhook verify handshake AND validates Meta's `X-Hub-Signature-256` payload signatures automatically.
2. **WhatsApp API** (for the *WhatsApp Business Cloud* send/media nodes): Access token + Business Account ID (WABA ID, from *WhatsApp → API Setup*). ⚠️ Test-mode temporary tokens expire in 24h — generate a durable one via *Business settings → System users → Generate token* (`whatsapp_business_messaging` + `whatsapp_business_management` scopes).
3. **Env**: `WHATSAPP_PHONE_NUMBER_ID=...` in `.env` (compose passes it to the container; send nodes read `$env.WHATSAPP_PHONE_NUMBER_ID`). `WHATSAPP_VERIFY_TOKEN` no longer needed — the trigger node manages verification itself.
4. Activate the workflow, then in Meta dashboard → *WhatsApp → Configuration → Webhook* paste the trigger's production webhook URL + verify string (the trigger node displays both) and subscribe to the `messages` field.
5. Test-mode limits: recipient allowlist of 5 numbers; recipients must first message the number or be added in API Setup.

Voice notes and forwarded audio both arrive as `type: "audio"` → treated identically. If an imported WhatsApp node shows a red parameter, re-pick the operation in its dropdown (n8n version drift) — the flow is: media *Get URL* → media *Download* → `/process`.

## 9. End-of-day report cron

Import [`daily-report-cron.json`](./daily-report-cron.json): Mon–Sat 18:30 → reads today's `Rapports` rows → `POST /daily-report` (Gemini→Groq rollup, see `api/app/daily_report.py`) → Gmail to the manager. Zero rows today = the run ends quietly, no email. `.docx` attachment remains a stretch goal.
