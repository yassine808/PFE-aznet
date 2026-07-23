---
tags: [pfe, google-sheets, integration, service-account, api]
type: technical
priority: high
status: current
---

# Google Sheets Integration

## Overview

Google Sheets serves as the **primary data store** for manager visibility. n8n appends each processed report as a new row.

```
Telegram → n8n → API → Sheets (append) → Email/Slack notification
```

---

## Spreadsheet Setup

### Create Spreadsheet

1. Go to [sheets.google.com](https://sheets.google.com)
2. Create new spreadsheet: **`Rapports Quotidiens - PFE`**
3. Rename first sheet: **`Rapports`**
4. Add second sheet: **`Erreurs`** (for dead letter logging)
5. Note **Spreadsheet ID** from URL:
   ```
   https://docs.google.com/spreadsheets/d/1ABC123XYZ/edit
   ID = 1ABC123XYZ
   ```

### Column Structure (Rapports Sheet)

| Col | Letter | Header | Source | Type | Validation |
|-----|--------|--------|--------|------|------------|
| 1 | A | Date | metadata.date | Date | Required |
| 2 | B | Technicien | extracted ∥ metadata | Text | Required |
| 3 | C | Chantier | extracted.chantier | Text | — |
| 4 | D | Type Travail | extracted.type_travail | Enum | tirage/pose/raccordement/maintenance |
| 5 | E | Goulottes (m) | extracted.goulottes_m | Number | ≥0 |
| 6 | F | Câbles Tirés | extracted.cables_tires | Text | — |
| 7 | G | Équipements Posés | extracted.equipements_poses | Text | — |
| 8 | H | Problèmes | extracted.problemes | JSON Array | — |
| 9 | I | Observations | extracted.observations | Text | — |
| 10 | J | Résumé | extracted.resume | Text | — |
| 11 | K | Lien Audio | metadata.lien_audio | URL | — |
| 12 | L | STT Confiance Faible | extracted.stt_confidence_low | Boolean | — |
| 13 | M | Confiance Extraction | extracted.extraction_confidence | Enum | high/medium/low |
| 14 | N | Telegram Msg ID | metadata.telegram_message_id | Number | Unique (dedup) |
| 15 | O | Created At | n8n timestamp | DateTime | Auto |
| 16 | P | Source | metadata.source | Enum | telegram/webform/manual |
| 17 | Q | Status | computed | Enum | ok/warning/error |
| 18 | R | Error Details | (if error) | Text | — |

### Data Validation Rules

```javascript
// Apply via Apps Script or manually in Sheets UI
// Column D (Type Travail)
=OR(D2="", D2="tirage", D2="pose", D2="raccordement", D2="maintenance")

// Column M (Confiance Extraction)
=OR(M2="", M2="high", M2="medium", M2="low")

// Column P (Source)
=OR(P2="", P2="telegram", P2="webform", P2="manual")

// Column Q (Status)
=OR(Q2="", Q2="ok", Q2="warning", Q2="error")
```

---

## Service Account Setup

### 1. Create Google Cloud Project

```bash
# Or use existing project
gcloud projects create pfe-aznet-sheets --name="PFE aznet Sheets"
gcloud config set project pfe-aznet-sheets
```

### 2. Enable Sheets API

```bash
gcloud services enable sheets.googleapis.com drive.googleapis.com
```

### 3. Create Service Account

```bash
gcloud iam service-accounts create pfe-sheets-writer \
  --display-name="PFE Sheets Writer" \
  --description="Appends daily reports from n8n"
```

### 4. Create & Download Key

```bash
gcloud iam service-accounts keys create credentials/sheets-service-account.json \
  --iam-account=pfe-sheets-writer@pfe-aznet-sheets.iam.gserviceaccount.com
```

### 5. Grant Permissions

**Option A: Share spreadsheet with service account email**
- Open spreadsheet → Share → Add `pfe-sheets-writer@pfe-aznet-sheets.iam.gserviceaccount.com` → **Editor**

**Option B: Domain-wide delegation (if using Workspace)**
- Admin console → Security → API controls → Domain-wide delegation
- Add client ID from service account details
- Scopes: `https://www.googleapis.com/auth/spreadsheets`

---

## n8n Google Sheets Node Configuration

### Credentials

1. n8n → Credentials → New Credential → **Google Sheets OAuth2 API** (or Service Account)
2. **Service Account** method:
   - Paste JSON key content
   - Scopes: `https://www.googleapis.com/auth/spreadsheets`
3. Test connection

### Append Node Settings

| Setting | Value |
|---------|-------|
| **Operation** | Append |
| **Spreadsheet ID** | `1ABC123XYZ` (from URL) |
| **Range** | `Rapports!A:R` |
| **Value Input Mode** | `USER_ENTERED` |
| **Insert Data Option** | `INSERT_ROWS` |

### Column Mapping (Function Node → Sheets)

```javascript
// Function: Build Sheets Row
const extracted = items[0].json.extracted_report;
const meta = items[0].json.metadata;
const warnings = items[0].json.warnings || [];

return [{
  json: {
    date: extracted.date || meta.date,
    technicien: extracted.technicien || meta.technicien,
    chantier: extracted.chantier || meta.chantier || "",
    type_travail: extracted.type_travail || "",
    goulottes_m: extracted.goulottes_m || "",
    cables_tires: extracted.cables_tires || "",
    equipements_poses: extracted.equipements_poses || "",
    problemes: JSON.stringify(extracted.problemes || []),
    observations: extracted.observations || "",
    resume: extracted.resume || "",
    lien_audio: meta.lien_audio || "",
    stt_confidence_low: extracted.stt_confidence_low || false,
    extraction_confidence: extracted.extraction_confidence || "medium",
    telegram_message_id: meta.telegram_message_id || "",
    created_at: new Date().toISOString(),
    source: meta.source || "telegram",
    status: warnings.includes("short_transcription") ? "warning" : "ok",
    error_details: ""
  }
}];
```

---

## Error Sheet (Dead Letter)

### Erreurs Sheet Columns

| Col | Header | Description |
|-----|--------|-------------|
| A | Timestamp | Error occurrence |
| B | Workflow | n8n workflow name |
| C | Node | Failing node |
| D | Error Type | Classification |
| E | Error Message | Full error |
| F | Input Data | Sanitized (no audio) |
| G | Retry Count | Auto-retry attempts |
| H | Resolved | Checkbox (manual) |
| I | Resolution Notes | Manual entry |

### Error Handler Workflow

```
Error Trigger (catch all)
    │
    ├─► Classify Error (Function)
    │      ├─ API 502 → "retryable"
    │      ├─ API 422 → "data_issue"
    │      ├─ Sheets 403 → "credentials"
    │      └─ Other → "unknown"
    │
    ├─► Log to Erreurs Sheet (Sheets Append)
    │
    ├─► If retryable & retries < 3 → Wait → Retry API Call
    │
    └─► Alert Manager
           ├─ Slack Webhook (critical)
           ├─ Email (all errors)
           └─ Telegram Admin (critical)
```

---

## Deduplication Strategy

### Problem

Telegram may send duplicate updates (network retry, polling overlap).

### Solution: Telegram Message ID as Primary Key

```javascript
// Before append: Check if message_id exists
// Function: Check Duplicate

const { google } = require('googleapis');
const sheets = google.sheets({ version: 'v4', auth });

async function checkDuplicate(messageId) {
  const response = await sheets.spreadsheets.values.get({
    spreadsheetId: '1ABC123XYZ',
    range: 'Rapports!N:N'  // Column N = telegram_message_id
  });
  
  const values = response.data.values || [];
  return values.flat().includes(String(messageId));
}
```

### n8n Implementation

```
Telegram Trigger
    │
    ▼
Function: Extract message_id
    │
    ▼
HTTP Request: Check Sheets for message_id
    │
    ├─ Exists → Stop (already processed)
    │
    └─ Not Exists → Continue → API → Sheets Append
```

---

## Batch Operations (Optimization)

### Problem

Individual `append` calls = 1 API call per report. Slow for bulk.

### Solution: Batch Append

```javascript
// Collect multiple reports, single batchUpdate
const batchData = reports.map(r => ({
  range: 'Rapports!A:R',
  majorDimension: 'ROWS',
  values: [r]  // Single row array
}));

await sheets.spreadsheets.values.batchUpdate({
  spreadsheetId: '1ABC123XYZ',
  resource: {
    valueInputOption: 'USER_ENTERED',
    data: batchData
  }
});
```

### n8n Batch Node

Use **Split In Batches** → **Merge** → **Sheets Batch Update** (custom HTTP Request)

---

## Formatting & Presentation

### Conditional Formatting Rules

| Range | Rule | Format |
|-------|------|--------|
| `Q:Q` | `=Q2="error"` | Red fill, white text |
| `Q:Q` | `=Q2="warning"` | Yellow fill |
| `L:L` | `=L2=TRUE` | Red text, bold |
| `M:M` | `=M2="low"` | Orange fill |

### Frozen Rows

- View → Freeze → **1 row** (headers)

### Filter Views

- Data → Create filter view
- Save as: "Par Technicien", "Par Chantier", "Erreurs Only"

---

## Manager Access

### Share Settings

1. Spreadsheet → Share
2. Add manager emails → **Viewer** (or **Commenter**)
3. Notify → Custom message with link

### Published Dashboard (Optional)

File → Share → Publish to web → **Link** → Embed in internal portal

---

## Backup & Retention

### Automated Backup (Apps Script)

```javascript
function backupSheets() {
  const ss = SpreadsheetApp.openById('1ABC123XYZ');
  const backupFolder = DriveApp.getFolderById('BACKUP_FOLDER_ID');
  const timestamp = Utilities.formatDate(new Date(), 'Africa/Casablanca', 'yyyy-MM-dd_HHmm');
  
  DriveApp.getFileById(ss.getId())
    .makeCopy(`Rapports_Backup_${timestamp}`, backupFolder);
  
  // Cleanup: keep last 30 days
  const files = backupFolder.getFilesByName('Rapports_Backup_');
  while (files.hasNext()) {
    const file = files.next();
    const created = file.getDateCreated();
    if (created < new Date(Date.now() - 30*24*60*60*1000)) {
      file.setTrashed(true);
    }
  }
}

// Trigger: Daily at 02:00 (Time-driven)
```

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `403: Caller does not have permission` | Service account not shared | Share spreadsheet with SA email |
| `400: Invalid value at 'data.values'` | Type mismatch (e.g., number in text col) | Use `USER_ENTERED`, stringify all |
| `429: Quota exceeded` | Too many requests | Batch updates, add delays |
| `Row data not appearing` | Wrong range/tab name | Check `Rapports!A:R` matches exactly |
| `Date shows as number` | Sheets serial date | Format column A as Date |

---

## API Limits

| Limit | Value | Notes |
|-------|-------|-------|
| Read requests/min | 300 | Per project |
| Write requests/min | 60 | Per project |
| Spreadsheet size | 10M cells | ~1M rows max |
| Cell data | 50k chars | Per cell |

---

## Related Notes

- [[Project Overview]]
- [[Architecture]]
- [[n8n Workflows]]
- [[API Schemas]]
- [[Deployment Guide]]