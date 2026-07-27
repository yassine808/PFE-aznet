# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PFE (end-of-studies project, deadline Aug 31 2026) at aznet.ma: voice notes in Moroccan Darija from cabling technicians (via Telegram) → STT → LLM extraction → professional French summary → Google Sheets → manager notifications. **PLAN.md is the source of truth** for architecture decisions, sprint timeline, and locked choices — read it before proposing design changes. Spec: `docs/cahier-des-charges.md`.

Zero-budget constraint: free tiers only (Groq, Gemini AI Studio, HF Inference, Telegram Bot API, Gmail SMTP, Vercel).

**Reception channels:** **both Telegram Bot API and WhatsApp Cloud API are live** (one workflow, imported from `n8n/aznet-complete.json` — reception + maintenance + daily report + error handler merged into a single file; brought up E2E 2026-07-23).

**Channel asymmetry — remember this when debugging:** Telegram *polls* (`getUpdates`, outbound, needs no tunnel); WhatsApp is *webhook-driven* and needs a public HTTPS URL. So "Telegram errors but WhatsApp is silent" means two different faults: an error reply proves the message reached the pipeline, silence means it never arrived. The public URL is a **Tailscale Funnel** (`https://<TAILSCALE_HOSTNAME>` → `127.0.0.1:5678`) — a stable hostname, so Meta is configured once and survives reboots. Telegram first (no Meta friction); WhatsApp needed a System User token (no expiry), a published app, a WABA `subscribed_apps` call, a manual GET-echo webhook (n8n's WhatsApp Trigger fails Meta's verification challenge), and media download via a plain HTTP node (native download op returns Bad request). Design is channel-agnostic — both feed one `/process` and one Sheet; the reply returns on the originating channel. Full walkthrough: `docs/setup-guide.md`.

## Commands

All Python work happens in `api/` with its venv (Python 3.9 — use `Optional[X]`, never `X | None`):

```bash
cd api
.venv/Scripts/python.exe -m pytest              # run all tests (46, no API keys and no database needed)
.venv/Scripts/python.exe -m pytest tests/test_process_endpoint.py -k test_voice_mode   # single test
.venv/Scripts/python.exe -m uvicorn app.main:app --reload   # dev server on :8000
```

Whole stack: `docker compose up -d` at repo root → n8n on http://localhost:5678, API on :8000, Postgres on :5432. All three are `restart: unless-stopped`, so the pipeline comes back on its own after a reboot. The API image is built from `api/Dockerfile`; compose overrides two env values for it — `DATABASE_URL` (host `postgres`, not `localhost`) and `GOOGLE_SERVICE_ACCOUNT_JSON` (absolute, because `sheets.py` anchors relative paths to `__file__.parents[2]`, which is `/` in the image). For API work, run `uvicorn --reload` on the host instead and set `API_BASE_URL=http://host.docker.internal:8000` so n8n reaches it. See `n8n/README.md` §7b. Telegram reception variants (polling for local dev, webhook for pilot) and smoke test: `n8n/README.md`.

Tests must pass without any API keys — external SDKs are lazy-imported inside functions and mocked at boundaries in tests. Keep it that way.

## Architecture

Hybrid: **n8n** is the glue (Telegram + WhatsApp reception → media download → HTTP call → Sheets append → notifications); **`api/`** is the custom AI microservice n8n calls. Metadata (date, technicien, canal, lien_audio) is added by n8n, not the API.

Endpoints in `api/app/main.py`: `POST /process` (core: audio, image or text → structured JSON), `POST /daily-report` (`app/daily_report.py`: today's Sheet rows → French manager email), the dashboard read/write pair `GET /reports` + `PATCH /reports/{row}` (`app/sheets.py`: service-account Sheets access, no auth — dashboard runs on the admin's PC only), `GET /health` (status + process `uptime_seconds`), `GET|PUT /settings` + `POST /notify/test` (Automation panel: trigger times, notification recipients, report format), `GET|POST|DELETE /technicians` + `/technicians/lookup` (access control), `POST|GET /service-samples` (uptime history), and the observability set `POST|GET|DELETE /logs`, `POST /logs/claim`, `POST|GET /sheet-queue` + `PATCH /sheet-queue/{id}` (`app/logs.py`, Postgres).

`/process` accepts **exactly one** of `audio`, `image` or `text` — anything else is a 422. Routing by input type happens in n8n (`Media or text?` then `Audio or image?`), never inside the API:

- **STT providers** (`api/app/providers/`): Strategy pattern. `TranscriptionProvider` ABC + `@register("name")` decorator populating a registry; adapters imported at the bottom of `providers/__init__.py` to trigger registration. Three engines (groq, gemini, hf-darija) pending the STT benchmark (`benchmark/run_benchmark.py`), which is **blocked on recording `benchmark/dataset/audio/`** — it is still empty, so `stt_provider` defaults to groq by assumption, not evidence.
- **Extraction** (`api/app/extraction.py`): ordered `provider:model` fallback chains, one per input shape (`EXTRACTION_TEXT_CHAIN`, `EXTRACTION_IMAGE_CHAIN`). The chain is tried left to right and returns which model answered; all of them failing raises a combined `ExtractionError` — never silent fallbacks, never invented data (prompt enforces null for absent fields). Rank models with `benchmark/run_model_benchmark.py`, and note that **being in `GET /models` does not mean a model is callable**: the 2026-07-27 run found `gemini-2.5-flash` 404ing and `gemini-3.5-flash` 503ing on every call. The text chain alternates vendors on purpose (Gemini and Groq meter free tiers separately); the image chain is Google-only because the free Groq catalogue has no vision model.
- **Image path**: the vision model reads the photo and fills the schema in one call — there is no intermediate transcription. `rapport_complet` gets the model's own summary prefixed `[photo] ` so it is never mistaken for a quote, and the row is always `flag_review=true`.
- **Error contract**: unknown provider / bad input → 422; engine failure (`TranscriptionError`, `ExtractionError`) → 502 so n8n can catch and flag the row; transcription under 10 chars → `short_transcription` warning, not an error.
- **Observability** (`api/app/logs.py`): PostgreSQL (compose service `postgres`) holding `pipeline_logs`, `processed_messages` (WhatsApp idempotency), `failed_writes` (Sheet retry queue), `technicians` (access control), `service_samples` (uptime history) and `app_settings`. n8n POSTs one row per stage; the API logs its own errors with the same `correlation_id`, so both processes join into one timeline in the dashboard's **Logs n8n** panel. Deliberately not the Sheet — a Sheets-backed log goes blind during a Sheets outage. `psycopg2` is lazy-imported and pooled; if `DATABASE_URL` is unset the API prints `[logs] DISABLED` and keeps serving.
- **Reply-first ordering**: in `n8n/reception-unified.json` the reply to the technician happens *before* the Sheet append. A failed write parks in `failed_writes` and is drained by `n8n/maintenance-cron.json`; it never costs the technician their summary. Do not reorder these nodes back.
- **Schemas** (`api/app/schemas.py`): `ExtractedReport` is the data contract with n8n and the Sheet — field changes ripple to the extraction prompts, the Sheet columns, and n8n mappings.

Config is env-driven via pydantic-settings (`api/app/config.py`, reads `.env`); keys are optional at startup and checked at call time (fail loudly with a clear message).

## Conventions

- Conventional commits (`feat(api): ...`)
- French domain vocabulary in schemas/prompts (chantier, goulottes_m, resume) — it matches the cahier des charges and the Sheet; don't anglicize
- Dashboard lives in **`Dashboard/`** (`web/` was deleted and rebuilt from scratch 2026-07-26 — do not resurrect it). Vite + React 19 + **Tailwind v4**, so there is **no `tailwind.config.js`**: the whole token layer is CSS-first in `src/index.css` (`@theme` holds the raw OKLCH ramp, `@theme inline` maps semantic names onto CSS vars that `:root`/`.dark` redefine). No shadcn, no Recharts — charts are hand-built SVG/CSS, animation is `motion/react`, icons are Phosphor (**the `*Icon` suffix is required**; bare names are deprecated). `@/` is aliased to `src` in **both** `vite.config.ts` and `tsconfig.json`. Design intent and its named rules: `DESIGN.md`, `PRODUCT.md`.
- **All UI copy lives in `Dashboard/src/locales/{fr,en,ar}.json`** (fr is the reference/fallback) — never hardcode strings in components; add the key to all three files. Arabic drives RTL, so use logical properties (`ms-`/`me-`/`start`/`end`), never `ml-`/`mr-`.
- Dashboard data flow: `useApi(key, fetcher, pollMs)` in `src/lib/api.ts` reads through a **module-level cache**, so navigating away and back repaints instantly and revalidates in the background — without it every panel reloads from a blank state. Ops polling and the uptime sampler live in `OpsProvider` *above* the router (`src/lib/ops-context.tsx`); moving them into a page stops them on navigation and leaves fake gaps in the uptime history. Perpetual motion (status pulse, breathing glow) is CSS keyframes, not React state, so re-renders cannot restart it. Metrics are computed client-side from `/reports`; only uptime comes from `/health` + `/service-samples`.
- n8n's API is reached through the Vite dev proxy (`/n8n`), which attaches `X-N8N-API-KEY` server-side — the key lives in `Dashboard/.env` **without** a `VITE_` prefix so it never reaches client JS. That also means n8n panels only work under `npm run dev`.
- Pyright: IDE may flag false positives if not using `api/.venv`; pytest is ground truth (`api/pyrightconfig.json` points at the venv)
