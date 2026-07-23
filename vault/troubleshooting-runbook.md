---
tags: [pfe, troubleshooting, runbook, incidents, debugging, oncall]
type: technical
priority: high
status: current
---

# Troubleshooting Runbook

## Quick Reference: Common Issues

| Symptom | Most Likely Cause | Quick Fix |
|---------|------------------|-----------|
| No reports in Sheets | n8n workflow inactive | Activate workflow in n8n |
| Telegram not receiving | Webhook URL expired | Reset webhook with current ngrok URL |
| API 502 errors | STT/LLM provider down | Check provider status, switch default |
| API timeout (>30s) | Large audio / slow provider | Enable audio preprocessing, reduce quality |
| Sheets 403 error | Service account not shared | Share spreadsheet with SA email |
| High error rate | Provider quota exceeded | Check quotas, rotate keys |
| n8n OOM kills | Large executions in memory | Increase VPS RAM, enable queue mode |

---

## Incident Response Flow

```
┌─────────────┐
│   ALERT     │
│  (Monitor)  │
└──────┬──────┘
       ▼
┌─────────────┐
│  TRIAGE     │◀── Check: Dashboard, Logs, Sentry
│  (< 5 min)  │
└──────┬──────┘
       ▼
┌─────────────┐     ┌─────────────┐
│  SEVERITY   │────▶│  SEV-1/2    │──▶ Page on-call, start incident
│  ASSESSMENT │     │  (Critical) │     channel, begin debugging
└──────┬──────┘     └─────────────┘
       ▼
┌─────────────┐
│  SEV-3/4    │
│ (Warning)   │──▶ Create ticket, fix in sprint
└─────────────┘
```

---

## Severity Definitions

| Level | Name | Response Time | Examples |
|-------|------|---------------|----------|
| **SEV-1** | Critical | Immediate (page) | No reports processed > 30 min, Data loss, Security breach |
| **SEV-2** | Major | < 15 min | API errors > 10%, Sheets not updating, Notifications failing |
| **SEV-3** | Minor | < 1 hour | Slow performance, Partial feature degradation |
| **SEV-4** | Low | Next sprint | UI cosmetic, Enhancement requests |

---

## Diagnostic Commands

### API Health Checks

```bash
# 1. Basic health
curl -s https://api.aznet.ma/health | jq

# 2. Test text mode
curl -s -X POST https://api.aznet.ma/process \
  -H "Content-Type: application/json" \
  -d '{"text": "test", "metadata": {"date": "2026-07-23", "technicien": "test"}}' | jq

# 3. Check Vercel logs
vercel logs https://api.aznet.ma --follow

# 4. Check function metrics
vercel inspect https://api.aznet.ma --token=$VERCEL_TOKEN
```

### n8n Health Checks

```bash
# 1. n8n API health
curl -u admin:devpassword http://localhost:5678/healthz

# 2. List active workflows
curl -u admin:devpassword http://localhost:5678/api/v1/workflows?active=true | jq '.data[] | {name, active}'

# 3. Recent executions (last 10)
curl -u admin:devpassword "http://localhost:5678/api/v1/executions?limit=10" | jq '.data[] | {workflowId, status, startedAt, finishedAt}'

# 4. Failed executions (last hour)
curl -u admin:devpassword "http://localhost:5678/api/v1/executions?status=error&limit=20" | jq '.data[] | {workflowId, error: .error.message, startedAt}'

# 5. Check specific execution
curl -u admin:devpassword http://localhost:5678/api/v1/executions/<EXECUTION_ID> | jq
```

### Telegram Debugging

```bash
# 1. Check webhook status
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo" | jq

# Expected healthy response:
# {
#   "ok": true,
#   "result": {
#     "url": "https://xxx.ngrok-free.app/webhook/telegram",
#     "has_custom_certificate": false,
#     "pending_update_count": 0,
#     "last_error_date": 0,
#     "max_connections": 40
#   }
# }

# 2. Test webhook manually
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://xxx.ngrok-free.app/webhook/telegram", "secret_token": "your-secret"}'

# 3. Get recent updates (polling fallback)
curl "https://api.telegram.org/bot<TOKEN>/getUpdates?limit=5" | jq
```

### Google Sheets Debugging

```bash
# 1. Test service account access
# In n8n: Google Sheets node → Test Connection

# 2. Direct API test (if you have credentials)
# Use Google OAuth Playground or:
curl -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://sheets.googleapis.com/v4/spreadsheets/<SPREADSHEET_ID>/values/Rapports!A1:R5"

# 3. Check quota
# Cloud Console → APIs & Services → Google Sheets API → Quotas
```

---

## Common Incident Scenarios

