# Product

## Register

product

## Users

One primary user: the aznet operations manager. Non-technical, sits at an office desktop in normal daytime light, opens the dashboard daily on `localhost` (no auth, single machine, decided 2026-07-23). Reads French; the interface also ships EN and AR (RTL) because the wider aznet context is Moroccan and the PFE jury may switch locales.

Secondary user: the project's technical operator (the student maintaining the pipeline), who needs the same surface to answer "did the machine work today?" without a second tool.

The job to be done, in order:

1. **See the day.** What field reports came in, from which technicien, on which chantier, with what quantities. Aggregation and reading, not data entry.
2. **Prove the pipeline works end to end.** Telegram/WhatsApp reception, transcription, extraction, Sheet write, notification: each stage visibly succeeded or visibly failed, with the failure legible enough to act on.

Correcting a bad extraction is supported, but it is a consequence of the two jobs above, not the entry point.

## Product Purpose

Field technicians send voice notes in Moroccan Darija from the worksite. The pipeline transcribes, extracts structured data, writes a professional French summary to Google Sheets, and notifies the manager. All of that is invisible machinery.

This dashboard is the only place that machinery becomes visible. It exists so a manager can trust the automation without reading n8n executions or a Postgres table, and so a failure is noticed on the day it happens rather than at month-end when the Sheet does not add up.

Success: the manager opens it once a day, understands the day in under thirty seconds, and never has to ask "is it still running?"

## Brand Personality

Calm, precise, factual.

The interface does not persuade, celebrate, or congratulate. It reports. Numbers are stated, not dramatized. Failures are stated plainly and are as visible as successes: a silent failure is the worst outcome this product can produce, so the design never softens bad news into a muted grey pill.

Voice in French, matching the cahier des charges vocabulary (chantier, technicien, goulottes, résumé). Never anglicized. Copy is short and declarative; no exclamation marks, no encouragement.

Closest product reference: **Linear**. Restrained neutrals, precise typography, near-invisible chrome, speed as a feature, keyboard reachability. Take Linear's discipline and quiet, not its exact palette.

## Anti-references

- **Generic AI/SaaS dashboard.** Gradient hero metric blocks, endless identical rounded card grids, violet-to-blue accent, emoji icons, "Welcome back 👋". This is the single most likely failure mode and is rejected outright.
- **Enterprise ERP / admin panel.** Grey chrome, stacked toolbars, hairline-dense legacy tables, SAP-adjacent visual language. Reads as unloved and untrustworthy.
- Also avoid, by extension: crypto/gamer neon on black, glassmorphism, and consumer-app playfulness (mascots, illustrations, oversized cheerful buttons). Wrong register for a fieldwork record system.

## Design Principles

1. **The data is the interface.** Chrome recedes; report content, quantities, and status are the loudest things on screen. If a decorative element competes with a number, the decoration loses.
2. **Failure is first-class.** A broken stage, a queued Sheet write, a low-confidence extraction each have a designed state that is impossible to miss. Never let an error be quieter than a success.
3. **One glance, then depth.** The day is legible in seconds at the top level; detail (per-report, per-stage, per-correlation-id) is one deliberate step away, never forced up front.
4. **Bilingual by construction, not by retrofit.** Every string is keyed; every spacing and border decision uses logical properties so Arabic RTL mirrors correctly without a second layout.
5. **Honest about the machine.** The dashboard shows what the pipeline actually did, including latency, uptime, and retries. It never implies more certainty than the AI produced.

## Accessibility & Inclusion

- **WCAG 2.2 AA.** 4.5:1 minimum for body text and 3:1 for UI boundaries, verified in both light and dark themes.
- **No color-only meaning.** Every status carries a label or icon alongside its color, so red/green confusion never hides a failed stage.
- **Reduced motion honored.** `prefers-reduced-motion: reduce` removes transitions and animated transforms; nothing conveys meaning through motion alone.
- **Full keyboard reach.** Visible focus rings on every interactive element; tables navigable and editable without a mouse.
- **RTL parity.** Arabic is a first-class layout direction, not a mirrored afterthought, and uses an Arabic-capable type stack rather than a Latin font's fallback.
