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