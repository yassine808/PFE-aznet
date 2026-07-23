---
tags: [pfe, deployment, vercel, advanced, serverless, optimization, monitoring]
type: technical
priority: high
status: partial
---

> **Reality check (2026-07-23):** substantial parts of this doc describe an API contract, file layout, or tooling that was never built (e.g. JSON+base64 `/process` body with metadata in the request, `ExtractedReport` fields like `technicien`/`type_travail`/`cables_tires`, ngrok, CI workflows, `requirements-dev.txt`, `.vscode/` configs). The real `/process` contract is multipart file upload (`audio`/`text` form fields), metadata is added by n8n *after* the API responds, and the real schema is in `api/app/schemas.py`. Treat concrete claims here as aspirational/unverified unless they match the real source files in `api/app/`, `api/tests/`, and `n8n/`.

# Vercel Advanced Deployment Guide

## Deep Dive: Vercel Serverless for FastAPI

### Why Vercel Works for This Project

| Factor | Assessment |
|--------|------------|
| **Python Support** | Native via `@vercel/python` builder |
| **Function Duration** | 30s (Hobby) / 60s (Pro) — sufficient for STT+LLM |
| **Memory** | 1024MB default — fits Whisper + extraction |
| **Cold Starts** | ~1-2s Python — mitigated by keep-alive |
| **Payload Limit** | 50MB — Telegram voice < 20MB |
| **Cost** | Free tier: 100GB-hrs/month — ample for PFE |
| **Concurrency** | 1000+ — auto-scales |

---

## Vercel Configuration Deep Dive

### Complete `vercel.json`

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "buildCommand": "pip install -r requirements.txt",
  "outputDirectory": ".",
  "devCommand": "uvicorn app.main:app --reload --port 3000",
  "installCommand": "pip install -r requirements.txt",
  "framework": null,
  "regions": ["iad1"],  // US East (closest to Morocco via undersea cables)
  "functions": {
    "api/app/main.py": {
      "runtime": "python3.9",
      "maxDuration": 30,
      "memory": 1024,
      "includeFiles": [
        "app/**",
        "requirements.txt"
      ],
      "excludePatterns": [
        "**/__pycache__/**",
        "**/*.pyc",
        "**/tests/**",
        "**/benchmark/**",
        "**/docs/**",
        "**/.venv/**",
        "**/*.md"
      ]
    }
  },
  "routes": [
    {
      "src": "/health",
      "dest": "api/app/main.py",
      "headers": {
        "Cache-Control": "no-cache"
      }
    },
    {
      "src": "/process",
      "methods": ["POST"],
      "dest": "api/app/main.py",
      "headers": {
        "Access-Control-Allow-Origin": "https://n8n.aznet.ma",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
      }
    },
    {
      "src": "/(.*)",
      "dest": "api/app/main.py"
    }
  ],
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "X-Frame-Options", "value": "DENY" },
        { "key": "X-XSS-Protection", "value": "1; mode=block" },
        { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" }
      ]
    }
  ],
  "crons": [
    {
      "path": "/health",
      "schedule": "*/5 * * * *"  // Keep-warm every 5 minutes
    }
  ],
  "env": {
    "PYTHON_VERSION": "3.9",
    "PYTHONPATH": "."
  }
}
```

### `.vercelignore` (Critical for Build Speed)

```
# Python
.venv/
venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.mypy_cache/

