---
tags: [pfe, project-overview, architecture]
type: overview
priority: high
status: current
---

# PFE aznet - Project Overview

## Project Summary

**End-of-studies project (PFE)** at **aznet.ma** — Voice notes in Moroccan Darija from cabling technicians → STT → LLM extraction → Professional French summary → Google Sheets → Manager notifications.

**Deadline:** August 31, 2026

## Architecture (Hybrid)

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Telegram      │────▶│      n8n         │────▶│   API (FastAPI) │
│   Bot API       │     │  (Orchestration) │     │   ai microsvc   │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                              ┌───────────────────────────┘
                              ▼
                    ┌──────────────────┐     ┌─────────────────┐
                    │  Google Sheets   │◀───▶│  Notifications  │
                    │  (Data store)    │     │  (Gmail SMTP)   │
                    └──────────────────┘     └─────────────────┘
```

**Key principle:** n8n is the glue; API is the custom AI microservice. Metadata (date, technicien, lien_audio) added by n8n, not the API.

## Tech Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| Reception | Telegram Bot API | Switched from WhatsApp (Meta friction) |
| Orchestration | n8n (Docker) | Polling for dev, webhook for pilot |
| AI API | FastAPI + Python 3.9 | Single endpoint: `POST /process` |
| STT | Groq Whisper / Gemini / HF Darija | Strategy pattern, benchmark pending |
| Extraction | Gemini (structured) → Groq fallback | Never silent fallback |
| Storage | Google Sheets | Free tier |
| Notifications | Gmail SMTP | Free tier |
| Deploy | Vercel (API) + VPS (n8n) | Zero budget — free tiers only |

## Budget Constraint

**Zero budget** — free tiers only:
- Groq API (Whisper, Llama)
- Gemini AI Studio
- Hugging Face Inference
- Telegram Bot API
- Gmail SMTP
- Vercel Hobby

## Data Flow

1. Technician sends voice note via Telegram
2. n8n receives (polling/webhook) → downloads audio
3. n8n calls `POST /process` with `audio` as a multipart file upload (not base64) — metadata (date, technicien, lien_audio) is added by n8n *after* the API responds, not sent to it
4. API: STT → Extraction → Returns `ProcessResponse` (wraps `ExtractedReport`)
5. n8n appends to Google Sheets
6. n8n sends manager notification (email)

## API Contract

**Endpoint:** `POST /process`

**Input (one of, multipart form):**
```
// Voice mode
audio: <file upload> (+ optional `provider` field to override STT engine)

// Web form mode
text: "transcribed text..."
```
n8n adds metadata (date, technicien, lien_audio) to the Sheets row itself — the API never sees it.

**Output:** `ProcessResponse` — `{ rapport_complet, report: ExtractedReport, transcription, warnings }` (see schemas)

## Key Files

| File | Purpose |
|------|---------|
| `PLAN.md` | Source of truth — architecture, sprint timeline, locked choices |
| `docs/cahier-des-charges.md` | Original specification (French) |
| `CLAUDE.md` | Claude Code instructions for this repo |
| `api/app/main.py` | FastAPI entry point |
| `api/app/providers/` | STT providers (strategy pattern) |
| `api/app/extraction.py` | LLM extraction logic |
| `api/app/schemas.py` | Data contracts (ExtractedReport) |
| `n8n/workflows/` | n8n workflow JSON exports |

## Sprint Timeline (from PLAN.md)

| Week | Focus |
|------|-------|
| Week 0 (Jul 16-22) | Setup, Telegram reception, API skeleton |
| Week 1 (Jul 23-29) | STT benchmark, provider selection |
| Week 2 (Jul 30-Aug 5) | Extraction pipeline, Sheets integration |
| Week 3 (Aug 6-12) | Notifications, end-to-end testing |
| Week 4 (Aug 13-19) | Pilot deployment, feedback |
| Week 5 (Aug 20-26) | Hardening, docs, handoff |
| Week 6 (Aug 27-31) | Buffer, final delivery |

## Current Status (Jul 23)

- [x] Project structure, git repo
- [x] Telegram Bot API reception (n8n polling workflow)
- [x] API skeleton with `/process` endpoint
- [x] STT provider abstraction (3 adapters registered)
- [x] Extraction pipeline (Gemini primary, Groq fallback)
- [x] Schemas defined (ExtractedReport)
- [x] Tests passing (33 tests, no API keys needed)
- [ ] STT benchmark to pick default provider
- [ ] Google Sheets append in n8n
- [ ] Manager notifications
- [ ] End-to-end smoke test

## Commands

```bash
# API development
cd api
.venv/Scripts/python.exe -m pytest              # All tests
.venv/Scripts/python.exe -m uvicorn app.main:app --reload  # Dev server :8000

# n8n
docker compose up -d                            # http://localhost:5678
```

## Links

- [[PLAN.md]]
- [[CLAUDE.md]]
- [[docs/cahier-des-charges.md]]
- [[STT Benchmark]]
- [[Extraction Pipeline]]
- [[n8n Workflows]]
- [[Google Sheets Integration]]