### Scenario 1: No Reports Appearing in Sheets

**Symptoms:** Telegram messages received, n8n workflow triggered, but Sheets empty

**Diagnosis:**
```bash
# 1. Check n8n executions
curl -u admin:pass http://localhost:5678/api/v1/executions?limit=5 | jq '.data[] | {status, workflowId}'

# 2. If executions exist but failed:
curl -u admin:pass "http://localhost:5678/api/v1/executions?status=error&limit=5" | jq '.data[].error.message'

# 3. If executions succeeded but no Sheets data:
# Check Sheets node output in execution details
```

**Common Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| Sheets node error | Check execution → Sheets node → error message |
| Service account not shared | Share spreadsheet with SA email (Editor) |
| Wrong spreadsheet ID | Verify ID in Sheets node matches URL |
| Column mapping wrong | Check "Map Columns" in Sheets node |
| Rate limited (429) | Add delay node, batch writes |

---

### Scenario 2: API Returns 502 (Provider Errors)

**Symptoms:** `/process` returns 502, n8n shows API error

**Diagnosis:**
```bash
# Check Vercel function logs
vercel logs https://api.aznet.ma --since=1h | grep -i "error\|502\|transcription\|extraction"

# Or check Sentry for ExtractionError/TranscriptionError
```

**Common Causes & Fixes:**

| Error | Cause | Fix |
|-------|-------|-----|
| `Groq: Rate limit exceeded` | Free tier limit hit | Switch DEFAULT_STT_PROVIDER to gemini |
| `Gemini: Quota exceeded` | Daily limit hit | Wait for reset, or use Groq |
| `HF: Model loading` | Cold start on HF | Use Groq/Gemini as primary |
| `Extraction: Both providers failed` | Both LLM APIs down | Check status pages, implement fallback |

**Immediate Mitigation:**
```bash
# Switch STT provider via Vercel env var (instant deploy)
vercel env add DEFAULT_STT_PROVIDER gemini production
vercel --prod

# Or switch extraction fallback order in code (requires deploy)
```

---

### Scenario 3: Telegram Bot Not Receiving Messages

**Symptoms:** Send voice note → no n8n execution → no report

**Diagnosis:**
```bash
# 1. Check webhook
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo" | jq

# 2. If pending_update_count > 0:
#    Webhook failing, Telegram queuing updates

# 3. Check n8n webhook endpoint
curl -X POST https://n8n.aznet.ma/webhook/telegram \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: your-secret" \
  -d '{"message":{"message_id":1,"from":{"id":123,"first_name":"Test"},"date":1234567890,"voice":{"duration":5,"mime_type":"audio/ogg","file_id":"test"}}}'
```

**Common Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| ngrok URL changed | Update webhook: `curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" -d "url=https://NEW_URL/webhook/telegram" -d "secret_token=SECRET"` |
| Secret token mismatch | Verify secret in n8n Webhook node matches Telegram |
| n8n container down | `docker compose ps`, restart if needed |
| Caddy/Caddy config wrong | Check Caddyfile routes to n8n:5678 |
| Telegram API issues | Check @BotSupport or status.telegram.org |

---

### Scenario 4: High Latency / Timeouts

**Symptoms:** API takes >25s, Vercel timeout (30s), n8n timeout

**Diagnosis:**
```bash
# Check Vercel function duration
# Dashboard → Functions → Duration histogram

# Check which stage is slow:
# 1. STT: Add timing logs in provider
# 2. Extraction: Add timing logs
# 3. Audio download (n8n): Check n8n execution timeline
```

**Optimization Checklist:**

| Stage | Optimization |
|-------|-------------|
| Audio download | n8n: Use streaming, limit file size |
| Audio preprocess | Convert to 16kHz mono Opus before STT |
| STT | Use Groq (fastest), enable prompt with vocab |
| Extraction | Gemini structured output (fastest) |
| Sheets write | Batch writes, async in n8n |
| Notifications | Fire-and-forget email/Slack |

---

### Scenario 5: Data Quality Issues

**Symptoms:** Reports in Sheets but wrong extraction, missing fields, hallucinated data

**Diagnosis:**
```bash
# 1. Check raw transcription
# In n8n execution: HTTP Request node output → transcription field

# 2. Check extraction confidence
# In Sheets: Column M (extraction_confidence) = "low"

# 3. Check STT confidence
# In Sheets: Column L (stt_confidence_low) = TRUE
```

**Common Causes & Fixes:**

