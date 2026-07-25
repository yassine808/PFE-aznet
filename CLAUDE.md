44123# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PFE (end-of-studies project, deadline Aug 31 2026) at aznet.ma: voice notes in Moroccan Darija from cabling technicians (via Telegram) → STT → LLM extraction → professional French summary → Google Sheets → manager notifications. **PLAN.md is the source of truth** for architecture decisions, sprint timeline, and locked choices — read it before proposing design changes. Spec: `docs/cahier-des-charges.md`.

Zero-budget constraint: free tiers only (Groq, Gemini AI Studio, HF Inference, Telegram Bot API, Gmail SMTP, Vercel).

**Reception channels:** **both Telegram Bot API and WhatsApp Cloud API are live** (unified n8n workflow `n8n/reception-unified.json`, brought up E2E 2026-07-23). Telegram first (no Meta friction); WhatsApp needed a System User token (no expiry), a published app, a WABA `subscribed_apps` call, a manual GET-echo webhook (n8n's WhatsApp Trigger fails Meta's verification challenge), and media download via a plain HTTP node (native download op returns Bad request). Design is channel-agnostic — both feed one `/process` and one Sheet; the reply returns on the originating channel. Full walkthrough: `docs/setup-guide.md`.

## Commands

All Python work happens in `api/` with its venv (Python 3.9 — use `Optional[X]`, never `X | None`):

```bash
cd api
.venv/Scripts/python.exe -m pytest              # run all tests (42, no API keys and no database needed)
.venv/Scripts/python.exe -m pytest tests/test_process_endpoint.py -k test_voice_mode   # single test
.venv/Scripts/python.exe -m uvicorn app.main:app --reload   # dev server on :8000
```

n8n (orchestration) + Postgres (pipeline logs): `docker compose up -d` at repo root → n8n on http://localhost:5678, Postgres on :5432. The API needs `DATABASE_URL` and n8n needs `API_BASE_URL` in `.env` — see `n8n/README.md` §7b. Telegram reception variants (polling for local dev, webhook for pilot) and smoke test: `n8n/README.md`.

Tests must pass without any API keys — external SDKs are lazy-imported inside functions and mocked at boundaries in tests. Keep it that way.

## Architecture

Hybrid: **n8n** is the glue (Telegram + WhatsApp reception → media download → HTTP call → Sheets append → notifications); **`api/`** is the custom AI microservice n8n calls. Metadata (date, technicien, canal, lien_audio) is added by n8n, not the API.

Endpoints in `api/app/main.py`: `POST /process` (core: audio or text → structured JSON), `POST /daily-report` (`app/daily_report.py`: today's Sheet rows → French manager email, same Gemini→Groq fallback), the dashboard read/write pair `GET /reports` + `PATCH /reports/{row}` (`app/sheets.py`: service-account Sheets access, no auth — dashboard runs on the admin's PC only), `GET /health` (status + process `uptime_seconds`, polled by the dashboard's API-uptime tile), and the observability set `POST|GET|DELETE /logs`, `POST /logs/claim`, `POST|GET /sheet-queue` + `PATCH /sheet-queue/{id}` (`app/logs.py`, Postgres). `/process` accepts exactly one of `audio` (voice mode) or `text` (form/typed mode):

- **STT providers** (`api/app/providers/`): Strategy pattern. `TranscriptionProvider` ABC + `@register("name")` decorator populating a registry; adapters imported at the bottom of `providers/__init__.py` to trigger registration. Three engines (groq, gemini, hf-darija) pending the week-1 benchmark (`benchmark/`) that picks the default in `config.py`.
- **Extraction** (`api/app/extraction.py`): Gemini structured output (`response_schema=ExtractedReport`) primary → Groq Llama JSON-mode fallback. Both failing raises a combined `ExtractionError` — never silent fallbacks, never invented data (prompt enforces null for absent fields).
- **Error contract**: unknown provider / bad input → 422; engine failure (`TranscriptionError`, `ExtractionError`) → 502 so n8n can catch and flag the row; transcription under 10 chars → `short_transcription` warning, not an error.
- **Observability** (`api/app/logs.py`): PostgreSQL (compose service `postgres`) holding `pipeline_logs`, `processed_messages` (WhatsApp idempotency) and `failed_writes` (Sheet retry queue). n8n POSTs one row per stage; the API logs its own errors with the same `correlation_id`, so both processes join into one timeline in the dashboard's **Logs n8n** panel. Deliberately not the Sheet — a Sheets-backed log goes blind during a Sheets outage. `psycopg2` is lazy-imported and pooled; if `DATABASE_URL` is unset the API prints `[logs] DISABLED` and keeps serving.
- **Reply-first ordering**: in `n8n/reception-unified.json` the reply to the technician happens *before* the Sheet append. A failed write parks in `failed_writes` and is drained by `n8n/maintenance-cron.json`; it never costs the technician their summary. Do not reorder these nodes back.
- **Schemas** (`api/app/schemas.py`): `ExtractedReport` is the data contract with n8n and the Sheet — field changes ripple to the extraction prompts, the Sheet columns, and n8n mappings.

Config is env-driven via pydantic-settings (`api/app/config.py`, reads `.env`); keys are optional at startup and checked at call time (fail loudly with a clear message).

## Conventions

- Conventional commits (`feat(api): ...`)
- French domain vocabulary in schemas/prompts (chantier, goulottes_m, resume) — it matches the cahier des charges and the Sheet; don't anglicize
- Dashboard (`web/`): neutral/monochrome Efferd-style theme. shadcn primitives live in `web/src/components/ui/` with `@/` aliased to `src` (declared in **both** `vite.config.ts` and `tsconfig.json`); `tailwind.config.js` aliases shadcn's semantic token names onto the existing Efferd CSS vars, so there is one palette, not two. **All UI copy lives in `web/src/locales/{fr,en,ar}.json`** (fr is the reference/fallback) — never hardcode strings in components; add a key to every locale file. Light/dark via `web/src/theme.tsx` (`.dark` class + RGB-triplet CSS vars in `index.css`); Arabic drives RTL. Recharts colors are duplicated per theme in `theme.tsx` (SVG can't read CSS vars). Metrics are computed client-side from `/reports`; only API uptime comes from `/health`.
- Pyright: IDE may flag false positives if not using `api/.venv`; pytest is ground truth (`api/pyrightconfig.json` points at the venv)
