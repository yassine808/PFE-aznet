---
tags: [pfe, monitoring, observability, alerting]
type: technical
priority: medium
status: built
---

> **Status (2026-07-25): a purpose-built observability layer now exists.** Still no Prometheus, Grafana, Loki or Sentry — deliberately. Instead of a generic metrics stack, the project logs its own pipeline events to Postgres and surfaces them in the manager dashboard. Sized to a zero-budget solo-dev PFE.

# Monitoring & Observability

## Reality check on scope

Solo-developer PFE, hard Aug 31 2026 deadline, zero budget, a handful of daily reports (~5-10/day per PLAN.md). A Prometheus/Grafana/Loki stack is disproportionate. A domain-specific event log is not — and answers the only question that actually matters here: *what happened to this technician's voice note?*

## What exists today

- **`pipeline_logs` in Postgres** (`api/app/logs.py`, compose service `postgres`). One row per stage — `received → authorized → transcribed → extracted → replied → sheet_written`, plus `denied`, `duplicate`, `sheet_failed`, `api`, `workflow_error`. Columns: `ts`, `correlation_id`, `channel`, `technicien`, `level`, `message`, `duration_ms`, `payload` JSONB.
- **`correlation_id`** minted by the n8n `Correlate` node and threaded through `/process`, so n8n's stages and the API's own errors — two separate processes — join into one timeline.
- **Logs n8n dashboard panel** (`web/src/components/logs-panel.tsx`): live tail polling `GET /logs` every 5 s with a pause toggle, filters (level/channel/stage), debounced search, expandable raw payload, and four 24-hour counters including pending Sheet writes.
- **Global error workflow** wired to `POST /logs` — any unhandled node crash lands in the panel as `workflow_error`.
- **`duration_ms` per stage**, which doubles as free data for the STT benchmark chapter.
- **`GET /health`** — status, version, `uptime_seconds`, STT providers. Feeds the dashboard's API-uptime tile.
- **Retention:** 30 days, pruned nightly at 03:00 by the maintenance workflow.

### Why Postgres and not the Google Sheet

The single most important event to record is *"the Sheet write failed"*. A Sheets-backed log goes blind during exactly the outage it exists to report. Postgres is an independent failure domain. Same reasoning applies to the error workflow, which was rewritten to post to `/logs` instead of appending to an `Errors` sheet tab.

### Known blind spot

The log only sees what **reaches n8n**. A dead webhook tunnel means Meta never delivers the WhatsApp message, no node runs, and nothing appears in the panel — the failure is invisible silence. Telegram is immune because it polls. See [[troubleshooting-runbook]].

## Still lightweight elsewhere

- **Errors:** the Logs panel + n8n's execution history. A hosted error tracker (e.g. free-tier Sentry) remains a "could" per PLAN.md's MoSCoW, not committed.
- **Uptime:** if/when a pilot server exists, a single free UptimeRobot monitor on `/health` would be proportionate. Not set up yet — there's no public URL to monitor.
- **Business-level visibility:** the manager dashboard surfaces report volume, low-confidence flags and per-technician activity directly from the Sheet — see [[to-do]] (heatmap, weekly/monthly rollups) rather than a separate metrics stack.
- **Uptime of the tunnel:** currently unmonitored, and it is the project's most frequent real outage. A dead tunnel is silent by construction. Worth a startup check.

## Explicitly out of scope for this PFE

Prometheus, Grafana, Loki/Promtail, Alertmanager, Datadog, custom `/metrics` Prometheus exporters, SLO burn-rate alerts — none of this is planned; the free-tier/solo-dev constraint and Aug 31 deadline don't support standing up and maintaining that stack. If it becomes relevant post-PFE, it belongs in the "perspectives/évolutions" chapter of the report (PLAN.md §7), not in this doc as current design.

## Related Notes

- [[Deployment Guide]]
- [[Architecture]]
- [[Troubleshooting Runbook]]
