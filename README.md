# Rapport Journalier — aznet.ma (PFE 2026)

Automated daily reporting for cabling technicians: voice note in Moroccan Darija (via Telegram) → transcription → AI extraction → professional French summary → Google Sheets → manager notification.

**Full project plan:** [PLAN.md](PLAN.md) · **Spec:** [docs/cahier-des-charges.md](docs/cahier-des-charges.md)

> **Reception channels:** the cahier des charges specifies WhatsApp Business API. The project now runs **both Telegram Bot API AND WhatsApp Cloud API** as live inputs (single unified n8n workflow, `n8n/reception-unified.json`). Telegram was added first (no Meta friction); WhatsApp was brought up end-to-end on 2026-07-23 (System User token, published app, WABA subscription). Reception is channel-agnostic by design: both feed the same `/process` API and the same Sheet; only the reception nodes differ per channel. A message received on a channel is replied to on that same channel.

## Architecture

```
Telegram voice/text (Darija) ─┐
WhatsApp voice/text ──────────┤→ n8n (unified) → FastAPI AI service → n8n → Google Sheets
Web form ─────────────────────┘        (STT + LLM JSON)     ├→ email notif (daily cron)
Dashboard (React) ←─ FastAPI /reports ──→ Google Sheets      └→ ✅ reply on same channel
```

## Repository layout

| Path | Content |
|---|---|
| `api/` | FastAPI AI service — STT adapters, LLM extraction, French reformulation, daily-report + dashboard endpoints |
| `web/` | React (TS) — manager dashboard (report list, filters, review queue, inline Sheet correction) |
| `n8n/` | Workflow exports (unified reception, error handler, daily cron) + setup guide |
| `benchmark/` | Darija STT benchmark — dataset protocol, WER harness (Sprint 1) |
| `docs/` | Cahier des charges, installation doc, user guide |

## Quickstart (n8n)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
cp .env.example .env        # fill keys as you obtain them
docker compose up -d        # n8n on http://localhost:5678
```

No Docker yet? Instant dev run: `npx n8n` (Node 20+). See `n8n/README.md` for webhook tunnel options.

## Status

- [x] Week 0: plan + scaffold
- [x] Week 0: E2E smoke test passed (Jul 17) — Telegram voice → transcription → extraction → French summary → reply, live
- [x] Sprint 2: **full dual-channel E2E** (2026-07-23) — Telegram + WhatsApp voice/text → `/process` → Google Sheets row → ✅ reply on the originating channel. Unified n8n workflow, access control + roles, dedupe, failure replies, low-confidence flagging, error-tab workflow, end-of-day report cron.
- [x] Sprint 2: **manager dashboard v1** — React (`web/`) + FastAPI `/reports` endpoints; report list, technicien/chantier/date filters, review queue on `flag_review`, confidence %, click-to-edit cells writing back to Sheets.
- [ ] STT benchmark → pick default provider (`benchmark/`)
- [ ] Dashboard redesign (efferd-style), durable Drive audio links, `/rapport` boss command
- [ ] Sprint 3: pilot + docs + PFE report

Setup walkthrough for the whole pipeline: [docs/setup-guide.md](docs/setup-guide.md).
Draft PFE report: `Pres+report/Rapport-PFE.docx`.
