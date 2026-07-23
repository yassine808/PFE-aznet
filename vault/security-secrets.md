---
tags: [pfe, security, secrets, api-keys, compliance, best-practices]
type: technical
priority: high
status: current
---

# Security & Secrets Management

## Threat Model

| Asset | Threat | Mitigation |
|-------|--------|------------|
| API Keys (Gemini, Groq, HF) | Leak via git/logs | Env vars only, never in code |
| Telegram Bot Token | Hijack bot | Webhook secret, IP allowlist |
| Sheets Service Account | Data exfiltration | Minimal scope (Sheets only) |
| Gmail App Password | Email abuse | App password, not main |
| Audio Data | PII exposure | Not logged, transient in memory |
| Technician Names | PII | Acceptable (business need) |

---

## Secrets Inventory

| Secret | Where Stored | Rotation | Access |
|--------|--------------|----------|--------|
| `GEMINI_API_KEY` | Vercel Env / `.env` | 90 days | API only |
| `GROQ_API_KEY` | Vercel Env / `.env` | 90 days | API only |
| `HF_API_KEY` | Vercel Env / `.env` | 90 days | API only |
| `TELEGRAM_BOT_TOKEN` | n8n Credentials | 180 days | n8n only |
| `TELEGRAM_WEBHOOK_SECRET` | n8n Credentials | 180 days | n8n only |
| `SHEETS_SERVICE_ACCOUNT_JSON` | n8n Credentials / file | 180 days | n8n only |
| `GMAIL_APP_PASSWORD` | n8n Credentials | 180 days | n8n only |
| `N8N_ENCRYPTION_KEY` | VPS `.env` | 365 days | n8n only |
| `N8N_BASIC_AUTH_PASSWORD` | VPS `.env` | 180 days | n8n UI |

---

## Local Development

### .env File (Never Commit)

```bash
# api/.env
GEMINI_API_KEY=your-key-here
GROQ_API_KEY=your-key-here
HF_API_KEY=your-key-here
DEFAULT_STT_PROVIDER=groq
STT_TIMEOUT_SECONDS=30
EXTRACTION_TIMEOUT=30
CORS_ORIGINS=http://localhost:5678,http://localhost:3000
```

```bash
# .gitignore (already configured)
.env
*.env.local
credentials/
*.service-account.json
```

### Pre-commit Hook (Optional)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks
        args: ['--config', '.gitleaks.toml']
```

---

## Production (Vercel + VPS)

### Vercel Environment Variables

Dashboard → Project → Settings → Environment Variables

| Name | Environment | Value |
|------|-------------|-------|
| `GEMINI_API_KEY` | Production, Preview | `sk-...` |
| `GROQ_API_KEY` | Production, Preview | `gsk_...` |
| `HF_API_KEY` | Production, Preview | `hf_...` |
| `DEFAULT_STT_PROVIDER` | All | `groq` |
| `CORS_ORIGINS` | All | `https://n8n.aznet.ma` |

**Never** use "System" environment type for secrets.

### VPS Environment (/opt/n8n/.env)

```bash
# n8n Auth
N8N_USER=admin
N8N_PASSWORD=strong-unique-password-123

# Encryption (generate: openssl rand -hex 32)
N8N_ENCRYPTION_KEY=a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef1234

# Optional Postgres
# POSTGRES_PASSWORD=another-strong-password
```

### File Permissions

```bash
# Restrict .env files
chmod 600 /opt/n8n/.env
chmod 600 /opt/n8n/credentials/*.json

# Ownership
sudo chown -R 1000:1000 /opt/n8n/data
sudo chown -R 1000:1000 /opt/n8n/credentials
```

---

## Telegram Security

### Webhook Secret Token

```bash
# Generate
openssl rand -hex 32
# → a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef1234
```

### Set Webhook with Secret

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://n8n.aznet.ma/webhook/telegram",
    "secret_token": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef1234",
    "allowed_updates": ["message", "edited_message"],
    "max_connections": 40
  }'
```

### Verify in n8n

```javascript
// Webhook Trigger → Function: Verify Secret
const secret = $credentials.telegramWebhook.secretToken;
const header = $request.headers["x-telegram-bot-api-secret-token"];

if (header !== secret) {
  return [{ json: { error: "Invalid secret" }, responseCode: 401 }];
}

return items; // Continue
```

### IP Allowlist (Optional)

Telegram webhook IPs: `149.154.167.0/24`, `91.108.4.0/22`, `91.108.8.0/22`, `91.108.12.0/22`, `91.108.16.0/22`

```javascript
// Caddy: restrict webhook to Telegram IPs
@telegram {
    remote_ip 149.154.167.0/24 91.108.4.0/22 91.108.8.0/22 91.108.12.0/22 91.108.16.0/22
}

@webhook path /webhook/telegram

handle @webhook @telegram {
    reverse_proxy localhost:5678
}

handle @webhook {
    respond "Forbidden" 403
}
```

---

## API Security

### CORS Configuration

```python
# app/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),  # Specific origins
    allow_credentials=False,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)
```

### Rate Limiting (Optional)

```python
# Add slowapi for rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/process")
@limiter.limit("30/minute")  # Adjust based on expected load
async def process(...):
    ...
