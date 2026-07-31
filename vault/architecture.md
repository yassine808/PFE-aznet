---
tags: [pfe, architecture, api, fastapi, n8n]
type: architecture
priority: high
status: current
---

# Architecture Details

## System Boundaries

### n8n (Orchestration Layer)
**Responsibilities:**
- Telegram message reception (polling via `getUpdates` every 15s, outbound-only)
- WhatsApp message reception (webhook-driven via Tailscale Funnel)
- Voice/audio file download from both channels
- HTTP call to API `/process` (multipart form, not JSON+base64)
- Adding metadata (date, technicien, lien_audio) to the row *after* the API responds
- Google Sheets row append (via service account)
- Technician reply on originating channel (after /process succeeds)
- Error handling: any unhandled crash → `POST /logs` (`stage: workflow_error`)

**NOT responsible for:** STT processing, LLM extraction, business logic validation, email reports, scheduling — those are the API's job.

### API (AI Microservice — `api/`)
**Responsibilities:**
- `POST /process` — accepts audio, image OR text, never more than one
- `POST /daily-report` — today's Sheet rows → LLM → French manager email
- `POST /generate-image` — illustrated summary card from a report
- STT provider selection & execution (strategy pattern, `api/app/providers/`)
- LLM extraction: ranked per-modality chains (`config.py`), text alternates Groq/Gemini, image is Google-only
- Image extraction: vision model → schema directly (no intermediate transcription)
- Profile injection: technician background paragraph injected into extraction prompt
- Schema validation (`ExtractedReport`, `api/app/schemas.py`)
- Scheduled jobs: sheet-queue drain, log/sample retention, profile rebuild, daily/weekly report
- Dashboard read/write: `GET|PATCH /reports`, `GET /health`, `GET|POST /service-samples`
- Access control: `GET|POST|DELETE /technicians`, `GET /technicians/lookup`
- Auth: session-based dashboard auth with `POST /auth/login`, cookie sessions in Postgres, `X-API-Key` for n8n
- Observability: `POST|GET|DELETE /logs`, `POST /logs/claim`, `POST|GET /sheet-queue`, `PATCH /sheet-queue/{id}`

**NOT responsible for:** Telegram integration, Google Sheets append (n8n does it), metadata enrichment.

## API Design

### `POST /process`

Multipart form data — exactly one of:
```
audio: <file upload>            # voice note, optional `provider` field to override STT engine
image: <file upload>            # photo, vision model path (flag_review=true always)
text: "<raw report text>"       # typed report mode
```

Plus metadata fields for logging: `correlation_id`, `channel`, `technicien`.

### Response: `ProcessResponse`

```python
class ProcessResponse(BaseModel):
    rapport_complet: str
    report: ExtractedReport
    transcription: Optional[TranscriptionInfo]
    warnings: List[str] = []
```

## STT Provider Architecture

### Strategy pattern (`api/app/providers/`)

```
TranscriptionProvider (ABC, base.py)
    └── transcribe(audio: bytes, mime_type: str) -> TranscriptionInfo

Registry (__init__.py): @register("groq") / @register("gemini") / @register("hf-darija")
```

| Provider | Engine | Confidence | Notes |
|---|---|---|---|
| `groq` | Whisper-large-v3 (Groq free tier) | derived from `avg_logprob` | current default (`stt_provider` in config) |
| `gemini` | Gemini native audio via `gemini_model` (flash-lite) | `None` (no logprob exposed) | |
| `hf-darija` | HF Inference API Darija fine-tune | `None` | checkpoint provisional, benchmark pending |

## Extraction Pipeline

See [[Extraction Pipeline]] for full detail. Two ordered fallback chains, one per input shape (ranked 2026-07-27 by `benchmark/run_model_benchmark.py`):
- `extraction_text_chain`: `groq gpt-oss-120b` → `gemini flash-lite-latest` → `gemini 3.6-flash` (alternates vendors so free-tier quotas meter separately)
- `extraction_image_chain`: Google-only — `gemini 3.6-flash` → `gemini 3.5-flash-lite` → `gemini flash-lite-latest` (no free Groq vision model)

Profiles: one short French paragraph per technician, rebuilt nightly at 03:00, injected as labelled context into the extraction prompt.

### Error contract

