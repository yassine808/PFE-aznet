# TO-DO

Open items only. Everything marked done moves to `FIXED.md` — that file is the done log, this one is the queue.

- [ ] Finish STT benchmark → pick default provider — **blocked on the dataset**: `benchmark/dataset/audio/` is still empty, so `stt_provider=groq` is an assumption, not a measurement. Harness is ready (`benchmark/run_benchmark.py`).
- [x] Daily stat: % spoken Darija words vs French (post-PFE, zero cahier value)

## Code audit 2026-08-04 → `docs/audit-2026-08-04.md`
Full-read audit of the backend + the dashboard's data spine. 11 findings, each with file, line, cause and fix; the status table in that file is the source of truth. **3 bugs fixed** (profile never reaching the primary text model; every API restart cancelling that day's report; the scheduler loop being killable). **8 open**: 4 hardening (login timing oracle, unbounded throttle dict, cache-by-reference, uncapped `limit` params), 3 perf (two Sheets calls per write, a DB write per authenticated request, polling a hidden tab), 1 maintainability (daily/weekly report duplication). Coverage gap: `app/logs.py`, the rest of `app/main.py`, and the Dashboard pages were not read.

## Code audit 2026-08-10 → `docs/audit-2026-08-10.md`
Coverage gap from the 04-08 audit closed: full read of `logs.py`, the rest of `main.py`, `imagegen.py`, `prompt_loader.py`, `schemas.py`, the `providers/` package, every Dashboard page, the `lib/` spine and all components. **0 bugs found** — verified `/process` contract, single-query list endpoints (no N+1), the provider registry, the `useApi` cache, and the lazy routes. Three planned perf optimizations (N+1 batching, `/service-samples` aggregation, bundle) measured and dismissed as non-problems. One stale doc line fixed (`api/README.md` listed the deleted `hf-darija` adapter).

## Open before production (found reviewing the `opencode` merge, 2026-08-04)
- [x] **Retention for the archive tables.** Done 2026-08-10 with the owner's policy: `media_files` 30 days, `chat_messages` 90 days, read `notifications` 30 days, `manager_reports` kept forever; env-tunable via `MEDIA_RETENTION_DAYS` / `CHAT_RETENTION_DAYS` / `NOTIF_RETENTION_DAYS`, swept by `logs.prune_meta` at 03:00 — see FIXED.md (Fourth pass)
- [ ] **`INTERNAL_API_KEY` must be set in the deployed n8n environment.** `/process` is auth-gated since this branch, and n8n has no browser, so it authenticates with `X-API-Key`. All 17 n8n HTTP nodes send the header; the key has to exist on *both* sides or every incoming message 401s. Unset on the API means machine access is disabled, never "everyone is a machine" — so the failure is a silent pipeline, not an open door.
- [ ] **`SMTP_USER` / `SMTP_PASS` are still unset in `.env`.** Every mail path is wired (`POST /notify/test`, the daily/weekly jobs, the to-do reminders) and none of them can actually send until the Gmail app password is filled in.
- [x] check email
- [] check Automated reports.
- [] check Automated weekly reports
- [] check images
- [x] better sign-in design (profesionnal) — 2026-08-10: rewritten with language switcher, accent glow, AZnet avatar, aria-busy submit — see FIXED.md (Fourth pass)
- [] adds 404 page.
- [x] remove image card generating in reports pages (make it auto when generating reports) — 2026-08-10: the card now rides along with the report's "Générer" click on both Daily and Weekly — see FIXED.md (Fourth pass)
- [] Add charging animation in the website, if things are getting charged from the database
- [] Add more columns inspired from the given data
