# n8n — orchestration layer

Role (per PLAN.md): WhatsApp reception → media download → call FastAPI `/process` → append Google Sheets row → email notification → WhatsApp confirmation reply.

Workflow exports (`*.json`) live here — export after every meaningful change (n8n UI → workflow menu → Download).

## Run

```bash
docker compose up -d     # from repo root → http://localhost:5678
```

## Exposing webhooks to Meta (dev)

Meta needs a public **HTTPS** URL to deliver WhatsApp events. Two free options:

**Option 1 — n8n built-in tunnel (fastest first test)**
Uncomment `command: start --tunnel` in `docker-compose.yml`, restart. n8n prints a public `*.hooks.n8n.cloud` URL. Dev only, not for pilot.

**Option 2 — Cloudflare quick tunnel**
```bash
winget install Cloudflare.cloudflared
cloudflared tunnel --url http://localhost:5678
```
Gives a random `https://<words>.trycloudflare.com` URL. Set it as `WEBHOOK_URL` in `.env`, restart compose. URL changes each run → re-paste in Meta app webhook config (fine during dev; pilot gets a stable server URL).

## WhatsApp webhook smoke test (Week 0 exit criterion)

1. Meta developer app → WhatsApp → API Setup: note test number, `META_ACCESS_TOKEN`, `META_PHONE_NUMBER_ID`; register your own phone among the 5 allowed recipients.
2. n8n: new workflow → **WhatsApp Trigger** node → paste callback URL + `WHATSAPP_VERIFY_TOKEN` into Meta webhook config → subscribe to `messages`.
3. Send a voice note from your registered phone to the test number.
4. PASS = execution appears in n8n with a media ID for the audio. That's the whole risk-kill.
