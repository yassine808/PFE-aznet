---
tags: [pfe, architecture, api, fastapi, n8n]
type: architecture
priority: high
status: partial
---

> **Note on status:** the system-boundary, API, STT, and extraction sections below describe what's actually built (Week 1, Jul 23 2026). The deployment, monitoring and scaling sections at the bottom describe **plans**, not running infrastructure — Vercel/VPS deployment, Prometheus/Grafana, and CI/CD do not exist in this repo yet. See PLAN.md for the real sprint timeline.

# Architecture Details

## System Boundaries

### n8n (Orchestration Layer)
**Responsibilities:**
- Telegram message reception (polling for dev; webhook for pilot, per `n8n/README.md`)
- Voice/audio file download from Telegram
- HTTP call to API `/process` (multipart form, not JSON+base64)
- Adding metadata (date, technicien, lien_audio) to the row *after* the API responds
- (Planned, not yet built) Google Sheets row append, email notification, Telegram confirmation reply

**NOT responsible for:** STT processing, LLM extraction, business logic validation — that's the API's job.

### API (AI Microservice — `api/`)
**Responsibilities:**
- Single endpoint: `POST /process` (`api/app/main.py`)
- STT provider selection & execution (strategy pattern, `api/app/providers/`)
- LLM extraction: Gemini primary → Groq fallback (`api/app/extraction.py`)
- Schema validation (`ExtractedReport`, `api/app/schemas.py`)
- Structured error contract (422 / 502)

**NOT responsible for:** Telegram integration, Google Sheets, email, metadata enrichment.

## API Design

### `POST /process`

Multipart form data — exactly one of:
```
audio: <file upload>            # + optional `provider` field to override STT engine
text: "<raw report text>"       # web form mode
```
No JSON body, no base64, no `metadata` object — n8n never sends metadata to the API.

### Response: `ProcessResponse`

```python
class ProcessResponse(BaseModel):
    rapport_complet: str
    report: ExtractedReport
    transcription: Optional[TranscriptionInfo]
    warnings: List[str] = []
```
See [[API Schemas]] for the full field list — there is no `technicien`/`date`/`type_travail`/`cables_tires`/`stt_confidence_low`/`extraction_confidence` on `ExtractedReport`; those were fabricated in an earlier version of this doc.

## STT Provider Architecture

### Strategy pattern (`api/app/providers/`)

```
TranscriptionProvider (ABC, base.py)
    └── transcribe(audio: bytes, mime_type: str) -> TranscriptionInfo

Registry (__init__.py): @register("groq") / @register("gemini") / @register("hf-darija")
```
Adapters (`groq_whisper.py`, `gemini_audio.py`, `hf_darija.py`) are imported at the bottom of `providers/__init__.py` purely to trigger their `@register` decorators.

| Provider | Engine | Confidence | Notes |
|---|---|---|---|
| `groq` | Whisper-large-v3 (Groq free tier) | derived from `avg_logprob` | current default (`stt_provider` in config) |
| `gemini` | Gemini native audio input | `None` (no logprob exposed) | |
| `hf-darija` | HF Inference API Darija fine-tune | `None` | checkpoint provisional, benchmark pending |

Selection: `settings.stt_provider` (default `"groq"`, pending the Week-1 benchmark per PLAN.md), overridable per-request via the `provider` form field.

## Extraction Pipeline

See [[Extraction Pipeline]] for full detail. Primary Gemini structured output (`response_schema=ExtractedReport`), fallback Groq JSON mode. No retries, no confidence bucketing.

### Error contract

| Error | HTTP | n8n handling (planned) |
|---|---|---|
| Bad input / unknown provider | 422 | Flag row |
| STT engine failure | 502 | Flag row |
| Extraction — both engines fail | 502 | Flag row |
| Short transcription (<10 chars) | 200 + `warnings` | Process anyway, flag |

## n8n Workflow (actual)

Only one reception path exists today: **Telegram polling** (`n8n/telegram-reception-polling.json`), plus a webhook variant (`n8n/telegram-reception.json`) targeted at the pilot. See [[n8n Workflows]] for the real node-by-node breakdown. Sheets append and email notification are **not implemented** — see TO-DO.md / PLAN.md Sprint 2.

## Data Models

Google Sheets column layout does not exist yet — no sheet has been created, no n8n Sheets node configured. Do not treat any column table as current; see [[Google Sheets Integration]] for the honest plan.

---

## Deployment Architecture (planned, not built)

Per PLAN.md: dev is Docker Compose (n8n) + local `uvicorn` for the API, with a Cloudflare tunnel (`cloudflared`) for webhook mode — **not ngrok**. Pilot target is the same Docker Compose stack on the aznet server if available, otherwise an Oracle Always Free VM. React dashboard, if built, targets Vercel free tier. None of this is provisioned yet; no `vercel.json`, no VPS, no CI/CD workflow exists in the repo.

## Security (planned)

- API keys in environment variables only (this part is real — see `api/app/config.py`)
- Everything else (webhook secret verification, service-account scoping, VPS hardening) is design intent, not implemented — see [[Security Secrets]]

## Monitoring & Observability (planned)

No metrics, dashboards, or alerting exist. See [[Monitoring Observability]] for the honest plan.

## Related Notes

- [[Project Overview]]
- [[STT Benchmark]]
- [[Extraction Pipeline]]
- [[n8n Workflows]]
- [[Google Sheets Integration]]
- [[Deployment Guide]]
