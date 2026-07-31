# Hardcoded secrets in n8n workflow

## 1. Google Sheet ID hardcoded

**File:** `n8n/aznet-complete.json:620`
```json
"documentId": {
  "__rl": true,
  "mode": "id",
  "value": "<GOOGLE_SHEET_ID>"
}
```

**Fix:** Replace with `$env.GOOGLE_SHEET_ID` expression.

## 2. HR email hardcoded in outsider reply

**File:** `n8n/aznet-complete.json:572,596`
```
"...contacter les ressources humaines : <HR_EMAIL>"
```

**Fix:** Replace `<HR_EMAIL>` with `$env.HR_EMAIL` expression in both occurrences.

## 3. Error handler HTTP node missing auth header

**File:** `n8n/aznet-complete.json:~1453`

The `POST /logs` node in the error handler band has no `X-API-Key` header. Every other HTTP node in the workflow sets it.

**Fix:** Add `sendHeaders: true` and `headerParameters: [{ name: "X-API-Key", value: "={{ $env.INTERNAL_API_KEY }}" }]` to the error handler's `POST /logs` node.

---

# Default Postgres credentials in docker-compose

**File:** `docker-compose.yml:16-17`
```yaml
POSTGRES_USER=${POSTGRES_USER:-pfe}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-pfe}
```

Defaults `pfe`/`pfe` are weak. Any deploy without `.env` overrides uses wide-open credentials.

**Fix:** Remove the `:-pfe` defaults so deployment fails hard if unset.

---

# Improvement Report — full-project audit (2026-07-31)

Three parallel audits covered `api/` (all 15 modules + tests), `Dashboard/` (all src), and n8n/benchmark/docs/spec. Bottom line: **the architecture is sound and unusually well-documented — but the security claim "everything is gated" is currently false, and the main pipeline path has a blocking-concurrency bug.**

## 🔴 Critical — fix before anything else

1. **Four endpoint groups are unauthenticated** — contradicting CLAUDE.md and the review-gate design:
   - `GET /logs` (api/app/main.py:563) — anyone reaching the API reads the full pipeline timeline incl. report payloads
   - `POST /process` (main.py:361) — direct callers bypass the n8n access-control lookup entirely and burn free-tier quota
   - `PATCH /sheet-queue/{id}` (main.py:904) — can drop parked reports (`ok=true` = data loss)
   - `POST|GET /service-samples` (main.py:883) — poisons uptime history
   Fix: `/process` = `X-API-Key` (machine), the rest `require_human`/`require_user`.
2. **No upload size cap** — `audio.read()`/`image.read()` (main.py:288,328) load the whole upload into RAM, defeating UploadFile's disk spooling. Cap at ~25 MB + content-type check.
3. **`.env` hygiene** — weak `ADMIN_PASSWORD` (8 chars), an n8n admin credential fragment in the `WEBHOOK_URL` comment, placeholder `DASHBOARD_PASSWORD`. Rotate + clean.
4. **Verify token literal `'pfe-aznet-verify'`** in `n8n/aznet-complete.json:950` (a public-repo file) — `check_secrets.py`'s 20-char regex misses it. Move to `$env.WHATSAPP_VERIFY_TOKEN`.

## 🟠 High — availability & correctness

5. **STT blocks the event loop** — `_transcribe_audio` calls the sync provider directly (main.py:294-296); a 120 s HF call stalls every request. Extraction/image already use `run_in_threadpool` (main.py:333) — the voice path missed it.
6. **STT has no fallback chain** — one engine (`config.py:21`); a Groq outage kills the primary path while extraction has ranked multi-vendor chains. Add `stt_chain` (groq → gemini) mirroring the design.
7. **Scheduler single-thread hang** — a hung model call (SDK default timeouts) stalls the 5-min drain and the 03:00 batch (jobs.py:158-183). Add per-job timeouts.
8. **`seed_admin` reads `os.environ`** (auth.py:125) instead of `settings` — under host-run `uvicorn --reload` (the documented dev flow) `.env` is never loaded, so seeding silently fails.
9. **Login throttle is in-memory + unbounded** (main.py:113,150-165) and **`sessions`/`processed_messages`/`user_actions` never prune** (only `pipeline_logs`/`service_samples` are swept).
10. **`refresh_one/all_profiles`** (main.py:773-800) lack try/except — Sheets outage → unhandled 500 instead of the 502 contract.
11. **Sheets client rebuilt per call** + no 429 backoff (sheets.py:19-34); **pool `getconn()` no timeout, dead connections returned un-closed** (logs.py:269-273).
12. **Timezone**: `jobs._due` uses naive `datetime.now()` (jobs.py:268) — hours silently shift on host-run dev.

## 🟡 Medium — dashboard

