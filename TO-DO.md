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

## Channels (2026-07-23: keep BOTH Telegram + WhatsApp as inputs)
- [x] WhatsApp Cloud API reception workflow (`n8n/whatsapp-reception.json`) — same access control + Sheet row as Telegram
- [x] **Unified reception workflow** (`n8n/reception-unified.json`) — one workflow, both triggers (Telegram polling + WhatsApp webhook), shared allowlist/pipeline/Sheet (`canal` column), channel-aware replies (WA in → WA reply, TG in → TG reply). This is the one to run; single-channel JSONs kept as fallback.
- [x] n8n credentials created (WhatsApp OAuth: App ID+Secret; WhatsApp API: token+WABA `<WABA_ID>`); `WHATSAPP_PHONE_NUMBER_ID` in .env
- [ ] Register WhatsApp webhook in Meta (cloudflared tunnel + trigger URL → Configuration → subscribe `messages`) → send test voice note
- [ ] Durable WhatsApp token: System User token (test-mode temp tokens die in 24h)

## Workflow improvements (discussed 2026-07-23, cheap → expensive)
- [ ] Text-message input: technician TYPES report instead of voice → API `/process` already supports `text` mode, just extend extract nodes to catch `message.text` / `type: "text"` and post as form field
- [ ] Failure reply to sender: on /process 502, tell technician "❌ Erreur, réessayez" (n8n error branch on HTTP node) instead of silence — pairs with Errors tab
- [ ] Durable audio links: upload audio to Google Drive, store share link in `lien_audio` (file_id/media_id not durable; Meta media URLs expire ~5 min)
- [ ] Caption support: voice/audio sent WITH caption text → append caption to transcription before extraction (extra context, free)
- [ ] Dedupe guard: skip already-processed `message_id`s in static data (poll restart can re-deliver)
- [ ] Boss commands: `directeur` role sends "/rapport" text → bot replies with today's rollup on demand (reuses `/daily-report`)
- [ ] "⏳ Traitement..." ack reply before STT (10s pipeline feels dead otherwise) — optional, adds 1 msg noise

## Notes
- "Add some solutions or critical things to be aware of" — captured in vault/roadmap.md cut-line + contradictions sections
