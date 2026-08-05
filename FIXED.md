# FIXED

Everything marked as done (`[x]`) in `TO-DO.md`, copied verbatim.

## Phase 0 — Prerequisites (now → Aug 1, close Sprint 1)
- [x] Text + image model benchmark → pick extraction chains — `benchmark/run_model_benchmark.py` over 10 hand-written Darija/French cases; results and the resulting `EXTRACTION_*_CHAIN` values in `benchmark/README.md`.

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

## Channels (2026-07-23: keep BOTH Telegram + WhatsApp as inputs)
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
- [x] Ack via emoji reaction instead of "⏳ Traitement en cours..." message: react on the sent voice note (TG `setMessageReaction`, WA `POST /messages type=reaction` on the wamid) — less chat noise, same signal. Flips to a green check when the summary lands, and is cleared when the pipeline fails.
- [x] **Don't call a greeting a report** — "hi" extracted cleanly (all fields `null`), so n8n replied "✅ Rapport enregistré" and appended a blank row. `ExtractedReport.has_data()` + a `no_report_content` warning + the `Rapport exploitable ?` IF node before `Append Sheet row` (2026-07-30).
- [x] Durable audio links: upload audio to Google Drive, store share link in `lien_audio` (file_id/media_id not durable; Meta media URLs expire ~5 min) — `app/drive.py`, same service account as Sheets, `drive.file` scope; best-effort on the `/process` path (a Drive outage falls back to the channel's own file id, never costs the technician their summary)
- [x] download audios and images and chat to the database — `media_files` (blobs, metadata-only listing at `GET /media`, one file at `GET /media/{id}/file`) and `chat_messages` (`GET /messages`); archived while the channel's ticket is still live
- [x] Caption support: audio sent WITH caption (mostly Telegram) → optional `caption` form field on `/process`, merged into text before extraction — also passed to the vision model with photos; n8n audio+image nodes send it
- [x] sending /rapport or /report, uploads the last version of report for the day in the assistant chat — reports are now per-manager: each chef's daily/weekly digest is stored in `manager_reports` at send time, and the `/rapport` command (new `Is /rapport?` branch in n8n) returns the sender's manager's last report via `GET /rapport`
- [x] **Message commands — edit by reply.** Technician replies to one of their own messages with `/modify {nouveau texte}`; the bot re-runs extraction on the new text and updates *that* Sheet row instead of appending a new one — shipped as `POST /modify-command`: the row number comes from `processed_messages.sheet_row` (written by `POST /messages/link` after the append), never from anything the technician typed; `/supprimer` empties the row in place rather than deleting it, because a positional delete would shift every row number below it and invalidate every stored message→row link at once.

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
- [x] Verify the dashboard visually — `Dashboard/scripts/visual-check.mjs`: headless login against the compose stack, walks all 9 pages, screenshots each (full-page PNG to `%TMP%/dashboard-shots/`), fails on console errors / HTTP >= 400 / horizontal overflow / broken images / blank pages. First run: clean on every check.
- [x] Inbox rebuild — left rail of recent technicians (count, channels, last date), right conversation window with per-message modify + a reply composer; replies are sent by the API on the technician's own channels via `POST /reply` (needs `TELEGRAM_BOT_TOKEN` + `WHATSAPP_ACCESS_TOKEN`/`WHATSAPP_PHONE_NUMBER_ID` in `.env`, same values as n8n's credentials; without them the composer answers 501 loudly)
- [x] Each generated report emails the saved account addresses (admin + site managers), manual list as fallback
- [x] Daily report panel made structurally identical to the weekly one — same stat panels (totals, production, per-tech)
- [x] Reports page defaults to a "Rapports générés" tab (the stored per-manager daily/weekly reports from `manager_reports`); the message ledger moved to a second tab
- [x] Site name is never auto-generated — the chantier is typed by admin/site manager: click the chantier cell in the Reports → Messages tab (`PATCH /reports/{row}` already existed; the UI was missing)
- [x] Report provenance — manual runs signed by the account that pressed the button ("generated by: {name}", shown in the mail and next to the report panel), scheduled mail labelled "automatique"
- [x] AM/PM in the frontend time
- [x] Dashboard settings saved per account in the database (clock format 24h/12h, density, confidence) — `person_settings` table + `GET/PUT /me/settings`, follow the person across browsers, confidence director-only on the API
- [x] WhatsApp phone numbers normalised on save whatever the operator types (drops `+`, rewrites a leading `0` to `212`)
- [x] Per-worker stats — WorkerStats in the equipe detail panel (messages, % darija vs french, flagged count, last activity)
- [x] Overview tile renamed "Messages aujourd'hui" (it counts messages, not reports)
- [x] Équipe org chart — three role bands (directeur → chefs → techs), `+` buttons, drag-drop reassignment, channels + access control merged into the same page
- [x] Ctrl-K searches everything — fuzzy subsequence matching, technicians indexed, "did you mean" fallback
- [x] Per-account notifications — the bell: own team's new reports, rows flagged for review, Sheet write failures, task reminders; unread badge, mark-all-read; only the signed-in person sees their own
- [x] Shared to-do page — title/notes/échéance/répétition (une fois, jour, semaine, mois); the scheduler rings every bell at échéance and emails the accounts, then advances the recurrence
- [x] To-do lead time and custom cadences — `remind_before_value/unit` open the reminder window early (calendar-aware months), `repeat_every/unit` add custom cadences beside the presets; the API rejects a lead as long as the repeat period (overlapping windows would re-ring every tick); bell + email say "Rappel : N jours avant l'échéance"
- [x] Report editor on the daily + weekly pages — edit subject and body, a GitHub-style line diff against the last save, an append-only version history in `report_versions` (open or restore any version), one export format. `.md`/`.txt` were dropped project-wide: only `.docx` can carry the generated card, so a text export was a document quietly missing half the report
- [x] Bell and settings popovers rendered see-through in both themes — `backdrop-filter` on the rail (and on the mobile bar) makes that element a backdrop root, so a popover overflowing it is composited against the blurred backdrop instead of over it. The desktop rail is a grid column with nothing scrolling under it, so its blur was deleted outright; the mobile bar keeps its blur on a `::before` layer instead of on the bar itself (2026-08-05)