13. **Skip link is broken by the hash router** — `href="#main"` (app-shell.tsx:57-62) parses as route `main` → falls back to Overview; clicking it on any page navigates you home. The one concrete functional bug found.
14. **No 401/session-expiry handling** — server-side session deletion leaves pages showing errors forever; no bounce to login. Add global 401 → `signOut()`.
15. **Duplicate polling** — pages + `OpsProvider` fetch the same keys (`/reports`, `/logs`, `/health`); `ServerStatus` hard-polls at 30 s even when the user chose Manual refresh (server-status.tsx:22-23).
16. **`queue` nav item is a dead stub** — in `ROUTES` + nav, but no route case and `api.queue` never called.
17. **Consolidate**: 7 hand-built copies of the segmented control, ~40 dead locale keys (pipeline-era leftovers), duplicated `Band` component + date utils + relative-time formatting.
18. **A11y**: no focus trap in either dialog, ARIA combobox violation in the command palette (`aria-activedescendant` + tabbable options), 371 tabbable day-cells in the contribution graph, empty `<track>` in inbox.

## 🟢 Low — cleanup & doc rot

19. **Triplicated chain parsing** (extraction.py:40, memory.py:43, imagegen.py:112) with three exception types; `daily_report.py` hardcodes models instead of using a chain.
20. **`vault/api-schemas.md` is flat-out wrong** — documents 7 fields that don't exist in `schemas.py`. Also stale: `vault/security-secrets.md` (claims SHA-256; it's bcrypt; lists ghost vars `SECRET_KEY`, `GOOGLE_DRIVE_REFRESH_TOKEN`), `vault/deployment-guide.md` (ports/3-services vs actual compose), `n8n/README.md` §5 ALLOWLIST + §8 native trigger (workflow uses table lookup + manual webhooks), `vault/n8n-workflows.md:16` ("legacy files kept" — deleted 2026-07-29), `.env.example` (missing 10+ vars, "Gemini 2.5 Flash" comment).
21. **n8n**: Graph API `v20.0` hardcoded ×3, `settings.errorWorkflow: ""` + `active: false` on export (fresh import silently lacks the error band), first-wins dedupe drops a message if n8n crashes between extraction and `/process`.
22. **Stray artifacts**: `opencode-fix.md`, `sonar-project.properties` at root; `requirements.in` referenced in headers but doesn't exist.
23. **STT benchmark fully blocked** — `benchmark/dataset/audio/` doesn't even exist (not just empty). Record ~15-20 real Darija clips this week; everything else about `stt_provider=groq` is assumption.

## 📋 Spec gaps (docs/cahier-des-charges.md)

- **§7 per-report manager notification**: only scheduled email exists, and **SMTP creds are still unset** — nothing has ever actually sent. Set them + test `POST /notify/test` before the demo.
- **§10 deliverables**: user guide (1 page) and the final report/presentation are unwritten (Sprint 3).
- `lien_audio` stores a `file_id` that expires; captions are captured but never sent to `/process`.
- WhatsApp still in Meta test mode; pilot runs on Tailscale, not the aznet server.

**Quick wins this week** (highest impact/time): items 1, 2, 5, 6, 13, 14, 23 — and then the demo deliverable (SMTP + user guide).

---

# Suggested TO-DO additions (2026-07-31)

Candidates for the TO-DO list, mapped to the audit findings (nothing duplicates existing items).

## Security (the 🔴 set from the audit)

- Gate the 4 unauthenticated endpoint groups: `GET /logs`, `POST /process`, `PATCH /sheet-queue/{id}`, `POST|GET /service-samples` (main.py)
- Cap upload size on `/process` (audio/image) at ~25 MB + content-type check
- Move `'pfe-aznet-verify'` WhatsApp verify token to `$env.WHATSAPP_VERIFY_TOKEN` in the n8n workflow
- Rotate weak `ADMIN_PASSWORD` + clean the n8n admin URL fragment in the `WEBHOOK_URL` comment in `.env`

## Reliability

- STT fallback chain (groq → gemini) so a Groq outage doesn't kill the main path
- Wrap the STT call in `run_in_threadpool` — it currently blocks the whole event loop
- Add per-job timeouts to the scheduler thread (a hung model call stalls the 5-min Sheet drain)
- Prune `sessions`/`processed_messages`/`user_actions` (only logs/samples are swept today)

## Dashboard

- Fix the skip-link/`#main` hash-router conflict (navigates back to Overview)
- Auto sign-out on 401 (session deleted server-side → currently stuck on error states)
- Dedupe polling: `ServerStatus` ignores the Manual-refresh setting; pages + OpsProvider fetch the same endpoints
- Build the `queue` nav item — it's a dead stub in the router
- Focus trap in the command palette + settings dialog

## Pipeline/data

- n8n crash-safe dedupe: currently a crash after extraction permanently drops that message (advance `lastUpdateId` only after `/process` succeeds)
- Per-report manager notification via WhatsApp (spec §7) — email only exists today, and SMTP is unset

## Spec/deliverables (for the Aug 31 deadline)

- Write the 1-page user guide (spec §10 deliverable)
- Record the STT benchmark dataset (~15-20 real Darija clips) — everything else is blocked on it
