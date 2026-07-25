# Rapport Journalier — aznet.ma (PFE 2026)

Automated daily reporting for cabling technicians: voice note in Moroccan Darija (via Telegram) → transcription → AI extraction → professional French summary → Google Sheets → manager notification.

**Full project plan:** [PLAN.md](PLAN.md) · **Spec:** [docs/cahier-des-charges.md](docs/cahier-des-charges.md)

> **Reception channels:** the cahier des charges specifies WhatsApp Business API. The project now runs **both Telegram Bot API AND WhatsApp Cloud API** as live inputs (one n8n workflow, imported from `n8n/aznet-complete.json`). Telegram was added first (no Meta friction); WhatsApp was brought up end-to-end on 2026-07-23 (System User token, published app, WABA subscription). Reception is channel-agnostic by design: both feed the same `/process` API and the same Sheet; only the reception nodes differ per channel. A message received on a channel is replied to on that same channel.

## Architecture

```
Telegram voice/text (Darija) ─┐
WhatsApp voice/text ──────────┤→ n8n (unified) → FastAPI AI service → ✅ reply on same channel
Web form ─────────────────────┘        (STT + LLM JSON)         └→ Google Sheets row
                                              │                     (failure → retry queue)
Dashboard (React) ←─ FastAPI /reports ────────┤→ email notif (daily cron)
                  ←─ FastAPI /logs  ←─ Postgres ←─ every pipeline stage
```

**The reply comes before the Sheet write.** The append used to sit between the LLM result and the technician, so a Google outage silently swallowed the report. It is now a recoverable side effect: a failed write parks in a retry queue and is drained every 5 minutes, and the technician always gets their summary.

## Repository layout

| Path | Content |
|---|---|
| `api/` | FastAPI AI service — STT adapters, LLM extraction, French reformulation, daily-report + dashboard endpoints |
| `web/` | React (TS) — manager dashboard: Efferd-style app-shell, light/dark + FR/EN/AR (RTL) i18n from JSON locales, KPI/production/quality/cadence metrics, charts, per-tech summary, review queue, inline Sheet correction |
| `n8n/` | **`aznet-complete.json` — the one file to import** (reception + maintenance + daily report + error handler in four labelled bands). Per-concern sources alongside it; `legacy-*.json` are superseded single-channel flows, never activate one |
| `benchmark/` | Darija STT benchmark — dataset protocol, WER harness (Sprint 1) |
| `docs/` | Cahier des charges, installation doc, user guide |

## Quickstart (n8n)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
cp .env.example .env        # fill keys as you obtain them (see docs/setup-guide.md)
docker compose up -d        # n8n :5678, API :8000, Postgres (pipeline logs) :5432
```

Then import `n8n/aznet-complete.json` — one import covers all four workflows.

No Docker yet? Instant dev run: `npx n8n` (Node 20+). See `n8n/README.md` for webhook tunnel options.

## Status

- [x] Week 0: plan + scaffold
- [x] Week 0: E2E smoke test passed (Jul 17) — Telegram voice → transcription → extraction → French summary → reply, live
- [x] Sprint 2: **full dual-channel E2E** (2026-07-23) — Telegram + WhatsApp voice/text → `/process` → Google Sheets row → ✅ reply on the originating channel. Unified n8n workflow, access control + roles, dedupe, failure replies, low-confidence flagging, error-tab workflow, end-of-day report cron.
- [x] Sprint 2: **manager dashboard v1** — React (`web/`) + FastAPI `/reports` endpoints; report list, technicien/chantier/date filters, review queue on `flag_review`, confidence %, click-to-edit cells writing back to Sheets.
- [x] Sprint 2: **dashboard redesign v2** (2026-07-24) — neutral/monochrome Efferd-style app-shell (framed KPI panels, gradient bars + glowing channel step-line), light/dark theme + FR/EN/AR language switch (RTL) from JSON locales (`web/src/locales/`), 16 metrics across Activité/Production/Qualité/Cadence (incl. WoW deltas, Darija-voice share, API uptime from `/health`), per-technician summary, recent-reports/health/activity bottom row.
- [x] Sprint 2: **resilience + observability** (2026-07-25) — reply-first ordering so a Sheets outage can no longer swallow a report (failed writes park in a Postgres retry queue, drained every 5 min); durable WhatsApp idempotency (was in-memory, wiped on restart); retries + timeouts on `/process`; global error workflow wired to `POST /logs`; per-stage pipeline logging joined by `correlation_id` across n8n and the API, surfaced in a new **Logs n8n** dashboard panel (live tail, filters, 30-day retention); all four workflows merged into a single importable `n8n/aznet-complete.json`.
- [ ] STT benchmark → pick default provider (`benchmark/`)
- [ ] Durable Drive audio links, `/rapport` boss command
- [ ] Sprint 3: pilot + docs + PFE report

Setup walkthrough for the whole pipeline: [docs/setup-guide.md](docs/setup-guide.md).
Draft PFE report: `Pres+report/Rapport-PFE.docx`.
