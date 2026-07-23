---
tags: [pfe, n8n, workflows, telegram, google-sheets, email]
type: technical
priority: high
status: current
---

# n8n Workflows

## Overview

Three workflows handle the three input channels. All converge on the same API → Sheets → Notification path.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Telegram   │     │   Web Form  │     │  Manual     │
│  (Polling)  │     │  (Webhook)  │     │  (Webhook)  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
              ┌────────────────────────┐
              │     API /process       │
              │  (STT → Extraction)    │
              └───────────┬────────────┘
                          │
              ┌───────────┼────────────┐
              ▼           ▼            ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │  Sheets  │ │  Email   │ │  Slack   │
       │  Append  │ │ Manager  │ │  Alert   │
       └──────────┘ └──────────┘ └──────────┘
```

---

## Workflow 1: Telegram Polling (Development)

**File:** `n8n/workflows/telegram-polling.json`  
**Trigger:** Cron (every 30s) → Telegram API `getUpdates`

### Nodes

| Node | Type | Purpose |
|------|------|---------|
| `Cron` | Cron | Poll every 30 seconds |
| `Telegram Get Updates` | HTTP Request | `GET /bot<token>/getUpdates?offset={{$json.last_update_id + 1}}` |
| `Filter Voice` | IF | `{{$json.message.voice || $json.message.audio}}` |
| `Download File` | HTTP Request | `GET /bot<token>/getFile?file_id={{$json.voice.file_id}}` → `GET /file/bot<token>/{{$json.result.file_path}}` |
| `Extract Metadata` | Function | Parse `message.from`, `message.date`, `message.caption` |
| `Encode Audio` | Function | Base64 encode audio buffer |
| `Call API` | HTTP Request | `POST {{API_URL}}/process` with audio + metadata |
| `Parse Response` | Function | Extract `ExtractedReport` from API response |
| `Sheets Append` | Google Sheets | Append row with all fields |
| `Email Manager` | Send Email | Gmail SMTP to manager |
| `Error Handler` | Error Trigger | Catch failures → Slack/Email alert |

### Key Function: Extract Metadata

```javascript
// Extract Metadata node
const msg = items[0].json.message;
const user = msg.from;

return {
  audio_base64: $json.audio_base64,
  metadata: {
    date: new Date(msg.date * 1000).toISOString().split('T')[0],
    technicien: msg.caption || user.first_name || user.username || "Inconnu",
    lien_audio: `https://api.telegram.org/file/bot${$credentials.telegramApi.token}/${$json.file_path}`,
    telegram_message_id: msg.message_id,
    telegram_user_id: user.id
  }
};
```

### Key Function: Parse Response

```javascript
// Parse API Response
const apiResponse = items[0].json;
const extracted = apiResponse.extracted_report;
const meta = $json.metadata;

return {
  // Google Sheets row
  date: meta.date,
  technicien: extracted.technicien || meta.technicien,
  chantier: extracted.chantier || "",
  type_travail: extracted.type_travail || "",
  goulottes_m: extracted.goulottes_m || "",
  cables_tires: extracted.cables_tires || "",
  equipements_poses: extracted.equipements_poses || "",
  problemes: JSON.stringify(extracted.problemes || []),
  observations: extracted.observations || "",
  resume: extracted.resume || "",
  lien_audio: meta.lien_audio,
  stt_confidence_low: extracted.stt_confidence_low || false,
  extraction_confidence: extracted.extraction_confidence || "medium",
  telegram_message_id: meta.telegram_message_id,
  created_at: new Date().toISOString()
};
```

---

## Workflow 2: Telegram Webhook (Pilot/Production)

**File:** `n8n/workflows/telegram-webhook.json`  
**Trigger:** Webhook `POST /webhook/telegram`

### Differences from Polling

| Aspect | Polling | Webhook |
|--------|---------|---------|
| Trigger | Cron (30s) | Telegram POST |
| Latency | ~30s avg | <1s |
| Reliability | High (no public URL needed) | Needs HTTPS, domain |
| Setup | Simple | ngrok (dev) / VPS (prod) |

### Webhook Verification

```javascript
// Verify Telegram secret token
const secret = $credentials.telegramWebhook.secretToken;
const header = $request.headers["x-telegram-bot-api-secret-token"];

if (header !== secret) {
  throw new Error("Invalid webhook secret");
}
```

### Telegram Webhook Setup

```bash
# Development (ngrok)
ngrok http 5678
# → https://abc123.ngrok-free.app/webhook/telegram

curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://abc123.ngrok-free.app/webhook/telegram", "secret_token": "your-secret"}'

