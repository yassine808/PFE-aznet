# TO-DO

Open items only. Everything marked done moves to `FIXED.md` — that file is the done log, this one is the queue.

- [x] Finish STT benchmark → pick default provider — **done 2026-08-07/08**: 13 engines, 3 by API and 12 locally on the RTX 3070, over 11 real clips. `stt_chain = gemini,local,groq`, ordered by accuracy judged against the audio by a native speaker rather than by latency. WER/CER deliberately not computed (`references.csv` stays header-only) — the criterion is preservation of digits and French technical loanwords, because that is all the journal consumes. Results: `benchmark/STT-BENCHMARK-STATUS.md`. The dead `hf-darija` adapter was deleted in the same pass.
- [x] Daily stat: % spoken Darija words vs French (post-PFE, zero cahier value)

## Code audit 2026-08-04 → `docs/audit-2026-08-04.md`
Full-read audit of the backend + the dashboard's data spine. 11 findings, each with file, line, cause and fix; the status table in that file is the source of truth. **3 bugs fixed** (profile never reaching the primary text model; every API restart cancelling that day's report; the scheduler loop being killable). **8 open**: 4 hardening (login timing oracle, unbounded throttle dict, cache-by-reference, uncapped `limit` params), 3 perf (two Sheets calls per write, a DB write per authenticated request, polling a hidden tab), 1 maintainability (daily/weekly report duplication). Coverage gap: `app/logs.py`, the rest of `app/main.py`, and the Dashboard pages were not read.

## Code audit 2026-08-10 → `docs/audit-2026-08-10.md`
Coverage gap from the 04-08 audit closed: full read of `logs.py`, the rest of `main.py`, `imagegen.py`, `prompt_loader.py`, `schemas.py`, the `providers/` package, every Dashboard page, the `lib/` spine and all components. **0 bugs found** — verified `/process` contract, single-query list endpoints (no N+1), the provider registry, the `useApi` cache, and the lazy routes. Three planned perf optimizations (N+1 batching, `/service-samples` aggregation, bundle) measured and dismissed as non-problems. One stale doc line fixed (`api/README.md` listed the deleted `hf-darija` adapter).

