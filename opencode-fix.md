# Hardcoded secrets in n8n workflow

## 1. Google Sheet ID hardcoded

**File:** `n8n/aznet-complete.json:620`
```json
"documentId": {
  "__rl": true,
  "mode": "id",
  "value": "<GOOGLE_SHEET_ID>"
}
```

**Fix:** Replace with `$env.GOOGLE_SHEET_ID` expression.

## 2. HR email hardcoded in outsider reply

**File:** `n8n/aznet-complete.json:572,596`
```
"...contacter les ressources humaines : <HR_EMAIL>"
```

**Fix:** Replace `<HR_EMAIL>` with `$env.HR_EMAIL` expression in both occurrences.

## 3. Error handler HTTP node missing auth header

**File:** `n8n/aznet-complete.json:~1453`

The `POST /logs` node in the error handler band has no `X-API-Key` header. Every other HTTP node in the workflow sets it.

**Fix:** Add `sendHeaders: true` and `headerParameters: [{ name: "X-API-Key", value: "={{ $env.INTERNAL_API_KEY }}" }]` to the error handler's `POST /logs` node.

---

# Default Postgres credentials in docker-compose

**File:** `docker-compose.yml:16-17`
```yaml
POSTGRES_USER=${POSTGRES_USER:-pfe}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-pfe}
```

Defaults `pfe`/`pfe` are weak. Any deploy without `.env` overrides uses wide-open credentials.

**Fix:** Remove the `:-pfe` defaults so deployment fails hard if unset.