| Issue | Cause | Fix |
|-------|-------|-----|
| Missing quantities | STT didn't capture numbers | Improve audio quality, add number vocab to STT prompt |
| Wrong chantier name | Darija transcription error | Add chantier names to STT prompt |
| Hallucinated data | LLM inventing fields | Verify prompt enforces "null if absent" |
| Low extraction confidence | Noisy audio / unclear speech | Flag for manual review (stt_confidence_low) |

---

## Debugging Tools

### n8n Debug Mode

```bash
# Enable debug logging
docker compose exec n8n sh -c 'echo "N8N_LOG_LEVEL=debug" >> /home/node/.n8n/.env'
docker compose restart n8n

# View debug logs
docker compose logs -f n8n | grep -i debug
```

### VS Code Remote Debug (API)

```json
// .vscode/launch.json (already configured)
// 1. Start API with debug: F5 → "API: Debug (Hot Reload)"
// 2. Set breakpoints in app/main.py, app/extraction.py, providers/
// 3. Trigger request via curl or n8n
// 4. Inspect variables, step through
```

### Log Aggregation Queries

```bash
# Search Vercel logs for specific error
vercel logs https://api.aznet.ma --since=24h | grep -i "extractionerror" | head -20

# Find slow requests
vercel logs https://api.aznet.ma --since=1h | awk '$NF > 10000 {print}'

# n8n error patterns
docker compose logs n8n --since=2h | grep -i "error\|failed\|timeout" | head -30
```

---

## Recovery Procedures

### Restore n8n from Backup

```bash
# 1. Stop n8n
docker compose stop n8n

# 2. Restore data
docker run --rm \
  -v /opt/n8n/data:/data \
  -v /opt/n8n/backups:/backup \
  alpine tar xzf /backup/n8n_data_20260723_020000.tar.gz -C /data

# 3. Restore workflows (if separate)
docker run --rm \
  -v /opt/n8n/workflows:/data \
  -v /opt/n8n/backups:/backup \
  alpine tar xzf /backup/n8n_workflows_20260723_020000.tar.gz -C /data

# 4. Start n8n
docker compose start n8n
```

### Rollback API Deployment

```bash
# Option 1: Vercel instant rollback
vercel ls api.aznet.ma
vercel promote <previous-deployment-url> --scope=team

# Option 2: Git revert + redeploy
git revert <bad-commit>
git push origin main
# Auto-deploys via GitHub Actions
```

### Reset Telegram Webhook

```bash
# 1. Delete webhook (fallback to polling)
curl -X POST "https://api.telegram.org/bot<TOKEN>/deleteWebhook"

# 2. Set new webhook
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://n8n.aznet.ma/webhook/telegram",
    "secret_token": "NEW_SECRET_FROM_PASSWORD_MANAGER",
    "allowed_updates": ["message", "edited_message"],
    "max_connections": 40
  }'

# 3. Verify
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

---

## Escalation Contacts

| Role | Contact | When to Escalate |
|------|---------|------------------|
| **On-call Engineer** | Telegram @oncall | SEV-1/2, any production issue |
| **Tech Lead** | Telegram @techlead | Architecture decisions, provider changes |
| **Manager** | Email/Phone | SEV-1 > 30 min, customer impact |
| **Groq Support** | console.groq.com/support | API issues, quota requests |
| **Gemini Support** | Cloud Console → Support | Quota, billing, model issues |
| **Vercel Support** | vercel.com/support | Platform issues, billing |
| **Telegram Bot API** | @BotSupport | Bot token, webhook issues |

---

## Post-Incident Process

1. **Resolve** → Fix root cause
2. **Document** → Create incident report in `docs/incidents/INC-YYYYMMDD-XXX.md`
3. **Review** → Team retro within 48h
4. **Action Items** → Add to TO-DO.md with `incident:` tag
5. **Update Runbook** → Add new scenario if not covered

### Incident Report Template

```markdown
---
tags: [incident, sev-X, YYYY-MM-DD]
type: incident
severity: X
status: resolved
---

# INC-YYYYMMDD-XXX: Brief Title

## Timeline
- **Detected**: YYYY-MM-DD HH:MM (UTC)
- **Resolved**: YYYY-MM-DD HH:MM (UTC)
- **Duration**: XX minutes

## Impact
- **User impact**: X reports lost / delayed
- **System impact**: API errors Y%, n8n failures Z%

## Root Cause
[Technical explanation]

## Resolution
[What fixed it]

## Action Items
- [ ] Fix: [Link to TO-DO]
- [ ] Monitor: [Dashboard/Alert]
- [ ] Prevent: [Architecture change]

## Lessons Learned
[What we learned]
```

---

## Related Notes

- [[Deployment Guide]]
- [[Monitoring Observability]]
- [[n8n Advanced]]
- [[Security Secrets]]
- [[Local Development]]