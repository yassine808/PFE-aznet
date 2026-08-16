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
| STT (Darija) | **Settled by benchmark, 2026-08-07/08** (`benchmark/STT-BENCHMARK-STATUS.md`): 13 engines, 3 by API and 12 locally on an RTX 3070, over 11 real clips. `stt_chain = gemini,local,groq` — ordered by **accuracy judged against the audio by a native speaker**, not by latency. `local` is `BounharAbdelaziz/Morocco-Darija-STT-large`, the only engine preserving both numeric quantities and French technical loanwords; groq is last on purpose, as the always-available floor. The `hf-darija` adapter was **deleted**: it pointed at a checkpoint that does not exist, and an unset `HF_TOKEN` made it fail at the token check before it could reach the 404, so it never ran once |
| Test dataset | 11 real Darija chantier clips, used for the benchmark. **WER and CER were deliberately not computed** — see §8 |
| LLM | **Ranked chains, one per input shape** (benchmark 2026-07-27 over 10 Darija/French cases): text = `groq gpt-oss-120b → gemini flash-lite → gemini-3.6-flash` (alternates vendors so free-tier quotas meter separately); image = Google-only `gemini-3.6-flash → 3.5-flash-lite → flash-lite` (no free Groq vision model, reconfirmed 2026-08-15 against the live catalogue); profiles = same text chain. **There is no image-generation chain** — it was deleted 2026-08-15, see Sprint 2 |
| Backend/Frontend | **FastAPI (Python)** + **React (TypeScript)**, web only (Electron dropped) |
| Hosting | Dev: Docker Compose + FastAPI hot-reload local. Public URL for the WhatsApp webhook is a **Tailscale Funnel** (stable hostname, so Meta is configured once and survives reboots) — Cloudflare was not used. **Vercel was rejected:** the dashboard is served same-origin behind the compose nginx, which is the only service publishing a host port. Pilot: the same compose on the aznet server |

## 2. Assumptions (veto anytime)

