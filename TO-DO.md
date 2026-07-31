# TO-DO

Phased and dependency-ordered. Full rationale + cut-line in `vault/roadmap.md`.
Hard deadline: Aug 31 2026. Dashboard is built and running (`Dashboard/`; the old `web/` was deleted 2026-07-26).

## Phase 0 — Prerequisites (now → Aug 1, close Sprint 1)
- [ ] Finish STT benchmark → pick default provider — **blocked on the dataset**: `benchmark/dataset/audio/` is still empty, so `stt_provider=groq` is an assumption, not a measurement. Harness is ready (`benchmark/run_benchmark.py`).
- [x] Text + image model benchmark → pick extraction chains — `benchmark/run_model_benchmark.py` over 10 hand-written Darija/French cases; results and the resulting `EXTRACTION_*_CHAIN` values in `benchmark/README.md`.
- [ ] Full n8n E2E: Telegram → /process → Sheets append → email notif

## Phase 1 — Pipeline (Sprint 2, no dashboard needed)
- [x] Treat voice messages and forwarded audios the same (n8n: match message.voice OR message.audio) — both workflows
- [x] Access control: allowlist employees + director; outsider gets one automated HR-contact reply. Same table gets a role column so boss behavior differs from employees (both changeable in settings later) — `Access control` node in both workflows; fill ALLOWLIST with real user IDs
- [x] Error logs: n8n error trigger → `POST /logs` (Postgres, not a sheet tab) — band 2 of `n8n/aznet-complete.json`; set the workflow as its own Error Workflow after import — **re-check this after every import or API push**, it lives in the workflow's `settings` and the public API silently drops keys it does not accept (set again 2026-07-30)
- [x] Low-confidence STT → flag_review=true column in the Sheet (not just backend log) — `Append Sheet row` node writes flag_review + confidence
- [x] End-of-day cron: assemble today's transcriptions + messages → LLM report → email — `api/app/jobs.py` (`daily_report`, plus `weekly_report`) + `POST /daily-report` (photos + .docx still open)

## Phase 2 — Dashboard v1+ (Sprint 2, Aug 3–14)
- [x] Save + show each audio with its transcription per row — Inbox panel plays `lien_audio` inline next to the transcription (`Dashboard/src/pages/inbox.tsx`). Link durability is still the open Drive item below.
- [x] Manual correction: edit an extracted field, write back via Sheets API — `PATCH /reports/{row}` + the Inbox **Modifier** form and the Reports ledger; Sheets stays the source of truth.
- [x] Review queue: filter view on flag_review rows — Reports panel "À vérifier" toggle (`onlyFlagged`).
- [x] Show confidence % per transcription — bar + column in the Reports ledger, threshold configurable in the settings panel. Labeled "confiance", never "accuracy".

## Phase 3 — Nice-to-haves (Sprint 3 buffer, only if ahead)
- [x] GitHub-style contribution heatmap — `Dashboard/src/components/contribution-graph.tsx`, on Overview, Daily and Weekly; today is outlined, clicking a day deep-links into the Inbox.
- [x] Weekly rollup report — Weekly panel: per-day and per-technician totals, week picker on the year graph, LLM narrative via `POST /daily-report` over the week's rows. Monthly still open.
- [x] Settings + Automation panels — refresh interval, confidence threshold, table density; plus daily/weekly trigger times, notification recipients with a live SMTP **Test** button, and report format (txt/md/docx). Stored server-side in `app_settings` via `GET|PUT /settings`. Times are stored **and enforced**: the cron bands moved out of n8n into `api/app/jobs.py`, which re-reads `app_settings` on every 30 s tick, so an edited hour takes effect without a restart.
- [ ] Daily stat: % spoken Darija words vs French (post-PFE, zero cahier value)
- [ ] Image generation from report via free API (post-PFE or cut — burns free-tier quota)

