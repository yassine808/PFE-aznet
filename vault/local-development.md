---
tags: [pfe, development, local, setup, docker, vscode, debugging]
type: technical
priority: high
status: current
---

# Local Development Environment Setup

## Overview

Complete local development setup for PFE aznet with hot-reload, debugging, and parity with production.

```
┌─────────────────────────────────────────────────────────────────┐
│                    LOCAL DEV ARCHITECTURE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Telegram   │───▶│    ngrok     │───▶│   n8n        │      │
│  │   (Phone)    │    │  (Tunnel)    │    │  (Docker)    │      │
│  └──────────────┘    └──────────────┘    └──────┬───────┘      │
│                                                  │              │
│  ┌──────────────┐    ┌──────────────┐           │              │
│  │   VS Code    │───▶│   API        │◀──────────┘              │
│  │  (Debug)     │    │  (uvicorn)   │                          │
│  └──────────────┘    └──────────────┘                          │
│         │                   │                                   │
│         ▼                   ▼                                   │
│  ┌──────────────────────────────────────┐                      │
│  │         Google Sheets (Real)         │                      │
│  │         Gmail SMTP (Real)            │                      │
│  └──────────────────────────────────────┘                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### System Requirements

| Tool | Version | Install Command |
|------|---------|-----------------|
| **Git** | 2.40+ | `winget install Git.Git` |
| **Python** | 3.9.x | `winget install Python.Python.3.9` |
| **Node.js** | 20 LTS | `winget install OpenJS.NodeJS.LTS` |
| **Docker Desktop** | Latest | `winget install Docker.DockerDesktop` |
| **VS Code** | Latest | `winget install Microsoft.VisualStudioCode` |
| **ngrok** | 3.x | `winget install ngrok.ngrok` |
| **Make** | Optional | `winget install GnuWin32.Make` |

### VS Code Extensions (Required)

```json
// .vscode/extensions.json
{
  "recommendations": [
    "ms-python.python",
    "ms-python.pylance",
    "ms-python.black-formatter",
    "charliermarsh.ruff",
    "ms-azuretools.vscode-docker",
    "redhat.vscode-yaml",
    "github.vscode-github-actions",
    "streetsidesoftware.code-spell-checker",
    "esbenp.prettier-vscode",
    "ms-vscode.makefile-tools"
  ]
}
```

---

## Quick Start (5 Minutes)

```bash
# 1. Clone & enter
git clone https://github.com/aznet/pfe-aznet.git
cd pfe-aznet

# 2. Start n8n + monitoring stack
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 3. Setup API environment
cd api
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
# Edit .env with your API keys

# 4. Start API with hot reload
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000

# 5. Start ngrok tunnel (new terminal)
ngrok http 5678

# 6. Configure Telegram webhook to ngrok URL
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -d "url=https://<NGROK_ID>.ngrok-free.app/webhook/telegram" \
  -d "secret_token=<YOUR_SECRET>"

# 7. Open n8n editor
# http://localhost:5678 (admin / from .env)

# 8. Import workflows from n8n/workflows/
# Configure credentials
# Activate workflows

# 9. Test: Send voice note to bot → Check Sheets
```

---

## Detailed Setup

### 1. n8n Development Stack

#### `docker-compose.dev.yml`

```yaml
version: '3.8'