## Third pass (from `TO-DO.md`, 2026-08-05)
- [x] Illustrated summary card — "Carte illustrée" button on the Daily and Weekly pages: explicit click only, `POST /generate-image` (Gemini), the data-URI card is displayed and downloadable, never written to the Sheet
- [x] **Assistant persona from leaked-system-prompt techniques** — role framing, refusal/uncertainty wording, formatting discipline and anti-hallucination phrasing folded into all three prompt sites (text extraction, STT post-processing, audio/vision). Identity is **"l'assistant AZnet"** — never Claude, ChatGPT, Gemini or any vendor name, in any language. The hard rule (`null` for absent fields, never invent) stays the top constraint; verified against the `t04_hallucination_trap` / `t08_no_quantities_at_all` benchmark cases.

## Second pass (was `TO-DO-2.md`, merged here 2026-07-30)
- [x] make sure the year is not hardcoded in the activity graphs
- [x] only 1 admin that is created, creds are from the .env, other created account are always site manager — `POST /users` hardcoded `role="chef"` server-side (was trusting client-sent role, letting a director mint a second director); dead role picker removed from the create-account form.
- [x] confidence level, only the admin who can view+ edit that setting, other change the rest.
- [x] emoji instead of "⏳ Traitement en cours..." (only works on whatsapp)
- [x] verify Access control
- [x] never hardcode anything sensitive (passwords, emails , especially in the n8n workflow). `n8n/aznet-complete.json` is clean now — Sheet document ID and `HR_EMAIL` both read `$env` (`cb7672d`). Still open: `Dashboard/.env` carries a second copy of `N8N_API_KEY` — the dev proxy reads it there, but the API now has its own; drop the duplicate.
- [x] use UX-UI skill
- [x] Better CI checks in github — `.github/workflows/ci.yml`: real gates (no more `|| true`), plus secret scan (`scripts/check_secrets.py` + gitleaks over full history), n8n expression lint (`scripts/check_workflow.py`), locale parity (`scripts/check_locales.py`), compose validation and a real Dashboard build. **The checks still cannot go green**: every job reports "The job was not started because recent account payments have failed or your spending limit needs to be increased" — an Actions billing block on the account. Fix billing, or make the repo public (unlimited free minutes) after the two items below.
- [x] **Revoke the Telegram bot token** (BotFather → `/mybots` → API Token → Revoke), then update `.env` + the n8n Telegram credential. It was committed in `how-to-setup.md` for ~38 commits. History was rewritten 2026-07-30 and force-pushed, but old commits stay fetchable by SHA on GitHub until purged — revocation is the only step that actually neutralizes it.
- [x] add the deployment keys to the root `.env`: `N8N_API_KEY` (move the value out of `Dashboard/.env`), `N8N_URL=http://n8n:5678`, a real `POSTGRES_PASSWORD` (default is still pfe/pfe and the port is now closed), `COOKIE_SECURE=true`, `WEB_PORT=8080`
