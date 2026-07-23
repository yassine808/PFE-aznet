---
tags: [pfe, monitoring, observability, alerting]
type: technical
priority: medium
status: partial
---

> **Note on status:** none of the tooling below is set up. No Prometheus, Grafana, Loki, Sentry, or uptime monitor is running anywhere in this project. This is a lightweight plan sized to a zero-budget solo-dev PFE, not a description of live infrastructure. A prior version of this doc described a full Prometheus/Grafana/Loki/Alertmanager stack, custom metrics endpoints, and pre-built dashboards — none of that exists or is realistically in scope for this project's timeline; it has been removed.

# Monitoring & Observability (Plan)

## Reality check on scope

This is a solo-developer PFE with a hard Aug 31 2026 deadline, zero budget, and a handful of daily reports (~5-10/day per PLAN.md). A Prometheus/Grafana/Loki stack is disproportionate. What's actually useful:

## What exists today

- `GET /health` on the API (`api/app/main.py`) returns `{"status": "ok", "stt_providers": [...], "stt_default": "..."}`. That's the only observability surface in the codebase right now.
- n8n's own execution history (built into the n8n UI) is the only workflow-level visibility, once reception workflows are active.
- No logs are shipped anywhere; no metrics are emitted; no error tracker is wired in.

## Planned, lightweight approach

- **Errors:** rely on n8n's execution history + FastAPI's own uncaught-exception traceback in the terminal during dev. A hosted error tracker (e.g. free-tier Sentry) is a "could" per PLAN.md's MoSCoW, not committed.
- **Uptime:** if/when a pilot server exists, a single free UptimeRobot monitor on `/health` would be proportionate. Not set up yet — there's no public URL to monitor.
- **Business-level visibility:** the manager dashboard (planned, unbuilt) is meant to surface report volume, low-confidence flags, and per-technician activity directly from the Sheet — see TO-DO.md's list (heatmap, weekly/monthly rollups, dashboard-visible STT accuracy) rather than a separate metrics stack.

## Explicitly out of scope for this PFE

Prometheus, Grafana, Loki/Promtail, Alertmanager, Datadog, custom `/metrics` Prometheus exporters, SLO burn-rate alerts — none of this is planned; the free-tier/solo-dev constraint and Aug 31 deadline don't support standing up and maintaining that stack. If it becomes relevant post-PFE, it belongs in the "perspectives/évolutions" chapter of the report (PLAN.md §7), not in this doc as current design.

## Related Notes

- [[Deployment Guide]]
- [[Architecture]]
- [[Troubleshooting Runbook]]
