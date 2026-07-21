# Rapport Journalier — aznet.ma (PFE 2026)

Automated daily reporting for cabling technicians: voice note in Moroccan Darija (via Telegram) → transcription → AI extraction → professional French summary → Google Sheets → manager notification.

**Full project plan:** [PLAN.md](PLAN.md) · **Spec:** [docs/cahier-des-charges.md](docs/cahier-des-charges.md)

> **Reception channel note:** the cahier des charges specifies WhatsApp Business API. Development and pilot currently use **Telegram Bot API** instead (Meta's test-mode friction — expiring tokens, webhook verification, 5-number allowlist — was blocking progress; cahier §5 permits *"passerelle équivalente"*). Reception is channel-agnostic by design: only the n8n reception workflow changes, the `/process` API is untouched. WhatsApp migration is documented as a production evolution, not blocking this PFE.

## Architecture

```
Telegram voice (Darija) → n8n (polling) ─→ FastAPI AI service ─→ n8n → Google Sheets
Web form ─────────────────────────────────↗   (STT + LLM JSON)        ├→ email notif
Dashboard (React) ← Google Sheets API                                 └→ Telegram reply
```

## Repository layout

| Path | Content |
|---|---|
| `api/` | FastAPI AI service — STT adapters, LLM extraction, French reformulation (Sprint 1) |
| `web/` | React (TS) — technician form + manager dashboard (Sprint 2) |
| `n8n/` | Workflow exports + n8n setup/tunnel instructions |
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
- [x] Week 0: reception channel switched to Telegram Bot API (WhatsApp blocked in Meta test mode)
- [x] Week 0: E2E smoke test passed (Jul 17) — voice note → transcription → extraction → French summary → Telegram confirmation reply, live
- [ ] Week 0: Darija test dataset (see `benchmark/README.md`)
- [ ] Sprint 1: AI core + STT benchmark
- [ ] Sprint 2: E2E pipeline (Sheets + email notif) + web app
- [ ] Sprint 3: pilot + docs + PFE report

Draft PFE report (structure + 4 chapters written from project state): `Pres+report/Rapport-PFE.docx`.