```

### Input Validation

```python
# app/schemas.py - Already strict
class ProcessVoiceRequest(BaseModel):
    audio: str = Field(..., min_length=1, max_length=34000000)  # ~25MB base64
    metadata: ReportMetadata

class ReportMetadata(BaseModel):
    date: date
    technicien: str = Field(..., min_length=1, max_length=100)
    # ...
```

---

## Audio Data Handling

### Principles

1. **Never log audio content** (base64 or binary)
2. **Never persist audio** to disk/database
3. **Transient in memory** only during processing
4. **Delete after STT** — don't pass to extraction

### Implementation

```python
# app/main.py
@app.post("/process")
async def process(request: ProcessRequest):
    if request.audio:
        # Decode in memory
        audio_bytes = base64.b64decode(request.audio)
        
        # STT
        transcription = await transcribe(audio_bytes)
        
        # Explicitly delete
        del audio_bytes
        
        # Pass only text to extraction
        report = await extract(transcription)
    
    return response
```

### n8n: No Audio in Logs

- n8n execution logs: **Disable "Save Execution Data"** for production
- Or: Filter sensitive fields in Error Trigger

---

## Google Sheets Service Account: Least Privilege

### Custom IAM Role (Recommended)

```yaml
# custom-role.yaml
title: "PFE Sheets Writer"
description: "Minimal permissions to append rows"
stage: "GA"
includedPermissions:
  - sheets.spreadsheets.values.append
  - sheets.spreadsheets.values.get  # For dedup check
```

```bash
gcloud iam roles create pfeSheetsWriter \
  --project=pfe-aznet-sheets \
  --file=custom-role.yaml
```

### Assign to Service Account

```bash
gcloud projects add-iam-policy-binding pfe-aznet-sheets \
  --member="serviceAccount:pfe-sheets-writer@pfe-aznet-sheets.iam.gserviceaccount.com" \
  --role="projects/pfe-aznet-sheets/roles/pfeSheetsWriter"
```

---

## VPS Hardening

### SSH

```bash
# /etc/ssh/sshd_config
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
AllowUsers youruser
Port 2222  # Non-standard

# Restart
sudo systemctl restart ssh
```

### Firewall (UFW)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 2222/tcp    # SSH
sudo ufw allow 80/tcp      # HTTP (Caddy)
sudo ufw allow 443/tcp     # HTTPS (Caddy)
sudo ufw enable
```

### Fail2Ban

```bash
sudo apt install fail2ban -y

# /etc/fail2ban/jail.local
[sshd]
enabled = true
port = 2222
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600

sudo systemctl restart fail2ban
```

### Automatic Updates

```bash
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure -plow unattended-upgrades
```

---

## Incident Response

### If API Key Leaked

1. **Immediately revoke** in provider dashboard (Gemini/Groq/HF)
2. **Generate new key**
3. **Update Vercel env vars** (instant deploy)
4. **Check usage logs** for abuse
5. **Rotate n8n credentials** if also exposed

### If Service Account Compromised

1. **Delete key** in GCP Console
2. **Create new key** → Update n8n credentials
3. **Check Sheets audit log** for unauthorized access
4. **Review sharing permissions** on spreadsheets

### If Telegram Token Leaked

1. **Revoke via @BotFather** → `/revoke`
2. **Generate new token** → Update n8n
3. **Reset webhook secret** → Update n8n
4. **Check bot message history** for spam

---

## Compliance Notes

### Data Processing

| Data | Category | Retention | Legal Basis |
|------|----------|-----------|-------------|
| Audio (transient) | Voice | None (memory only) | Contract |
| Transcription | Text | 30 days (logs) | Contract |
| Extracted Report | Business | Indefinite (Sheets) | Contract |
| Technician Name | PII | Indefinite (Sheets) | Contract |
| Chat ID/Message ID | Technical | 30 days | Legitimate interest |

### GDPR Considerations (if applicable)

- **Data minimization**: Only collect needed fields
- **Right to deletion**: Manual process (remove row from Sheets)
- **Data portability**: Export from Sheets → CSV
- **DPIA**: Not required (low risk, small scale)

---

## Security Checklist (Pre-Launch)

- [ ] No secrets in git history (`git log --all --full-history -- .env`)
- [ ] `.env` in `.gitignore`
- [ ] Vercel env vars set (not in code)
- [ ] n8n credentials encrypted (N8N_ENCRYPTION_KEY set)
- [ ] Telegram webhook secret verified
- [ ] Service account minimal permissions
- [ ] Gmail app password (not main)
- [ ] VPS SSH key-only auth
- [ ] VPS firewall configured
- [ ] Fail2ban active
- [ ] Automatic updates enabled
- [ ] Caddy HTTPS enforced
- [ ] API CORS restricted to n8n domain
- [ ] Rate limiting considered
- [ ] Audio not logged anywhere
- [ ] Error logs don't leak secrets
- [ ] Backup encryption considered

---

## Related Notes

- [[Project Overview]]
- [[Architecture]]
- [[Deployment Guide]]
- [[n8n Workflows]]
- [[Google Sheets Integration]]