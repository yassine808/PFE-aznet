---
tags: [pfe, testing, pytest, ci, coverage, tdd]
type: technical
priority: high
status: partial
---

# Testing Strategy

> **Reality check (2026-07-23):** this doc previously described a test suite, mocking fixtures, and CI pipeline that were never built. Corrected below to match what actually exists: 3 test files, 33 tests, no `conftest.py`, no CI. The code blocks under "Key Test Patterns" / "Extraction Tests" / "Provider Tests" / "Schema Tests" / "CI Configuration" further down are **illustrative/aspirational only** — they reference modules, classes, and fixtures (`GroqProvider`, `ProcessVoiceRequest`, `conftest.py` fixtures, `.github/workflows/test.yml`) that do not exist in this repo. Treat them as a possible future direction, not documentation of current behavior.

## Overview

All tests run **without API keys** — external SDKs (`groq`, `google.genai`) are lazy-imported inside functions and mocked at their import boundary in tests (e.g. `unittest.mock.patch("app.extraction.genai")`). There is **no CI pipeline** configured (no `.github/workflows/` at all) — tests currently run manually / locally only.

---

## Test Structure (actual)

```
api/
└── tests/
    ├── __init__.py
    ├── test_process_endpoint.py  # /process endpoint, voice + text mode, error contract
    ├── test_providers.py         # STT provider registry + adapters
    └── test_schemas.py           # ExtractedReport / ProcessResponse validation
```

No `conftest.py`, no `test_extraction.py`, no `test_config.py`, no `tests/test_providers/` subpackage, no `requirements-dev.txt` (dev deps live in `api/requirements.txt` alongside runtime deps) — none of that exists yet.

---

## Running Tests

```bash
cd api

# All tests (33 tests, ~1s)
.venv/Scripts/python.exe -m pytest

# Single test file
.venv/Scripts/python.exe -m pytest tests/test_process_endpoint.py -v

# Single test
.venv/Scripts/python.exe -m pytest tests/test_process_endpoint.py::test_voice_mode_success -v

# With coverage
.venv/Scripts/python.exe -m pytest --cov=app --cov-report=term-missing

# Verbose + show slowest
.venv/Scripts/python.exe -m pytest -v --durations=10
```

---

## Test Categories

No pytest markers are used in this repo (no `@pytest.mark.unit` etc.) — tests are organized purely by file: endpoint tests, provider tests, schema tests. The table below (unit/integration/contract split with marker counts) does not reflect actual code and should be treated as aspirational.

---

## Key Test Patterns

### Mocking External Providers

```python
# conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_groq_client():
    with patch("app.providers.groq.Groq") as mock:
        client = MagicMock()
        client.audio.transcriptions.create = AsyncMock(
            return_value=MagicMock(text="Transcribed text")
        )
        mock.return_value = client
        yield client

@pytest.fixture
def mock_gemini_model():
    with patch("app.extraction.genai.GenerativeModel") as mock:
        model = MagicMock()
        model.generate_content = AsyncMock(
            return_value=MagicMock(
                text='{"technicien": "Ahmed", "chantier": "Hay Riad"}'
            )
        )
        mock.return_value = model
        yield model
```

### Testing the `/process` Endpoint

```python
# test_process_endpoint.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_voice_mode_success(mock_groq_client, mock_gemini_model):
    """Voice mode: audio → STT → Extraction → Report"""
    audio_b64 = "UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQ=="
    
    response = client.post("/process", json={
        "audio": audio_b64,
        "metadata": {
            "date": "2026-07-23",
            "technicien": "Ahmed",
            "lien_audio": "https://api.telegram.org/file/bot123/voice.ogg"
        }
    })
    
    assert response.status_code == 200
    data = response.json()
    assert "extracted_report" in data
    assert data["extracted_report"]["technicien"] == "Ahmed"
    assert "processing_time_ms" in data

def test_text_mode_success(mock_gemini_model):
    """Text mode: direct text → Extraction → Report"""
    response = client.post("/process", json={
        "text": "Bonjour c'est Ahmed, chantier Hay Riad...",
        "metadata": {"date": "2026-07-23", "technicien": "Ahmed"}
    })
    
    assert response.status_code == 200
    assert response.json()["transcription"] is None  # Text mode

def test_voice_mode_short_transcription_warning(mock_groq_client, mock_gemini_model):
    """Short transcription (<10 chars) → warning but not error"""
    mock_groq_client.audio.transcriptions.create.return_value = MagicMock(text="Ok")
    
    response = client.post("/process", json={...})
    
    assert response.status_code == 200
    assert "short_transcription" in response.json()["warnings"]

def test_bad_input_returns_422():
    """Missing both audio and text → 422"""
    response = client.post("/process", json={"metadata": {...}})
    assert response.status_code == 422
```

---

## Extraction Tests

```python
# test_extraction/test_extraction.py
import pytest
from app.extraction import extract_report, ExtractionError

class TestExtraction:
    @pytest.mark.asyncio
    async def test_gemini_success(self, mock_gemini_model):
        result = await extract_report("Transcription text here")
        
        assert result.provider == "gemini"
        assert result.report.technicien == "Ahmed"
        assert result.confidence == "high"
    
    @pytest.mark.asyncio
    async def test_gemini_fails_groq_succeeds(self, mock_gemini_model, mock_groq_client):
        mock_gemini_model.generate_content.side_effect = Exception("API Error")
        mock_groq_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"technicien": "Ahmed"}'))]
        )
        
        result = await extract_report("Text")
        
        assert result.provider == "groq"
    
    @pytest.mark.asyncio
    async def test_both_fail_raises_extraction_error(self, mock_gemini_model, mock_groq_client):
        mock_gemini_model.generate_content.side_effect = Exception("Gemini down")
        mock_groq_client.chat.completions.create.side_effect = Exception("Groq down")
        
        with pytest.raises(ExtractionError) as exc:
            await extract_report("Text")
        
        assert "Gemini" in str(exc.value)
        assert "Groq" in str(exc.value)
```

