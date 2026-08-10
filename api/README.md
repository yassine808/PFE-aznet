# AI Service (FastAPI) — Sprint 1

The coded brain of the pipeline. Exposes `/process`:

- input: audio file (voice note) **or** raw text (web form mode)
- pipeline: `TranscriptionProvider` (adapters: groq / gemini / local) → LLM extraction to Pydantic schema (14 cahier fields) → professional French reformulation
- output: structured JSON consumed by n8n

Scaffold lands at Sprint 1 start: `uv` or `venv` + `fastapi` + `pydantic` + `pytest`. Runs with `uvicorn --reload` in dev, containerized at sprint end (see commented `api` service in root `docker-compose.yml`).
