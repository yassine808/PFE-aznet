---
tags: [pfe, api, schemas, pydantic, contracts]
type: technical
priority: high
status: current
---

# API Schemas (Data Contracts)

## Overview

`api/app/schemas.py` defines the **single source of truth** for data flowing between:
- n8n workflows (input/output)
- API endpoint `/process`
- Google Sheets columns
- Manager notifications

**Rule:** Any field change ripples to extraction prompts, Sheets mapping, n8n functions, and tests.

---

## Core Schema: ExtractedReport

```python
# api/app/schemas.py
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import date

class ExtractedReport(BaseModel):
    """Structured extraction output — matches Google Sheets columns"""
    
    # Identity (from metadata or extraction)
    technicien: Optional[str] = Field(None, description="Nom du technicien")
    date: Optional[date] = Field(None, description="Date d'intervention (YYYY-MM-DD)")
    chantier: Optional[str] = Field(None, description="Nom/Lieu du chantier")
    
    # Work classification
    type_travail: Optional[str] = Field(None, description="Type: tirage, pose, raccordement, maintenance")
    
    # Quantities (French vocab per cahier des charges)
    goulottes_m: Optional[str] = Field(None, description="Mètres de goulottes posées")
    cables_tires: Optional[str] = Field(None, description="Câbles tirés (ex: 'FO 12 fibres, CU 4 paires')")
    equipements_poses: Optional[str] = Field(None, description="Équipements posés (boîtiers, prises, etc.)")
    
    # Issues & observations
    problemes: Optional[List[str]] = Field(default_factory=list, description="Liste des problèmes rencontrés")
    observations: Optional[str] = Field(None, description="Observations libres")
    
    # Summary (French, professional)
    resume: Optional[str] = Field(None, description="Résumé professionnel en français pour le manager")
    
    # Quality flags (added by API, not extracted)
    stt_confidence_low: bool = Field(False, description="Transcription < 10 chars — review audio")
    extraction_confidence: str = Field("medium", description="high | medium | low")
    
    class Config:
        json_schema_extra = {
            "example": {
                "technicien": "Ahmed Benali",
                "date": "2026-07-23",
                "chantier": "Hay Riad - Lot 45",
                "type_travail": "tirage",
                "goulottes_m": "45",
                "cables_tires": "FO 12 fibres + CU 4 paires",
                "equipements_poses": "2 boîtiers de raccordement, 4 prises optiques",
                "problemes": ["Gaine bouchée au regard 3", "Accès difficile parking sous-sol"],
                "observations": "Client absent, clé laissée chez gardien",
                "resume": "Tirage FO 12 fibres et CU 4 paires sur 45m goulottes. 2 boîtiers et 4 prises posées. Gaine bouchée au regard 3 résolue par nettoyage. Accès parking difficile.",
                "stt_confidence_low": false,
                "extraction_confidence": "high"
            }
        }
```

---

## API Request/Response Schemas

### Request: Voice Mode

```python
class ProcessVoiceRequest(BaseModel):
    audio: str = Field(..., description="Base64 encoded audio (ogg/opus/mp3/wav)")
    metadata: ReportMetadata = Field(..., description="Enriched by n8n")
    
    class Config:
        json_schema_extra = {
            "example": {
                "audio": "UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQ...",
                "metadata": {
                    "date": "2026-07-23",
                    "technicien": "Ahmed",
                    "lien_audio": "https://api.telegram.org/file/bot123/voice.ogg"
                }
            }
        }
```

### Request: Text Mode (Web Form)

```python
class ProcessTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=50000, description="Transcribed text")
    metadata: ReportMetadata = Field(...)
    
    class Config:
        json_schema_extra = {
            "example": {
                "text": "Bonjour, c'est Ahmed. Aujourd'hui chantier Hay Riad...",
                "metadata": {
                    "date": "2026-07-23",
                    "technicien": "Ahmed",
                    "chantier": "Hay Riad",
                    "lien_audio": ""
                }
            }
        }
```

### Unified Request (Discriminated Union)

```python
from typing import Union

ProcessRequest = Union[ProcessVoiceRequest, ProcessTextRequest]
```

### Metadata Schema

```python
class ReportMetadata(BaseModel):
    date: date = Field(..., description="Date intervention (YYYY-MM-DD)")
    technicien: str = Field(..., min_length=1, max_length=100)
    chantier: Optional[str] = Field(None, max_length=200)
    lien_audio: Optional[str] = Field(None, description="URL audio Telegram")
    telegram_message_id: Optional[int] = None
    telegram_user_id: Optional[int] = None
    source: str = Field("telegram", description="telegram | webform | manual")
```

### Response Schema

```python
class ProcessResponse(BaseModel):
    extracted_report: ExtractedReport
    transcription: Optional[str] = Field(None, description="Raw STT output (voice mode only)")
    warnings: List[str] = Field(default_factory=list, description="Non-blocking warnings")
    processing_time_ms: int = Field(..., description="Total processing time")
    
    class Config:
        json_schema_extra = {
            "example": {
                "extracted_report": { ... },  # ExtractedReport example
                "transcription": "Bonjour c'est Ahmed, aujourd'hui chantier Hay Riad...",
                "warnings": ["short_transcription"],
                "processing_time_ms": 4200
            }
        }
```

