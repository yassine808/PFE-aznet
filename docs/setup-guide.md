# Setup Guide — Telegram + WhatsApp + n8n + API + Sheets

End-to-end setup of the reception pipeline. Written for a fresh machine, annotated with what was **actually done on 2026-07-23** (live pilot) — future me / anyone redeploying from zero. Every secret location is explicit. Previously two files (`docs/setup-guide.md` + `how-to-setup.md`); merged into this one.

```
Telegram (polling) ─┐
                    ├→ n8n "Reception unified" → FastAPI /process → Google Sheets → reply (same channel)
WhatsApp (webhook) ─┘
```

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
| **Docker Desktop** | Runs n8n, Postgres, the API and the web proxy | <https://docs.docker.com/desktop/> |
| **Python 3.11** | Runs the AI microservice locally (dev mode with hot reload) | <https://www.python.org/downloads/release/python-3119/> |
| **Node.js 18+** | Runs the dashboard dev server | <https://nodejs.org/> |
| **Git** | Clone the repo | <https://git-scm.com/> |
| **Tailscale** | Public HTTPS tunnel for WhatsApp webhooks (Tailscale Funnel) | <https://tailscale.com/download> |

Check that everything is installed:

```bash
docker --version
python --version        # must be 3.11.x
node --version          # >= 18
git --version
```

`.env` at the repo root (never committed) holds every secret: `TELEGRAM_BOT_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `WEBHOOK_URL`, `GOOGLE_SHEET_ID` + `SHEET_ID`, `HR_EMAIL`, `INTERNAL_API_KEY`, `DATABASE_URL`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `SMTP_*` (full list in §3, table in §3.8).

---

## 2. Clone & first boot

```bash
git clone <repo-url> pfe-aznet
cd pfe-aznet
```

Copy the env template and start the stack:

```bash
cp .env.example .env
docker compose up -d
```

This starts the **whole stack** — postgres, n8n, the API and the web proxy:

| Service | Container | Reachable at |
|---|---|---|
| n8n | `pfe-n8n` | <http://localhost:5678> |
| API (built from `api/Dockerfile`) | `pfe-api` | no published port — via the proxy at <http://localhost:8080/api> |
| Web proxy (dashboard + `/api` + `/webhook`) | `pfe-web` | <http://localhost:8080> |
| Postgres | `pfe-postgres` | no published port — only `api` reaches it as `postgres:5432` |

All `restart: unless-stopped` — the pipeline comes back on its own after a reboot.

> **Dev mode:** for hot reload run uvicorn on the host instead (`§2.1`) and set `API_BASE_URL=http://host.docker.internal:8000` so the n8n container reaches it. The compose default is `http://api:8000`.

### 2.1 Run the API on the host (dev)

```bash
cd api
.venv/Scripts/python.exe -m uvicorn app.main:app --reload   # :8000, hot reload
```

The container overrides two env values (`DATABASE_URL` → `postgres:5432`, `GOOGLE_SERVICE_ACCOUNT_JSON` → `/app/credentials/...`); on the host your `.env` values apply as written (`localhost:5432`, relative `./credentials/...`).

---

## 3. API keys — where to get each one

Edit `.env` at the repo root. **Never commit this file.**

### 3.1 Groq (STT + text extraction primary)

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

### 3.2 Gemini (LLM fallback + STT candidate)

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

### 3.3 HuggingFace (optional, STT benchmark only)

**Used for:** Running the Darija fine-tune benchmark (week 1 benchmark, not needed for the pipeline).

| Step | What to do |
|------|-----------|
| 1 | Go to <https://huggingface.co/settings/tokens> |
| 2 | Click **New token**, give it a name, role `read` |
| 3 | Copy the token |
| 4 | Paste into `.env`: `HF_TOKEN=hf_...` |

**Can skip** if not running the benchmark.

### 3.4 Telegram bot token

See §4 below. Token looks like `<TELEGRAM_BOT_TOKEN>`.

Paste into `.env`:

```
TELEGRAM_BOT_TOKEN=<TELEGRAM_BOT_TOKEN>
```

### 3.5 WhatsApp (Meta) credentials

See §5 below. Two items go in `.env`:

```
WHATSAPP_PHONE_NUMBER_ID=<number from Meta dashboard>
WEBHOOK_URL=https://<your-tunnel-url>/    # trailing slash is important
```

### 3.6 Google Sheets service account

See §6 below. The JSON file itself is not an env var — you download it and place it at:

```
credentials/service-account.json
```

Then in `.env`:

