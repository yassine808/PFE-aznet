# n8n — orchestration layer

Role (per PLAN.md): **Telegram** reception → voice download → call FastAPI `/process` → append Google Sheets row → email notification → Telegram confirmation reply.

> Channel note: reception is channel-agnostic. The API (`/process`) only ever sees an audio blob — it has no idea the channel is Telegram. WhatsApp Business API is the documented production-evolution path; Telegram carries the pilot + defense demo (free, no approval, no recipient cap, no token expiry). See PLAN.md §1.

Workflow exports (`*.json`) live here — export after every meaningful change (n8n UI → workflow menu → Download).

Two import-ready variants:
- [`telegram-reception-polling.json`](./telegram-reception-polling.json) — **current dev approach.** Polls `getUpdates` every 15s; outbound-only so plain `localhost` works — no tunnel, no public URL. Paste the bot token in the "Offset + token" Code node + a Telegram credential on "Get Voice File", toggle Active. If `getUpdates` returns 409, clear a leftover webhook once via `https://api.telegram.org/bot<TOKEN>/deleteWebhook`.
- [`telegram-reception.json`](./telegram-reception.json) — webhook variant (needs the public HTTPS tunnel below; n8n's built-in `start --tunnel` is dead in n8n 2.x — use cloudflared). Pilot/server target.

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

**Cloudflare quick tunnel (recommended)**
```bash
winget install Cloudflare.cloudflared          # once
cloudflared tunnel --url http://localhost:5678
```
Gives `https://<words>.trycloudflare.com`. Put it in `.env` as `WEBHOOK_URL` (with trailing `/`), then `docker compose up -d` to restart so n8n adopts it.

> Why WEBHOOK_URL matters: when you **activate** a workflow, n8n calls Telegram's `setWebhook` for you, pointing Telegram at `WEBHOOK_URL` + the trigger's path. Set the tunnel URL *before* activating, or Telegram gets told to deliver to `localhost` and nothing arrives. The URL changes each `cloudflared` run → update `.env` and re-activate the workflow (fine for dev; pilot gets a stable server URL).

**Alternative — n8n built-in tunnel:** uncomment `command: start --tunnel` in `docker-compose.yml`, restart. Prints a `*.hooks.n8n.cloud` HTTPS URL n8n uses automatically. Dev only.

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