---

## Error Schemas

```python
class ErrorResponse(BaseModel):
    error: str = Field(..., description="Error code: validation_error | transcription_error | extraction_error")
    message: str = Field(..., description="Human-readable message")
    details: Optional[dict] = Field(None, description="Additional context")

# HTTP Status Mapping:
# 422 → validation_error (bad input, unknown provider)
# 502 → transcription_error / extraction_error (engine failure)
# 500 → unexpected (should not happen)
```

---

## STT Provider Schemas

```python
class TranscriptionResult(BaseModel):
    text: str = Field(..., description="Transcribed text")
    language: Optional[str] = Field(None, description="Detected language code")
    duration_seconds: Optional[float] = None
    provider: str = Field(..., description="groq | gemini | hf-darija")

class TranscriptionError(Exception):
    def __init__(self, message: str, provider: str, original_error: Exception):
        self.message = message
        self.provider = provider
        self.original_error = original_error
        super().__init__(f"{provider}: {message}")
```

---

## Extraction Schemas

```python
class ExtractionResult(BaseModel):
    report: ExtractedReport
    provider: str = Field(..., description="gemini | groq")
    confidence: str = Field("medium", description="high | medium | low")
    raw_response: Optional[str] = None  # For debugging

class ExtractionError(Exception):
    def __init__(self, message: str, provider: str, original_error: Exception, gemini_error: Optional[Exception] = None, groq_error: Optional[Exception] = None):
        self.message = message
        self.provider = provider
        self.original_error = original_error
        self.gemini_error = gemini_error
        self.groq_error = groq_error
        # Combined message for 502 response
        details = []
        if gemini_error: details.append(f"Gemini: {gemini_error}")
        if groq_error: details.append(f"Groq: {groq_error}")
        super().__init__(f"Extraction failed ({provider}): {message}. {'; '.join(details)}")
```

---

## Google Sheets Row Mapping

```python
# n8n function: Parse Response → Sheets Row
def report_to_sheets_row(report: ExtractedReport, metadata: ReportMetadata, warnings: List[str]):
    return {
        "date": report.date or metadata.date,
        "technicien": report.technicien or metadata.technicien,
        "chantier": report.chantier or metadata.chantier or "",
        "type_travail": report.type_travail or "",
        "goulottes_m": report.goulottes_m or "",
        "cables_tires": report.cables_tires or "",
        "equipements_poses": report.equipements_poses or "",
        "problemes": json.dumps(report.problemes or []),
        "observations": report.observations or "",
        "resume": report.resume or "",
        "lien_audio": metadata.lien_audio or "",
        "stt_confidence_low": report.stt_confidence_low,
        "extraction_confidence": report.extraction_confidence,
        "telegram_message_id": metadata.telegram_message_id,
        "created_at": datetime.utcnow().isoformat(),
        "source": metadata.source,
        "status": "warning" if "short_transcription" in warnings else "ok"
    }
```

---

## Field Definitions (French Domain Vocab)

| Field | French Term | English | Notes |
|-------|-------------|---------|-------|
| `chantier` | Chantier | Work site | Location name |
| `goulottes_m` | Goulottes (m) | Cable trays (meters) | Linear meters installed |
| `cables_tires` | Câbles tirés | Cables pulled | Type + quantity |
| `equipements_poses` | Équipements posés | Equipment installed | Boîtiers, prises, etc. |
| `type_travail` | Type de travail | Work type | tirage / pose / raccordement / maintenance |
| `problemes` | Problèmes | Issues | Array of strings |
| `resume` | Résumé | Summary | Professional French for manager |

**Do not anglicize** — matches cahier des charges & Sheets headers.

---

## Versioning Strategy

| Change Type | Action |
|-------------|--------|
| Add optional field | Safe — deploy API first, then n8n |
| Add required field | Breaking — coordinate deploy |
| Rename field | Breaking — use alias + deprecation |
| Change type | Breaking — validate n8n & Sheets |
| Remove field | Breaking — archive in Sheets first |

**Current version:** `v1` (implicit, no version in schema yet)

---

## Validation Rules

### API Input Validation
- `audio`: Valid base64, max 25MB (Telegram limit)
- `text`: 1-50000 chars
- `metadata.date`: Valid date, not future
- `metadata.technicien`: 1-100 chars
- Exactly one of `audio` OR `text` (xor)

### Extraction Output Validation
- `extraction_confidence` ∈ {high, medium, low}
- `problemes` = array (empty ok)
- `date` = valid ISO date if present
- `goulottes_m` = numeric string if present

---

## Testing Schema Changes

```bash
# 1. Update schemas.py
# 2. Run tests (validates serialization)
cd api && .venv/Scripts/python.exe -m pytest tests/test_schemas.py -v

# 3. Check n8n function compatibility
# 4. Test Sheets append with sample data
# 5. Verify email template renders
```

---

## Related Notes

- [[Project Overview]]
- [[Architecture]]
- [[Extraction Pipeline]]
- [[n8n Workflows]]
- [[API Endpoint]]
- [[Testing Strategy]]