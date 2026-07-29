---
tags: [pfe, monitoring, observability, postgres]
type: guide
priority: medium
status: built
---

# Monitoring & Observability

## PostgreSQL observability

Five tables in `aznet_pfe` store pipeline lifecycle data:

### `pipeline_logs`

One row per pipeline stage. n8n POSTs a row for each stage (reception, download, process, sheets); the API logs its own errors with the same `correlation_id`. Both processes join into one timeline in the dashboard's **Logs n8n** panel.

Deliberately not the Sheet — a Sheets-backed log goes blind during a Sheets outage.

### `processed_messages`

WhatsApp idempotency. When n8n receives a WhatsApp message webhook, it first checks this table. If the message ID exists, it's skipped (WhatsApp delivers at-least-once). Insert uses `ON CONFLICT DO NOTHING`.

Also used for Telegram deduplication (same message received in consecutive polls).

### `failed_writes`

Sheet retry queue. When a Sheet append fails (in n8n or in the drain job), the payload is stored here. The `drain_sheet_queue` job (every 5 min) retries. Capped at 10 attempts, then the row is orphaned for manual review.

### `service_samples`

Uptime history. Written by the OpsProvider (`Dashboard/src/lib/ops-context.tsx`) every minute. Combined with `/health` to compute the reliability indicator in the dashboard's status bar. Retained for 30 days (pruned at 03:00 daily).

### `users` + `sessions`

Dashboard accounts. `users` has username and password hash; `sessions` has opaque session tokens linked to users. Retention: sessions older than the `session_ttl_hours` setting are pruned.

## Endpoints

- `POST|GET|DELETE /logs` — CRUD for pipeline logs
- `POST /logs/claim` — assign an unclaimed log to a session (for dashboard "acknowledge error")
- `POST|GET /sheet-queue` — read/write the retry queue
- `PATCH /sheet-queue/{id}` — update queue item status (resolve, increment attempts)
- `GET /health` — `{"status": "ok", "uptime_seconds": N, "models": {...}}`

## Dashboard panels

| Panel | Data source | Poll interval |
|---|---|---|
| Status pulse + uptime | `GET /health` + `GET /service-samples` | 30s (OpsProvider) |
| Pipeline tail | `GET /logs?limit=50` | 5s (Logs page) |
| Report list | `GET /reports` | on load, no auto-poll |
| Model status | `GET /health` → models | 30s (OpsProvider) |

## Alerts

- **None automated.** The only alert is the daily report email (Mon–Sat). If that email doesn't arrive, something upstream is broken (n8n not polling, API down, Gmail SMTP rejected).

## Related

- [[architecture]] — logs architecture
- [[Deployment Guide]] — Postgres setup
- [[Project Overview]]