## Channels (2026-07-23: keep BOTH Telegram + WhatsApp as inputs)
Full config walkthrough: `docs/setup-guide.md`.
- [x] WhatsApp Cloud API reception workflow — folded into `n8n/aznet-complete.json` band 1
- [x] **Unified reception workflow** (`n8n/aznet-complete.json`) — one workflow, both triggers, shared allowlist/pipeline/Sheet (`canal` column), channel-aware replies. Fully patched: credential IDs, spreadsheet ID + column schema, allowlist (TG `<TELEGRAM_USER_ID>`, WA `<WHATSAPP_NUMBER>`), env-based tokens.
- [x] n8n credentials created (Telegram, WhatsApp OAuth, WhatsApp API + WABA `<WABA_ID>`, Google service account `n8n-sheets@pfe-aznet`); env passthrough + `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` in compose
- [x] Google Sheet `Rapports` created (headers split), shared with service account
- [x] Telegram E2E smoke test: voice → ⏳ → ✅ → Sheet row
- [x] WhatsApp E2E: webhook registered (manual GET-echo webhook — n8n WhatsApp Trigger fails Meta's challenge), app published (gist privacy policy), **app subscribed to WABA via `POST /subscribed_apps`** (root cause of silent non-delivery: only Meta's internal test app was subscribed), media download via HTTP node + predefined WhatsApp credential (native download op = Bad request)
- [x] Durable WhatsApp token: System User token (never expires) in n8n `WhatsApp account` credential

## Workflow improvements (discussed 2026-07-23, cheap → expensive)
- [x] Text-message input: typed reports on both channels → `Audio or text?` fork, `POST /process (text)` with `text` form field (bot commands `/...` ignored)
- [x] Failure reply to sender: both /process nodes `onError: continueErrorOutput` → channel-aware "❌ Erreur, réessayez" reply
- [x] Dedupe guard: processed message keys in static data (`tg:chat:msgid` / `wa:wamid`) — survives poll restarts + Meta webhook retries
- [x] "⏳ Traitement en cours..." ack sent right after authorization, before STT
- [x] **Image input**: photo → vision model → same structured row. `Media or text?` then `Audio or image?` (audio and image share one download subgraph); Telegram `photo`/image `document`, WhatsApp `type=image`; `POST /process (image)`. Photo rows always `flag_review=true`.
- [x] **Per-modality model chains with fallbacks**: `EXTRACTION_TEXT_CHAIN` / `EXTRACTION_IMAGE_CHAIN` in `api/app/config.py`, tried in order, logging which model answered. Text alternates vendors so a Gemini quota trips over to Groq's separate meter.
- [ ] Durable audio links: upload audio to Google Drive, store share link in `lien_audio` (file_id/media_id not durable; Meta media URLs expire ~5 min)
- [ ] Caption support: audio sent WITH caption (mostly Telegram) → needs optional `caption` form field on `/process`, merged into text before extraction
- [ ] Boss commands: `directeur` role sends "/rapport" text → bot replies with today's rollup on demand (reuses `/daily-report`)
- [ ] **Message commands — edit by reply.** Technician replies to one of their own messages with `/modify {nouveau texte}`; the bot re-runs extraction on the new text and updates *that* Sheet row instead of appending a new one. Needs: (a) store the origin message id per row (`tg:chat:msgid` / `wa:wamid` — already minted for the dedupe guard, currently thrown away after the claim) plus its Sheet row number, in `processed_messages`; (b) an n8n branch that detects `reply_to_message` / `context.id` + a `/`-prefixed body before the normal audio/text fork; (c) `PATCH /reports/{row}` already exists for the write-back. Same branch is the natural home for `/supprimer` and the `/rapport` boss command below.
- [ ] **Assistant persona from leaked-system-prompt techniques** — mine <https://github.com/yassine808/system_prompts_leaks> for prompt structure that production assistants actually use (role framing, refusal/uncertainty wording, formatting discipline, anti-hallucination phrasing) and fold the useful parts into all three prompt sites: text extraction, STT post-processing, and the audio/vision paths (`app/extraction.py` `_INSTRUCTIONS`, the image instructions in `benchmark/run_model_benchmark.py`, `app/daily_report.py`). Identity is **"l'assistant AZnet"** — never Claude, ChatGPT, Gemini or any vendor name, in any language. Keep the existing hard rule (`null` for absent fields, never invent) as the top constraint; borrowed phrasing must not dilute it. Verify with the `t04_hallucination_trap` / `t08_no_quantities_at_all` benchmark cases before and after.
- [x] Ack via emoji reaction instead of "⏳ Traitement en cours..." message: react on the sent voice note (TG `setMessageReaction`, WA `POST /messages type=reaction` on the wamid) — less chat noise, same signal. Flips to a green check when the summary lands, and is cleared when the pipeline fails.
- [x] **Don't call a greeting a report** — "hi" extracted cleanly (all fields `null`), so n8n replied "✅ Rapport enregistré" and appended a blank row. `ExtractedReport.has_data()` + a `no_report_content` warning + the `Rapport exploitable ?` IF node before `Append Sheet row` (2026-07-30).
- [ ] **Secrets still hardcoded in `n8n/aznet-complete.json`** (TO-DO-2 item 11): the Google Sheet document ID in `Append Sheet row`, and `<HR_EMAIL>` in both HR reply nodes. Move to `$env` alongside the keys already in the root `.env`.

