---
tags: [pfe, deployment, vercel, planning]
type: technical
priority: low
status: partial
---

> **Note on status:** no Vercel project exists for this PFE. There is no `vercel.json`, no deployment, no serverless function. Per PLAN.md, Vercel free tier is earmarked for the **React dashboard** (front-end only, reading Google Sheets directly), not the FastAPI service — the API is planned to run alongside n8n on the same Docker Compose host (pilot server or Oracle Always Free VM). A prior version of this doc described deploying the FastAPI service itself to Vercel serverless functions with a detailed `vercel.json`, cron keep-warm, and CI/CD pipeline; none of that is accurate to the current plan and it has been removed.

# Vercel (Plan — Dashboard Only)

## What Vercel is actually for in this project

PLAN.md §1: *"Front: Vercel free"* — the React (TypeScript) manager dashboard, once built (Sprint 2/3), deploys to Vercel's free Hobby tier as a static/SSR front-end. It reads report data from the Google Sheets API directly (Sheets is the source of truth, per the locked architecture decision) — it does not call the FastAPI service for anything beyond, at most, the web-form submission path (text mode, `POST /process`).

## Why not the API itself

FastAPI-on-Vercel-serverless was considered in an earlier (fabricated) version of this doc but isn't the current plan. The API is meant to run as a regular long-lived process (uvicorn, later containerized) alongside n8n on whatever host serves the pilot — see [[Deployment Guide]]. This avoids Vercel's function-duration limits being a concern for STT/LLM calls that can take several seconds.

## Nothing to document yet

No `vercel.json`, no environment variable dashboard, no build pipeline, no cron keep-warm, no CI/CD — none of it exists. When the dashboard is actually built, this doc should be replaced with its real deploy config, not a projection of one.

## Related Notes

- [[Deployment Guide]]
- [[Architecture]]
- [[Google Sheets Integration]]
