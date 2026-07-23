---
tags: [pfe, extraction, llm, gemini, groq, schemas]
type: technical
priority: high
status: current
---

# Extraction Pipeline

## Overview

LLM-based structured extraction from Darija transcript → Professional French report (`ExtractedReport` schema).

**Primary:** Gemini 1.5 Flash (structured output)  
**Fallback:** Groq Llama-3.1-70B (JSON mode)  
**Never:** Silent fallback, invented data

## Pipeline Flow

```
Transcription (Darija text)
         │
         ▼
┌─────────────────────┐
│  Build Prompt       │
│  - Schema context   │
│  - Few-shot examples│
│  - Null enforcement │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Gemini Structured  │──── Success ──▶ ExtractedReport
│  Output             │
└─────────┬───────────┘
          │ Failure
          ▼
┌─────────────────────┐
│  Groq JSON Mode     │──── Success ──▶ ExtractedReport
└─────────┬───────────┘
          │ Failure
          ▼
    ExtractionError (502)
```

## Prompt Engineering

### System Prompt (Gemini)

```python
SYSTEM_PROMPT = """Tu es un extracteur de rapports techniques pour techniciens câbleurs au Maroc.

RÈGLES STRICTES:
1. Extrais UNIQUEMENT ce qui est explicitement dit. Si absent → null.
2. JAMAIS d'invention, JAMAIS de déduction.
3. "resume" : français professionnel, style rapport d'intervention.
4. Termes techniques en français : goulotte, câble, tirage, pose, chantier.
5. Confiance extraction : "high"/"medium"/"low" selon clarté audio.

SCHÉMA: ExtractedReport (tous champs optionnels)"""
```

### Few-Shot Examples (3)

```python
EXAMPLES = [
    {
        "input": "Salam, aujourd'hui 23 juillet, chantier Hay Riad. On a tiré 150m goulotte, posé 5 boîtes. Problème: goulotte cassée à l'entrée.",
        "output": {
            "technicien": None, "date": "2026-07-23", "chantier": "Hay Riad",
            "type_travail": "tirage", "goulottes_m": 150.0, "cables_tires": None,
            "equipements_poses": 5, "problemes": ["goulotte cassée à l'entrée"],
            "observations": None, "resume": "Tirage de 150m de goulotte et pose de 5 boîtes au chantier Hay Riad. Incident: goulotte endommagée à l'entrée.",
            "stt_confidence_low": False, "extraction_confidence": "high"
        }
    },
    # ... 2 more examples
]
```

### User Prompt Template

```python
USER_PROMPT = f"""Transcription (Darija):
{transcription}

Extrais le rapport structuré. Champs absents = null."""
```

## Schema: ExtractedReport

```python
class ExtractedReport(BaseModel):
    # Identification (from metadata + extraction)
    technicien: Optional[str] = None
    date: Optional[str] = None          # YYYY-MM-DD
    chantier: Optional[str] = None
    
    # Work performed
    type_travail: Optional[str] = None  # "tirage" | "pose" | "maintenance" | "reparation"
    goulottes_m: Optional[float] = None
    cables_tires: Optional[int] = None
    equipements_poses: Optional[int] = None
    
    # Issues & observations
    problemes: List[str] = Field(default_factory=list)
    observations: Optional[str] = None
    
    # Professional summary (French)
    resume: Optional[str] = None
    
    # Confidence flags
    stt_confidence_low: bool = False
    extraction_confidence: Literal["high", "medium", "low"] = "medium"
```

**Field Notes:**
- All optional → LLM can return null
- `problemes` = array (multiple issues possible)
- `resume` = generated French paragraph
- Confidence fields help downstream filtering

## Error Handling

### ExtractionError
```python
class ExtractionError(Exception):
    def __init__(self, primary_error: str, fallback_error: str):
        self.primary_error = primary_error    # Gemini error
        self.fallback_error = fallback_error  # Groq error
        super().__init__(f"Both providers failed. Gemini: {primary_error} | Groq: {fallback_error}")
```

### Retry Logic
- Gemini: 2 retries, exponential backoff (1s, 2s)
- Groq: 1 retry, 2s backoff
- Total timeout: 30s

## Confidence Scoring

### STT Confidence (set by API)
```python
if len(transcription.strip()) < 10:
    result.stt_confidence_low = True
    result.metadata["stt_warning"] = "short_transcription"
```

### Extraction Confidence (set by LLM)
- **high**: Clear transcription, all key fields extracted
- **medium**: Some ambiguity, partial extraction
- **low**: Noisy transcription, many nulls, contradictory info

## Testing Strategy

### Unit Tests (`tests/test_extraction.py`)
- Mock Gemini & Groq clients
- Test prompt construction
- Test schema validation
- Test error propagation

### Integration Tests
- Real API calls (optional, requires keys)
- Golden dataset: 20 transcriptions → expected reports

### Test Cases
| Input Type | Expected Behavior |
|------------|-------------------|
| Clean, complete | All fields populated, high confidence |
| Partial info | Present fields filled, rest null |
| Noisy/garbled | Low confidence, minimal extraction |
| Empty/short | stt_confidence_low=true, low extraction |
| Technical terms | Correct French terminology |

## Configuration

```python
# api/app/config.py
class Settings(BaseSettings):
    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    
    EXTRACTION_TIMEOUT: int = 30
    GEMINI_MODEL: str = "gemini-1.5-flash"
    GROQ_MODEL: str = "llama-3.1-70b-versatile"
    
    EXTRACTION_MAX_RETRIES: int = 2
```

## API Key Management

- Keys optional at startup (checked at call time)
- Clear error if missing: `"GEMINI_API_KEY not configured"`
- No keys in logs, no keys in repo

## Future Improvements

1. **Fine-tuned Darija model** for extraction (if budget allows)
2. **Confidence calibration** with human labels
3. **Multi-pass extraction** for complex notes
4. **Schema versioning** for backward compatibility

## Related Notes

- [[Project Overview]]
- [[Architecture]]
- [[STT Benchmark]]
- [[API Schemas]]
- [[Testing Strategy]]