1. PFE report written in **French** (EMSI standard); code/comments in English.
2. Methodology: **Scrum-light** — 3 sprints × 2 weeks, backlog on GitHub Projects, sprint demo to director each cycle. Gives the report a methodology chapter.
3. **Google Sheets = single source of truth** (per cahier). Dashboard reads Sheets API. PostgreSQL/Supabase documented as evolution path, not built.
4. Notifications: **email (Gmail SMTP)** primary + **Telegram** confirmation reply to the technician (no session-window limit, unlike WhatsApp's 24h rule). Teams webhook documented as config option.
5. Dashboard: **authenticated since 2026-07-29** — reversed the 2026-07-23 "no auth, admin PC only" assumption because the director and the chefs de chantier now use it and the history has to say who did what. Accounts live in `persons` (the `users` table was folded in on 2026-08-01 — an account is a person with a `password_hash`), bcrypt, opaque session tokens in Postgres behind an httpOnly cookie, roles `directeur` / `chef`, and every endpoint gated on the API rather than on the login form. n8n gets in with `X-API-Key`. Still on one PC, but the two publishing blockers were cleared on 2026-07-30: `cors_origins` defaults to the two Vite dev origins and never `*` (a wildcard cannot coexist with `allow_credentials` anyway), and `/auth/login` throttles at 8 failures / 5 min per client address, resolved through `trusted_proxy_hops` — 1 for nginx alone, 2 with a Tailscale Funnel in front, because a wrong value either lets a script rotate the header or locks every visitor onto one key. Rebuilt 2026-07-26 in `Dashboard/` (light/dark + FR/EN/AR RTL i18n from `Dashboard/src/locales/`).
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
 ├─ audio → STT chain: gemini → local (GPU sidecar) → groq   ← order set by the
 │            benchmark, by accuracy against the audio, not by latency
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
 POST /journal  (the API writes the Sheet, not n8n — since 2026-08-05)
   ├─ merge on (date, technicien) in that chantier's own tab
   │    numbers add · locations union · prose appends · stock replaces
   ├─ reconcile stock; a mismatch emits stock_ecart with the delta
   ├─ mirror a flat row into Rapports for the dashboard feed
   └─ write failed → 502 + failed_writes (Postgres) → drained every 5 min
        through this same function, so a retry cannot become a duplicate

 API scheduler (jobs.py, 30 s tick, times from app_settings):
   ├─ sheet-queue drain       — every 5 min
   ├─ prune logs/samples      — 03:00, 30-day retention
   ├─ refresh profiles        — 03:00, reads the Sheet
   ├─ daily report email      — Mon–Sat, default 18:30, Gmail SMTP
   └─ weekly report email     — weekly_day/weekly_time (0 = Monday)
   (both carry the .docx and the material alerts; both proven by a forced run
    on 2026-08-16 — the weekly one had never fired and its subject said
    "Rapport journalier")

 Dashboard (React, login required — sessions in Postgres, X-API-Key for n8n)
   ├─ GET /reports · PATCH /reports/{row}      → Sheets read/write
   ├─ GET /jobs · POST /jobs/{name}/run        → run + re-run scheduler jobs
   ├─ GET/PUT /settings · POST /notify/test    → automation + SMTP proof
   ├─ GET/PUT /me/settings                     → per-account UI prefs (clock, density, seuil)
   ├─ GET /messages · GET /media/{id}/file     → archived chat + audio/photo blobs
   ├─ POST /reply                              → answer a technician on their own channel
   ├─ GET /notifications · POST /notifications/read → the per-account bell
   ├─ GET/POST/PATCH/DELETE /tasks             → shared to-do + reminders
   ├─ POST|GET /logs · GET /n8n/*              → live pipeline + n8n tails
   └─ GET/POST/DELETE /technicians …           → access control

 Chat commands: REMOVED 2026-08-15 (see §4, Sprint 2). Telegram now ignores
 any message starting with a slash.
```

**The schema was rebuilt on 2026-08-05** from the director's real tracking file (*Tableau de Suivi projet*), replacing the generic cahier §3 field list. It now carries one typed quantity field per journal column — `cables_prepares_m`, `cables_installes_m`, `goulotte_m`, three separate prise counters (bureau, panneau, testée), `fibre_m`, `interconnexions`, `connexions_optiques_brins` — plus an enum-validated multi-valued location (`etages` RDC/E1..E4, `ailes`, `locaux_techniques` RG/SR1..SR10), stock, and `remarques`. An unrecognised location **raises** rather than being dropped, so the chain retries instead of writing an invented floor. **`chantier_mentionne` became a model field on 2026-08-15**, reversing the earlier rule ("routing comes from the org chart, never from what the model thought it heard"). The org chart is only correct while a manager maintains it, and managers do not open the dashboard — so the technician naming their own site wins. Precedence: **the spoken name → the site on their own most recent row ("sticky", no expiry, and the reply says `(repris du dernier rapport)` so an inherited site is visible) → the chef's `persons.chantier_id` via `manager_id` → `Non affecté`**. The spoken name is never trusted as a tab name: it is normalized (accents, case, punctuation, leading article) and matched against the `chantiers` table, deliberately **without** fuzzy matching — collapsing `ACAPS` into `ACAPS 2` is a silent wrong row, while failing to match only creates a visible one. A genuine no-match creates the chantier marked `verifie = false` and flags the row, so a real new site works the first time it is mentioned and the director confirms it afterwards.

**Reply-first ordering is deliberate:** the technician gets their summary before the Sheet append, so a Sheets outage never costs them their reply. The `Rapport exploitable ?` gate therefore sits *after* the reply, never before it.

**A clean extraction is not the same as a report.** "Salam" extracts perfectly — every field `null` plus a polite `resume` — so the API emits a `no_report_content` warning when no data field was filled. Without it the pipeline answered "✅ Rapport enregistré" to a greeting and wrote a row of blanks (fixed 2026-07-30).

## 4. Timeline (Jul 15 → Aug 31)

### Week 0 — Setup & risk-kill (Jul 15–19)
- [x] Accounts: Telegram bot (BotFather), Google Cloud (Sheets API), Groq, Gemini (AI Studio), WhatsApp Cloud API. **Not used:** Cloudflare (public URL is a Tailscale Funnel instead), Vercel (rejected — the dashboard is served same-origin behind nginx).
- [x] Repo scaffold: `api/`, `Dashboard/` (replaced `web/` 2026-07-26), `n8n/`, `docs/`, `benchmark/`
- [x] Docker Compose n8n up + **E2E smoke test PASSED (Jul 17): Telegram voice note → n8n polling workflow → binary audio downloaded** (biggest integration risk killed; localhost-only via getUpdates polling, no tunnel needed)
- [x] Dataset recorded — 11 real Darija chantier clips, enough to run the benchmark (2026-08-07/08)
- [ ] Director sign-off on this plan + ask: aznet server? real technician recordings?

### Sprint 1 — AI core + benchmark (Jul 20 – Aug 1)
- [x] FastAPI skeleton, `TranscriptionProvider` interface + 3 adapters (`groq` / `gemini` / `local`; `hf-darija` deleted, it had never run)
- [x] **Benchmark run and settled (2026-08-07/08)** — 13 engines over 11 real clips, 3 by API and 12 locally on the RTX 3070. It reversed the initial hypothesis twice and exposed a silent harness bug that had been crowning a winner on a transcription never generated. Results in `benchmark/STT-BENCHMARK-STATUS.md`. The *extraction* side is measured separately: `benchmark/run_model_benchmark.py` ranks text and vision models on 10 hand-written Darija/French cases, and that table sets `extraction_text_chain` / `extraction_image_chain`.
- [x] Extraction: Pydantic schema, ordered per-modality fallback chains (text: `groq gpt-oss-120b` → `gemini flash-lite` → `3.6-flash`; image: `3.6-flash` → `3.5-flash-lite` → `flash-lite`), French reformulation prompt
- [x] Unit tests (**412** across 33 files, no API keys and no database needed) + golden-set eval on extraction (the benchmark's 10 cases, two of which exist purely to catch invented quantities)
- **Exit:** `/process` endpoint audio→structured JSON works; benchmark results table done ✅
- Report in parallel: état de l'art (STT Darija, LLM extraction, outils)

### Sprint 2 — E2E pipeline + web app (Aug 3 – Aug 14)
- [x] Full n8n workflow (unified Telegram + WhatsApp): reception → media download → `/process` → Sheets append → ✅ reply on originating channel. Access control + roles, dedupe, text-input mode, failure replies, end-of-day report cron, error-handler band. Scheduled work moved to the API scheduler (`api/app/jobs.py`) on 2026-07-29; n8n keeps reception + the error trigger.
- [x] Google Sheet `Rapports` structured per cahier §6 (+ `canal`, `confidence`, `flag_review`)
- [x] Text mode via `/process` (typed reports on both channels); standalone React form still optional
- [x] Dashboard v1: report list, filters (technicien/chantier/date), review queue on `flag_review`, confidence %, inline Sheet correction. Backend `/reports` + `/reports/{row}` (`api/app/sheets.py`).
- [x] Failure path: low-confidence → `flag_review=true` row + confidence column, surfaced in dashboard review queue
- [x] Dashboard v2 redesign (2026-07-24): neutral Efferd-style framed panels, light/dark, FR/EN/AR (RTL) i18n from JSON, 16 metrics (Activité/Production/Qualité/Cadence incl. WoW, Darija-voice share, API uptime), per-tech summary, recent/health/activity row. Backend `GET /health` now returns uptime for the ops tile.
- [x] **Four models, not one** (2026-07-27/29, image generation dropped 2026-08-15): STT, text extraction, vision extraction, and a nightly technician-profile model (`app/memory.py`). Image *generation* was the fifth and is gone — Google answers every free image model with `429` and "check your plan and billing details", reproduced twice including on a cold quota, and none of the other free endpoints returned pixels either (0 of 8). Image *understanding* stays and is the half that works. Prompts moved out of Python into versioned Markdown under `api/app/prompts/` with a shared `00-soul.md` identity.
- [x] **One person across channels** (2026-07-29): `persons` / `technicians` split so a colleague's profile follows them rather than their phone number; the n8n allowlist now reads the table instead of a hardcoded JS literal.
- [x] **Dashboard accounts + audit trail** (2026-07-29): login, bcrypt, revocable sessions, roles, `user_actions` (with before → after on report edits) and `page_visits`, surfaced in the new **Équipe** panel. New **Journaux** panel renders the live pipeline log.
- [x] **One person, one row** (2026-08-01): the `users` table folded into `persons`; `password_hash IS NOT NULL` is now the whole of "this row is an account", so a chef who also sends voice notes is one box on the org chart instead of two unrelated rows.
- [x] **Archive + conversation** (2026-08-04): audio pushed to Drive for a durable `lien_audio`, raw media and chat archived in Postgres (`media_files`, `chat_messages`), and the Inbox rebuilt as a real conversation view with a reply composer (`POST /reply`, the API answers on the technician's own channel).
- [x] ~~**Technician-side commands** (2026-08-04): `/rapport`, `/modify`, `/supprimer`~~ — **removed 2026-08-15.** They were a second, text-parsed way into data the dashboard already edits, and every one of them had to be kept true twice. Out with them went the four n8n command nodes and their six reply nodes, `GET /rapport`, `POST /modify-command`, `POST /messages/link`, `logs.message_row` and `logs.latest_manager_report`. `processed_messages.rapports_row` **stayed**: `GET /audio/row/{row}` resolves a message's archived voice note through it for the inbox player.
- [x] **Report editing + versions** (2026-08-04): daily and weekly reports are editable in the dashboard with a line diff and an append-only history (`report_versions`); export is `.docx` only — txt and markdown carry neither the figures table nor the heading structure, so exporting one produced a document quietly missing half of what the operator was looking at. **The renderer moved into the API on 2026-08-16** (`app/docx_report.py`): it lived in the browser, so the *scheduled* mail — sent by `jobs.py` from a thread inside the container — could not attach a document at all, and one only existed if a human clicked Export. Now every report mail carries it, `POST /reports/export` serves the same bytes to the dashboard button, and the figures are recomputed server-side from the Sheet rows rather than posted by the client.
- [x] **Bell, tasks and per-account settings** (2026-08-04): per-account notifications, a shared to-do page with lead times and custom cadences (both rung by `jobs.py`), and UI preferences stored server-side in `person_settings` so they follow the person, not the browser.
- [x] Visual verification of the dashboard — `Dashboard/scripts/visual-check.mjs` logs in headless, walks all 9 pages and fails on console errors, HTTP ≥ 400, horizontal overflow, broken images or a blank page.
- [x] **The schema rebuilt on the director's real file** (2026-08-05): typed quantity fields per journal column, enum-validated locations, stock, remarques. `has_data` now counts remarques, location and stock — a day with no metres but a blocker *is* the report he most needs.
- [x] **The Sheet write moved from n8n into the API** (2026-08-05, `POST /journal`): one row per (date, technicien) in that chantier's own tab. Two rules make it correct — **accumulation** (a second message the same day merges: numbers add, locations union, prose appends) and **stock reconciliation** (a reported figure wins and becomes the new baseline; a mismatch emits `stock_ecart` with the delta rather than silently picking a number). Merging needs a read-modify-write that an IF node cannot express. Reply-first ordering is unchanged.
- [x] **Chantiers and the bordereau** (2026-08-05): a site owns a journal tab and a contract quantity list. The chef's `persons.chantier_id`, inherited by their technicians, was the whole of routing at first; since 2026-08-15 it is the **third** rule, behind the site the technician names and the site on their own last row — a stale assignment ahead of a live signal silently misfiles a crew that moved. `GET /chantiers/{id}/bordereau` computes installed quantities from the journal on every call and stores them nowhere.
- [x] **Rapports mirror + n8n rewire** (2026-08-09): `file_report` also appends a flat row for the dashboard feed, so the field→column mapping moved out of untestable n8n expressions into Python. The googleSheets append node and its four companions are gone; n8n now writes no Sheet at all.
- [x] **Local Darija engine containerised** (`stt-local`, GPU sidecar): weights bind-mounted rather than baked (5.8 GB, over GitHub's LFS ceiling), lock-guarded so two notes cannot both start a 4 GB load and OOM an 8 GB card. **Preloaded at startup since 2026-08-16** (`STT_LOCAL_PRELOAD=1`): the load takes 280-394 s and used to be paid *inside the first request*, which was over the 300 s client budget — so every first call failed, and failing warmed the model so the retry passed. From outside that reads as "slow the first time", which is why it went unnoticed: this engine had never once answered its first request.
- [x] **Material received ≠ material installed, and alerts before a site runs out** (2026-08-16): `extraction-image.md` was telling the vision model to read a bon de livraison into the *installed* article columns, so delivered quantities inflated the very number the bordereau's `avancement` is computed from. `ExtractedReport.nature` / `livraisons` split them, deliveries go to a `receptions` ledger (Postgres) mirrored to a flat `Livraisons` tab, and no journal row is written for one. On top of that, `app/stock.py` answers "what is about to run out": a ranked source chain (stock followed on the tab → `Σ reçu − Σ posé` → `qte_marche − installé` → nothing), **days of cover over active days** rather than a flat percentage, and every finding carrying the sentence saying which source answered. Python decides every figure and the model only writes French around it. Surfaces in the report mail, the .docx and the new **Chantiers** page, which is also where confirming an unverified site moved from Overview.
- [x] Email notif: SMTP wired (`POST /notify/test`, recipients in the Automation panel), `SMTP_USER`/`SMTP_PASS` set in `.env` (2026-08-12)
- [ ] Live demo to director
- Report in parallel: conception (UML: use cases, séquence, classes, déploiement)

### Sprint 3 — Pilot, docs, report (Aug 17 – Aug 28)
- [ ] Deploy pilot (aznet server), register 2–3 real phone numbers — **the last open item that gates real numbers**: §4.6.4 (latence E2E), §4.6.5 (pilote) and the résumé/abstract/ملخص all reserve a slot for them
- [x] Wave-2 benchmark on real notes — done as *the* benchmark (11 real clips, 2026-08-07/08)
- [x] Cahier deliverables: documented n8n workflow (Annexe D), AI prompts doc (Annexe C), installation doc (Annexe E), user guide (Annexe F)
- [x] Report bulk writing: réalisation, banc d'essai, conclusion & perspectives — `Pres+report/Rapport-PFE.md` → `.docx`, 137 pages, EMSI-compliant (margins, i/ii/iii → 1/2/3 pagination, 61 cited figures and tables, table titles above)
- [x] Presentation deck — `Pres+report/Soutenance-PFE.pptx`, 23 slides + 6 backup captures, built from `presentation.py`. **Demo will be live from the laptop**; the backup captures cover the same parcours if the network or a free tier fails, so no recorded video is needed
- **Exit:** report v1 complete ✅, pilot still to run

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

## 7. PFE report — as written (French)

`Pres+report/Rapport-PFE.md` is the single source; `build.ps1` produces the `.docx`
(and the PDF with `-ExportPdf`). Four chapters rather than the seven planned —
analyse et spécification folded into chapter 1, tests folded into chapter 4:

1. **Contexte général** — organisme, étude de l'existant, problématique, besoins, MoSCoW, conduite du projet, risques
2. **État de l'art et étude technique** — darija comme langue peu dotée, Whisper vs wav2vec2/CTC, extraction par LLM à sortie contrainte, plateformes d'orchestration, canal de réception, technologies retenues
3. **Conception** — architecture hybride et la frontière orchestration/code, modèle de données, service applicatif (Stratégie, chaînes de repli, contrat d'erreurs, prompts versionnés, profils, journal, ordonnanceur), workflow, tableau de bord, sécurité, données personnelles
4. **Réalisation, banc d'essai, tests et résultats** — environnement, le banc d'essai des 13 moteurs, difficultés résolues, stratégie de test et CI, résultats, coûts et quotas, statistiques et qualité
- Bilan et compétences · Conclusion et perspectives · Références · **Annexes A–H**

Format is checked against `Pres+report/build/guidance-emsi.pdf` (now in version
control — the generic `build/` rule in `.gitignore` had been swallowing it).

## 8. Success metrics (defense-ready numbers)

- Report submission time < 2 min (cahier's own KPI)
- E2E latency voice-note → journal row: **to be measured on the pilot**. Unit latencies are known: transcription 1,53 s (Groq) to 7,7 s (local engine) — **warm**. The local engine's 280-394 s model load is now paid at container startup (`STT_LOCAL_PRELOAD=1`, 2026-08-16), not inside the first request; `COLD_START_BUDGET_S = 420` client-side and `proxy_read_timeout 460s` in nginx remain, and nginx's must stay above the client budget or the proxy silently caps a budget the API thinks it owns. Any quoted local-engine latency must say whether it is warm or cold
- Extraction accuracy on golden set: target > 90% fields correct
- **STT: WER and CER were deliberately not computed.** Establishing a ground truth in darija presupposes a reference orthography that does not exist — two equally correct transcriptions diverge on spelling, and WER punishes that divergence exactly like an error of meaning. The criterion is applicative instead: preservation of numeric quantities and French technical loanwords, judged against the audio by a native speaker, because that is all the journal consumes. The limit is stated in the report: rigorous, but not reproducible by a third party without the same speaker.
