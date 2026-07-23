---
tags: [pfe, api, schemas, pydantic, contracts]
type: technical
priority: high
status: current
---

# API Schemas (Data Contracts)

## Overview

`api/app/schemas.py` is the single source of truth for data flowing between the API, n8n, and (eventually) the Google Sheet. Metadata fields (`date`, `heure`, `technicien`, `lien_audio`) are **not** part of these schemas — n8n adds them to the Sheets row itself, from the Telegram message context, after the API responds. The API only returns what it can derive from the audio/text content.

## `ExtractedReport`

```python
class ExtractedReport(BaseModel):
    chantier: Optional[str] = None
    client: Optional[str] = None
    type_activite: Optional[str] = None       # ex: câblage, finition
    goulottes_m: Optional[float] = None       # >= 0
    cables_m: Optional[float] = None          # >= 0
    bureaux_termines: Optional[int] = None    # >= 0
    panneaux_raccordes: Optional[int] = None  # >= 0
    autres_travaux: Optional[str] = None
    observations: Optional[str] = None
    resume: str                               # required, 2-4 phrases FR
```

A `field_validator("*", mode="before")` normalizes the *string* `"null"`/`"none"`/`""` to `None` — Groq's JSON mode occasionally emits the literal string instead of a JSON null.

All fields except `resume` are optional; the extraction prompt enforces `null` for anything not explicitly stated (never invented).

## `TranscriptionInfo`

```python
class TranscriptionInfo(BaseModel):
    text: str
    provider: str
    latency_s: float           # >= 0
    confidence: Optional[float]  # 0-1, None if the provider exposes no signal
```

Only Groq derives a confidence score (from Whisper's per-segment `avg_logprob`, via `exp(avg_logprob)`); Gemini and HF Darija leave it `None` — no fabricated numbers.

## `ProcessResponse`

```python
class ProcessResponse(BaseModel):
    rapport_complet: str                  # raw transcription or form text
    report: ExtractedReport
    transcription: Optional[TranscriptionInfo]  # None in text mode
    warnings: List[str] = []
```

`warnings` currently carries two values, both set in `api/app/main.py`:
- `"short_transcription"` — `rapport_complet` under 10 chars
- `"low_confidence_transcription"` — `transcription.confidence < 0.5` (Groq only)

## What the API does NOT define

There is no `ProcessVoiceRequest`/`ProcessTextRequest`/`ReportMetadata` model — the `/process` endpoint (`api/app/main.py`) takes plain FastAPI `File`/`Form` parameters directly:

```python
async def process(
    audio: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    provider: Optional[str] = Form(None),
) -> ProcessResponse
```

Request body is **multipart/form-data**, not JSON+base64. Exactly one of `audio`/`text` is required (422 if both or neither are present).

## Error contract

| Condition | HTTP | Notes |
|---|---|---|
| Neither/both of `audio`/`text` | 422 | |
| Empty audio file / empty text | 422 | |
| Unknown `provider` name | 422 | `ValueError` from the registry |
| STT engine failure | 502 | `TranscriptionError` |
| Extraction failure (both Gemini and Groq) | 502 | `ExtractionError`, combined message |
| Transcription < 10 chars | 200 + `warnings` | not an error |

There is no separate `ErrorResponse`/`TranscriptionError`/`ExtractionError` Pydantic model exposed over the wire — FastAPI's default `HTTPException` JSON body (`{"detail": "..."}`) is what n8n sees.

## Google Sheets row mapping

Not implemented yet (Week 1, per PLAN.md — n8n Sheets append is a Sprint 2 item, see TO-DO.md). No column mapping code or n8n function exists in the repo today. When it lands, it will map `ExtractedReport` fields + n8n-added metadata (`date`, `technicien`, `lien_audio`) directly — do not invent a richer intermediate schema ahead of that work.

## French domain vocabulary

| Field | Meaning |
|---|---|
| `chantier` | Work site |
| `goulottes_m` | Cable trays, meters |
| `cables_m` | Network cable, meters |
| `bureaux_termines` | Offices completed |
| `panneaux_raccordes` | Patch panels wired |
| `autres_travaux` | Work not covered by the standard quantities |
| `resume` | Professional French summary for the chef de chantier |

**Do not anglicize** — matches the cahier des charges and (future) Sheet headers.

## Testing schema changes

```bash
cd api
.venv/Scripts/python.exe -m pytest tests/test_schemas.py -v
```

`api/tests/test_schemas.py` covers the null-string coercion, numeric-string coercion, and both response shapes (voice mode with `transcription`, text mode without).

## Related Notes

- [[Project Overview]]
- [[Architecture]]
- [[Extraction Pipeline]]
- [[n8n Workflows]]
- [[Testing Strategy]]