services:
  n8n:
    image: n8nio/n8n:latest
    restart: unless-stopped
    ports:
      - "5678:5678"
    environment:
      # Basic Auth
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=admin
      - N8N_BASIC_AUTH_PASSWORD=devpassword
      
      # Webhook (ngrok will provide HTTPS)
      - WEBHOOK_URL=https://localhost:5678/
      - N8N_HOST=0.0.0.0
      - N8N_PORT=5678
      - N8N_PROTOCOL=http
      
      # Timezone
      - GENERIC_TIMEZONE=Africa/Casablanca
      - TZ=Africa/Casablanca
      
      # Development settings
      - EXECUTIONS_MODE=regular
      - EXECUTIONS_TIMEOUT=3600
      - N8N_LOG_LEVEL=debug
      - N8N_LOG_OUTPUT=console,file
      - N8N_METRICS=true
      
      # Allow external libraries in Function nodes
      - NODE_FUNCTION_ALLOW_EXTERNAL=axios,lodash,moment,uuid,cheerio,form-data
      
      # Disable telemetry
      - N8N_TELEMETRY_DISABLED=true
      
    volumes:
      - ./n8n/data:/home/node/.n8n
      - ./n8n/workflows:/home/node/.n8n/workflows
      - ./n8n/credentials:/home/node/.n8n/credentials
      - ./n8n/custom:/home/node/.n8n/custom
      
    networks:
      - dev-network
      
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:5678/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # LocalStack for AWS services simulation (if needed)
  # localstack:
  #   image: localstack/localstack:latest
  #   ports:
  #     - "4566:4566"
  #   environment:
  #     - SERVICES=s3,sqs,lambda
  #   volumes:
  #     - localstack_data:/var/lib/localstack

networks:
  dev-network:
    driver: bridge

# volumes:
#   localstack_data:
```

#### Start n8n Stack

```bash
# Start
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Logs
docker compose logs -f n8n

# Stop
docker compose down

# Reset (careful - deletes data!)
docker compose down -v
```

### 2. API Development Setup

#### Virtual Environment

```bash
cd api

# Create venv (Python 3.9 required)
python -m venv .venv

# Activate (PowerShell)
.venv/Scripts/Activate.ps1

# Activate (Command Prompt)
.venv/Scripts/activate.bat

# Activate (Git Bash)
source .venv/Scripts/activate

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Verify
python -c "import fastapi; print(fastapi.__version__)"
```

#### Environment Configuration (`.env`)

```bash
# api/.env
# ──────────────────────────────────────────────
# ENVIRONMENT
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG

# API SETTINGS
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=1
CORS_ORIGINS=http://localhost:5678,https://*.ngrok-free.app

# STT PROVIDERS (at least one required)
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
HF_API_KEY=hf_xxxxxxxxxxxxxxxxxxxxxxxx

# DEFAULT PROVIDER (after benchmark)
DEFAULT_STT_PROVIDER=groq

# TIMEOUTS
STT_TIMEOUT_SECONDS=30
EXTRACTION_TIMEOUT_SECONDS=30

# SENTRY (optional)
SENTRY_DSN=https://xxxxx@sentry.io/xxxxx

# GOOGLE SHEETS (for n8n integration testing)
# Use service account JSON path
GOOGLE_SHEETS_CREDENTIALS_PATH=../credentials/sheets-service-account.json
GOOGLE_SHEETS_SPREADSHEET_ID=1ABC123XYZ

# EMAIL (for n8n notifications)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
EMAIL_FROM=PFE Reports <noreply@aznet.ma>
EMAIL_TO=manager@aznet.ma
```

#### Run API with Hot Reload

```bash
# Development server with auto-reload
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Alternative: Using the dev script
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000 --log-level debug
```

**Output should show:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using StatReload
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### 3. ngrok Tunnel Setup

#### Install & Authenticate

```bash
# Install (if not done)
winget install ngrok.ngrok

# Authenticate (get token from https://dashboard.ngrok.com/get-started/your-authtoken)
ngrok config add-authtoken <YOUR_AUTHTOKEN>
```

#### Start Tunnel

```bash
# Terminal 1: ngrok for n8n webhooks
ngrok http 5678

# Terminal 2 (optional): ngrok for API direct access
ngrok http 8000
```

**Expected output:**
```
Session Status    online
Account           Your Name (Plan: Free)
Version           3.x.x
Region            United States (us)
Latency           -
Web Interface     http://127.0.0.1:4040
Forwarding        https://abc123.ngrok-free.app -> http://localhost:5678
Forwarding        http://abc123.ngrok-free.app -> http://localhost:5678
Connections       ttl     opn     rt1     rt5     p50     p90
                  0       0       0.00    0.00    0.00    0.00
```

#### Configure Telegram Webhook

```bash
# Replace with your ngrok URL and secret
NGROK_URL=https://abc123.ngrok-free.app
SECRET_TOKEN=your-super-secret-webhook-token

curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"url\": \"${NGROK_URL}/webhook/telegram\",
    \"secret_token\": \"${SECRET_TOKEN}\",
    \"allowed_updates\": [\"message\", \"edited_message\"]
  }"

# Verify
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

### 4. n8n Workflow Configuration

#### Import Workflows

1. Open http://localhost:5678
2. Login: `admin` / `devpassword`
3. Workflows → Import → Select files from `n8n/workflows/`
   - `telegram-polling.json` (for polling mode)
   - `telegram-webhook.json` (for webhook mode)
   - `web-form.json` (manual entry)
4. Activate desired workflow

#### Configure Credentials

| Credential Type | Setup |
|----------------|-------|
| **Google Sheets OAuth2** | n8n → Credentials → New → Google Sheets OAuth2 → Connect Google account |
| **Google Sheets Service Account** | Paste JSON from `credentials/sheets-service-account.json` |
| **Gmail SMTP** | Host: `smtp.gmail.com`, Port: `587`, User: `your@gmail.com`, Password: App Password |
| **Telegram API** | Token from BotFather |
| **HTTP Header Auth** | For API calls: `Authorization: Bearer <internal-token>` |

#### Update Workflow Settings

**For Webhook Mode:**
1. Open `telegram-webhook` workflow
2. Webhook URL node → Update path if needed
3. HTTP Request node (API call) → URL: `https://<NGROK_API>.ngrok-free.app/process`
4. Save & Activate

**For Polling Mode:**
1. Open `telegram-polling` workflow
2. Cron node → Every 30 seconds (or adjust)
3. HTTP Request node → URL: `https://<NGROK_API>.ngrok-free.app/process`
4. Save & Activate

---

## VS Code Debug Configuration

### `.vscode/launch.json`

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "API: Debug (Hot Reload)",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "app.main:app",
        "--reload",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--log-level", "debug"
      ],
      "cwd": "${workspaceFolder}/api",
      "python": "${workspaceFolder}/api/.venv/Scripts/python.exe",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/api"
      },
      "console": "integratedTerminal",
      "justMyCode": true,
      "subProcess": true
    },
    {
      "name": "API: Debug Tests",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": [
        "-v",
        "--tb=short",
        "--no-cov"
      ],
      "cwd": "${workspaceFolder}/api",
      "python": "${workspaceFolder}/api/.venv/Scripts/python.exe",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/api"
      },
      "console": "integratedTerminal"
    },
    {
      "name": "API: Debug Single Test",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": [
        "-v",
        "--tb=long",
        "${file}"
      ],
      "cwd": "${workspaceFolder}/api",
      "python": "${workspaceFolder}/api/.venv/Scripts/python.exe",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/api"
      },
      "console": "integratedTerminal"
    },
    {
      "name": "n8n: Attach to Docker",
      "type": "docker",
      "request": "attach",
      "containerName": "pfe-aznet-n8n-1",
      "port": 9229,
      "localRoot": "${workspaceFolder}/n8n",
      "remoteRoot": "/home/node/.n8n"
    }
  ],
  "compounds": [
    {
      "name": "Full Stack Debug",
      "configurations": ["API: Debug (Hot Reload)"],
      "stopAll": true
    }
  ]
}
```

### `.vscode/settings.json`

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/api/.venv/Scripts/python.exe",
  "python.analysis.extraPaths": ["${workspaceFolder}/api"],
  "python.analysis.typeCheckingMode": "basic",
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": "explicit",
    "source.fixAll.ruff": "explicit"
  },
  "files.exclude": {
    "**/__pycache__": true,
    "**/.pytest_cache": true,
    "**/.ruff_cache": true,
    "**/.venv": true,
    "**/node_modules": true
  },
  "search.exclude": {
    "**/__pycache__": true,
    "**/.pytest_cache": true,
    "**/.ruff_cache": true,
    "**/.venv": true,
    "**/node_modules": true,
    "**/n8n/data": true
  },
  "docker.defaultRegistryPath": "docker.io",
  "terminal.integrated.defaultProfile.windows": "PowerShell",
  "terminal.integrated.profiles.windows": {
    "PowerShell": {
      "path": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
      "args": ["-NoExit", "-Command", "cd ${workspaceFolder}"]
    }
  }
}
```

