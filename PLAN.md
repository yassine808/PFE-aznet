# PFE Plan — Daily Report Automation for Cabling Technicians (aznet.ma)

**Student:** Yassine · **School:** EMSI · **Hard deadline:** Aug 31, 2026 (code + report + presentation, 100%)
**Constraint:** zero budget — free tiers only.

---

## 1. Decisions locked (interview July 15)

| Branch | Decision |
|---|---|
| Scope | Hybrid: n8n orchestration (per cahier) + custom-coded AI service + web app (for PFE substance) |
| Code boundary | **Option A** — you code: FastAPI AI service (STT + LLM extraction + French reformulation), React web form, manager dashboard. n8n does: **Telegram** reception, Sheets writes, notifications |
| Reception channel | **Telegram Bot API + WhatsApp Cloud API — both live** (unified n8n workflow, one import: `n8n/aznet-complete.json`). Telegram first (no Meta friction); WhatsApp brought up E2E 2026-07-23 (System User token = no expiry, published app, WABA `subscribed_apps`, manual GET-echo webhook since n8n's WhatsApp Trigger fails Meta's challenge, media download via HTTP node). Cahier §5 *"passerelle équivalente"* satisfied and then some. Channel-agnostic: both feed one `/process` + one Sheet; reply goes back on the originating channel |
| STT (Darija) | Week-1 **benchmark** via `TranscriptionProvider` adapter interface: Groq Whisper-large-v3, Gemini native audio (uses `gemini_model`, currently flash-lite), 1 HF Darija fine-tune. Benchmark picks the primary; until the dataset is recorded, `stt_provider=groq` by assumption |
| Test dataset | 15–20 **self-simulated** Darija voice notes + hand-written reference transcriptions. Wave 2 with real technician notes if director provides |
| LLM | **Ranked chains, one per input shape** (benchmark 2026-07-27 over 10 Darija/French cases): text = `groq gpt-oss-120b → gemini flash-lite → gemini-3.6-flash` (alternates vendors so free-tier quotas meter separately); image = Google-only `gemini-3.6-flash → 3.5-flash-lite → flash-lite` (no free Groq vision model); image card = `gemini-3.1-flash-image → nano-banana-pro → 3-pro-image` (click-only, never a cron); profiles = same text chain |
| Backend/Frontend | **FastAPI (Python)** + **React (TypeScript)**, web only (Electron dropped) |
| Hosting | Dev: Docker Compose (n8n) + FastAPI hot-reload local + **Cloudflare tunnel** for webhooks. Front: Vercel free. Pilot: same compose on aznet server if available, else Oracle Always Free VM |

## 2. Assumptions (veto anytime)

