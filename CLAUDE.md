# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PFE (end-of-studies project, deadline Aug 31 2026) at aznet.ma: voice notes in Moroccan Darija from cabling technicians (via Telegram) → STT → LLM extraction → professional French summary → Google Sheets → manager notifications. **PLAN.md is the source of truth** for architecture decisions, sprint timeline, and locked choices — read it before proposing design changes. Spec: `docs/cahier-des-charges.md`.

Zero-budget constraint: free tiers only (Groq, Gemini AI Studio, HF Inference, Telegram Bot API, Gmail SMTP, Vercel).

**Reception channel:** cahier des charges specifies WhatsApp Business API; switched to **Telegram Bot API** on 2026-07-16 (Meta test-mode friction — expiring tokens, webhook verify handshake, 5-number allowlist — was burning Week-0 time; cahier §5 permits *"passerelle équivalente"*). Design is channel-agnostic — only the n8n reception workflow changes, `/process` API untouched. WhatsApp documented as production evolution, not built.

## Commands

All Python work happens in `api/` with its venv (Python 3.9 — use `Optional[X]`, never `X | None`):

```bash
cd api
.venv/Scripts/python.exe -m pytest              # run all tests (24, no API keys needed)
.venv/Scripts/python.exe -m pytest tests/test_process_endpoint.py -k test_voice_mode   # single test
.venv/Scripts/python.exe -m uvicorn app.main:app --reload   # dev server on :8000
```

n8n (orchestration): `docker compose up -d` at repo root → http://localhost:5678. Telegram reception variants (polling for local dev, webhook for pilot) and smoke test: `n8n/README.md`.

Tests must pass without any API keys — external SDKs are lazy-imported inside functions and mocked at boundaries in tests. Keep it that way.

## Architecture

Hybrid: **n8n** is the glue (Telegram reception → media download → HTTP call → Sheets append → notifications); **`api/`** is the custom AI microservice n8n calls. Metadata (date, technicien, lien_audio) is added by n8n, not the API.

The API has one real endpoint, `POST /process` (`api/app/main.py`), accepting exactly one of `audio` (voice mode) or `text` (web form mode):

- **STT providers** (`api/app/providers/`): Strategy pattern. `TranscriptionProvider` ABC + `@register("name")` decorator populating a registry; adapters imported at the bottom of `providers/__init__.py` to trigger registration. Three engines (groq, gemini, hf-darija) pending the week-1 benchmark (`benchmark/`) that picks the default in `config.py`.
- **Extraction** (`api/app/extraction.py`): Gemini structured output (`response_schema=ExtractedReport`) primary → Groq Llama JSON-mode fallback. Both failing raises a combined `ExtractionError` — never silent fallbacks, never invented data (prompt enforces null for absent fields).
- **Error contract**: unknown provider / bad input → 422; engine failure (`TranscriptionError`, `ExtractionError`) → 502 so n8n can catch and flag the row; transcription under 10 chars → `short_transcription` warning, not an error.
- **Schemas** (`api/app/schemas.py`): `ExtractedReport` is the data contract with n8n and the Sheet — field changes ripple to the extraction prompts, the Sheet columns, and n8n mappings.

Config is env-driven via pydantic-settings (`api/app/config.py`, reads `.env`); keys are optional at startup and checked at call time (fail loudly with a clear message).

## Conventions

- Conventional commits (`feat(api): ...`)
- French domain vocabulary in schemas/prompts (chantier, goulottes_m, resume) — it matches the cahier des charges and the Sheet; don't anglicize
- Pyright: IDE may flag false positives if not using `api/.venv`; pytest is ground truth (`api/pyrightconfig.json` points at the venv)