# Tests & Benchmarks
tests/
benchmark/
**/test_*.py
**/*_test.py

# Documentation
docs/
*.md
!README.md

# IDE
.vscode/
.idea/
*.swp
*.swo

# Git
.git/
.gitignore

# Environment
.env
.env.local
.env.*.local

# OS
.DS_Store
Thumbs.db

# n8n
.n8n/

# Logs
*.log
logs/

# Vercel
.vercel/
```

---

## FastAPI App Optimization for Vercel

### App Structure for Serverless

```python
# api/app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

# Configure logging for Vercel
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global clients (reused across invocations)
_groq_client = None
_gemini_model = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize clients on cold start"""
    global _groq_client, _gemini_model
    
    # Lazy imports (don't fail at import time)
    try:
        from groq import AsyncGroq
        import google.generativeai as genai
        
        from app.config import settings
        
        if settings.GROQ_API_KEY:
            _groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
            logger.info("Groq client initialized")
        
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            _gemini_model = genai.GenerativeModel(
                settings.GEMINI_MODEL,
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": ExtractedReport,
                }
            )
            logger.info("Gemini model initialized")
    except Exception as e:
        logger.warning(f"Client init deferred: {e}")
    
    yield
    
    # Cleanup
    if _groq_client:
        await _groq_client.close()
    logger.info("Shutdown complete")

app = FastAPI(
    title="PFE aznet API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None
)

# CORS - restrictive
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    max_age=3600
)

# Health check (no auth, fast)
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "pfe-aznet-api",
        "version": "1.0.0",
        "groq_ready": _groq_client is not None,
        "gemini_ready": _gemini_model is not None
    }

# Main endpoint
@app.post("/process")
async def process(request: Request):
    # ... implementation
    pass
```

### Dependency Optimization

#### `requirements.txt` (Minimal, Pinned)

```txt
# Core
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0
python-multipart==0.0.6

# STT Providers
groq==0.5.0
google-generativeai==0.7.2
huggingface-hub==0.20.3

# Utilities
python-dotenv==1.0.0
httpx==0.26.0
tenacity==8.2.3

# Only in dev (excluded via .vercelignore)
# pytest==7.4.4
# pytest-asyncio==0.23.3
# pytest-mock==3.12.0
```

#### Use `requirements-dev.txt` for Dev Dependencies

```txt
-r requirements.txt
pytest==7.4.4
pytest-asyncio==0.23.3
pytest-mock==3.12.0
pytest-cov==4.1.0
httpx==0.26.0
ruff==0.1.15
```

---

## Cold Start Mitigation

### 1. Keep-Warm Cron (Vercel Native)

```json
// In vercel.json
"crons": [
  { "path": "/health", "schedule": "*/5 * * * *" }
]
```

**Cost:** ~8640 invocations/month = ~0.08 GB-hrs (negligible on free tier)

### 2. External Keep-Warm (GitHub Actions)

```yaml
# .github/workflows/keep-warm.yml
name: Keep Warm

on:
  schedule:
    - cron: '*/10 * * * *'  # Every 10 minutes
  workflow_dispatch:

jobs:
  warm:
    runs-on: ubuntu-latest
    steps:
      - name: Ping API
        run: |
          curl -f https://api.aznet.ma/health
          curl -f https://api.aznet.ma/process \
            -X POST \
            -H "Content-Type: application/json" \
            -d '{"text": "warmup", "metadata": {"date": "2026-01-01", "technicien": "warmup"}}' \
            --max-time 10 || true
```

### 3. Code-Level Optimizations

```python
# Lazy imports inside functions (not at module level)
async def transcribe_groq(audio_bytes: bytes) -> TranscriptionResult:
    from groq import AsyncGroq  # Import here!
    from app.config import settings
    
    client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    # ...
```

```python
# Reuse HTTP clients
import httpx

_http_client: httpx.AsyncClient = None

async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
    return _http_client
```

---

## Monitoring & Observability on Vercel

### 1. Vercel Dashboard Metrics

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| **Invocation Count** | Track daily | >10x baseline |
| **Function Duration (p95)** | <10s | >25s |
| **Error Rate** | <1% | >5% |
| **Cold Start Rate** | <20% | >50% |
| **Memory Usage** | <512MB | >900MB |

### 2. Custom Logging for Analysis

```python
# app/middleware/logging.py
import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("pfe.api")

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        
        # Log request (no sensitive data)
        logger.info(
            "Request started",
            extra={
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host if request.client else "unknown"
            }
        )
        
        try:
            response = await call_next(request)
            duration = (time.time() - start) * 1000
            
            logger.info(
                "Request completed",
                extra={
                    "status_code": response.status_code,
                    "duration_ms": round(duration, 2),
                    "path": request.url.path
                }
            )
            return response
            
        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.error(
                "Request failed",
                extra={
                    "error": str(e),
                    "duration_ms": round(duration, 2),
                    "path": request.url.path
                },
                exc_info=True
            )
            raise