### `.vscode/tasks.json`

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "API: Install Dependencies",
      "type": "shell",
      "command": "${workspaceFolder}/api/.venv/Scripts/pip.exe",
      "args": ["install", "-r", "requirements.txt", "-r", "requirements-dev.txt"],
      "group": "build",
      "problemMatcher": []
    },
    {
      "label": "API: Run Tests",
      "type": "shell",
      "command": "${workspaceFolder}/api/.venv/Scripts/python.exe",
      "args": ["-m", "pytest", "-v", "--tb=short"],
      "group": "test",
      "problemMatcher": ["$pytest"],
      "detail": "Run all API tests"
    },
    {
      "label": "API: Run Tests with Coverage",
      "type": "shell",
      "command": "${workspaceFolder}/api/.venv/Scripts/python.exe",
      "args": ["-m", "pytest", "--cov=app", "--cov-report=term-missing", "--cov-fail-under=80"],
      "group": "test",
      "problemMatcher": ["$pytest"]
    },
    {
      "label": "API: Lint (Ruff)",
      "type": "shell",
      "command": "${workspaceFolder}/api/.venv/Scripts/ruff.exe",
      "args": ["check", "app", "tests"],
      "group": "build",
      "problemMatcher": []
    },
    {
      "label": "API: Format (Black)",
      "type": "shell",
      "command": "${workspaceFolder}/api/.venv/Scripts/black.exe",
      "args": ["app", "tests"],
      "group": "build",
      "problemMatcher": []
    },
    {
      "label": "n8n: Start Dev Stack",
      "type": "shell",
      "command": "docker",
      "args": ["compose", "-f", "docker-compose.yml", "-f", "docker-compose.dev.yml", "up", "-d"],
      "group": "build",
      "problemMatcher": []
    },
    {
      "label": "n8n: Stop Dev Stack",
      "type": "shell",
      "command": "docker",
      "args": ["compose", "down"],
      "group": "build",
      "problemMatcher": []
    },
    {
      "label": "n8n: View Logs",
      "type": "shell",
      "command": "docker",
      "args": ["compose", "logs", "-f", "n8n"],
      "group": "build",
      "problemMatcher": []
    },
    {
      "label": "ngrok: Start (n8n)",
      "type": "shell",
      "command": "ngrok",
      "args": ["http", "5678"],
      "group": "build",
      "problemMatcher": [],
      "isBackground": true
    },
    {
      "label": "Telegram: Set Webhook",
      "type": "shell",
      "command": "bash",
      "args": ["-c", "curl -X POST \"https://api.telegram.org/bot${BOT_TOKEN}/setWebhook\" -d \"url=https://$(curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[0].public_url')/webhook/telegram\" -d \"secret_token=${WEBHOOK_SECRET}\""],
      "group": "build",
      "problemMatcher": [],
      "env": {
        "BOT_TOKEN": "${input:botToken}",
        "WEBHOOK_SECRET": "${input:webhookSecret}"
      }
    }
  ],
  "inputs": [
    {
      "id": "botToken",
      "type": "promptString",
      "description": "Telegram Bot Token",
      "password": true
    },
    {
      "id": "webhookSecret",
      "type": "promptString",
      "description": "Webhook Secret Token",
      "password": true
    }
  ]
}
```

---

## Testing Locally

### API Tests

```bash
cd api

# All tests
.venv/Scripts/python.exe -m pytest -v

# Specific test file
.venv/Scripts/python.exe -m pytest tests/test_process_endpoint.py -v

# Specific test
.venv/Scripts/python.exe -m pytest tests/test_process_endpoint.py::test_voice_mode_success -v

# With coverage
.venv/Scripts/python.exe -m pytest --cov=app --cov-report=html --cov-fail-under=80

# Watch mode (requires pytest-watch)
.venv/Scripts/python.exe -m pytest --watch
```

### Manual API Testing

```bash
# Health check
curl http://localhost:8000/health