## Open before production (found reviewing the `opencode` merge, 2026-08-04)
- [x] **Retention for the archive tables.** Done 2026-08-10 with the owner's policy: `media_files` 30 days, `chat_messages` 90 days, read `notifications` 30 days, `manager_reports` kept forever; env-tunable via `MEDIA_RETENTION_DAYS` / `CHAT_RETENTION_DAYS` / `NOTIF_RETENTION_DAYS`, swept by `logs.prune_meta` at 03:00 — see FIXED.md (Fourth pass)
- [ ] **`INTERNAL_API_KEY` must be set in the deployed n8n environment.** `/process` is auth-gated since this branch, and n8n has no browser, so it authenticates with `X-API-Key`. All 17 n8n HTTP nodes send the header; the key has to exist on *both* sides or every incoming message 401s. Unset on the API means machine access is disabled, never "everyone is a machine" — so the failure is a silent pipeline, not an open door.
- [x] **`SMTP_USER` / `SMTP_PASS` set in `.env`** (2026-08-12) — every mail path is live; remaining action is a real test send via `POST /notify/test`.
- [x] check email
- [] check Automated reports.
- [] check Automated weekly reports
- [] check images
- [x] better sign-in design (profesionnal) — 2026-08-10: rewritten with language switcher, accent glow, AZnet avatar, aria-busy submit — see FIXED.md (Fourth pass)
- [x] adds 404 page — exists and is captured in the report (Annexe H): an unknown address says so explicitly instead of redirecting silently to the home page, where the user would think their link had worked.
- [x] remove image card generating in reports pages (make it auto when generating reports) — 2026-08-10: the card now rides along with the report's "Générer" click on both Daily and Weekly — see FIXED.md (Fourth pass)
- [] Add charging animation in the website, if things are getting charged from the database
- [] Add more columns inspired from the given data
- [] add techs vertically instead of horizentaly to reduce scroll (in TEAM panel)
## Batch 2026-08-15 (grilled and locked with the owner before starting)
- [x] **1. WhatsApp voice notes come back untagged — CLOSED, not fixable and never was a bug of ours (2026-08-15).** — fixed 2026-08-15: Text replies carry the grey quote, audio ones do not. Cause: the reply/ack nodes dereference `$('Filtrer accès').item`, and the paired-item chain breaks across the media branch (`WA Get media URL` → `WA Download audio`). Fix: carry `chat_id` + `message_id` in each item's own JSON through the media branch and read `$json` in the reply nodes — hardens the text and image paths too.
- [x] **2. Remove the chat commands** — done 2026-08-15; `rapports_row` stayed, because `GET /audio/row/{row}` plays the inbox's voice notes through it. `/rapport`, `/modify`, `/delete` everywhere: the n8n command nodes and their six reply nodes, `POST /modify-command`, and the now write-only message→row link (`processed_messages.sheet_row` / `sheet_tab` / `rapports_row` plus every `logs.link_message_row` call). `processed_messages` itself stays — WhatsApp idempotency lives there.
- [x] **3. Moroccan phone numbers: store `2126…`, always show `06…`/`07…`.** One `toMsisdn()` normalizer on the way in (Team form *and* the API, so `find_technician` cannot miss) and one `formatPhone()` on the way out, used by every place a WhatsApp id renders. — done 2026-08-15: the API already canonicalized (`logs.normalize_external_id`), so this was the display half — `toMsisdn`/`formatPhone` in `lib/utils.ts` with a runnable `utils.selfcheck.ts`, wired into the Team form, the identity chips and the inbox address.
- [x] **4. New settings panel, bottom-left, tabbed full-screen overlay** — Appearance, Pipeline, Automation, Notifications, Account. Mirrors the server settings as well as the local ones, gated by role (the confidence threshold and `/settings` writes stay director-only). — done 2026-08-15 in `components/settings-overlay.tsx`; the gear is now only the trigger. Not verified in a browser — no Chrome on this machine — build, typecheck and locale parity are green.
- [x] **5. Inbox shows new messages by itself, with a ⏳ per sender while their message is being processed.** In-flight is derived from `pipeline_logs` (a `received` row with no matching `replied`/`failed`), so no new table. Polling is adaptive: 5 s while anything is in flight, 30 s otherwise. — done 2026-08-15 (`GET /in-flight` + `HourglassMediumIcon` in the rail)
- [x] **6. Split the notification area: messages vs alerts.** Two tabs in the bell panel; the unread badge counts alerts only. A received message toasts as “Message reçu de {name}” and nothing else, clicking it opens the inbox on that technician. — done 2026-08-15
- [x] **7. WhatsApp-like inbox chat surface** — bubbles with tails, sender right / technician left, date pills, delivery ticks, textured thread background, all in the dashboard's own palette (no WhatsApp green). — done 2026-08-15: tails and the dot-grid ground are CSS (`.bubble`/`.thread-canvas` in `index.css`), the ticks say “sent” and never claim a read receipt the channel never gives us.
- [x] **8. Choose where a reply is sent.** — done 2026-08-15 The composer defaults to the channel and identity the last message arrived on and shows it as a chip; clicking it lists every identity of that person. `POST /reply` gains an optional `identity_id` — omitted, it still broadcasts, so nothing existing breaks.
- [x] **9. Space the n8n nodes on a grid** — done 2026-08-15: layered left-to-right by longest-path depth, 320 px between columns and 150 px of vertical pitch, branches kept next to the node they fork from. 56 nodes, 26 columns, widest column 6.
- [ ] **10. `WHATSAPP_ACCESS_TOKEN` is missing from `.env`.** The dashboard's WhatsApp reply answers "Réponse WhatsApp non configurée" because `reply.py` reads that variable and the API container has it unset — the token currently exists only inside n8n's WhatsApp *credential*, which the API cannot read. Add the System User token to `.env` (the API already loads it via `env_file`) and `docker compose up -d api`.
- [x] **11. Reply quote restored** (2026-08-15). The #1 "fix" caused it. Routing the reply's `chat_id`/`message_id` through `Process output` instead of `$('Filtrer accès')` produced a byte-identical payload in every execution I inspected — and still killed the quoted bubble, so `.item` resolves to something different at send time than the stored run data shows. Known good beats a theory: every message field is back on `$('Filtrer accès')`, and the reply nodes are now byte-identical to commit 047ab64, where it worked. Kept: `/process` still echoes `correlation_id`/`message_id` (free, and a real join key if one is ever needed). **Do not re-route the message fields through `Process output`.**

## WhatsApp quoting of voice notes — settled 2026-08-15, do not re-investigate
`context.message_id` pointing at a **voice note** is accepted by the Cloud API
(HTTP 200, a message id comes back) and then **not rendered as a quote** by
WhatsApp. Proven outside n8n: two messages sent straight to
`graph.facebook.com`, same code path, same recipient, one quoting an audio
`wamid` and one quoting a text `wamid` — only the text one showed the grey
quoted bubble.

So the workflow was never wrong. Three attempts were spent moving the
reference (`$('Filtrer accès').item` → `$('Process output').item` → `$json`)
on the theory that `pairedItem` did not survive the media branch; all three
sent the correct raw id, and none of them could have worked. The expressions
are back on `$('Filtrer accès')`, byte-identical to 047ab64.

What marks the message instead: the bot already reacts ⏳ on arrival and ✅ on
success, and a reaction *does* attach to the voice note itself. That is the
tag, and it is the owner's decision (2026-08-15) to leave it at that.

Kept from the investigation: `/process` echoes `correlation_id` and
`message_id` back in `ProcessResponse` (free, and a real join key if one is
ever needed).
