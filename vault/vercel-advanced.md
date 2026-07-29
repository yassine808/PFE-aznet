---
tags: [pfe, deployment, vercel, planning]
type: technical
priority: low
status: partial
---

# Vercel (Plan — Dashboard Only, Not Deployed)

## Status: Dashboard built, not deployed to Vercel

The dashboard (`Dashboard/`) is fully built (React 19, Vite, TypeScript, Tailwind v4) and runs via `npm run dev` on localhost:5173. It is **not deployed** to Vercel or any other hosting.

## What would deploy to Vercel

The dashboard reads from the **API**, not directly from Google Sheets (`GET /reports`, `GET /health`, etc.). A Vercel deployment would need:
1. A `VITE_API_BASE_URL` set to the public API URL (currently `localhost:8000` in dev)
2. `allow_origins` on the API CORS middleware tightened from `["*"]` to the Vercel domain
3. Auth: session cookies work across same-origin; cross-origin would need CORS + `withCredentials`

## Why it hasn't happened

PLAN.md's deployment plan targets **Docker Compose** (all three services: API, n8n, Postgres) on the same machine, exposed via Tailscale Funnel. The dashboard in this setup runs on the developer's machine only (Vite dev server). No Vercel project, no `vercel.json`, no preview deployment exists.

## Current deployment architecture

```
n8n (Docker, :5678) ← Tailscale Funnel → WhatsApp/Meta
API (Docker or host, :8000) ← n8n calls
Postgres (Docker, :5432) ← API reads/writes
Dashboard (Vite dev, :5173) ← developer only
```

There is no public hosting for the dashboard. The dashboard panels that interact with n8n (`/n8n` proxy route) only work under `npm run dev` anyway.

## Related Notes

- [[Deployment Guide]]
- [[architecture]]
- [[Local Development]]
