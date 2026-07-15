# Darija STT Benchmark (Sprint 1 — dataset recorded Week 0)

Decides the primary transcription engine with evidence. Results feed PLAN.md §8 metrics and the PFE report's Tests chapter.

## Engines under test

| Adapter | Model | Access |
|---|---|---|
| `groq` | Whisper-large-v3 | Groq API free tier |
| `gemini` | Gemini 2.5 Flash (native audio) | AI Studio free tier |
| `hf-darija` | Whisper fine-tuned on Darija (pick best available on HF) | HF Inference / local |

## Dataset recording protocol (Week 0 — do this now)

**Target: 15–20 voice notes**, 30–90 s each, recorded on a phone (WhatsApp-quality), stored in `dataset/audio/` as `note_XX.ogg` (gitignored — keep a copy in Drive).

Each note = realistic end-of-day chantier report in Darija with French code-switching. Vary deliberately:

- **Quantities** — always include some of: goulotte (m), câble (m), bureaux terminés, panneaux de brassage raccordés
- **Named entities** — chantier + client names
- **Code-switching level** — some notes heavy French mix, some nearly pure Darija
- **Background noise** — quiet room / street / echo
- **Speakers** — yourself + any Darija speakers you can recruit (3+ voices ideal)
- **Edge cases** — hesitations, corrections ("non, 300 mètres... non 350"), numbers said in French vs Arabic

Example content (from the cahier): *"Installation de 150 m de goulotte, tirage et pose de 800 m de câble informatique, finition de 5 bureaux du 1er étage, connexion de 2 panneaux de brassage."* — say it as you naturally would in Darija.

## Reference data — `dataset/references.csv`

| column | content |
|---|---|
| `file` | `note_01.ogg` |
| `speaker` | anonymized id (`s1`) |
| `duration_s` | integer |
| `noise` | `quiet` / `street` / `echo` |
| `reference_transcription` | hand-written exact transcription (the ground truth — write it while recording, painful later) |
| `expected_json` | the correct extraction: `{"goulottes_m":150,"cables_m":800,...}` |

## Metrics

- **WER/CER** per engine (via `jiwer`) on `reference_transcription`
- **Extraction accuracy**: % of JSON fields correct after LLM step (measures the pipeline, not just STT)
- **Latency** per engine

Harness code lands here in Sprint 1 (`run_benchmark.py`).
