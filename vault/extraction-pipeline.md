---
tags: [pfe, extraction, llm, gemini, groq, schemas]
type: technical
priority: high
status: current
---

# Extraction Pipeline

## Overview

LLM-based structured extraction: raw transcript (Darija/French/mixed) → `ExtractedReport` (see [[API Schemas]]).

**Primary:** Gemini structured output (`gemini_model` setting, currently `gemini-flash-lite-latest`)
**Fallback:** Groq Llama JSON mode (`groq_llm_model`, currently `llama-3.3-70b-versatile`)
**Never:** silent fallback, invented data — both engines failing raises a combined `ExtractionError`

Implementation: `api/app/extraction.py`.

## Pipeline flow

```
rapport_complet (text)
     │
     ▼
_extract_gemini()  ── success ──▶ ExtractedReport
     │ ExtractionError
     ▼
_extract_groq()    ── success ──▶ ExtractedReport
     │ ExtractionError
     ▼
ExtractionError("extraction failed on both engines — gemini: ... | groq: ...")
```

`extract_report()` in `extraction.py` is the entry point; `api/app/main.py` catches `ExtractionError` and turns it into an HTTP 502.

## Prompt

Single shared instruction string (`_INSTRUCTIONS` in `extraction.py`), not a separate system/few-shot pair. It tells the model:
- The text is a Moroccan cabling technician's daily report, possibly Darija/French/mixed, often from an imperfect voice transcription
- Correct plausible STT errors using domain vocabulary (goulotte, câble réseau, panneau de brassage, prise RJ45, baie, bureau, étage, chantier)
- Convert spoken numbers (in words, Arabic or French) to digits
- Absent field → `null`, never invent
- `resume`: 2-4 professional French sentences, third person, chef-de-chantier report style — always filled

There are no separate few-shot examples embedded in code; the instructions above are the entire prompt, concatenated with the transcript.

## Gemini path

```python
client.models.generate_content(
    model=settings.gemini_model,
    contents=_INSTRUCTIONS + text,
    config={"response_mime_type": "application/json", "response_schema": ExtractedReport},
)
```
Uses `response.parsed`; raises `ExtractionError` if it isn't an `ExtractedReport` instance or the API call throws.

## Groq path (fallback)

Builds a `schema_hint` from `ExtractedReport.model_json_schema()` and asks for `{"type": "json_object"}` mode:

```python
client.chat.completions.create(
    model=settings.groq_llm_model,
    response_format={"type": "json_object"},
    messages=[{"role": "system", "content": _INSTRUCTIONS + f"\nRéponds en JSON avec exactement ces clés: {schema_hint}"},
              {"role": "user", "content": text}],
)
```
Parses the response content with `ExtractedReport.model_validate_json`.

## Error handling

```python
class ExtractionError(RuntimeError):
    pass
```
No custom fields (`gemini_error`/`groq_error` attributes, `provider`, etc.) — the combined message string carries both underlying errors. No retry/backoff logic exists in `extraction.py` today; a call either succeeds or raises immediately.

## Confidence

There is no `extraction_confidence` field on `ExtractedReport` and no "high/medium/low" concept from the LLM. The only quality signals are:
- `warnings: ["short_transcription"]` — set in `main.py` when `rapport_complet` < 10 chars
- `warnings: ["low_confidence_transcription"]` — set when the STT `TranscriptionInfo.confidence` (Groq only) is below 0.5

Both live on `ProcessResponse`, not on `ExtractedReport`.

## Configuration (`api/app/config.py`)

```python
groq_api_key: Optional[str] = None
gemini_api_key: Optional[str] = None
gemini_model: str = "gemini-flash-lite-latest"
groq_llm_model: str = "llama-3.3-70b-versatile"
```
Keys optional at startup, checked at call time with a clear `ExtractionError` message (`"GEMINI_API_KEY not configured"` / `"GROQ_API_KEY not configured"`). No `EXTRACTION_TIMEOUT` or `EXTRACTION_MAX_RETRIES` settings exist.

## Testing

`api/tests/` has no dedicated `test_extraction.py` file today — extraction is exercised indirectly through `test_process_endpoint.py` (mocking `app.extraction.genai`/`groq` at the import boundary) and validated for schema shape in `test_schemas.py`. There is no golden 20-transcription dataset yet; that's part of the Sprint-1 benchmark work (see [[STT Benchmark]], PLAN.md).

## Not built yet

- Golden-set extraction accuracy eval (PLAN.md Sprint 1 exit criterion)
- Confidence calibration / "high/medium/low" bucketing on extraction
- Retry/backoff on the LLM calls
- Multi-pass or parallel sub-extraction

## Related Notes

- [[Project Overview]]
- [[Architecture]]
- [[STT Benchmark]]
- [[API Schemas]]
- [[Testing Strategy]]
