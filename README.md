# Rapport Journalier — aznet.ma (PFE 2026)

Automated daily reporting for cabling technicians: WhatsApp voice note in Moroccan Darija → transcription → AI extraction → professional French summary → Google Sheets → manager notification.

**Full project plan:** [PLAN.md](PLAN.md) · **Spec:** [docs/cahier-des-charges.md](docs/cahier-des-charges.md)

## Architecture

```
WhatsApp voice (Darija) → Meta Cloud API → n8n ─→ FastAPI AI service ─→ n8n → Google Sheets
Web form ────────────────────────────────────────↗   (STT + LLM JSON)        ├→ email notif
Dashboard (React) ← Google Sheets API                                        └→ WhatsApp reply
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
- [ ] Week 0: Meta dev account + WhatsApp webhook smoke test
- [ ] Week 0: Darija test dataset (see `benchmark/README.md`)
- [ ] Sprint 1: AI core + STT benchmark
- [ ] Sprint 2: E2E pipeline + web app
- [ ] Sprint 3: pilot + docs + PFE report
