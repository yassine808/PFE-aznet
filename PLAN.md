# PFE Plan — Daily Report Automation for Cabling Technicians (aznet.ma)

**Student:** Yassine · **School:** EMSI · **Hard deadline:** Aug 31, 2026 (code + report + presentation, 100%)
**Constraint:** zero budget — free tiers only.

---

## 1. Decisions locked (interview July 15)

| Branch | Decision |
|---|---|
| Scope | Hybrid: n8n orchestration (per cahier) + custom-coded AI service + web app (for PFE substance) |
| Code boundary | **Option A** — you code: FastAPI AI service (STT + LLM extraction + French reformulation), React web form, manager dashboard. n8n does: **Telegram** reception, Sheets writes, notifications |
| Reception channel | **Telegram Bot API + WhatsApp Cloud API — both live** (unified n8n workflow `reception-unified.json`). Telegram first (no Meta friction); WhatsApp brought up E2E 2026-07-23 (System User token = no expiry, published app, WABA `subscribed_apps`, manual GET-echo webhook since n8n's WhatsApp Trigger fails Meta's challenge, media download via HTTP node). Cahier §5 *"passerelle équivalente"* satisfied and then some. Channel-agnostic: both feed one `/process` + one Sheet; reply goes back on the originating channel |
| STT (Darija) | Week-1 **benchmark** via `TranscriptionProvider` adapter interface: Groq Whisper-large-v3, Gemini 2.5 Flash native audio, 1 HF Darija fine-tune. Benchmark picks the primary |
| Test dataset | 15–20 **self-simulated** Darija voice notes + hand-written reference transcriptions. Wave 2 with real technician notes if director provides |
| LLM | **Gemini 2.5 Flash** primary (structured JSON output, strong French) + **Groq Llama 3.3 70B** fallback adapter |
| Backend/Frontend | **FastAPI (Python)** + **React (TypeScript)**, web only (Electron dropped) |
| Hosting | Dev: Docker Compose (n8n) + FastAPI hot-reload local + **Cloudflare tunnel** for webhooks. Front: Vercel free. Pilot: same compose on aznet server if available, else Oracle Always Free VM |

## 2. Assumptions (veto anytime)

1. PFE report written in **French** (EMSI standard); code/comments in English.
2. Methodology: **Scrum-light** — 3 sprints × 2 weeks, backlog on GitHub Projects, sprint demo to director each cycle. Gives the report a methodology chapter.
3. **Google Sheets = single source of truth** (per cahier). Dashboard reads Sheets API. PostgreSQL/Supabase documented as evolution path, not built.
4. Notifications: **email (Gmail SMTP)** primary + **Telegram** confirmation reply to the technician (no session-window limit, unlike WhatsApp's 24h rule). Teams webhook documented as config option.
5. Dashboard: **no auth** — runs on the admin's PC only (localhost), decided 2026-07-23. Redesigned 2026-07-24 to a neutral Efferd-style app-shell with light/dark + FR/EN/AR (RTL) i18n loaded from JSON locales (`web/src/locales/`).
6. Git repo (this one), conventional commits, README per module.

## 3. Architecture

```
Technician
   │ voice note (Darija) / Telegram
   ▼
Telegram Bot API ──webhook──► n8n (Docker)
                                          │ download media
                                          ▼
                             FastAPI AI Service  ◄──── React Web Form (text mode)
                             ├─ TranscriptionProvider (adapters: Groq / Gemini / HF)
                             ├─ Extractor: LLM → Pydantic JSON (14 cahier fields)
                             └─ Reformulator: professional French summary
                                          │ JSON
                                          ▼
                                 n8n: append row → Google Sheets
                                          ├─ email to chef de chantier + resp. technique
                                          └─ Telegram confirmation reply to technician
                                          
Manager Dashboard (React/Vercel) ◄─ reads ─ Google Sheets API
```

JSON schema = cahier §3: date, heure, technicien, chantier, client, type d'activité, goulottes_m, cables_m, bureaux_termines, panneaux_raccordes, autres_travaux, observations, rapport_complet, lien_audio.

## 4. Timeline (Jul 15 → Aug 31)

### Week 0 — Setup & risk-kill (Jul 15–19)
- [ ] Accounts: **Telegram bot (BotFather)**, Google Cloud (Sheets API), Groq, Gemini (AI Studio), HF, Cloudflare, Vercel
- [ ] Repo scaffold: `api/`, `web/`, `n8n/`, `docs/`, `benchmark/`
- [x] Docker Compose n8n up + **E2E smoke test PASSED (Jul 17): Telegram voice note → n8n polling workflow → binary audio downloaded** (biggest integration risk killed; localhost-only via getUpdates polling, no tunnel needed)
- [ ] Record dataset: 15–20 simulated Darija chantier voice notes + reference transcriptions
- [ ] Director sign-off on this plan + ask: aznet server? real technician recordings?

### Sprint 1 — AI core + benchmark (Jul 20 – Aug 1)
- [ ] FastAPI skeleton, `TranscriptionProvider` interface + 3 adapters
- [ ] Benchmark harness: WER/CER per engine + extraction accuracy → **pick primary STT** (report chapter material)
- [ ] Extraction: Pydantic schema, Gemini structured output, French reformulation prompt
- [ ] Unit tests + golden-set eval on extraction
- **Exit:** `/process` endpoint audio→structured JSON works; benchmark results table done
- Report in parallel: état de l'art (STT Darija, LLM extraction, outils)

### Sprint 2 — E2E pipeline + web app (Aug 3 – Aug 14)
- [x] Full n8n workflow (unified Telegram + WhatsApp): reception → media download → `/process` → Sheets append → ✅ reply on originating channel. Access control + roles, dedupe, text-input mode, failure replies, end-of-day report cron (`daily-report-cron.json`), error-tab workflow.
- [x] Google Sheet `Rapports` structured per cahier §6 (+ `canal`, `confidence`, `flag_review`)
- [x] Text mode via `/process` (typed reports on both channels); standalone React form still optional
- [x] Dashboard v1: report list, filters (technicien/chantier/date), review queue on `flag_review`, confidence %, inline Sheet correction. Backend `/reports` + `/reports/{row}` (`api/app/sheets.py`).
- [x] Failure path: low-confidence → `flag_review=true` row + confidence column, surfaced in dashboard review queue
- [x] Dashboard v2 redesign (2026-07-24): neutral Efferd-style framed panels, light/dark, FR/EN/AR (RTL) i18n from JSON, 16 metrics (Activité/Production/Qualité/Cadence incl. WoW, Darija-voice share, API uptime), per-tech summary, recent/health/activity row. Backend `GET /health` now returns uptime for the ops tile.
- [ ] Email notif on each report (daily cron done; per-report email optional) + live demo to director
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