## Dashboard v2 (rebuilt from scratch 2026-07-26 in `Dashboard/`)
- [x] Design system first: `PRODUCT.md` + `DESIGN.md`, OKLCH tokens, Tailwind v4 CSS-first theming, light/dark authored independently, FR/EN/AR with RTL
- [x] Overview: masthead, day ribbon, production band, per-service uptime strips, year heatmap
- [x] Reports ledger: search, flagged filter, confidence column, inline correction
- [x] Inbox: messages/audio per channel and technician, **Modifier** reveals the edit form
- [x] Daily + Weekly report panels with generate, copy and download (txt/md/docx)
- [x] Access control panel: add/remove technicians (telegram/whatsapp + id + name + role), backed by the `technicians` table and `/technicians/lookup`
- [x] Automation panel: trigger times, notification recipients + SMTP test, report format
- [x] Ops resilience: stale-while-revalidate cache so panels keep their data across navigation; uptime sampler above the router, persisted to `service_samples`; CSS-keyframe status pulse that React re-renders cannot restart
- [x] API-down alarm: masthead flashes red and beeps (WebAudio, no asset), with a mute toggle
- [x] Enforce the stored schedule — done by moving the cron bands into `api/app/jobs.py` (they read `app_settings` every tick) rather than teaching n8n to read `/settings`. The Automation page can also show what ran and force a re-run, which a cron node cannot.
- [ ] Verify the dashboard visually — never done; Playwright's Chrome is not installed (`npx playwright install chrome`)

## Second pass (was `TO-DO-2.md`, merged here 2026-07-30)
- [ ] Inbox: give it better UI, show recent users, after i click on the user, it shows like a big window inside it in the left canals, and on the right the conversation + reply + add the modify button. make everything simple and clear.
- [ ] on each report generated, it emails the saved emails for the login (admin + Site manager)
- [x] make sure the year is not hardcoded in the activity graphs
- [ ] make daily reports similar to weely reports
- [ ] reports should show daily + weekly reports, not the messages
- [ ] for each user (admin or site manager), if he ever generated the report ( manually) then it should show in the report at the end (generated by:{name}) then it should show also next to the report panel. if it was auto generated then it should tell aswell.
- [x] only 1 admin that is created, creds are from the .env, other created account are always site manager — `POST /users` hardcoded `role="chef"` server-side (was trusting client-sent role, letting a director mint a second director); dead role picker removed from the create-account form.
- [x] confidence level, only the admin who can view+ edit that setting, other change the rest.
- [x] emoji instead of "⏳ Traitement en cours..." (only works on whatsapp)
- [x] verify Access control
- [ ] never hardcode anything sensitive (passwords, emails , especially in the n8n workflow). `n8n/aznet-complete.json` is clean now — Sheet document ID and `HR_EMAIL` both read `$env` (`cb7672d`). Still open: `Dashboard/.env` carries a second copy of `N8N_API_KEY` — the dev proxy reads it there, but the API now has its own; drop the duplicate.
- [x] use UX-UI skill
- [x] Better CI checks in github — `.github/workflows/ci.yml`: real gates (no more `|| true`), plus secret scan (`scripts/check_secrets.py` + gitleaks over full history), n8n expression lint (`scripts/check_workflow.py`), locale parity (`scripts/check_locales.py`), compose validation and a real Dashboard build. **The checks still cannot go green**: every job reports "The job was not started because recent account payments have failed or your spending limit needs to be increased" — an Actions billing block on the account. Fix billing, or make the repo public (unlimited free minutes) after the two items below.
- [x] **Revoke the Telegram bot token** (BotFather → `/mybots` → API Token → Revoke), then update `.env` + the n8n Telegram credential. It was committed in `how-to-setup.md` for ~38 commits. History was rewritten 2026-07-30 and force-pushed, but old commits stay fetchable by SHA on GitHub until purged — revocation is the only step that actually neutralizes it.
- [x] add the deployment keys to the root `.env`: `N8N_API_KEY` (move the value out of `Dashboard/.env`), `N8N_URL=http://n8n:5678`, a real `POSTGRES_PASSWORD` (default is still pfe/pfe and the port is now closed), `COOKIE_SECURE=true`, `WEB_PORT=8080`
- [ ] add AM/Pm in the frontend time.

## Notes
- "Add some solutions or critical things to be aware of" — captured in vault/roadmap.md cut-line + contradictions sections