```

### 3. Structured Logs for Vercel

```python
# app/main.py - Add to lifespan startup
import json
import sys

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": "pfe-aznet-api"
        }
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ["name", "msg", "args", "levelname", "levelno", 
                          "pathname", "filename", "module", "lineno",
                          "funcName", "created", "msecs", "relativeCreated",
                          "thread", "threadName", "processName", "process",
                          "message", "asctime"]:
                log_obj[key] = value
        return json.dumps(log_obj)

# Apply to root logger
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JSONFormatter())
logging.root.handlers = [handler]
logging.root.setLevel(logging.INFO)
```

### 4. External Monitoring (Free Options)

#### Sentry (Error Tracking)

```bash
# Add to requirements.txt
sentry-sdk[fastapi]==1.39.1
```

```python
# app/main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

sentry_logging = LoggingIntegration(
    level=logging.INFO,
    event_level=logging.ERROR
)

sentry_sdk.init(
    dsn="YOUR_SENTRY_DSN",  # From Vercel env
    integrations=[FastApiIntegration(), sentry_logging],
    traces_sample_rate=0.1,
    environment="production"
)
```

#### Datadog (APM) - If Needed

```bash
ddtrace==2.12.0
```

```bash
# Vercel: DD_API_KEY, DD_ENV, DD_SERVICE, DD_VERSION
# Run with: ddtrace-run uvicorn app.main:app
```

---

## Edge Cases & Troubleshooting

### 1. Function Timeout (30s Limit)

**Symptoms:** 504 Gateway Timeout, function killed

**Solutions:**
```python
# 1. Parallel STT + Extraction (if independent)
# 2. Async throughout (no sync blocking)
# 3. Reduce audio quality before STT
# 4. Use faster model (Whisper-tiny on Groq)

# Audio preprocessing (if you control input)
import io
import soundfile as sf

def compress_audio(audio_bytes: bytes, target_sr=16000) -> bytes:
    """Downsample to 16kHz mono for faster STT"""
    data, sr = sf.read(io.BytesIO(audio_bytes))
    if sr != target_sr:
        import resampy
        data = resampy.resample(data, sr, target_sr)
    if len(data.shape) > 1:
        data = data.mean(axis=1)  # Mono
    # Re-encode
    output = io.BytesIO()
    sf.write(output, data, target_sr, format='OGG', subtype='OPUS')
    return output.getvalue()
```

### 2. Memory Limit (1024MB)

**Symptoms:** OOM kills, 502 errors

**Solutions:**
```python
# 1. Stream large audio (don't load all at once)
# 2. Delete large objects explicitly
# 3. Use generators for processing

async def process_large_audio(audio_bytes: bytes):
    # Process in chunks if needed
    chunk_size = 1024 * 1024  # 1MB
    for i in range(0, len(audio_bytes), chunk_size):
        chunk = audio_bytes[i:i+chunk_size]
        yield chunk
    
    # Force garbage collection
    import gc
    gc.collect()
```

### 3. Payload Too Large (>50MB)

**Solutions:**
- n8n: Compress audio before sending (Opus @ 32kbps)
- Reject early with clear error

```python
@app.post("/process")
async def process(request: Request):
    # Check content-length header
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 50 * 1024 * 1024:
        return JSONResponse(
            status_code=413,
            content={"error": "payload_too_large", "message": "Audio file exceeds 50MB limit"}
        )
```

### 4. Cold Start Latency

**Measure:** Add timing to health endpoint

```python
@app.get("/health")
async def health():
    import time
    start = time.time()
    
    # Quick dependency checks
    checks = {}
    checks["groq"] = _groq_client is not None
    checks["gemini"] = _gemini_model is not None
    
    return {
        "status": "healthy",
        "cold_start": _groq_client is None,  # True if just initialized
        "init_time_ms": round((time.time() - start) * 1000, 2),
        "checks": checks
    }
