---
tags: [pfe, n8n, advanced, workflows, patterns]
type: technical
priority: medium
status: partial
---

> **Note on status:** n8n today is a single local Docker container running two reception-workflow variants (polling + webhook). Queue mode, Postgres, Redis, circuit breakers, and VPS scaling tiers described below are **not built and not currently planned within PFE scope** — PLAN.md's volume estimate is ~5-10 reports/day, which never approaches the scale where any of this matters. A prior version of this doc described a full production scaling architecture; it has been removed as fabricated/out of scope.

# n8n — Beyond the Basics (Notes)

## Actual current setup

`docker-compose.yml` (repo root) runs a single `n8n` service, SQLite-backed (n8n's default), no basic auth configured, `WEBHOOK_URL` driven by an env var for the tunnel case. See [[Local Development]] for the exact file.

## Why "advanced" scaling isn't relevant here

PLAN.md's own risk register: *"Free-tier quotas — volume tiny (~5-10 reports/day)."* Queue mode, worker replicas, and Postgres-backed executions solve a throughput problem this project doesn't have. If volume genuinely grows post-PFE, n8n's own docs on queue mode are the reference point — no custom architecture from this vault should be treated as validated or built.

## Patterns actually worth keeping in mind (design intent, not code)

- **Idempotency:** WhatsApp message dedup uses `processed_messages` table (Postgres, `ON CONFLICT DO NOTHING`). Telegram dedup uses the same mechanism (TG message ID checked before processing). Both avoid double-processing on at-least-once deliveries.
- **Error visibility:** n8n's own Error Trigger + execution history is the primary mechanism. On top of that: the API logs all stages to Postgres with the same `correlation_id`, visible in the dashboard's **Logs n8n** panel. No custom circuit breaker, retry-with-backoff, or dead-letter workflow exists — the retry queue for Sheet failures is in Postgres (`failed_writes`), drained every 5 minutes.
- **Confirmation reply as user-facing acknowledgment:** the polling workflow already replies to the technician (see [[n8n Workflows]]) — that doubles as an implicit "your report was received" signal, reducing the need for separate delivery monitoring.

## What's explicitly not planned

Redis, Postgres, n8n queue mode, Caddy, custom Prometheus scraping of `n8n_workflow_executions_total` — none of this is in PLAN.md's scope or timeline. Don't build against it.

## Related Notes

- [[Deployment Guide]]
- [[n8n Workflows]]
- [[Google Sheets Integration]]