1. PFE report written in **French** (EMSI standard); code/comments in English.
2. Methodology: **Scrum-light** — 3 sprints × 2 weeks, backlog on GitHub Projects, sprint demo to director each cycle. Gives the report a methodology chapter.
3. **Google Sheets = single source of truth** (per cahier). Dashboard reads Sheets API. PostgreSQL/Supabase documented as evolution path, not built.
4. Notifications: **email (Gmail SMTP)** primary + **Telegram** confirmation reply to the technician (no session-window limit, unlike WhatsApp's 24h rule). Teams webhook documented as config option.
5. Dashboard: **authenticated since 2026-07-29** — reversed the 2026-07-23 "no auth, admin PC only" assumption because the director and the chefs de chantier now use it and the history has to say who did what. Accounts live in `persons` (the `users` table was folded in on 2026-08-01 — an account is a person with a `password_hash`), bcrypt, opaque session tokens in Postgres behind an httpOnly cookie, roles `directeur` / `chef`, and every endpoint gated on the API rather than on the login form. n8n gets in with `X-API-Key`. Still on one PC; publishing needs CORS narrowed and a login rate limit first. Rebuilt 2026-07-26 in `Dashboard/` (light/dark + FR/EN/AR RTL i18n from `Dashboard/src/locales/`).
6. Git repo (this one), conventional commits, README per module.

## 3. Architecture

```
Technician
   │ voice note (Darija) / photo / typed text
   ▼
Telegram (polling)  +  WhatsApp Cloud API (webhook via Tailscale Funnel)
   └─────────┬───────────┘
             ▼
          n8n (Docker) — unified workflow (reception + error handler)
             │ mint correlation_id → POST /logs/claim (dedupe)
             │ GET /technicians/lookup → authorized?  (persons ⟷ technicians)
             │   ├─ outsider → one HR-contact reply, then silence
             │   └─ employee → Media or text?  →  Audio or image?
             ▼
 FastAPI AI Service   (exactly one of audio | image | text)
 ├─ audio → STT (groq whisper-large-v3 → gemini → hf-darija) → text
 ├─ image → vision chain, photo → schema in one call (flag_review=true)
 ├─ text  → extraction chain (ranked, cross-vendor fallback)
 └─ extraction prompt ← persons.profile (nightly model, context only)
             │ JSON (ExtractedReport)
             ▼
 n8n: ✅ reply to technician (originating channel)   ← reply FIRST
             │
             ▼
      `Rapport exploitable ?`  (has_data → no_report_content?)
             │
             ▼
      append row → Google Sheets (Rapports)
           └─ write failed → failed_writes (Postgres) → drain every 5 min

 API scheduler (jobs.py, 30 s tick, times from app_settings):
   ├─ sheet-queue drain       — every 5 min
   ├─ prune logs/samples      — 03:00, 30-day retention
   ├─ refresh profiles        — 03:00, reads the Sheet
   ├─ daily report email      — Mon–Sat, default 18:30, Gmail SMTP
   └─ weekly report email     — weekly_day/weekly_time (0 = Monday)

 Dashboard (React, login required — sessions in Postgres, X-API-Key for n8n)
   ├─ GET /reports · PATCH /reports/{row}      → Sheets read/write
   ├─ GET /jobs · POST /jobs/{name}/run        → run + re-run scheduler jobs
   ├─ POST /generate-image                     → illustrated summary card (click only)
   ├─ GET/PUT /settings · POST /notify/test    → automation + SMTP proof
   ├─ GET/PUT /me/settings                     → per-account UI prefs (clock, density, seuil)
   ├─ GET /messages · GET /media/{id}/file     → archived chat + audio/photo blobs
   ├─ POST /reply                              → answer a technician on their own channel
   ├─ GET /notifications · POST /notifications/read → the per-account bell
   ├─ GET/POST/PATCH/DELETE /tasks             → shared to-do + reminders
   ├─ POST|GET /logs · GET /n8n/*              → live pipeline + n8n tails
   └─ GET/POST/DELETE /technicians …           → access control

 Technician-side commands (n8n branch → API):
   ├─ /rapport      → GET /rapport          (their manager's last digest)
   ├─ /modify …     → POST /modify-command  (re-extract, rewrite that Sheet row)
   └─ /supprimer    → POST /modify-command  (empty the row in place, never delete)
```

JSON schema = cahier §3: date, heure, technicien, chantier, client, type d'activité, goulottes_m, cables_m, bureaux_termines, panneaux_raccordes, autres_travaux, observations, rapport_complet, lien_audio (+ `canal`, `confidence`, `flag_review` added in Sprint 2).

**Reply-first ordering is deliberate:** the technician gets their summary before the Sheet append, so a Sheets outage never costs them their reply. The `Rapport exploitable ?` gate therefore sits *after* the reply, never before it.

**A clean extraction is not the same as a report.** "Salam" extracts perfectly — every field `null` plus a polite `resume` — so the API emits a `no_report_content` warning when no data field was filled. Without it the pipeline answered "✅ Rapport enregistré" to a greeting and wrote a row of blanks (fixed 2026-07-30).

## 4. Timeline (Jul 15 → Aug 31)

### Week 0 — Setup & risk-kill (Jul 15–19)
- [x] Accounts: Telegram bot (BotFather), Google Cloud (Sheets API), Groq, Gemini (AI Studio), WhatsApp Cloud API. **Not used:** Cloudflare (public URL is a Tailscale Funnel instead), Vercel (dashboard runs on the admin's PC). **HF token still unset** — the `hf-darija` adapter therefore cannot run.
- [x] Repo scaffold: `api/`, `Dashboard/` (replaced `web/` 2026-07-26), `n8n/`, `docs/`, `benchmark/`
- [x] Docker Compose n8n up + **E2E smoke test PASSED (Jul 17): Telegram voice note → n8n polling workflow → binary audio downloaded** (biggest integration risk killed; localhost-only via getUpdates polling, no tunnel needed)
- [ ] Record dataset: 15–20 simulated Darija chantier voice notes + reference transcriptions — **still empty; this is the single blocker on the STT decision**
- [ ] Director sign-off on this plan + ask: aznet server? real technician recordings?

### Sprint 1 — AI core + benchmark (Jul 20 – Aug 1)
- [x] FastAPI skeleton, `TranscriptionProvider` interface + 3 adapters (groq / gemini / hf-darija)
- [~] Benchmark harness: WER/CER harness written (`benchmark/run_benchmark.py`) but **cannot run without the audio dataset**, so the primary STT is still unpicked. The *extraction* side is measured: `benchmark/run_model_benchmark.py` ranks text and vision models on 10 hand-written Darija/French cases, and that table sets `extraction_text_chain` / `extraction_image_chain`.
- [x] Extraction: Pydantic schema, ordered per-modality fallback chains (text: `groq gpt-oss-120b` → `gemini flash-lite` → `3.6-flash`; image: `3.6-flash` → `3.5-flash-lite` → `flash-lite`), French reformulation prompt
- [x] Unit tests (53, no API keys or DB needed) + golden-set eval on extraction (the benchmark's 10 cases, two of which exist purely to catch invented quantities)
- **Exit:** `/process` endpoint audio→structured JSON works; benchmark results table done
- Report in parallel: état de l'art (STT Darija, LLM extraction, outils)

### Sprint 2 — E2E pipeline + web app (Aug 3 – Aug 14)
- [x] Full n8n workflow (unified Telegram + WhatsApp): reception → media download → `/process` → Sheets append → ✅ reply on originating channel. Access control + roles, dedupe, text-input mode, failure replies, end-of-day report cron, error-handler band. Scheduled work moved to the API scheduler (`api/app/jobs.py`) on 2026-07-29; n8n keeps reception + the error trigger.
- [x] Google Sheet `Rapports` structured per cahier §6 (+ `canal`, `confidence`, `flag_review`)
- [x] Text mode via `/process` (typed reports on both channels); standalone React form still optional
- [x] Dashboard v1: report list, filters (technicien/chantier/date), review queue on `flag_review`, confidence %, inline Sheet correction. Backend `/reports` + `/reports/{row}` (`api/app/sheets.py`).
- [x] Failure path: low-confidence → `flag_review=true` row + confidence column, surfaced in dashboard review queue
- [x] Dashboard v2 redesign (2026-07-24): neutral Efferd-style framed panels, light/dark, FR/EN/AR (RTL) i18n from JSON, 16 metrics (Activité/Production/Qualité/Cadence incl. WoW, Darija-voice share, API uptime), per-tech summary, recent/health/activity row. Backend `GET /health` now returns uptime for the ops tile.
- [x] **Five models, not one** (2026-07-27/29): STT, text extraction, vision extraction, image-card generation (`POST /generate-image`), and a nightly technician-profile model (`app/memory.py`). Prompts moved out of Python into versioned Markdown under `api/app/prompts/` with a shared `00-soul.md` identity.
- [x] **One person across channels** (2026-07-29): `persons` / `technicians` split so a colleague's profile follows them rather than their phone number; the n8n allowlist now reads the table instead of a hardcoded JS literal.
- [x] **Dashboard accounts + audit trail** (2026-07-29): login, bcrypt, revocable sessions, roles, `user_actions` (with before → after on report edits) and `page_visits`, surfaced in the new **Équipe** panel. New **Journaux** panel renders the live pipeline log.
- [x] **One person, one row** (2026-08-01): the `users` table folded into `persons`; `password_hash IS NOT NULL` is now the whole of "this row is an account", so a chef who also sends voice notes is one box on the org chart instead of two unrelated rows.
- [x] **Archive + conversation** (2026-08-04): audio pushed to Drive for a durable `lien_audio`, raw media and chat archived in Postgres (`media_files`, `chat_messages`), and the Inbox rebuilt as a real conversation view with a reply composer (`POST /reply`, the API answers on the technician's own channel).
- [x] **Technician-side commands** (2026-08-04): `/rapport` returns their manager's last digest, `/modify` re-extracts and rewrites *that* Sheet row via `processed_messages.sheet_row`, `/supprimer` empties the row in place — a positional delete would shift every row number below it and break every stored message→row link.
- [x] **Report editing + versions** (2026-08-04): daily and weekly reports are editable in the dashboard with a line diff and an append-only history (`report_versions`); export is `.docx` only, because it is the one format that can carry the generated card.
- [x] **Bell, tasks and per-account settings** (2026-08-04): per-account notifications, a shared to-do page with lead times and custom cadences (both rung by `jobs.py`), and UI preferences stored server-side in `person_settings` so they follow the person, not the browser.
- [x] Visual verification of the dashboard — `Dashboard/scripts/visual-check.mjs` logs in headless, walks all 9 pages and fails on console errors, HTTP ≥ 400, horizontal overflow, broken images or a blank page.
- [ ] Email notif on each report (daily cron done; per-report email optional) + live demo to director — SMTP is wired (`POST /notify/test`, recipients in the Automation panel) but `SMTP_USER`/`SMTP_PASS` are still unset in `.env`, so nothing can actually send yet
- Report in parallel: conception (UML: use cases, séquence, classes, déploiement)

### Sprint 3 — Pilot, docs, report (Aug 17 – Aug 28)
- [ ] Deploy pilot (aznet server or Oracle VM), register 2–3 real phone numbers
- [ ] Wave-2 benchmark on real notes if available
- [ ] Cahier deliverables: documented n8n workflow, AI prompts doc, installation doc (= compose + README), user guide (1 page)
- [ ] Report bulk writing: réalisation, tests/benchmark, conclusion & perspectives
- [ ] Presentation deck + **recorded demo video** (backup if live demo fails at defense)
- **Exit:** report v1 complete, pilot running

### Buffer (Aug 28–31)
Report polish, rehearsal, slack for slippage.

## 5. Risk register

| Risk | Mitigation |
|---|---|
| Darija WER too high on all engines | LLM prompt corrects STT noise using domain vocab (goulotte, câble, brassage...); Telegram reply asks technician to confirm summary; form fallback always works |
| WhatsApp prod migration (post-PFE) | Telegram carries pilot + defense (no recipient cap, no token expiry); Meta business verification + message-template approval documented as evolution, explicitly out of scope |
| Free-tier quotas | Volume tiny (~5–10 reports/day); adapter pattern swaps provider in minutes |
| Timeline slip | Cut-line order: dashboard → benchmark wave 2 → Teams option. Core (voice→Sheet+notif, form) protected. Fallback = Option B scope |
| Solo dev, report squeeze | Report written 2h/day in parallel from Sprint 1, not at the end |
| Deploying a fix that never ran | The API is a **built image** (`build: ./api`), so `docker compose restart` re-runs old code — use `up -d --build api`. n8n keeps its own copy of the workflow in its volume, so editing `n8n/aznet-complete.json` changes nothing until it is re-imported. Both bit on 2026-07-30; verify inside the container / via the n8n API, not by assuming |

## 6. Scope guard (MoSCoW)

- **Must:** Telegram voice → transcription → extraction → French summary → Sheets → email notif; web form; install doc; user guide
- **Should:** dashboard, STT benchmark chapter, Telegram confirmation reply, failure flagging
- **Could:** Teams webhook, PWA manifest, wave-2 benchmark, Supabase migration doc
- **Won't (this PFE):** Meta production approval, Electron, multi-company tenancy, Slack

## 7. PFE report skeleton (French)

1. Introduction générale — contexte aznet, problématique (rapports terrain non structurés)
2. État de l'art — STT arabe dialectal, LLM extraction structurée, outils d'automatisation (n8n vs alternatives)
3. Analyse & spécification — cahier des charges, besoins fonctionnels/non-fonctionnels, MoSCoW
4. Conception — architecture, UML (cas d'utilisation, séquence, classes, déploiement), choix technologiques justifiés (benchmarks)
5. Réalisation — service IA, workflow n8n, form & dashboard, sécurité
6. Tests & évaluation — benchmark STT (WER), précision d'extraction, latence E2E, pilote
7. Conclusion & perspectives — Supabase, WhatsApp prod, multi-chantiers, analytics

## 8. Success metrics (defense-ready numbers)

- Report submission time < 2 min (cahier's own KPI)
- E2E latency voice-note → Sheet row: target < 60 s
- Extraction accuracy on golden set: target > 90% fields correct
- STT WER per engine: measured, compared, argued