| Error | HTTP | n8n handling |
|---|---|---|
| Bad input / unknown provider | 422 | Flag row |
| STT engine failure | 502 | Flag row |
| Extraction — both engines fail | 502 | Flag row |
| Short transcription (<10 chars) | 200 + `warnings` | Process anyway, flag |

## n8n Workflow (current)

Single workflow `n8n/aznet-complete.json` with two labelled bands:

| Band | Triggers | Role |
|---|---|---|
| Réception | Every 15s (TG poll), 2 WA webhooks | dedupe → access control → voice/text/image → `/process` → reply → Sheet |
| Erreurs | Error Trigger | crash → `POST /logs` |

The maintenance and daily/weekly report bands moved to the API scheduler (`api/app/jobs.py`) on 2026-07-29 — a cron node cannot show an operator what it produced or let them re-run it. After every import or API push, re-set **Settings → Error Workflow → this same workflow**: it lives in the workflow's `settings` and the public API silently drops keys it does not accept.

Legacy workflows (single-channel `legacy-*.json`) kept for reference only — never activate alongside the unified flow.

## Observability layer (PostgreSQL)

`postgres` compose service behind `api/app/logs.py`:

| Table | Role |
|---|---|
| `pipeline_logs` | one row per stage, joined by `correlation_id` |
| `processed_messages` | WhatsApp idempotency, atomic `ON CONFLICT DO NOTHING` |
| `failed_writes` | Sheet retry queue, capped at 10 attempts |
| `technicians` | Channel identity directory with active/inactive toggle |
| `service_samples` | Uptime history, written by the dashboard every minute |
| `persons` | Human identity (name, role, profile) |
| `users` + `sessions` | Dashboard accounts and session tokens |
| `app_settings` | Scheduler times, notification recipients |

Endpoints: `POST|GET|DELETE /logs`, `POST /logs/claim`, `POST|GET /sheet-queue`, `PATCH /sheet-queue/{id}`.
psycopg2 is lazy-imported, so the test suite runs with no database. Pooled connections (`ThreadedConnectionPool`, max 10).

## Scheduled jobs (API scheduler, `api/app/jobs.py`)

Five jobs, one daemon thread with a 30s tick. Times read from `app_settings` on every check:
- Sheet-queue drain (5 min)
- Log/sample retention (03:00)
- Profile rebuild (03:00)
- Daily report email (Mon–Sat, configurable time)
- Weekly report email (configurable day/time)

## Data flow diagram

```
Technician (Telegram / WhatsApp)
    │ voice note / photo / text
    ▼
n8n Reception (unified workflow)
    │ mint correlation_id → POST /logs/claim (dedupe)
    │ GET /technicians/lookup → authorized? (persons ⟷ technicians)
    │   ├─ outsider → one HR-contact reply, then silence
    │   └─ employee → download media (TG / WA) → Media or text? → Audio or image?
    ▼
POST /process (FastAPI)
    ├─ Audio → STT (Groq Whisper / Gemini / HF) → raw text
    ├─ Image → Vision model (no transcription, flag_review=true)
    └─ Text → direct extraction
    │
    ▼
LLM Extraction (ranked chains, profile context from persons.profile)
    ▼
JSON response → n8n
    ├─ ✅ Reply on originating channel (reply-first ordering)
    ├─ `Rapport exploitable ?` (has_data → no_report_content?)
    ├─ Append row → Google Sheets (Rapports tab)
    └─ (on failure) failed_writes queue → drained every 5 min

Scheduled jobs (API scheduler, jobs.py):
    ├─ sheet-queue drain (5 min) · prune logs (03:00) · profiles (03:00)
    └─ daily email (Mon–Sat) · weekly email (weekly_day/time)

Manager Dashboard (React, login required)
    ├─ GET /reports → inline corrections → PATCH /reports/{row}
    ├─ Logs n8n panel → POST|GET /logs
    ├─ Automation → GET|PUT /settings · GET /jobs · POST /jobs/{name}/run
    └─ Access control → /technicians CRUD
```

## Related Notes

- [[Project Overview]]
- [[STT Benchmark]]
- [[Extraction Pipeline]]
- [[n8n Workflows]]
- [[Google Sheets Integration]]
- [[Deployment Guide]]