# Production (VPS)
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -d '{"url": "https://n8n.aznet.ma/webhook/telegram", "secret_token": "prod-secret"}'
```

---

## Workflow 3: Web Form (Manual Entry)

**File:** `n8n/workflows/web-form.json`  
**Trigger:** Webhook `POST /webhook/report`

### Input Schema

```json
{
  "text": "Transcribed text from technician...",
  "metadata": {
    "date": "2026-07-23",
    "technicien": "Ahmed",
    "chantier": "Hay Riad",
    "lien_audio": ""
  }
}
```

### Flow
1. Webhook receives JSON
2. Validate required fields (`text`, `metadata.date`, `metadata.technicien`)
3. Call API `/process` with `text` mode
4. Same Sheets → Email → Slack path

---

## Google Sheets Integration

### Sheet Structure

**Spreadsheet:** `Rapports Quotidiens - PFE`  
**Worksheet:** `Rapports`  
**Columns:** (A→R)

| Col | Field | Source |
|-----|-------|--------|
| A | Date | metadata.date |
| B | Technicien | extracted.technicien ∥ metadata.technicien |
| C | Chantier | extracted.chantier |
| D | Type Travail | extracted.type_travail |
| E | Goulottes (m) | extracted.goulottes_m |
| F | Câbles Tirés | extracted.cables_tires |
| G | Équipements Posés | extracted.equipements_poses |
| H | Problèmes | extracted.problemes (JSON) |
| I | Observations | extracted.observations |
| J | Résumé | extracted.resume |
| K | Lien Audio | metadata.lien_audio |
| L | STT Confidence Low | extracted.stt_confidence_low |
| M | Extraction Confidence | extracted.extraction_confidence |
| N | Telegram Msg ID | metadata.telegram_message_id |
| O | Created At | n8n execution timestamp |
| P | Source | "telegram" ∥ "webform" |
| Q | Status | "ok" ∥ "warning" ∥ "error" |
| R | Error Details | (if error) |

### n8n Google Sheets Node Config

- **Operation:** Append
- **Range:** `Rapports!A:R`
- **Value Input Mode:** `USER_ENTERED` (preserves dates/numbers)
- **Credentials:** Service Account (JSON key)

### Service Account Setup

1. Google Cloud Console → IAM → Service Accounts
2. Create → `pfe-sheets-writer`
3. Grant: `Sheets API` → Editor (or custom role: `spreadsheets.values.append`)
4. Download JSON → Save as `credentials/sheets-service-account.json`
5. Share target spreadsheet with service account email

---

## Email Notifications

### Gmail SMTP Config (n8n Credentials)

| Field | Value |
|-------|-------|
| Host | `smtp.gmail.com` |
| Port | `587` |
| Security | `STARTTLS` |
| User | `your-email@gmail.com` |
| Password | App Password (not main password) |

### Email Template

**Subject:** `[PFE] Nouveau rapport - {{ $json.technicien }} - {{ $json.date }}`

**Body:**
```
Nouveau rapport d'intervention reçu.

Technicien: {{ $json.technicien }}
Date: {{ $json.date }}
Chantier: {{ $json.chantier }}
Type: {{ $json.type_travail }}

Goulottes: {{ $json.goulottes_m }} m
Câbles tirés: {{ $json.cables_tires }}
Équipements posés: {{ $json.equipements_poses }}

Problèmes:
{{#each $json.problemes}}
- {{this}}
{{/each}}

Observations: {{ $json.observations }}

Résumé:
{{ $json.resume }}

---
Lien audio: {{ $json.lien_audio }}
Confiance STT: {{ $json.stt_confidence_low ? "FAIBLE" : "OK" }}
Confiance extraction: {{ $json.extraction_confidence }}
Source: {{ $json.source }}
```

---

## Error Handling & Alerts

### Dead Letter Flow

Failed executions → Separate workflow `error-handler.json`:

1. **Error Trigger** catches all workflow errors
2. **Classify Error**:
   - API 502 → Retryable (STT/Extraction failure)
   - API 422 → Data issue (bad input)
   - Sheets 403 → Credentials/permission
   - Email 5xx → Transient
3. **Log to Error Sheet** (separate tab `Erreurs`)
4. **Alert Manager**:
   - Slack webhook (critical)
   - Email (all errors)
   - Telegram to admin (critical)

### Error Sheet Columns

| Field | Description |
|-------|-------------|
| Timestamp | Error time |
| Workflow | Which workflow failed |
| Node | Failing node name |
| Error Type | Classification |
| Error Message | Full error |
| Input Data | Sanitized input (no audio) |
| Retry Count | Auto-retry attempts |
| Resolved | Manual checkbox |

---

## Deployment

### Development (Docker Compose)

```yaml
# docker-compose.yml
services:
  n8n:
    image: n8nio/n8n:latest
    ports:
      - "5678:5678"
    environment:
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=admin
      - N8N_BASIC_AUTH_PASSWORD=changeme
      - WEBHOOK_URL=http://localhost:5678/
      - GENERIC_TIMEZONE=Africa/Casablanca
    volumes:
      - ./n8n/data:/home/node/.n8n
      - ./n8n/workflows:/home/node/.n8n/workflows
      - ./credentials:/home/node/.n8n/credentials
```

### Production (VPS)

- Docker on Ubuntu VPS
- Caddy reverse proxy (HTTPS auto)
- Persistent volumes for workflows/credentials
- systemd service for auto-restart
- Backup: daily workflow export to Git

---

## Testing Workflows

### Local Testing

```bash
# Start n8n
docker compose up -d

# Open editor
open http://localhost:5678

# Import workflows from n8n/workflows/
# Configure credentials
# Test with Telegram test bot
```

### Smoke Test Checklist

- [ ] Telegram polling receives message
- [ ] Audio downloads & base64 encodes
- [ ] API call succeeds (200)
- [ ] Sheets row appended correctly
- [ ] Email sent to manager
- [ ] Error flow triggers on API 500
- [ ] Webhook verification works
- [ ] Web form submission works

---

## Related Notes

- [[Project Overview]]
- [[Architecture]]
- [[API Endpoint]]
- [[Google Sheets Setup]]
- [[Deployment Guide]]