```
GOOGLE_SERVICE_ACCOUNT_JSON=./credentials/service-account.json
SHEET_ID=<GOOGLE_SHEET_ID>        # read by the API (sheets.py)
GOOGLE_SHEET_ID=<GOOGLE_SHEET_ID> # read by the n8n workflow ($env.GOOGLE_SHEET_ID)
HR_EMAIL=<email displayed to outsiders>  # read by the n8n HR-reply nodes
```

The Sheet ID and HR email are kept **out of the workflow JSON** on purpose (compose comment): the Sheet ID is effectively read access to every technician report if the document is link-shared, and the address is worth scraping — so the file can live in a public repo.

### 3.7 SMTP (email notifications, optional)

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASS=<app password, not your regular password>
NOTIF_RECIPIENTS=manager@example.com,supervisor@example.com
```

**Gmail app password:** <https://myaccount.google.com/apppasswords> (requires 2FA enabled). Click "Select app" → Other → name it `aznet` → copy the 16-char password.

**Can skip** — the pipeline works without email; only the daily/weekly report jobs fail.

### 3.8 `.env` reference

| Var | Consumer | Required |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | n8n (`$env`) | yes (Telegram channel) |
| `WHATSAPP_PHONE_NUMBER_ID` | n8n (`$env`, send nodes) | only for WhatsApp |
| `WEBHOOK_URL` | n8n (webhook registration) | yes — trailing `/` |
| `GROQ_API_KEY` | API | yes |
| `GEMINI_API_KEY` | API | yes (fallback chain) |
| `HF_TOKEN` | API (benchmark only) | no |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | API | yes |
| `SHEET_ID` | API (`sheets.py`) | yes |
| `GOOGLE_SHEET_ID` | n8n (`$env`) | yes |
| `HR_EMAIL` | n8n (`$env`, HR replies) | yes |
| `INTERNAL_API_KEY` | API + n8n (`X-API-Key`) | yes once auth is on |
| `DATABASE_URL` | API (logs, access control) | yes |
| `API_BASE_URL` | n8n → API | compose default `http://api:8000`; host-dev `http://host.docker.internal:8000` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` | API (mailer) | no (report emails) |
| `NOTIF_RECIPIENTS` | API (mailer) | no (report emails) |

---

## 4. Telegram bot

