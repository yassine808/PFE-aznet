---
tags: [pfe, google-sheets, integration, service-account, api]
type: technical
priority: high
status: partial
---

> **Note on status:** Google Sheets integration is **not built** as of Jul 23 2026 (Week 1). No spreadsheet exists, no service account has been provisioned, no n8n Sheets node is configured. This document is a plan for Sprint 2 (PLAN.md), not a description of anything running. Any prior version of this doc with concrete spreadsheet IDs, column letters, Apps Script backups, or batching code was fabricated — none of it exists in this repo.

# Google Sheets Integration (Plan)

## Role (per PLAN.md)

Google Sheets is the **single source of truth** for report data — the assumption locked in the July 15 interview. n8n will append one row per processed report; the manager dashboard (if built) reads the Sheets API directly, not a database.

```
Telegram → n8n → API /process → (planned) Sheets append → (planned) email notification
```

## What determines the column layout

The row will be built from:
- `ExtractedReport` fields returned by the API — see [[API Schemas]] for the real field list (`chantier`, `client`, `type_activite`, `goulottes_m`, `cables_m`, `bureaux_termines`, `panneaux_raccordes`, `autres_travaux`, `observations`, `resume`)
- Metadata n8n adds itself: `date`, `heure`, `technicien`, `lien_audio` (never sent to the API — see [[Architecture]])
- `ProcessResponse.warnings` (`short_transcription`, `low_confidence_transcription`) for manual-review flagging (TO-DO.md explicitly asks for this to surface in a dashboard, not just a log)

No column-by-column mapping has been decided or coded yet. Do not invent field names like `stt_confidence_low`/`extraction_confidence`/`type_travail`/`cables_tires` — those don't exist on the real schema.

## Planned setup steps (not yet done)

1. Create a Google Cloud project + service account, enable the Sheets API.
2. Share a new spreadsheet with the service account (Editor).
3. n8n → Credentials → Google Sheets (Service Account) → paste the JSON key.
4. Add a Google Sheets node (Append) to the reception workflow, after the API call.

## Known open questions (from TO-DO.md)

- Manual correction in the dashboard — letting a manager edit/fix an extracted field without touching the Sheet directly
- Low-confidence STT flag as an explicit dashboard signal, not just a `warnings` entry
- Weekly/monthly rollups across chantiers
- A per-technician activity heatmap

None of these have an implementation yet; they're backlog items, not features to document as built.

## Related Notes

- [[Project Overview]]
- [[Architecture]]
- [[n8n Workflows]]
- [[API Schemas]]
- [[Deployment Guide]]
