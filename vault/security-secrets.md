---
tags: [pfe, security, secrets, env]
type: guide
priority: high
status: current
---

# Security and Secrets

## Environment Variables

Configuration is **env-driven** via `pydantic-settings` (`api/app/config.py`). No hardcoded secrets in code.

Keys are **optional at startup** and checked at call time (fail loudly with a clear message). `Config` is a global singleton with `frozen=True` — `@lru_cache` on the config class.

```python
# config.py pattern:
groq_api_key: Optional[str] = Field(None, description="Groq API key")
# Checked at call time:
if not config.groq_api_key:
    raise TranscriptionError("Groq API key not configured")
```

## Secrets inventory

### In `.env` (repo root, gitignored)

| Variable | Used by | Risk |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | n8n (TG Trigger node) | Can send messages as the bot |
| `WHATSAPP_TOKEN` | n8n (WA nodes) | Can send messages as the WABA |
| `WHATSAPP_VERIFY_TOKEN` | n8n (WA webhook verify) | Low risk (just a verification string) |
| `GROQ_API_KEY` | API | Metered usage on our Groq account |
| `GEMINI_API_KEY` | API (extraction + STT fallback) | Metered usage on our GCP project |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | API (`sheets.py`) | Full access to the Sheet + Drive |
| `GOOGLE_SHEET_ID` | API + n8n | Low risk (just a sheet ID) |
| `GOOGLE_DRIVE_REFRESH_TOKEN` | API | Drive upload capability |
| `DATABASE_URL` | API (`logs.py`) | Full access to the Postgres database |
| `INTERNAL_API_KEY` | n8n → API auth | Shared secret for machine-to-machine calls |
| `SECRET_KEY` | API (auth) | Cookie signing key — compromise = forged sessions |
| `SMTP_*` | API (`mailer.py`) | Gmail account access |

### In `Dashboard/.env` (gitignored)

| Variable | Used by | Risk |
|---|---|---|
| `VITE_API_BASE_URL` | Vite dev server proxy | Low (just a URL) |
| `N8N_API_KEY` | Vite dev proxy (non-`VITE_` prefix) | n8n admin access |

### In `credentials/service-account.json` (gitignored)

Full Google service account key — access to the Sheet, Drive, and any other enabled GCP API under the project.

### Not in any file

- Session tokens: stored in Postgres `sessions` table, opaque random tokens (not JWTs), server-side only
- User passwords: hashed via `hashlib.sha256` (salted with a secret suffix; `bcrypt` not used to keep the dependency light)
- n8n's own SQLite DB: lives in a Docker named volume (`n8n_data`)

## Auth Architecture

Everything is gated (`api/app/auth.py`). Two ways through:

1. **Session cookie** (for humans browsing the dashboard): `POST /auth/login` validates username/password, creates a session in Postgres, sets a signed cookie. `GET /auth/me` returns the current user. `POST /auth/logout` deletes the session.
2. **`X-API-Key` header** (for n8n machine calls): checked against `INTERNAL_API_KEY`.

Three auth gates:
- `require_user` — accepts either cookie or API key
- `require_human` — rejects API key (settings, report edits, accounts)
- `require_director` — narrows further by role

`INTERNAL_API_KEY` unset means machine access is **disabled** — never "everyone is a machine."

## Open items before publishing

- `allow_origins=["*"]` in the FastAPI CORS middleware — fine for one-PC usage, needs tightening before internet deployment
- No rate limit on `/auth/login` — fine for one PC, needed before internet
- Passwords use SHA-256 (salted), not bcrypt — dependency-light choice but should be upgraded if user count grows

## Git hygiene

- `.env`, `*.env`, `credentials/`, `.venv/` are in `.gitignore`
- `Dashboard/.env` is separately gitignored
- Never commit `.env` files or service account keys
- `git add .` is forbidden by protocol — add files individually

## Related

- [[Deployment Guide]] — provisioning secrets
- [[Local Development]] — using `.env.example` as template
