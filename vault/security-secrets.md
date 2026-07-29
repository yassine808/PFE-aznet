---
tags: [pfe, security, secrets, api-keys]
type: technical
priority: high
status: partial
---

> **Note on status:** the local-dev secrets handling below (env vars, lazy key checks) is real and current. Everything about VPS hardening, Vercel env dashboards, webhook secret tokens, and service-account IAM roles is **plan**, describing infrastructure that doesn't exist yet — there is no VPS, no Vercel project, no Google service account, no Telegram webhook secret configured (the dev workflow uses polling, which needs none of that). A prior version of this doc presented all of this as already configured; it wasn't.

# Security & Secrets (Current + Plan)

## What's real today

### Secrets storage

`api/app/config.py` reads from a `.env` file at the **repo root** (shared with docker-compose), via pydantic-settings:

```python
groq_api_key: Optional[str] = None
gemini_api_key: Optional[str] = None
hf_token: Optional[str] = None
```

All optional at import time; each provider/extraction path raises a clear error at call time if its key is missing (`"GROQ_API_KEY not configured"`, etc.) — never a silent fallback. This is the entire secrets story in the current codebase.

`.env` is (per standard practice, and CLAUDE.md's zero-invented-behavior stance) expected to be gitignored — verify with `git check-ignore .env` rather than assuming.

### Telegram bot token

Stored as an n8n credential (Telegram API), pasted from BotFather. The **polling** workflow used in dev needs no webhook secret, no public URL, no signature verification — it only makes outbound `getUpdates` calls.

## Threat model (current scope)

| Asset | Threat | Current mitigation |
|---|---|---|
| Groq/Gemini/HF API keys | Leak via git/logs | Env var only, never hardcoded; not committed |
| Telegram bot token | Hijack | Stored as n8n credential, not in workflow JSON |
| Audio content | PII exposure | Processed in memory, not persisted by the API; not logged |
| Technician names | PII | Acceptable per cahier des charges (business need) |

## Planned, not yet applicable

- **Webhook secret token verification** — relevant to the WhatsApp branch, which is webhook-driven behind the Tailscale Funnel; the Telegram branch polls and exposes nothing.
- **Google Sheets service account, minimal-scope IAM** — moot until a service account is created at all (see [[Google Sheets Integration]]).
- **Gmail app password** — moot until email notification is built.
- **VPS hardening (SSH, firewall, fail2ban)** — moot until a pilot VPS/server exists (see [[Deployment Guide]]).
- **Vercel environment variables** — moot; no Vercel project exists for the API (see [[Vercel Advanced]]).

## Incident response (still applicable, regardless of deployment stage)

If a key leaks:
1. Revoke it in the provider dashboard (Groq/Gemini/HF console) immediately.
2. Generate a new key, update the local `.env`.
3. Check the provider's usage/audit log for abuse.

If the Telegram bot token leaks: revoke via `@BotFather` → `/revoke`, generate a new token, update the n8n credential.

## Related Notes

- [[Project Overview]]
- [[Architecture]]
- [[Deployment Guide]]
- [[n8n Workflows]]
