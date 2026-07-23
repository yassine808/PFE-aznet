# TO-DO

Phased and dependency-ordered. Full rationale + cut-line in `vault/roadmap.md`.
Hard deadline: Aug 31 2026. Most items need the admin dashboard (not built yet — `web/` empty).

## Phase 0 — Prerequisites (now → Aug 1, close Sprint 1)
- [ ] Finish STT benchmark → pick default provider (blocks everything downstream)
- [ ] Full n8n E2E: Telegram → /process → Sheets append → email notif

## Phase 1 — Pipeline (Sprint 2, no dashboard needed)
- [x] Treat voice messages and forwarded audios the same (n8n: match message.voice OR message.audio) — both workflows
- [x] Access control: allowlist employees + director; outsider gets one automated HR-contact reply. Same table gets a role column so boss behavior differs from employees (both changeable in settings later) — `Access control` node in both workflows; fill ALLOWLIST with real user IDs
- [x] Error logs: n8n error workflow → Errors sheet tab (timestamp, node, message, payload link) — `n8n/error-workflow.json`; set it as Error Workflow in each production workflow
- [x] Low-confidence STT → flag_review=true column in the Sheet (not just backend log) — `Append Sheet row` node writes flag_review + confidence
- [x] End-of-day cron: assemble today's transcriptions + messages → LLM report → email — `n8n/daily-report-cron.json` + `POST /daily-report` (photos + .docx still open)

## Phase 2 — Dashboard v1+ (Sprint 2, Aug 3–14)
- [ ] Save + show each audio with its transcription per row
- [ ] Manual correction: edit an extracted field, write back via Sheets API (keeps Sheets as source of truth)
- [ ] Review queue: filter view on flag_review rows
- [ ] Show confidence % per transcription (model confidence proxy, labeled "confidence" not "accuracy")

## Phase 3 — Nice-to-haves (Sprint 3 buffer, only if ahead)
- [ ] GitHub-style contribution heatmap: report count/day/technician
- [ ] Weekly/monthly rollup report: trends across chantiers (materials, recurring issues)
- [ ] Settings panel: cron timers, emails, API uptime/usage (post-PFE unless time allows)
- [ ] Daily stat: % spoken Darija words vs French (post-PFE, zero cahier value)
- [ ] Image generation from report via free API (post-PFE or cut — burns free-tier quota)

## Notes
- "Add some solutions or critical things to be aware of" — captured in vault/roadmap.md cut-line + contradictions sections