---

## Provider Tests

```python
# test_providers/test_groq.py
import pytest
from app.providers.groq import GroqProvider
from app.providers.base import TranscriptionError

class TestGroqProvider:
    @pytest.mark.asyncio
    async def test_transcribe_success(self, mock_groq_client):
        provider = GroqProvider()
        result = await provider.transcribe(b"audio_data")
        
        assert result.text == "Transcribed text"
        assert result.provider == "groq"
    
    @pytest.mark.asyncio
    async def test_transcribe_api_error(self, mock_groq_client):
        mock_groq_client.audio.transcriptions.create.side_effect = Exception("Rate limited")
        
        provider = GroqProvider()
        with pytest.raises(TranscriptionError) as exc:
            await provider.transcribe(b"audio")
        
        assert exc.value.provider == "groq"
```

---

## Schema Tests

```python
# test_schemas.py
from app.schemas import ExtractedReport, ProcessVoiceRequest, ProcessTextRequest
from pydantic import ValidationError

class TestSchemas:
    def test_extracted_report_minimal(self):
        """All fields optional — empty dict valid"""
        report = ExtractedReport()
        assert report.technicien is None
        assert report.problemes == []
    
    def test_extracted_report_full(self):
        report = ExtractedReport(
            technicien="Ahmed",
            date="2026-07-23",
            goulottes_m="45",
            problemes=["Gaine bouchée"],
            extraction_confidence="high"
        )
        assert report.technicien == "Ahmed"
        assert report.extraction_confidence == "high"
    
    def test_process_request_xor_validation(self):
        """Exactly one of audio or text required"""
        # Valid: audio only
        req = ProcessVoiceRequest(audio="b64", metadata={...})
        assert req.audio == "b64"
        
        # Valid: text only
        req = ProcessTextRequest(text="hello", metadata={...})
        assert req.text == "hello"
        
        # Invalid: neither
        with pytest.raises(ValidationError):
            ProcessVoiceRequest(metadata={...})  # No audio
        
        # Invalid: both (if using union)
        # Handled at endpoint level
```

---

## CI Configuration

```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [main, telegram-input-approach]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ./api
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.9"
          cache: "pip"
          cache-dependency-path: api/requirements.txt
      
      - name: Install dependencies
        run: |
          python -m venv .venv
          .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
      
      - name: Run tests
        run: .venv/bin/python -m pytest -v --tb=short
      
      - name: Check coverage
        run: .venv/bin/python -m pytest --cov=app --cov-fail-under=80
```

---

## Coverage Targets

No coverage tooling (`pytest-cov`) is configured or run in this repo — the table below is aspirational, not a measured result.

| Module | Target | Current |
|--------|--------|---------|
| `app/main.py` | 90% | not measured |
| `app/extraction.py` | 85% | not measured |
| `app/providers/` | 80% | not measured |
| `app/schemas.py` | 95% | not measured |
| `app/config.py` | 80% | not measured |
| **Overall** | **80%** | **not measured** |

---

## TDD Workflow

1. **Write failing test** for new behavior
2. **Run test** → confirm red
3. **Implement minimal code** to pass
4. **Run test** → confirm green
5. **Refactor** if needed
6. **Commit** test + implementation together

### Example: Adding New STT Provider

```bash
# 1. Create test file
touch api/tests/test_providers/test_new_provider.py

# 2. Write test for provider interface
# 3. Run: pytest tests/test_providers/test_new_provider.py -v
# 4. Implement provider in app/providers/new_provider.py
# 5. Register in app/providers/__init__.py
# 6. Run all tests
# 7. Add to benchmark
```

---

## Debugging Tests

```bash
# Drop into debugger on failure
.venv/Scripts/python.exe -m pytest tests/test_process_endpoint.py::test_voice_mode_success -v --pdb

# Show print output
.venv/Scripts/python.exe -m pytest -v -s

# Run single test with max verbosity
.venv/Scripts/python.exe -m pytest tests/test_extraction/test_extraction.py::TestExtraction::test_gemini_success -vvv
```

---

## Test Data

### Fixtures Location

```
api/tests/fixtures/
├── audio_samples/          # Base64 encoded test audio (small)
├── transcriptions/         # Expected STT outputs
├── extracted_reports/      # Expected extraction outputs
└── api_responses/          # Full API response examples
```

### Generating Fixtures

```python
# scripts/generate_fixtures.py (run manually with API keys)
import base64
from app.providers.groq import GroqProvider

provider = GroqProvider()
with open("test_audio.ogg", "rb") as f:
    audio = f.read()

result = await provider.transcribe(audio)
with open("tests/fixtures/transcriptions/sample1.json", "w") as f:
    json.dump(result.model_dump(), f)
```

---

## Related Notes

- [[Project Overview]]
- [[Architecture]]
- [[Extraction Pipeline]]
- [[API Schemas]]
- [[CI/CD Pipeline]]