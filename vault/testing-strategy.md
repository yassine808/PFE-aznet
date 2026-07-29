---
tags: [pfe, testing, pytest, ci]
type: guide
priority: high
status: current
---

# Testing Strategy

## Approach

**No API keys, no database needed.** All tests run with mocked external services. External SDKs are lazy-imported inside functions, so module-level imports don't trigger them. Tests mock at function boundaries — individual providers, the extraction chain, Sheets.

## Test Suite

Current: **62 tests in 7 files** (`api/tests/`)

| File | Tests | What it covers |
|---|---|---|
| `test_process_endpoint.py` | 24 | `POST /process` with audio/image/text, bad inputs, error handling, warnings |
| `test_providers.py` | 9 | STT provider registry, individual provider adapters |
| `test_schemas.py` | 7 | Schema validation, null-string coercion, response shapes |
| `test_jobs.py` | 8 | Scheduler jobs, queue drain, profile rebuild |
| `test_daily_report_endpoint.py` | 4 | Email generation, date range, manager summary |
| `test_reports_endpoints.py` | 5 | `GET /reports`, `PATCH /reports/{row}` |
| `test_n8n_proxy.py` | 5 | n8n API proxy through Vite dev server |

### Running tests

```bash
cd api
.venv/Scripts/python.exe -m pytest          # all 62
.venv/Scripts/python.exe -m pytest -v        # verbose
.venv/Scripts/python.exe -m pytest tests/test_process_endpoint.py -k test_voice_mode  # single
```

### What's not tested

- **n8n workflows** — tested manually via smoke tests (see `n8n/README.md` §"Smoke test"). Node behavior is tested with real Telegram/WhatsApp messages during development
- **Performance** — no load testing (expected volume: <20 messages/day)
- **LLM output quality** — handled by the STT benchmark (`benchmark/run_benchmark.py`) and model benchmark (`benchmark/run_model_benchmark.py`), not by unit tests
- **Dashboard (React)** — no frontend tests configured (Vite dev build, no CI). The n8n proxy (`test_n8n_proxy.py`) tests the Vite dev proxy, not the React components themselves

## Test patterns

### Mocking external services

```python
# Test for STT provider (mocked at function boundary)
@patch("app.providers.groq.GroqProvider.transcribe")
def test_groq_transcription(mock_transcribe):
    mock_transcribe.return_value = TranscriptionInfo(
        text="test transcription",
        confidence=0.95,
        model="whisper-large-v3",
        duration_seconds=10.5,
        language="ar",
        processing_time=2.3,
        raw_response={}
    )
    # ...
```

### Testing without database

```python
# If DATABASE_URL is unset, logs.py prints "[logs] DISABLED" and returns safe defaults
# All log-related endpoints work with in-memory fallbacks or skip gracefully
```

## Fixtures

- `test_audio.ogg` — a real 2-second OGG Opus voice note for STT tests
- `test_image.jpg` — test image for vision extraction tests
- Test client (`TestClient(app)` from FastAPI/Starlette)

## Related
- [[Local Development]]
- [[STT Benchmark]] — quality benchmarking (pending dataset)
- [[Project Overview]]
