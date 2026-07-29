---
tags: [pfe, roadmap, planned]
type: roadmap
priority: high
status: current
---

# Roadmap — TO-DO triaged against PLAN.md

> **Status 2026-07-29:** Phases 0–2 substantially done. What remains: STT benchmark (dataset still empty), a few Phase 3 nice-to-haves, and hardening before the defense.

## What's built

| Item | Phase | Status |
|---|---|---|
| n8n E2E pipeline (TG + WA → Sheet) | 0 | ✅ Live since March (TG), July 23 (WA) |
| Access control / roles | 1 | ✅ `technicians` table + active/inactive toggle. Outsider detection via allowlist |
| Error logs | 1 | ✅ Postgres `pipeline_logs` + dashboard **Logs n8n** panel |
| Low-confidence flagging | 1 | ✅ `flag_review=true` on short transcriptions + image input |
| End-of-day report email | 1 | ✅ Moved to API scheduler (`daily_report.py`, Mon–Sat) |
| Audio + transcription per row | 2 | ✅ Player + transcription shown in dashboard inbox |
| Manual correction of extracted fields | 2 | ✅ Inline cell editing via `PATCH /reports/{row}` |
| Review queue | 2 | ✅ Filter view on `flag_review=true` |
| Confidence % per transcription | 2 | ✅ Shown as logprob or null in dashboard |
| Settings panel | 3 | ✅ `GET|PUT /settings` + Automation page in dashboard |
| Image generation from reports | 3 | ✅ `POST /generate-image` (Gemini, `imagegen.py`) |
| Weekly rollup report | 3 | ✅ Reuses daily report logic with date-range label |

## What remains

| Item | Phase | Notes |
|---|---|---|
| STT benchmark | 0 | **Blocked** — `benchmark/dataset/audio/` still empty. No field recordings |
| Contribution heatmap | 3 | Not started. Cheap React component (report count/day/technician) |
| Darija-vs-French % stat | 3 | Post-PFE or cut. No cahier justification |
| `.docx` report download | 1 | Not built. HTML email sufficient |
| Dashboard auth hardening | — | `allow_origins=["*"]`, no rate limit on `/login`, SHA-256 for passwords |
| CI / automated testing | — | No CI configured. Manual `pytest` only |
| Public deployment | — | Docker Compose on local machine + Tailscale Funnel. No VPS |

## Cut-line (unchanged from PLAN.md)

Phase 3 dies first. Dashboard extras after heatmap are post-PFE.

## Contradictions resolved

- **Manual correction + settings panels** — resolved via Sheets API write-back (`PATCH /reports/{row}`) + Postgres `app_settings` table.
- **"Accuracy %"** — reframed as "confidence" (logprob or null).

## Related Notes

- [[to-do]]
- [[Project Overview]]
- [[architecture]]
- [[STT Benchmark]]
- [[n8n Workflows]]
