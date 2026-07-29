---
tags: [pfe, extraction, prompts, llm]
type: architecture
priority: high
status: current
---

# Extraction Pipeline

## Flow

Three input shapes, all handled by a single `POST /process` endpoint:

```
Audio → STT (Groq/Gemini/HF) → raw text → extraction chain → ExtractedReport
Image → Vision model → schema directly (no transcription) → ExtractedReport  
Text  → (skip STT) → extraction chain → ExtractedReport
```

## Prompt Architecture

All prompts are **versioned Markdown files** (`api/app/prompts/`), loaded by `PromptLoader` (`api/app/prompt_loader.py`). Read once per process via `@lru_cache` — restart the API to pick up edits.

| Prompt file | Role |
|---|---|
| `00-soul.md` | Prepended to every model-facing prompt. Identity, never-invent rule, absence ≠ zero rule |
| `extraction.md` | Main extraction instruction with French schema fields |
| `stt-vocabulary.md` | **No soul added.** Whisper reads `prompt` as transcript prefix, not instructions; soul would be echoed into transcript |
| `daily-report.md` | Aggregation of today's rows → French email |
| `image-generation.md` | Image generation prompt for summary cards |
| `profile.md` | Technician profile construction from past reports |

### Soul (00-soul.md) — enforced rules

1. **Never invent** — if the technician didn't mention it, mark it null. Do not infer, guess, or hallucinate equipment, causes, or actions.
2. **Absence ≠ zero** — if the technician doesn't mention material used, it's null, not "0" or "none".
3. **Numbers in profiles** — the profile prompt explicitly bans numbers.
4. **Model identity** — preface: "Tu es l'assistant IA de relevé d'intervention d'Aznet Maroc."

## Extraction Chain

Two ordered fallback chains (`config.py`), tried left to right:

### Text extraction (`extraction_text_chain`)

```
1. Gemini 2.5 Flash (structured output) → preferred, cheaper
2. Groq Llama 3.3 70B (JSON mode) → fallback
```

The chain alternates vendors (Gemini and Groq meter free tiers separately). If both fail, a combined `ExtractionError` is raised → HTTP 502.

### Image extraction (`extraction_image_chain`)

```
1. Gemini 2.5 Flash (vision) → only option
```

Google-only because the free Groq catalogue has no vision model. `flag_review=true` always. The model fills the schema in one call — no intermediate transcription. `rapport_complet` gets `[photo] ` prefix so it's never mistaken for a quote.

### Profile injection

`extraction.py` calls `get_technician_profile(name)` from `memory.py`. If a profile exists, it's injected as a labelled block in the extraction message:

```
Contexte sur le technicien (informations générales, NE PAS utiliser comme source de valeurs):
{profile_text}
```

The prompt frames it as "informational, not a source of values" — otherwise a profile saying "intervient surtout sur Sidi Maarouf" would fill `chantier` on a message that never named a site.

## Model Availability (`GET /models`)

Not all listed models are callable. The 2026-07-27 run found:
- `gemini-2.5-flash` → 404 on every call
- `gemini-3.5-flash` → 503 on every call

The endpoint returns the configured list from `config.py`; it does not probe availability.

## Error contract

| Condition | HTTP | Detail |
|---|---|---|
| Unknown provider / bad input | 422 | |
| STT engine failure | 502 + `TranscriptionError` | |
| All extraction engines fail | 502 + `ExtractionError` | Combined error from both engines |
| Short transcription (<10 chars) | 200 + warning | Not an error, but flagged in n8n |
| Empty/invalid profile request | `{}` profile | `get_technician_profile` returns empty if no profile exists |

## Related
- [[architecture]] — system boundaries
- [[STT Benchmark]] — provider comparison (pending)
- [[Project Overview]] — top-level feature status
- [[Google Sheets Integration]] — where the extracted report goes