```

---

## CI/CD Pipeline for Vercel

### GitHub Actions: Full Deploy

```yaml
# .github/workflows/deploy-vercel.yml
name: Deploy to Vercel

on:
  push:
    branches: [main]
    paths:
      - 'api/**'
      - 'vercel.json'
      - '.github/workflows/deploy-vercel.yml'
  pull_request:
    branches: [main]
    paths:
      - 'api/**'

env:
  VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}
  VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}

jobs:
  test:
    name: Run Tests
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ./api
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.9"
          cache: "pip"
          cache-dependency-path: api/requirements.txt
      - name: Install deps
        run: |
          python -m venv .venv
          .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
      - name: Run tests
        run: .venv/bin/python -m pytest -v --tb=short --cov=app --cov-fail-under=80

  deploy-preview:
    name: Deploy Preview
    needs: test
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install Vercel CLI
        run: npm i -g vercel@latest
      - name: Pull Vercel Environment
        run: vercel pull --yes --environment=preview --token=${{ secrets.VERCEL_TOKEN }}
      - name: Build Project
        run: vercel build --token=${{ secrets.VERCEL_TOKEN }}
      - name: Deploy to Preview
        run: |
          url=$(vercel deploy --prebuilt --token=${{ secrets.VERCEL_TOKEN }})
          echo "PREVIEW_URL=$url" >> $GITHUB_ENV
      - name: Comment PR
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: ${{ github.event.pull_request.number }},
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: '🚀 Preview deployment: ${{ env.PREVIEW_URL }}'
            })

  deploy-production:
    name: Deploy Production
    needs: test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install Vercel CLI
        run: npm i -g vercel@latest
      - name: Pull Vercel Environment
        run: vercel pull --yes --environment=production --token=${{ secrets.VERCEL_TOKEN }}
      - name: Build Project
        run: vercel build --prod --token=${{ secrets.VERCEL_TOKEN }}
      - name: Deploy to Production
        run: vercel deploy --prebuilt --prod --token=${{ secrets.VERCEL_TOKEN }}
      - name: Verify Deployment
        run: |
          sleep 10
          curl -f https://api.aznet.ma/health
```

### Vercel Secrets Setup

```bash
# In GitHub repo Settings → Secrets → Actions
VERCEL_TOKEN          # From vercel account settings
VERCEL_ORG_ID         # From vercel link output
VERCEL_PROJECT_ID     # From vercel link output
GEMINI_API_KEY        # For production env
GROQ_API_KEY          # For production env
HF_API_KEY            # For production env
SENTRY_DSN            # Optional error tracking
```

---

## Rollback Strategy

### Vercel Instant Rollback

```bash
# List deployments
vercel ls api.aznet.ma

# Promote previous deployment
vercel promote <deployment-url> --scope=<team>

# Or via dashboard: Deployments → Three dots → Promote to Production
```

### Git-Based Rollback

```bash
# Revert commit
git revert <bad-commit>
git push origin main

# Triggers new deployment automatically
```

---

## Cost Optimization

### Free Tier Limits (Hobby)

| Resource | Limit | PFE Usage |
|----------|-------|-----------|
| Function Executions | Unlimited | ~500/day |
| Function Duration | 100 GB-hrs/mo | ~5 GB-hrs |
| Bandwidth | 100 GB/mo | ~1 GB |
| Build Time | 6000 min/mo | ~100 min |
| Edge Functions | 125k/mo | 0 |

### Staying in Free Tier

1. **No Edge Functions** — Use regular functions
2. **Optimize build** — Cache pip, minimal deps
3. **Keep-warm** — Low cost, prevents cold starts
4. **Monitor** — Check Vercel dashboard weekly

---

## Related Notes

- [[Deployment Guide]]
- [[Architecture]]
- [[Testing Strategy]]
- [[Security Secrets]]
- [[n8n Workflows]]