### 4.1 Create the bot

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Give it a **display name** (e.g. `AZNET Rapports`)
4. Give it a **username ending in `bot`** (e.g. `aznet_rapports_bot`)
5. BotFather replies with a token like `<TELEGRAM_BOT_TOKEN>`
6. Copy the token into `.env` as `TELEGRAM_BOT_TOKEN=...` — **never hardcode it in the workflow JSON** (the workflow's Code nodes read `$env.TELEGRAM_BOT_TOKEN`)

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
- Only ONE active workflow may poll the same bot token — two pollers steal each other's messages
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

### 5.3 Generate a durable token (recommended — never expires)

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

`.env`: `WHATSAPP_PHONE_NUMBER_ID=...` (send nodes read `$env.WHATSAPP_PHONE_NUMBER_ID`).

### 5.5 Set up the tunnel

WhatsApp needs a public HTTPS URL. Use Tailscale Funnel (n8n's built-in `start --tunnel` is dead in n8n 2.x):

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

The hostname is **stable**, so Meta is configured once and never again — unlike a cloudflared quick tunnel, whose URL changes on every run.

### 5.6 Register the webhook with Meta

1. In n8n, open the **WhatsApp Trigger** node
2. Copy the **Production webhook URL** and **Verify token** from the node
3. Go to Meta dashboard → WhatsApp → **Configuration** → **Webhook**
4. Paste both → **Verify and save**
5. Subscribe to the **messages** field

> **Until the tunnel is up:** keep the WhatsApp Trigger node deactivated (right-click → Deactivate node), otherwise workflow activation fails with "Bad request / Invalid parameter" (Meta rejects a localhost callback).

Test-mode limits: 5 recipient numbers max, each must message the test number first or be added in the API Setup page. Temp tokens die in 24h.

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
7. Set in `.env`: `SHEET_ID=the_id` **and** `GOOGLE_SHEET_ID=the_id` (API and n8n each read their own var, see §3.6)

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

Credentials (compose defaults, overridable in `.env`): user `pfe`, password `pfe`, database `pfe_logs`. The container publishes **no port** — only the `api` service reaches it as `postgres:5432`.

### 7.2 Set DATABASE_URL in .env

```
DATABASE_URL=postgresql://pfe:pfe@localhost:5432/pfe_logs
```

`localhost:5432` is for a **host-run uvicorn**; the compose `environment` block overrides it to `postgresql://pfe:pfe@postgres:5432/pfe_logs` inside the container, so both run modes work without editing `.env`.

The API creates the tables automatically on startup (`logs.init_schema()`). If Postgres is unreachable, the API logs `[logs] DISABLED` and keeps serving — the pipeline never breaks because observability is down.

### 7.3 (Optional) Verify

```bash
docker exec -it pfe-postgres psql -U pfe -d pfe_logs -c "\dt"
```

Should show: `pipeline_logs`, `processed_messages`, `failed_writes`, `persons`, `technicians`, `users`, `sessions`, `user_actions`, `page_visits`, `service_samples`, `app_settings`.

---

## 8. n8n workflows — import & configure

### 8.1 Import the complete workflow

The recommended approach: import the merged file.

1. n8n UI → **Workflows** → **Add Workflow**
2. Click the three dots (`···`) → **Import from File**
3. Pick **`n8n/aznet-complete.json`**
4. The editor shows two labelled bands (Réception, Gestionnaire d'erreurs) — the maintenance and daily/weekly report bands moved to the API scheduler (`api/app/jobs.py`)

Already baked into the file (patched via scripts, re-import = zero manual wiring):
- credential IDs for Telegram / WhatsApp API / WhatsApp OAuth / Google service account
- 19-column schema on *Append Sheet row* (n8n v4 Sheets node requires `columns.schema` when mapping is `defineBelow`)
- ALLOWLIST in *Access control*: Telegram `<TELEGRAM_USER_ID>` + WhatsApp `<WHATSAPP_NUMBER>` (both `directeur`)
- spreadsheet ID + bot token + phone number ID via `$env.*` (`GOOGLE_SHEET_ID`, `TELEGRAM_BOT_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`) — nothing to hardcode

Behavior (both channels, identical): voice notes, forwarded audio AND typed text reports (`/commands` ignored); allowlist gate — outsiders get exactly one HR reply per chat (via `$env.HR_EMAIL`), then silence; ⏳ ack after authorization; ✅ résumé reply (or ❌ error reply) always on the originating channel; dedupe via `POST /logs/claim` (keys `tg:<chat>:<msgid>` / `wa:<wamid>`); Sheet row includes `canal`, `confidence`, `flag_review`.

### 8.2 Configure credentials

After import, every credential shows a red warning. Click each one and re-select:

| Node type | Credential to attach |
|-----------|---------------------|
| Telegram Trigger / TG nodes | The Telegram API credential from §4.4 |
| WhatsApp Trigger | WhatsApp OAuth from §5.4 |
| WA send/media nodes | WhatsApp Business Cloud API from §5.4 |
| Google Sheets nodes | Google Service Account from §6.4 |

Credential/ID changes later: edit the JSON (or re-run the patch scripts) and re-import — n8n binds credentials by ID.

### 8.3 Set the error workflow

1. Open workflow **Settings** (tab below the canvas)
2. **Error Workflow** → select the same workflow
3. A workflow can be its own error handler; the field ships empty because it needs the ID n8n assigns at import

> **Re-check after every import or API push:** the error-workflow id lives in the workflow's `settings`, and the public API silently drops settings keys it does not accept — so a workflow pushed via `PUT /api/v1/workflows/{id}` comes back without it. The Error Trigger never fires otherwise.

### 8.4 Sheet target

The **Append Sheet row** node reads the spreadsheet id from `$env.GOOGLE_SHEET_ID` (root `.env`) — nothing to replace. If you created a new Sheet, update the env var and restart compose. The sheet tab is `Rapports`.

The daily/weekly reports do **not** read the Sheet through n8n — the API scheduler (`api/app/jobs.py`) reads it itself via `sheets.py` using `SHEET_ID` + `GOOGLE_SERVICE_ACCOUNT_JSON`. There is no "Read Rapports sheet" node left to update.

### 8.5 Recipients of report emails (API, not n8n)

Report emails are sent by the API via SMTP — no Gmail OAuth credential in n8n. Set in `.env`:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASS=<app password>
NOTIF_RECIPIENTS=manager@example.com
```

Schedule and recipients are editable in the dashboard **Automation** page (stored in `app_settings`); `POST /notify/test` sends a test email. See `api/app/jobs.py`.

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

> Note: the workflow still carries a fallback allowlist for the pipeline; the dashboard's **Access** page (`persons`/`technicians` in Postgres) is the live access-control source for the API — `GET /technicians/lookup` filters on `active`, so the dashboard's toggle actually revokes access.

### 8.7 Activate

Click **Active** toggle (top right). The workflow starts:
- Polling Telegram every 15s
- Listening for WhatsApp webhooks (only if the tunnel is registered — §5.5)
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

Opens on <http://localhost:5173> — proxies `/api` to the compose nginx at `http://127.0.0.1:8080` (which maps `/api/ → api:8000/`) and `/n8n` to n8n on `:5678`. The `api` service publishes no host port, so calling `:8000` directly 502s.

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

The Vite dev proxy attaches `X-N8N-API-KEY` server-side, so the key lives here **without** a `VITE_` prefix and never reaches client JS.

### 9.4 Build for production

```bash
cd Dashboard
npm run build
```

The static build goes to `Dashboard/dist/`, served by the compose `web` nginx container on <http://localhost:8080> (same origin as `/api` — that is what keeps the session cookie `SameSite=Lax` and makes CORS a non-issue). Behind the Tailscale Funnel the same nginx serves the pilot; only the hostname in front of it changes. (Deploying `Dashboard/dist/` separately, e.g. Vercel, is not yet implemented — the `/api` proxy would not exist there.)

---

## 10. Smoke test

1. API health:

   ```bash
   curl http://localhost:8000/health   # host-run uvicorn, or http://localhost:8080/api/health via the proxy
   ```

   Expected (dev):
   ```json
   {"status":"ok","version":"0.1.0","uptime_seconds":42.0,"stt_providers":["gemini","groq","hf-darija"],"stt_default":"groq"}
   ```

2. Workflow Active (WhatsApp Trigger deactivated unless the tunnel is registered).
3. **Telegram voice note:** open the bot chat → hold mic → speak → release. Within ~15s an execution appears in n8n; the bot replies with a French summary; a row lands in the Sheet.
4. **Telegram typed text report:** type a message instead of a voice note:

   ```
   chantier oulad hadj, client AKDITAL, tirsaa 3 goulottes o 50 metre dial cable, 2 bureaux termines o 1 panneau raccorde, wahd l'probleme f-matériel hadi n9ssin l-brassage
   ```

   Same flow, no confidence value.
5. **Access control:** a Telegram account NOT in the ALLOWLIST sends a voice note → exactly one "contact HR" reply, nothing in the Sheet, log shows stage `denied`.
6. **WhatsApp (post-registration):** voice note from an allowlisted test number → same flow, reply on WhatsApp.
7. **Dashboard:** <http://localhost:5173> (dev) — Overview shows metrics; Inbox shows editable reports; Access page adds/removes technicians.

---

## 11. Troubleshooting

All hit for real during setup (2026-07-23) unless noted:

| Symptom | Cause → fix |
|---|---|
| `[logs] DISABLED` on API startup | Postgres not running or `DATABASE_URL` wrong → `docker compose up -d postgres`, check `.env` |
| n8n Code node says "access to env vars denied" | `N8N_BLOCK_ENV_ACCESS_IN_NODE=true` → set `false` in `docker-compose.yml`, restart container |
| "Node does not have any credentials set" after import | JSON credential IDs don't match instance → patch real IDs (credential ID = string in URL when credential open), see §8.2 |
| "`columns.schema` is required…" on Sheets node | populate `schema` in JSON, or open node and re-select the Sheet so n8n refetches columns |
| WhatsApp "Invalid parameter" on activate | No public `WEBHOOK_URL` yet → deactivate the WhatsApp Trigger node until the tunnel is registered |
| Sheets append 403 | Sheet not shared with the service-account email → share as Editor (§6.3) |
| Telegram voice notes vanish randomly | second active workflow polling same token → keep one |
| `getUpdates` returns 409 | stale webhook → `deleteWebhook` once (§4.5) |
| `getUpdates` returns empty, no execution | workflow not activated OR two workflows polling same token → activate only ONE; check n8n executions page |
| Workflow error on `/process` 502 | API not running or unreachable → check `API_BASE_URL` in `.env`, `curl localhost:8000/health` |
| Dashboard shows "API unreachable" | FastAPI not running → `docker compose up -d --build api` or start uvicorn manually |
| Dashboard n8n status shows no workflows | n8n API key wrong or n8n not running → check `N8N_API_KEY` in `Dashboard/.env` |
| Gemini extraction returns empty | Safety filter blocked content → check the model response in logs; retry with different phrasing |
| SMTP email not sending | Gmail requires an app password, not the regular one → <https://myaccount.google.com/apppasswords> |
| Arabic text garbled in Sheet | Sheets encoding → should work; if not, check service account region settings |
| Docker containers restart in loop | Port conflict (5432, 5678, 8080 already in use) → `netstat -ano | findstr :<port>` to find the process, stop it |
| `pairedItem` warnings in n8n | Version drift in `$Node.item` references → update expressions to use `$json.*` directly where possible |
