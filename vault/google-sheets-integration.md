---
tags: [pfe, sheets, google, integration, architecture]
type: architecture
priority: high
status: current
---

# Google Sheets Integration

## Status — Built (since 2026-03)

The full pipeline is built and running:

1. **Service account** (`credentials/service-account.json`) with a Google Sheet that has edit access for `aznet-pfe@aznet-pfe.iam.gserviceaccount.com`
2. **`api/app/sheets.py`** — reads `GOOGLE_SERVICE_ACCOUNT_JSON` (path or JSON inline), uses `gspread` for `get_all_records()` and `append_row()`, `gspread-formatting` for header styling (frozen, bold, blue)
3. **n8n sheets nodes** — two Google Sheets nodes in the unified workflow (`N9_Append_Success`, `N10_Append_Flag`) using the service account
4. **Dashboard read/write** — `GET /reports` (paginated, last 1000, ordered by date desc → ligne desc), `PATCH /reports/{row}` (target a row by 1-indexed row number)
5. **Retry queue** — failed writes go to Postgres `failed_writes`, drained every 5 minutes by `jobs.drain_sheet_queue`

## Sheet Structure

Two tabs are used by the system:

### Rapports (main data tab)

Columns match the `ExtractedReport` schema + metadata added by n8n:

| Column | Data | Source |
|---|---|---|
| Date | YYYY-MM-DD HH:MM | n8n adds |
| Technicien | name + (TG) or (WA) suffix | n8n adds |
| Chantier | site name | API extraction |
| Type d'intervention | trouble/fibre/... | API extraction |
| Equipements concernés | comma-separated | API extraction |
| Cause identifiée | root cause | API extraction |
| Actions réalisées | steps taken | API extraction |
| Matériel utilisé | consumables used | API extraction |
| Observations | additional notes | API extraction |
| Résumé (pour l'email) | French summary | API extraction |
| Catégorie | cat label | API extraction |
| A relire ? | TRUE/FALSE | API (TRUE if image path) |
| Lien audio | Dropbox share link | n8n adds |
| Canal | Telegram / WhatsApp | n8n adds |
| Rapport complet | model summary prefixed `[audio]`, `[photo]` or `[texte]` | API extraction |
| Statut | OK, warning, error | n8n sets |
| Message ID | Telegram chat_id:msg_id / WhatsApp msg_id | n8n adds |
| Transcription (brute) | Arabic/Latin raw text | API transcription |
| Modèle (transcription) | e.g. whisper-large-v3 | API transcription |
| Confiance transcription | logprob or null | API transcription |
| Modèle (extraction) | e.g. gpt-oss-120b (the chain member that answered) | API extraction |
| Provider (extraction) | groq or gemini | API extraction |
| Nombre de tentatives | retry count | API extraction |
| Délai (secondes) | wall-clock processing time | API extraction |
| Erreur | error message if any | API / n8n |
| Correlation ID | UUIDv4 | n8n generates |

### flag_review (filter tab)

A filter view of Rapports where `A relire ? = TRUE`. The dashboard can make this writable because the row numbers in the filter match the source sheet — Google Sheets filter views preserve row index.

## Endpoints

### `GET /reports`

- Query params: `page_size` (default 1000), `fetch_all` (bool, bypass page_size for CSV export)
- Returns `{"reports": [...], "total": int, "page": int}`
- Ordered by date descending, then `ligne` (row number) descending
- Uses `get_all_records()` with `value_render_option='UNFORMATTED_VALUE'` (dates as strings)

### `PATCH /reports/{row}`

- `row` is 1-indexed (matching Google Sheets row numbers)
- Body: dict of column names to new values
- Uses `worksheet.update()` on specific cell ranges
- Supports partial updates (only send changed columns)
- Converts boolean fields to `TRUE`/`FALSE` (Google Sheets string convention)

### Retry queue (`api/app/logs.py`)

When a Sheet append fails in n8n, it posts to `POST /sheet-queue`, which writes to Postgres `failed_writes`. The scheduler drains this every 5 minutes (unless the queue is empty), calling `sheets.append_report` with the original payload. Succeeds → deletes from queue; fails → increments `attempts`, capped at 10.

## Configuration

```
GOOGLE_SERVICE_ACCOUNT_JSON=credentials/service-account.json
# or inline JSON string (for Docker compose)
```

In Docker compose, `GOOGLE_SERVICE_ACCOUNT_JSON` is an **absolute path** (e.g. `/app/credentials/service-account.json`) because `sheets.py` anchors relative paths to `__file__.parents[2]`, which is `/` inside the image. The `credentials/` dir is `COPY`d into the Docker image; mounted volumes also work for local testing.

## Related
- [[Deployment Guide]] — service account provisioning
- [[n8n Workflows]] — how n8n calls Sheets
- [[Project Overview]] — top-level data flow
