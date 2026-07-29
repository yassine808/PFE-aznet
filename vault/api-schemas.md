---
tags: [pfe, api, schemas, pydantic, contracts]
type: technical
priority: high
status: current
---

# API Schemas (Data Contracts)

## Overview

`api/app/schemas.py` is the single source of truth for data flowing between the API and n8n / the Sheet. Metadata fields (`date`, `technicien`, `lien_audio`, `canal`) are added by n8n after the API responds — the API only returns what it can derive from the audio/image/text content.

## ExtractedReport

```python
class ExtractedReport(BaseModel):
    chantier: Optional[str] = None
    client: Optional[str] = None
    type_intervention: Optional[str] = None
    equipements_conernes: Optional[str] = None
    cause_identifiee: Optional[str] = None
    actions_realisees: Optional[str] = None
    materiel_utilise: Optional[str] = None
    observations: Optional[str] = None
    resume: str
    flag_review: bool = False
    categorie: Optional[str] = None
```

A `field_validator("*", mode="before")` normalizes `"null"`/`"none"`/`""` to `None` — Groq's JSON mode occasionally emits the literal string instead of a JSON null. All fields except `resume` are optional.

Field changes ripple to:
- Extraction prompts (`api/app/prompts/extraction.md`)
- Sheet column headers (`Rapports` tab)
- n8n mappings (Set nodes in `aznet-complete.json`)

## TranscriptionInfo

```python
class TranscriptionInfo(BaseModel):
    text: str
    provider: str
    model: str
    confidence: Optional[float]  # 0-1, None if provider exposes no signal
    duration_seconds: Optional[float]
    language: Optional[str]
    processing_time: float       # wall-clock seconds
    raw_response: dict = {}
```

Only Groq derives a confidence score (from Whisper's per-segment `avg_logprob`, via `exp(avg_logprob)`); Gemini and HF Darija leave it `None`.

## ProcessResponse

```python
class ProcessResponse(BaseModel):
    rapport_complet: str
    report: ExtractedReport
    transcription: Optional[TranscriptionInfo]  # None in text mode
    warnings: List[str] = []
```

`warnings` carries:
- `"short_transcription"` — `rapport_complet` under 10 chars
- `"low_confidence_transcription"` — `transcription.confidence < 0.5` (Groq only)

## Process endpoint

`POST /process` accepts **multipart/form-data** (not JSON+base64). Parameters:

```python
async def process(
    audio: Optional[UploadFile] = File(None),     # voice note file
    image: Optional[UploadFile] = File(None),      # photo
    text: Optional[str] = Form(None),              # typed report
    provider: Optional[str] = Form(None),          # STT provider override
    correlation_id: Optional[str] = Form(None),    # UUID for log joining
    channel: Optional[str] = Form(None),           # telegram / whatsapp
    technicien: Optional[str] = Form(None),        # technician name
) -> ProcessResponse
```

Exactly one of `audio`/`image`/`text` is required (422 if zero or more than one). See [[Extraction Pipeline]] for routing logic.

## Error contract

| Condition | HTTP | Notes |
|---|---|---|
| Zero or multiple of `audio`/`image`/`text` | 422 | |
| Empty file / empty text | 422 | |
| Unknown `provider` name | 422 | `ValueError` from the registry |
| STT engine failure | 502 | `TranscriptionError` |
| Extraction failure (both engines) | 502 | `ExtractionError`, combined message |
| Transcription < 10 chars | 200 + `warnings` | Not an error, but flagged |

No separate `ErrorResponse` Pydantic model over the wire — FastAPI's `HTTPException` JSON body (`{"detail": "..."}`) is what n8n sees.

## Google Sheets row mapping

Fully implemented. n8n maps `ExtractedReport` fields + metadata (`date`, `technicien`, `lien_audio`, `canal`, `Statut`, `Message ID`, `Correlation ID`, etc.) to `Rapports` tab columns. See [[Google Sheets Integration]] for the full column mapping. The Sheet is appended via n8n's Google Sheets node (service account auth); failed writes go to a Postgres retry queue.

## French domain vocabulary

| Field | Meaning |
|---|---|
| `chantier` | Work site |
| `type_intervention` | trouble / fibre / installation / etc. |
| `equipements_conernes` | Equipment involved |
| `cause_identifiee` | Root cause |
| `actions_realisees` | Steps taken |
| `materiel_utilise` | Consumables used |
| `resume` | Professional French summary for the chef de chantier (2-4 sentences) |

**Do not anglicize** — matches the cahier des charges and the Sheet headers.

## Testing

```bash
cd api
.venv/Scripts/python.exe -m pytest tests/test_process_endpoint.py -v
.venv/Scripts/python.exe -m pytest tests/test_extraction.py -v
```

Schema validation is covered by `test_process_endpoint.py` and `test_extraction.py`.

## Related Notes

- [[Project Overview]]
- [[architecture]]
- [[Extraction Pipeline]]
- [[n8n Workflows]]
- [[Google Sheets Integration]]
- [[Testing Strategy]]