# Text mode
curl -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Bonjour c\'est Ahmed, aujourd\'hui 23 juillet, chantier Hay Riad. On a tiré 150m goulotte, posé 5 boîtiers. Problème: gaine bouchée au regard 3.",
    "metadata": {
      "date": "2026-07-23",
      "technicien": "Ahmed",
      "chantier": "Hay Riad",
      "lien_audio": ""
    }
  }'

# Voice mode (with base64 audio)
curl -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{
    "audio": "UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQ...",
    "metadata": {
      "date": "2026-07-23",
      "technicien": "Ahmed",
      "lien_audio": "https://api.telegram.org/file/bot123/voice.ogg"
    }
  }'
```

### n8n Testing

```bash
# Check workflow executions
curl -u admin:devpassword http://localhost:5678/api/v1/executions

# Trigger webhook manually
curl -X POST http://localhost:5678/webhook/telegram \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: your-secret" \
  -d '{
    "message": {
      "message_id": 123,
      "from": {"id": 123456, "first_name": "Test", "username": "testuser"},
      "date": 1690000000,
      "voice": {
        "duration": 10,
        "mime_type": "audio/ogg",
        "file_id": "test_file_id",
        "file_size": 10000
      }
    }
  }'
```

---

## Common Issues & Fixes

### Issue: n8n Can't Reach API via ngrok

**Error:** `ECONNREFUSED` or timeout

**Fix:**
```bash
# 1. Verify ngrok is running for API port
ngrok http 8000

# 2. Use the API ngrok URL in n8n workflow
# Update HTTP Request node URL to: https://<API_NGROK>.ngrok-free.app/process

# 3. Check CORS in API .env
CORS_ORIGINS=https://*.ngrok-free.app,http://localhost:5678
```

### Issue: Telegram Webhook Not Receiving

**Diagnosis:**
```bash
# Check webhook info
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"

# Should show:
# - url: your ngrok URL
# - has_custom_certificate: false
# - pending_update_count: 0
# - last_error_date: 0
```

**Common fixes:**
- ngrok URL changed → Reset webhook
- Secret token mismatch → Verify in n8n Webhook node
- n8n not running → `docker compose ps`

### Issue: Python Import Errors in VS Code

**Fix:**
1. `Ctrl+Shift+P` → "Python: Select Interpreter" → Choose `.venv/Scripts/python.exe`
2. Reload window: `Ctrl+Shift+P` → "Developer: Reload Window"
3. Check `.vscode/settings.json` has correct `python.defaultInterpreterPath`

### Issue: n8n Workflow Not Triggering

**Debug steps:**
1. Check n8n execution list: http://localhost:5678/executions
2. Check workflow is **Active** (toggle on)
3. Check webhook path matches exactly
4. Check credentials are configured
5. View execution logs (click on failed execution)

---

## Development Workflow

### Daily Startup

```bash
# 1. Start n8n stack
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 2. Start API (in api/ folder)
.venv/Scripts/Activate.ps1
python -m uvicorn app.main:app --reload --port 8000

# 3. Start ngrok
ngrok http 5678

# 4. Update Telegram webhook if ngrok URL changed
# (Use VS Code task: "Telegram: Set Webhook")

# 5. Open n8n editor
# http://localhost:5678
```

### Code Changes

| Change | Action |
|--------|--------|
| API Python code | Auto-reloads (uvicorn --reload) |
| n8n workflow | Save in editor, auto-saved to `n8n/workflows/` |
| n8n credentials | Stored in `n8n/credentials/` (encrypted) |
| Docker config | `docker compose down && docker compose up -d` |
| Requirements | `pip install -r requirements.txt` then restart API |

### Before Commit

```bash
cd api

# Format
.venv/Scripts/black.exe app tests
.venv/Scripts/ruff.exe check --fix app tests

# Test
.venv/Scripts/python.exe -m pytest -v --tb=short

# Type check (optional)
.venv/Scripts/python.exe -m pyright
```

---

## Related Notes

- [[Deployment Guide]]
- [[n8n Advanced]]
- [[Vercel Advanced]]
- [[Testing Strategy]]
- [[Architecture]]