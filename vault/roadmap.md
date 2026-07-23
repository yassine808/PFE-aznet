---
tags: [pfe, roadmap, planned]
type: roadmap
priority: high
status: current
---

# Roadmap — TO-DO triaged against PLAN.md

Turns the raw [[to-do]] backlog into a phased, dependency-ordered plan scoped to [[project-overview]] sprint timeline and PLAN.md's MoSCoW cut-line. Hard deadline **Aug 31 2026**.

> **Status 2026-07-23:** Phase 0 + Phase 1 **done**; Phase 2 dashboard **v1 built**. Dual-channel reception (Telegram + WhatsApp) is live E2E through one unified workflow (`n8n/reception-unified.json`): access control + roles, dedupe, text input, failure replies, low-confidence flagging, error-tab workflow, end-of-day cron. Dashboard (`web/` + FastAPI `/reports`) reads the Sheet with filters, review queue, confidence %, inline correction. Remaining Phase 2: dashboard restyle (efferd), durable Drive audio links. See [[n8n-workflows]] and `docs/setup-guide.md`.

**Key constraint (now resolved):** dashboard existed only as an empty `web/` when this roadmap was written — hence the re-sequencing below. Dashboard v1 now exists (Vite + React TS), so Phase 2 items are unblocked.

---

## Phase 0 — Prerequisites (now → Aug 1, close out Sprint 1)

Nothing in the backlog is buildable before the core pipeline works.

1. Finish STT benchmark → pick default provider (`benchmark/`). Blocks everything downstream. See [[stt-benchmark]].
2. Full n8n E2E: Telegram → `/process` → Sheets append → email notif. Sprint 2 entry condition. See [[n8n-workflows]], [[google-sheets-integration]].

## Phase 1 — Pipeline-level items (Sprint 2, no dashboard needed)

Live in n8n/API. Cheapest wins first.

3. **Voice + forwarded audio treated the same** — n8n reception matches `message.voice` OR `message.audio`, both into same download→process branch. ~1h.
4. **Access control / roles** — allowlist of Telegram user IDs (employees + director) checked at workflow start; outsiders get one canned HR-contact reply. Same lookup table gets a `role` column → branch boss vs employee behavior. Covers backlog items "security" + "boss knows different".
5. **Error logs** — API already raises typed errors (422/502). Add n8n error workflow appending failures to an `Errors` Sheet tab (timestamp, node, message, payload link). Foundation for dashboard error panel later.
6. **Low-confidence STT flag** — API already emits `short_transcription` warning; extend to low-confidence signal, n8n writes `flag_review=true` column. Dashboard surfaces it in Phase 2.
7. **End-of-day report cron** — second n8n cron reads today's rows → LLM summary → email + .docx. `.docx` = stretch (python-docx endpoint); ship email HTML first.

## Phase 2 — Dashboard v1+ (Sprint 2, Aug 3–14)

Dashboard v1 (list + filters) already planned. Fold backlog in, this order:

8. **Audio + transcription per row** — `lien_audio` column exists; show player + transcription text.
9. **Manual correction of extracted fields** — edit form writes back via Sheets API. **Decision:** write-back to Sheets keeps "Sheets = single source of truth" (PLAN.md assumption 3). No separate DB.
10. **Review queue** — filter view on `flag_review=true` rows (from item 6).
11. **Confidence % per transcription** — honest framing: STT gives no word-level truth, so show model confidence proxy (avg logprob where available, else heuristic), labeled "confidence" not "accuracy".

## Phase 3 — Nice-to-haves (Sprint 3 buffer, only if ahead)

12. **Contribution heatmap** — report count/day/technician from Sheet. Cheap React component, strong defense visual — promote if time allows.
13. **Weekly/monthly rollup** — same machinery as end-of-day cron, wider window + trends prompt.
14. **Settings panel** (cron timers, emails, API uptime/usage) — needs config store + persistence; n8n env vars suffice for PFE. Panel is post-PFE.
15. **Darija-vs-French % stat** — needs per-word language ID; cheap LLM pass but zero cahier value. Post-PFE.
16. **Image generation from reports** — no cahier justification, burns free-tier quota. Post-PFE or cut.

## Cut-line

PLAN.md guard: core pipeline protected, dashboard extras die first. If Sprint 2 slips → drop all of Phase 3 + items 9/11. Items 3–7 are cheap and report-defensible — keep.

## Contradictions resolved

- **Manual correction + settings panels** imply a mutable backend, but PLAN.md assumption 3 locks "Sheets = single source of truth." Resolved via Sheets API write-back (item 9) — no mid-PFE DB migration.
- **"Accuracy %"** is unmeasurable without ground truth. Reframed as "confidence" (item 11) to avoid presenting a fabricated metric at the defense.

## Related Notes

- [[to-do]]
- [[project-overview]]
- [[architecture]]
- [[stt-benchmark]]
- [[n8n-workflows]]
