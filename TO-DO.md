# TO-DO

Open items only. Everything marked done moves to `FIXED.md` — that file is the done log, this one is the queue.

- [ ] Finish STT benchmark → pick default provider — **blocked on the dataset**: `benchmark/dataset/audio/` is still empty, so `stt_provider=groq` is an assumption, not a measurement. Harness is ready (`benchmark/run_benchmark.py`).
- [x] Daily stat: % spoken Darija words vs French (post-PFE, zero cahier value)

## Code audit 2026-08-04 → `docs/audit-2026-08-04.md`
Full-read audit of the backend + the dashboard's data spine. 11 findings, each with file, line, cause and fix; the status table in that file is the source of truth. **3 bugs fixed** (profile never reaching the primary text model; every API restart cancelling that day's report; the scheduler loop being killable). **8 open**: 4 hardening (login timing oracle, unbounded throttle dict, cache-by-reference, uncapped `limit` params), 3 perf (two Sheets calls per write, a DB write per authenticated request, polling a hidden tab), 1 maintainability (daily/weekly report duplication). Coverage gap: `app/logs.py`, the rest of `app/main.py`, and the Dashboard pages were not read.

## Open before production (found reviewing the `opencode` merge, 2026-08-04)
- [ ] **Retention for the archive tables.** `media_files` holds raw audio/photo blobs in Postgres (25 MB cap each) and is never pruned; `chat_messages`, `notifications` and `manager_reports` grow without limit too. `jobs.prune_logs` → `logs.prune_meta` sweeps sessions/claims/audit/visits only. Needs a policy decision first — "archive" implies permanence, so this is a product call, not a bug: audio already has a durable Drive link, so the blobs are the cheapest thing to age out; read notifications older than 30 days are the next.
- [ ] **`INTERNAL_API_KEY` must be set in the deployed n8n environment.** `/process` is auth-gated since this branch, and n8n has no browser, so it authenticates with `X-API-Key`. All 17 n8n HTTP nodes send the header; the key has to exist on *both* sides or every incoming message 401s. Unset on the API means machine access is disabled, never "everyone is a machine" — so the failure is a silent pipeline, not an open door.
- [ ] **`SMTP_USER` / `SMTP_PASS` are still unset in `.env`.** Every mail path is wired (`POST /notify/test`, the daily/weekly jobs, the to-do reminders) and none of them can actually send until the Gmail app password is filled in.
- [x] check email
- [] check Automated reports.
- [] check Automated weekly reports
- [] check images
- [] better sign-in design (profesionnal)
- [] adds 404 page.
- [] remove image card generating in reports pages (make it auto when generating reports)
- [] Add charging animation in the website, if things are getting charged from the database
