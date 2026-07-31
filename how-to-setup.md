# How to Set Up the Project on a New PC

Step-by-step guide to get the full pipeline running from a fresh machine.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Clone & first boot](#2-clone--first-boot)
3. [API keys — where to get each one](#3-api-keys--where-to-get-each-one)
4. [Telegram bot](#4-telegram-bot)
5. [WhatsApp (Meta Cloud API)](#5-whatsapp-meta-cloud-api)
6. [Google Sheets (service account)](#6-google-sheets-service-account)
7. [PostgreSQL database](#7-postgresql-database)
8. [n8n workflows — import & configure](#8-n8n-workflows--import--configure)
9. [Dashboard](#9-dashboard)
10. [Smoke test](#10-smoke-test)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Prerequisites

| Tool | Why | Get it |
|------|-----|--------|
| **Docker Desktop** | Runs n8n, Postgres, and optionally the API | <https://docs.docker.com/desktop/> |
| **Python 3.9** | Runs the AI microservice locally (dev mode) | <https://www.python.org/downloads/release/python-3913/> |
| **Node.js 18+** | Runs the dashboard dev server | <https://nodejs.org/> |
| **Git** | Clone the repo | <https://git-scm.com/> |
| **Tailscale** (optional) | Public HTTPS tunnel for WhatsApp webhooks | <https://tailscale.com/download> |

Check that everything is installed:

```bash
docker --version
python --version        # must be 3.9.x
node --version          # >= 18
git --version
```

---

## 2. Clone & first boot

```bash
git clone <repo-url> pfe-aznet
cd pfe-aznet
```

Copy the env template and start the stack:

```bash
cp .env.example .env
docker compose up -d          # starts postgres + n8n on :5678
```

> The `api` service is commented out by default in compose — in dev you run it on the host for hot-reload. To include it: `docker compose up -d --build`.

Open the n8n UI: <http://localhost:5678>

---

## 3. API keys — where to get each one

Edit `.env` at the repo root. **Never commit this file.**

### 3a. Groq (STT + text extraction primary)

**Used for:** Transcribing Darija voice notes (Whisper-large-v3) + structured JSON extraction primary (gpt-oss-120b).

| Step | What to do |
|------|-----------|
| 1 | Go to <https://console.groq.com> |
| 2 | Log in with Google/GitHub |
| 3 | Click **API Keys** in the left sidebar |
| 4 | Click **Create API Key**, give it a name like `pfe-aznet` |
| 5 | Copy the key starting with `gsk_...` |
| 6 | Paste into `.env`: `GROQ_API_KEY=gsk_...` |

**Free tier:** 30 req/min on Whisper-large-v3, 30 req/min on gpt-oss-120b — more than enough for a pilot.

---

### 3b. Gemini (LLM fallback + STT candidate)

**Used for:** Structured JSON extraction (fallback in the text chain) + Darija audio transcription (benchmark).

| Step | What to do |
|------|-----------|
| 1 | Go to <https://aistudio.google.com> |
| 2 | Log in with a Google account |
| 3 | Click **Get API Key** in the left sidebar |
| 4 | Click **Create API Key** — pick an existing GCP project or create one |
| 5 | Copy the key starting with `AIza...` or `AQ.` |
| 6 | Paste into `.env`: `GEMINI_API_KEY=AIza...` |

**Free tier:** flash-lite (the extraction fallback) has 1500 req/day free — plenty. The bigger flash models are quota-limited on the free tier (the 2026-07-27 benchmark saw gemini-3.6-flash 503 after a few calls), which is why they sit at the end of the chains.

---

### 3c. HuggingFace (optional, STT benchmark only)

**Used for:** Running the Darija fine-tune benchmark (week 1 benchmark, not needed for the pipeline).

| Step | What to do |
|------|-----------|
| 1 | Go to <https://huggingface.co/settings/tokens> |
| 2 | Click **New token**, give it a name, role `read` |
| 3 | Copy the token |
| 4 | Paste into `.env`: `HF_TOKEN=hf_...` |

**Can skip** if not running the benchmark.

---

### 3d. Telegram bot token

See §4 below. Token looks like `<TELEGRAM_BOT_TOKEN>`.

Paste into `.env`:

```
TELEGRAM_BOT_TOKEN=<TELEGRAM_BOT_TOKEN>
```

---

### 3e. WhatsApp (Meta) credentials

See §5 below. Two items go in `.env`:

```
WHATSAPP_PHONE_NUMBER_ID=<number from Meta dashboard>
WEBHOOK_URL=https://<your-tunnel-url>/    # trailing slash is important
```

---

### 3f. Google Sheets service account

See §6 below. The JSON file itself is not an env var — you download it and place it at:

```
credentials/service-account.json
```

Then in `.env`:

```
GOOGLE_SERVICE_ACCOUNT_JSON=./credentials/service-account.json
SHEET_ID=<GOOGLE_SHEET_ID>
```

---

### 3g. SMTP (email notifications, optional)

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASS=<app password, not your regular password>
NOTIF_RECIPIENTS=manager@example.com,supervisor@example.com
```

**Gmail app password:** <https://myaccount.google.com/apppasswords> (requires 2FA enabled). Click "Select app" → Other → name it `aznet` → copy the 16-char password.

**Can skip** — the pipeline works without email; only the end-of-day cron fails.

---

## 4. Telegram bot

### 4.1 Create the bot

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Give it a **display name** (e.g. `AZNET Rapports`)
4. Give it a **username ending in `bot`** (e.g. `aznet_rapports_bot`)
5. BotFather replies with a token like `<TELEGRAM_BOT_TOKEN>`
6. Copy the token into `.env` as `TELEGRAM_BOT_TOKEN=...`

### 4.2 Find your Telegram user ID

1. Search for **@userinfobot** on Telegram
2. Start it, send any message
3. It replies with your numeric ID (e.g. `<TELEGRAM_USER_ID>`)

### 4.3 Add yourself to the access control list

After importing the workflow (see §8), edit the **Access control** Code node. Find the `ALLOWLIST` object and add your ID:

```javascript
const ALLOWLIST = {
  '<TELEGRAM_USER_ID>': { name: 'Yassine', role: 'directeur' },
  // add more technicians here
}
```

### 4.4 Create the n8n Telegram credential

1. n8n UI → **Credentials** → **Add**
2. Pick **Telegram API**
3. Name: `Telegram account`
4. Paste the same bot token
5. **Save**

### 4.5 Polling note

The unified workflow uses **polling** (`getUpdates` every 15s), not webhooks. This means:
- No tunnel needed for Telegram
- Only ONE active workflow may poll the same bot token
- If you get error 409: go to `https://api.telegram.org/bot<TOKEN>/deleteWebhook` in a browser once

---

## 5. WhatsApp (Meta Cloud API)

This is optional — Telegram alone is enough for the PFE. WhatsApp adds a second reception channel.

### 5.1 Create a Meta app

1. Go to <https://developers.facebook.com/>
2. Click **My Apps** → **Create App**
3. Pick **Business** → **Next**
4. Name: `AZNET PFE` → **Create App**
5. In the dashboard, find the **WhatsApp** use case → **Set up**

### 5.2 Collect credentials

| Item | Where to find it |
|------|-----------------|
| **App ID** | App dashboard → **Settings → Basic** (top of page) |
| **App Secret** | Same page, click **Show** |
| **Phone Number ID** | WhatsApp → **API Setup** (formerly "Step 1. Try it out") |
| **WABA ID** (Business Account ID) | Same page, just above the phone number |
| **Temporary Access Token** | Same page — expires in 24h |

### 5.3 Generate a durable token (optional but recommended)

1. Go to <https://business.facebook.com/>
2. Top right → **Business settings** (gear icon)
3. **Users → System users**
4. **Add** → name: `aznet-bot`, role: **Admin**
5. In the new user row, click **Assign assets**
6. Select your app and the WhatsApp account
7. Click **Generate token** → scopes: `whatsapp_business_messaging` + `whatsapp_business_management`
8. Copy the token (starts with `EAA...`)

### 5.4 Create n8n credentials

Two separate credentials:

**Credential 1 — WhatsApp OAuth** (for the WhatsApp Trigger node):
- Type: **WhatsApp OAuth**
- Client ID = App ID
- Client Secret = App Secret

**Credential 2 — WhatsApp API** (for send/media nodes):
- Type: **WhatsApp Business Cloud API**
- Access Token = durable token from step 5.3
- Business Account ID = WABA ID

### 5.5 Set up the tunnel

WhatsApp needs a public HTTPS URL. Use Tailscale Funnel:

```bash
tailscale funnel --bg 5678
tailscale funnel status
# → https://<machine>.<tailnet>.ts.net -> 127.0.0.1:5678
```

Set in `.env`:

```
WEBHOOK_URL=https://<machine>.<tailnet>.ts.net/
```

Then restart compose: `docker compose up -d`.

### 5.6 Register the webhook with Meta

1. In n8n, open the **WhatsApp Trigger** node
2. Copy the **Production webhook URL** and **Verify token** from the node
3. Go to Meta dashboard → WhatsApp → **Configuration** → **Webhook**
4. Paste both → **Verify and save**
5. Subscribe to the **messages** field

---

## 6. Google Sheets (service account)

### 6.1 Create or find the Sheet

The Sheet URL is: <https://docs.google.com/spreadsheets/d/<GOOGLE_SHEET_ID>>

If you're recreating it:

1. Create a new Google Sheet
2. Rename the first tab to **`Rapports`**
3. In cell A1 paste this header row:

```
date, heure, canal, technicien, role, chantier, client, type_activite, goulottes_m, cables_m, bureaux_termines, panneaux_raccordes, autres_travaux, observations, resume, rapport_complet, confidence, flag_review, lien_audio
```

4. Select row 1 → **Data → Split text to columns** (separator: comma)
5. Optionally add a second tab named `Errors` with header: `timestamp, workflow, node, message, execution_url`
6. Copy the Sheet ID from the URL: `https://docs.google.com/spreadsheets/d/<THIS_IS_THE_ID>/edit`
7. Set in `.env`: `SHEET_ID=the_id`

### 6.2 Create a Google Cloud service account

1. Go to <https://console.cloud.google.com/>
2. Create a project or select existing → name: `pfe-aznet`
3. Click **Enable APIs & Services** → search for **Google Sheets API** → **Enable**
4. Go to **IAM & Admin** → **Service Accounts**
5. Click **Create Service Account** → name: `n8n-sheets` → **Create and Continue**
6. Skip adding roles for now → **Done**
7. In the list, find `n8n-sheets` → click the email
8. Go to **Keys** tab → **Add Key** → **Create New Key** → **JSON**
9. A file downloads automatically — **save it as `credentials/service-account.json`** in the project

### 6.3 Share the Sheet with the service account

1. Open the Google Sheet
2. Click **Share** (top right)
3. Paste the service account email: `<SERVICE_ACCOUNT_EMAIL>`
4. Role: **Editor**
5. Uncheck "Notify people" → **Share**

> **Skipping this step = 403 Forbidden on every Sheet append.** This is the most common setup mistake.

### 6.4 Create the n8n Google credential

1. n8n → **Credentials** → **Add**
2. Pick **Google Service Account API**
3. Name: `Google Sheets`
4. **Service Account Email:** `<SERVICE_ACCOUNT_EMAIL>`
5. **Private Key:** open `credentials/service-account.json`, copy the full `private_key` value (starts with `-----BEGIN PRIVATE KEY-----\n...`)
6. Paste it **as-is** (with the `\n` characters, they are actual newlines), **Fixed** mode (not Expression)
7. **Save**

---

## 7. PostgreSQL database

### 7.1 Start Postgres

```bash
docker compose up -d postgres
```

This starts PostgreSQL on port 5432 with:
- User: `pfe`
- Password: `pfe`
- Database: `pfe_logs`

### 7.2 Set DATABASE_URL in .env

```
DATABASE_URL=postgresql://pfe:pfe@localhost:5432/pfe_logs
```

The API creates the tables automatically on startup (`logs.init_schema()`). If Postgres is unreachable, the API logs `[logs] DISABLED` and keeps serving — the pipeline never breaks because observability is down.

### 7.3 (Optional) Verify

```bash
docker exec -it pfe-postgres psql -U pfe -d pfe_logs -c "\dt"
```

Should show: `pipeline_logs`, `processed_messages`, `failed_writes`, `technicians`, `service_samples`.

---

## 8. n8n workflows — import & configure

### 8.1 Import the complete workflow

The recommended approach: import the merged file.

1. n8n UI → **Workflows** → **Add Workflow**
2. Click the three dots (`···`) → **Import from File**
3. Pick **`n8n/aznet-complete.json`**
4. The editor shows two labelled bands (Réception, Gestionnaire d'erreurs) — the maintenance and daily/weekly report bands moved to the API scheduler (`api/app/jobs.py`)

### 8.2 Configure credentials

After import, every credential shows a red warning. Click each one and re-select:

| Node type | Credential to attach |
|-----------|---------------------|
| Telegram Trigger / TG nodes | The Telegram API credential from §4.4 |
| WhatsApp Trigger | WhatsApp OAuth from §5.4 |
| WA send/media nodes | WhatsApp Business Cloud API from §5.4 |
| Google Sheets nodes | Google Service Account from §6.4 |
| Gmail nodes | Gmail OAuth (see §8.5) |

### 8.3 Set the error workflow

1. Open workflow **Settings** (tab below the canvas)
2. **Error Workflow** → select the same workflow
3. A workflow can be its own error handler

### 8.4 Set the Sheet ID

In the **Append Sheet row** nodes, the spreadsheet ID should be pre-filled. If you created a new Sheet, update it:
- Open the Sheets node
- Click **Select** next to "Document" → pick your Sheet
- Click **Select** next to "Sheet" → pick `Rapports`

Also update the **Read Rapports sheet** node in the daily-report band.

### 8.5 Gmail credential (for daily-report email)

1. n8n → **Credentials** → **Add** → **Gmail OAuth2**
2. Follow n8n's OAuth flow — you'll sign in with the sending Gmail account
3. Attach this credential to the **Email manager** node

Update the recipient email:
- Find the **Email manager** node
- Change `sendTo` to the manager's actual email

### 8.6 Edit the access control list

Find the **Access control** Code node. Edit the `ALLOWLIST` object:

```javascript
const ALLOWLIST = {
  '<TELEGRAM_USER_ID>': { name: 'Admin', role: 'directeur' },
  // '2126xxxxxxxx': { name: 'Technicien', role: 'technicien' },  // WhatsApp number
  // '123456789': { name: 'Autre', role: 'technicien' },          // Telegram user ID
}
```

To find a WhatsApp sender's ID: ask them to message the bot number once, then look in n8n execution data for `entry[0].changes[0].value.messages[0].from`.

### 8.7 Activate

Click **Active** toggle (top right). The workflow starts:
- Polling Telegram every 15s
- Listening for WhatsApp webhooks
- If you see 409 on Telegram: run `deleteWebhook` once (see §4.5)

---

## 9. Dashboard

### 9.1 Seed the technician directory

The dashboard needs a Postgres table with technician info for the access control page. This happens automatically when the API starts (if Postgres is reachable).

### 9.2 Start the dashboard dev server

```bash
cd Dashboard
npm install
npm run dev
```

Opens on <http://localhost:5173> — proxies `/api` to FastAPI on :8000 and `/n8n` to n8n on :5678.

### 9.3 Dashboard .env file

`Dashboard/.env` is already configured for local dev:

```
N8N_URL=http://127.0.0.1:5678
N8N_API_KEY=<n8n API key from docker n8n>
N8N_WORKFLOW_MATCH=reception
```

To get the **n8n API key**:
1. n8n UI → **Settings** → **API**
2. Copy the key or generate one
3. Paste into `Dashboard/.env`

### 9.4 Build for production (Vercel)

```bash
cd Dashboard
npm run build
```

The static build goes to `Dashboard/dist/`. To deploy on Vercel:
- Import the `Dashboard/` directory as a new project
- Set environment variables in Vercel dashboard (not `.env`)
- The `/api` proxy won't work from Vercel — you'll need to point directly at the API URL

---

## 10. Smoke test

### 10.1 Check the API

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status":"ok","version":"0.1.0","uptime_seconds":42.0,"stt_providers":["gemini","groq","hf-darija"],"stt_default":"groq"}
```

### 10.2 Send a Telegram voice note

1. Open the bot chat on Telegram
2. Record and send a voice note (hold mic icon, speak, release)
3. Within ~15s you should see an execution in n8n
4. The bot replies with a French summary
5. A row appears in the Google Sheet

### 10.3 Send a typed text report

Same bot, but type a message instead of a voice note:
```
chantier oulad hadj, client AKDITAL, tirsaa 3 goulottes o 50 metre dial cable, 2 bureaux termines o 1 panneau raccorde, wahd l'probleme f-matériel hadi n9ssin l-brassage
```

### 10.4 Test the dashboard

1. Open <http://localhost:5173>
2. The Overview page shows metrics, recent reports, service status
3. The Inbox page shows individual reports with editable fields
4. The Access Control page lets you add/remove technicians

### 10.5 Test access control

1. Find a Telegram user ID that is NOT in the ALLOWLIST
2. Send a voice note from that account
3. The workflow sends exactly one "contact HR" reply
4. Nothing is written to the Sheet
5. The log shows stage `denied`

---

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `[logs] DISABLED` on API startup | Postgres not running or `DATABASE_URL` wrong | `docker compose up -d postgres`, check `.env` |
| n8n Code node says "access to env vars denied" | `N8N_BLOCK_ENV_ACCESS_IN_NODE=true` | Set to `false` in `docker-compose.yml`, restart container |
| Telegram 409 Conflict | Old webhook registered | Visit `https://api.telegram.org/bot<TOKEN>/deleteWebhook` |
| Sheets append 403 | Sheet not shared with service account | Share the Sheet with the service account email as Editor |
| "Node does not have any credentials set" | Credential IDs from original machine | Re-attach credentials in n8n UI (see §8.2) |
| WhatsApp webhook verification fails | No public tunnel URL | `tailscale funnel --bg 5678`, set `WEBHOOK_URL`, re-register |
| WhatsApp "Invalid parameter" on activate | No `WEBHOOK_URL` set | Deactivate the WhatsApp Trigger node until tunnel is up |
| Workflow error on `/process` 502 | API not running or unreachable | Check `API_BASE_URL` in `.env`, `curl localhost:8000/health` |
| `getUpdates` returns empty, no execution | Workflow not activated OR two workflows polling same token | Activate only ONE workflow; check n8n executions page |
| Dashboard shows "API unreachable" | FastAPI not running on :8000 | `docker compose up -d api` or start uvicorn manually |
| Dashboard n8n status shows no workflows | n8n API key wrong or n8n not running | Check `N8N_API_KEY` in `Dashboard/.env`, `curl localhost:5678` |
| Gemini extraction returns empty | Safety filter blocked content | Check the model response in logs; retry with different phrasing |
| SMTP email not sending | Gmail requires app password, not regular password | Generate app password at <https://myaccount.google.com/apppasswords> |
| Arabic text garbled in Sheet | Sheets encoding | Should work; if not, check service account region settings |
| Docker containers restart in loop | Port conflict (5432, 5678, 8000 already in use) | `netstat -ano | findstr :5432` to find the process, stop it |
| `pairedItem` warnings in n8n | Version drift in `$Node.item` references | Update expressions to use `$json.*` directly where possible |
