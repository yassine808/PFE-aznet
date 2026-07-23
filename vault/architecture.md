---
tags: [pfe, architecture, api, fastapi, n8n]
type: architecture
priority: high
status: current
---

# Architecture Details

## System Boundaries

### n8n (Orchestration Layer)
**Responsibilities:**
- Telegram message reception (polling/webhook)
- Audio file download from Telegram
- Base64 encoding of audio
- Metadata extraction (date, technicien, audio URL)
- HTTP call to API `/process`
- Google Sheets row append
- Email notification dispatch
- Error handling & retry logic
- Workflow versioning

**NOT responsible for:**
- STT processing
- LLM extraction
- Business logic validation

### API (AI Microservice)
**Responsibilities:**
- Single endpoint: `POST /process`
- STT provider selection & execution
- LLM extraction (Gemini → Groq fallback)
- Schema validation (ExtractedReport)
- Error contract)
- Returns structured data only

**NOT responsible for:**
- Telegram integration
- Google Sheets
- Email sending
- Metadata enrichment

## API Design

### Endpoint: `POST /process`

```python
# Voice mode
{
  "audio": "base64_encoded_audio",
  "metadata": {
    "date": "2026-07-23",
    "technicien": "Ahmed",
    "lien_audio": "https://api.telegram.org/file/bot<token>/..."
  }
}

# Text mode (web form)
{
  "text": "Transcribed text from technician...",
  "metadata": { ... }
}
```

**Validation:** Exactly one of `audio` or `text` required (XOR).

### Response: `ExtractedReport`

```python
class ExtractedReport(BaseModel):
    # Identification
    technicien: Optional[str] = None
    date: Optional[str] = None
    chantier: Optional[str] = None
    
    # Work details
    type_travail: Optional[str] = None  # "tirage", "pose", "maintenance"
    goulottes_m: Optional[float] = None
    cables_tires: Optional[int] = None
   'equipements_poses': Optional[int] = None
    
    # Issues & observations
    problemes: List[str] = []
    observations: Optional[str] = None
    
    # Summary (French)
    resume: Optional[str] = None
    
    # Confidence flags
    stt_confidence_low: bool = False
    extraction_confidence: Literal["high", "medium", "low"] = "medium"
```

## STT Provider Architecture

### Strategy Pattern Implementation

```
TranscriptionProvider (ABC)
    ├── transcribe(audio_bytes) -> TranscriptionResult
    ├── name: str
    └── supports_format(format) -> bool

Registry: @register("groq") / @register("gemini") / @register("hf-darija")
```

### Providers

| Provider | Model | Cost | Darija Support | Latency |
|----------|-------|------|----------------|---------|
| **Groq** | Whisper-large-v3 | Free tier | Good | ~1-2s |
| **Gemini** | Gemini-1.5-flash | Free tier | Good | ~2-3s |
| **HF Darija** | custom-darija-model | Free tier | Best (specialized) | ~3-5s |

### Selection Logic

```python
# config.py - DEFAULT_PROVIDER set after benchmark
DEFAULT_PROVIDER = "groq"  # TBD after Week 1 benchmark

# Runtime override via metadata
metadata.get("stt_provider", DEFAULT_PROVIDER)
```

## Extraction Pipeline

### Primary: Gemini Structured Output

```python
model = genai.GenerativeModel(
    "gemini-1.5-flash",
    generation_config={
        "response_mime_type": "application/json",
        "response_schema": ExtractedReport,
    }
)
```

**Prompt enforces:**
- Null for absent fields (never invent)
- French professional tone for `resume`
- Confidence assessment

### Fallback: Groq JSON Mode

```python
client.chat.completions.create(
    model="llama-3.1-70b-versatile",
    response_format={"type": "json_object"},
    messages=[...]
)
```

### Error Contract

| Error | HTTP | n8n Handling |
|-------|------|--------------|
| Bad input / unknown provider | 422 | Flag row, alert |
| STT engine failure | 502 | Retry (3x), then flag |
| Extraction both fail | 502 | Flag row, alert |
| Short transcription (<10 chars) | 200 + warning | Process anyway, flag |

## n8n Workflow Design

### Workflow 1: Telegram Reception (Polling)
```
Telegram Trigger (polling) 
    → Download File 
    → Extract Metadata 
    → Base64 Encode Audio 
    → HTTP Request to API 
    → Google Sheets Append 
    → Email Notification
    → Error Handler (Slack/Email alert)
```

### Workflow 2: Telegram Reception (Webhook - Pilot)
```
Webhook (Telegram callback)
    → Verify Signature
    → Same as polling
```

### Workflow 3: Web Form (Manual)
```
Webhook (form submit)
    → Validate
    → HTTP Request (text mode)
    → Sheets + Email
```

## Data Models

### Google Sheets Columns

| Column | Source | Type |
|--------|--------|------|
| Date | metadata.date | Date |
| Technicien | metadata.technicien | String |
| Chantier | extracted.chantier | String |
| Type Travail | extracted.type_travail | String |
| Goulottes (m) | extracted.goulottes_m | Number |
| Câbles Tirés | extracted.cables_tires | Number |
| Équipements Posés | extracted.equipements_poses | Number |
| Problèmes | extracted.problemes | String (JSON array) |
| Observations | extracted.observations | String |
| Résumé | extracted.resume | String |
| Lien Audio | metadata.lien_audio | URL |
| STT Confidence Low | extracted.stt_confidence_low | Boolean |
| Extraction Confidence | extracted.extraction_confidence | Enum |
| Created At | n8n execution time | DateTime |

## Deployment Architecture

### Development
```
Local: n8n (Docker) → API (uvicorn :8000) → ngrok tunnel → Telegram webhook
```

### Pilot / Production
```
Vercel: API (serverless functions)
VPS: n8n (Docker, persistent)
Telegram: Webhook → VPS n8n
```

### Vercel Config (`vercel.json`)
```json
{
  "builds": [{ "src": "api/app/main.py", "use": "@vercel/python" }],
  "routes": [{ "src": "/(.*)", "dest": "api/app/main.py" }],
  "functions": {
    "api/app/main.py": { "maxDuration": 30 }
  }
}
```

## Error Handling Strategy

### API Level
- **Fail loud**: No silent fallbacks, no invented data
- **Structured errors**: `TranscriptionError`, `ExtractionError` with provider context
- **Timeouts**: 30s per provider, configurable

### n8n Level
- **Retry**: 3x with exponential backoff for 5xx
- **Dead letter**: Failed executions → separate sheet + email alert
- **Idempotency**: Telegram message ID as deduplication key

## Security

- API keys in environment variables only
- Telegram webhook secret token verification
- Google Sheets: Service account with minimal scope
- Gmail: App password, not main password
- No PII in logs (technician names OK, audio content not logged)

## Monitoring & Observability

### API (Vercel)
- Function logs
- Invocation count / duration / errors

### n8n
- Execution history (last 10k)
- Workflow-level error rates
- Custom webhook for alerts

### Key Metrics
- End-to-end latency (voice → sheet)
- STT success rate by provider
- Extraction confidence distribution
- Failed executions / day

## Related Notes

- [[Project Overview]]
- [[STT Benchmark]]
- [[Extraction Pipeline]]
- [[n8n Workflows]]
- [[Google Sheets Integration]]
- [[Deployment Guide]]