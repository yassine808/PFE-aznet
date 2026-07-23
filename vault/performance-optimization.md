---
tags: [pfe, performance, optimization, latency, throughput, bottleneck, profiling]
type: technical
priority: high
status: current
---

# Performance Optimization Guide

## Performance Targets

| Metric | Target | Critical Threshold |
|--------|--------|-------------------|
| **API p95 Latency** | < 10s | > 25s |
| **STT Processing** | < 5s | > 15s |
| **Extraction Processing** | < 3s | > 10s |
| **End-to-End (Voice → Sheets)** | < 30s | > 60s |
| **Cold Start** | < 2s | > 5s |
| **Error Rate** | < 1% | > 5% |
| **Throughput** | 10 req/s sustained | 50 req/s burst |

---

## Profiling & Benchmarking

### Local Profiling (API)

```bash
cd api

# 1. Install profiling tools
.venv/Scripts/pip.exe install py-spy snakeviz scalene

# 2. CPU Profiling (py-spy - no code changes)
.venv/Scripts/python.exe -m py_spy record -o profile.svg -- uvicorn app.main:app --reload

# 3. Memory Profiling (scalene)
.venv/Scripts/python.exe -m scalene --html --outfile memory.html -m uvicorn app.main:app

# 4. Function-level (cProfile)
.venv/Scripts/python.exe -m cProfile -o profile.stats -m uvicorn app.main:app
# Analyze: snakeviz profile.stats

# 5. Line-by-line (line_profiler)
.venv/Scripts/pip.exe install line_profiler
# Add @profile decorator to functions
# Run: .venv/Scripts/python.exe -m line_profiler main.py.lprof
```

### Load Testing

```bash
# Install
.venv/Scripts/pip.exe install locust

# locustfile.py
from locust import HttpUser, task, between

class APIUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def text_mode(self):
        self.client.post("/process", json={
            "text": "Test transcription " * 50,
            "metadata": {"date": "2026-07-23", "technicien": "Test"}
        })
    
    @task(1)
    def voice_mode(self):
        import base64
        audio = base64.b64encode(b"fake audio data" * 1000).decode()
        self.client.post("/process", json={
            "audio": audio,
            "metadata": {"date": "2026-07-23", "technicien": "Test"}
        })

# Run
.venv/Scripts/locust.exe -f locustfile.py --host=http://localhost:8000
# Open http://localhost:8089
```

### Vercel Production Load Test

```bash
# k6 (better for serverless)
# Install: https://k6.io/docs/getting-started/installation/

# k6-script.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 10 },   // Ramp up
    { duration: '5m', target: 10 },   // Sustained
    { duration: '2m', target: 50 },   // Spike
    { duration: '5m', target: 50 },   // Sustained spike
    { duration: '2m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<10000'],  // 95th percentile < 10s
    http_req_failed: ['rate<0.01'],       // Error rate < 1%
  },
};

export default function () {
  const payload = JSON.stringify({
    text: "Test " + Math.random(),
    metadata: { date: "2026-07-23", technicien: "LoadTest" }
  });
  
  const params = { headers: { 'Content-Type': 'application/json' } };
  
  const res = http.post('https://api.aznet.ma/process', payload, params);
  
  check(res, {
    'status is 200': (r) => r.status === 200,
    'has extracted_report': (r) => r.json().extracted_report !== undefined,
  });
  
  sleep(1);
}

# Run
k6 run k6-script.js
```

---

## STT Provider Optimization

### Audio Preprocessing (Massive Impact)

```python
# api/app/providers/audio_utils.py
import io
import soundfile as sf
import numpy as np

TARGET_SR = 16000  # Whisper optimal
MAX_DURATION = 60  # seconds

def optimize_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> bytes:
    """
    Preprocess audio for faster, more accurate STT:
    1. Convert to mono 16kHz
    2. Trim silence
    3. Normalize volume
    4. Re-encode as Opus (smaller)
    """
    # Load
    data, sr = sf.read(io.BytesIO(audio_bytes))
    
    # Mono
    if len(data.shape) > 1:
        data = data.mean(axis=1)
    
    # Resample
    if sr != TARGET_SR:
        import resampy
        data = resampy.resample(data, sr, TARGET_SR)
        sr = TARGET_SR
    
    # Trim silence (simple VAD)
    data = trim_silence(data, sr)
    
    # Normalize
    data = normalize_audio(data)
    
    # Truncate if too long
    max_samples = MAX_DURATION * TARGET_SR
    if len(data) > max_samples:
        data = data[:max_samples]
    
    # Re-encode as Opus (smaller, faster to upload)
    output = io.BytesIO()
    sf.write(output, data, sr, format='OGG', subtype='OPUS')
    return output.getvalue()

def trim_silence(data: np.ndarray, sr: int, threshold_db: float = -40) -> np.ndarray:
    """Remove leading/trailing silence"""
    # Simple energy-based VAD
    frame_length = int(0.02 * sr)  # 20ms frames
    hop_length = int(0.01 * sr)    # 10ms hop
    
    energy = np.array([
        np.mean(data[i:i+frame_length]**2)
        for i in range(0, len(data)-frame_length, hop_length)
    ])
    
    threshold = np.max(energy) * (10 ** (threshold_db / 10))
    voice_frames = energy > threshold
    
    if not np.any(voice_frames):
        return data  # All silence, return original
    
    first_voice = np.where(voice_frames)[0][0] * hop_length
    last_voice = (np.where(voice_frames)[0][-1] + 1) * hop_length + frame_length
    
    # Add 100ms padding
    pad = int(0.1 * sr)
    return data[max(0, first_voice-pad):min(len(data), last_voice+pad)]

def normalize_audio(data: np.ndarray, target_db: float = -20) -> np.ndarray:
    """Normalize to target dBFS"""
    rms = np.sqrt(np.mean(data**2))
    if rms == 0:
        return data
    current_db = 20 * np.log10(rms)
    gain = 10 ** ((target_db - current_db) / 20)
    return np.clip(data * gain, -1.0, 1.0)
```

### Provider-Specific Tuning

```python
# api/app/providers/groq.py
class GroqProvider:
    # Optimal settings for Whisper-large-v3 on Groq
    MODEL = "whisper-large-v3"
    LANGUAGE = "ar"  # Darija uses Arabic script
    TEMPERATURE = 0.0  # Deterministic
    RESPONSE_FORMAT = "verbose_json"  # Includes timestamps, segments
    
    async def transcribe(self, audio_bytes: bytes) -> TranscriptionResult:
        # Preprocess
        optimized = optimize_audio(audio_bytes)
        
        # Transcribe with optimal params
        transcription = await self.client.audio.transcriptions.create(
            file=("audio.ogg", optimized, "audio/ogg"),
            model=self.MODEL,
            language=self.LANGUAGE,
            temperature=self.TEMPERATURE,
            response_format=self.RESPONSE_FORMAT,
            prompt="مغرب، دارجة، كابلاج،ݣولوط، كابل، تشبيك، بواتيي، فيبر"  # Domain vocab
        )
        
        return TranscriptionResult(
            text=transcription.text,
            language=transcription.language,
            duration=transcription.duration,
            segments=transcription.segments  # For confidence scoring
        )
```

### Confidence Scoring from Segments

```python
def calculate_stt_confidence(segments: list) -> tuple[float, bool]:
    """
    Calculate confidence from Whisper segments.
    Returns (confidence_score, is_low_confidence)
    """
    if not segments:
        return 0.0, True
    
    # Whisper provides avg_logprob per segment
    logprobs = [seg.avg_logprob for seg in segments if seg.avg_logprob is not None]
    
    if not logprobs:
        return 0.5, True
    
    # Convert logprob to 0-1 confidence
    # logprob range: ~-1 (good) to ~-10 (bad)
    confidences = [min(1.0, max(0.0, (lp + 1) / 1)) for lp in logprobs]
    avg_confidence = sum(confidences) / len(confidences)
    
    # Low if avg < 0.5 or any segment very low
    is_low = avg_confidence < 0.5 or any(c < 0.3 for c in confidences)
    
    return avg_confidence, is_low
```

---

## Extraction Optimization

### Prompt Caching Strategy

```python
# api/app/extraction.py
from functools import lru_cache
import hashlib

# Cache compiled prompts
@lru_cache(maxsize=10)
def get_system_prompt(schema_hash: str) -> str:
    """Cache system prompt by schema version"""
    return f"""Tu es un extracteur de rapports techniques pour techniciens câbleurs au Maroc.

SCHÉMA: {schema_hash}

RÈGLES STRICTES:
1. Extrais UNIQUEMENT ce qui est explicitement dit. Si absent → null.
2. JAMAIS d'invention, JAMAIS de déduction.
3. "resume" : français professionnel, style rapport d'intervention.
4. Termes techniques en français: goulotte, câble, tirage, pose, chantier.
5. Confiance extraction: "high"/"medium"/"low" selon clarté audio."""

# Reuse model instances
_gemini_model = None
_groq_client = None

def get_gemini_model():
    global _gemini_model
    if _gemini_model is None:
        import google.generativeai as genai
        from app.config import settings
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel(
            "gemini-1.5-flash",
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": ExtractedReport,
                "temperature": 0.1,
                "top_p": 0.9,
                "max_output_tokens": 2048,
            }
        )
    return _gemini_model
```

### Parallel Processing (If Multiple Fields Independent)

```python
# Not currently needed - extraction is single call
# But useful if splitting into parallel sub-extractions:

import asyncio

async def extract_parallel(transcription: str) -> ExtractedReport:
    """Parallel sub-extractions for complex reports"""
    
    async def extract_identity():
        # Technicien, date, chantier
        pass
    
    async def extract_work():
        # Type, quantities
        pass
    
    async def extract_issues():
        # Problemes, observations
        pass
    
    async def generate_summary():
        # Resume
        pass
    
    # Run in parallel
    identity, work, issues, summary = await asyncio.gather(
        extract_identity(),
        extract_work(),
        extract_issues(),
        generate_summary()
    )
    
    return ExtractedReport(
        **identity.model_dump(),
        **work.model_dump(),
        **issues.model_dump(),
        resume=summary
    )
```

---

## Caching Strategy

### Multi-Layer Caching

```
┌─────────────────────────────────────────────────────────────┐
│                    CACHING LAYERS                           │
├─────────────────┬─────────────────┬─────────────────────────┤
│   L1: Memory    │   L2: Redis     │   L3: Application       │
│   (In-process)  │   (Vercel KV /  │   (Prompt, Schema,      │
│   - Models      │    Upstash)     │    Config)              │
│   - Prompts     │   - Transcripts │   - Static assets       │
│   - Schemas     │   - Extractions │                         │
└─────────────────┴─────────────────┴─────────────────────────┘
```

### Vercel KV Integration (Redis)

```python
# api/app/cache.py
from vercel_kv import KV
import json
import hashlib

kv = KV()

class Cache:
    TTL_TRANSCRIPTION = 86400 * 7      # 7 days
    TTL_EXTRACTION = 86400 * 30        # 30 days
    TTL_SCHEMA = 86400 * 365           # 1 year
    
    @staticmethod
    def transcription_key(audio_hash: str, provider: str) -> str:
        return f"transcript:{provider}:{audio_hash[:16]}"
    
    @staticmethod
    def extraction_key(transcript_hash: str, schema_version: str) -> str:
        return f"extract:v{schema_version}:{transcript_hash[:16]}"

    async def get_transcription(self, audio_bytes: bytes, provider: str):
        audio_hash = hashlib.sha256(audio_bytes).hexdigest()
        key = self.transcription_key(audio_hash, provider)
        
        cached = await kv.get(key)
        if cached:
            return TranscriptionResult.parse_raw(cached)
        return None
    
    async def set_transcription(self, audio_bytes: bytes, provider: str, result: TranscriptionResult):
        audio_hash = hashlib.sha256(audio_bytes).hexdigest()
        key = self.transcription_key(audio_hash, provider)
        await kv.set(key, result.model_dump_json(), ex=self.TTL_TRANSCRIPTION)
    
    async def get_extraction(self, transcript: str, schema_version: str):
        transcript_hash = hashlib.sha256(transcript.encode()).hexdigest()
        key = self.extraction_key(transcript_hash, schema_version)
        
        cached = await kv.get(key)
        if cached:
            return ExtractedReport.parse_raw(cached)
        return None
    
    async def set_extraction(self, transcript: str, schema_version: str, result: ExtractedReport):
        transcript_hash = hashlib.sha256(transcript.encode()).hexdigest()
        key = self.extraction_key(transcript_hash, schema_version)
        await kv.set(key, result.model_dump_json(), ex=self.TTL_EXTRACTION)

# Usage in endpoint
cache = Cache()

@app.post("/process")
async def process(request: ProcessRequest):
    # Check transcription cache
    if request.audio:
        cached = await cache.get_transcription(request.audio_bytes, settings.DEFAULT_STT_PROVIDER)
        if cached:
            transcription = cached.text
            stt_cached = True
        else:
            transcription = await transcribe(request.audio_bytes)
            await cache.set_transcription(request.audio_bytes, settings.DEFAULT_STT_PROVIDER, result)
            stt_cached = False
    else:
        transcription = request.text
        stt_cached = False
    
    # Check extraction cache
    schema_version = "1"  # Increment on schema change
    cached = await cache.get_extraction(transcription, schema_version)
    if cached:
        return ProcessResponse(
            extracted_report=cached,
            transcription=transcription if not stt_cached else None,
            cached=True
        )
    
    # Extract
    extracted = await extract(transcription)
    await cache.set_extraction(transcription, schema_version, extracted)
    
    return ProcessResponse(extracted_report=extracted, ...)
```

---

## Database/Sheets Optimization

### Batch Writes (n8n)

```javascript
// n8n Function Node: Batch Buffer
// Accumulates items and flushes every 10 items or 30 seconds

const buffer = $getWorkflowStaticData('global').sheetsBuffer || [];
const maxBatch = 10;
const flushInterval = 30000;

buffer.push($json);

if (buffer.length >= maxBatch) {
  // Flush
  $getWorkflowStaticData('global').sheetsBuffer = [];
  return buffer.map(item => ({ json: item }));
}

// Set timer if first item
if (buffer.length === 1) {
  setTimeout(() => {
    const buf = $getWorkflowStaticData('global').sheetsBuffer || [];
    if (buf.length > 0) {
      $getWorkflowStaticData('global').sheetsBuffer = [];
      // Trigger self via internal webhook
      $executeWorkflow('sheets-flush', { items: buf });
    }
  }, flushInterval);
}

$getWorkflowStaticData('global').sheetsBuffer = buffer;
return []; // Don't continue yet
```

### Sheets API Optimization

```python
# Batch append instead of single rows
# In n8n Google Sheets node: Use "Append" with multiple rows

# Optimal batch size: 50-100 rows per request
# Rate limit: 60 writes/min per project (Google default)

# If hitting limits:
# 1. Request quota increase
# 2. Use batchUpdate with multiple ranges
# 3. Implement exponential backoff
```

---

## Cold Start Mitigation

### 1. Minimize Import Time

```python
# BAD: Heavy imports at module level
import torch
import tensorflow as tf
from transformers import WhisperModel

# GOOD: Lazy imports inside functions
async def transcribe_hf(audio_bytes):
    from transformers import pipeline  # Only loads when called
    pipe = pipeline("automatic-speech-recognition", model="...")

# In api/app/providers/__init__.py
# Use lazy import pattern:
def get_provider(name: str):
    providers = {
        "groq": "api.app.providers.groq:GroqProvider",
        "gemini": "api.app.providers.gemini:GeminiProvider",
        "hf-darija": "api.app.providers.hf_darija:HFDarijaProvider",
    }
    module_path, class_name = providers[name].split(":")
    module = __import__(module_path, fromlist=[class_name])
    return getattr(module, class_name)()
```

### 2. Warm Dependencies at Startup

```python
# api/app/main.py
@app.on_event("startup")
async def warmup():
    """Pre-load heavy dependencies"""
    import asyncio
    
    async def warm_provider(name):
        try:
            provider = get_provider(name)
            # Quick test call (tiny audio)
            await provider.transcribe(b"RIFF....")  # 100ms WAV header
        except:
            pass  # Ignore warmup failures
    
    # Warm in parallel
    await asyncio.gather(*[
        warm_provider("groq"),
        warm_provider("gemini"),
    ])
```

### 3. Vercel Function Warmers

```javascript
// api/_warmup.js (Edge Function)
export const config = { runtime: 'edge' };

export default async function handler(req) {
  // Called by cron every 5 min
  if (req.headers.get('x-vercel-cron') !== 'true') {
    return new Response('Unauthorized', { status: 401 });
  }
  
  // Ping main function
  await fetch('https://api.aznet.ma/health', { method: 'GET' });
  
  return new Response('Warmed');
}
```

```json
// vercel.json
{
  "crons": [
    { "path": "/_warmup", "schedule": "*/5 * * * *" }
  ]
}
```

---

## Memory Optimization

### Python Memory Patterns

```python
# BAD: Accumulating in memory
def process_large_batch(items):
    results = []
    for item in items:
        results.append(process(item))  # Keeps all in memory
    return results

# GOOD: Generator
def process_large_batch(items):
    for item in items:
        yield process(item)  # Streams, constant memory

# GOOD: Explicit cleanup
def process_with_cleanup(items):
    for item in items:
        result = process(item)
        yield result
        del result  # Help GC
    
    import gc
    gc.collect()  # Force collection after batch
```

### Audio Streaming (Large Files)

```python
# Stream audio instead of loading fully
async def transcribe_streaming(audio_url: str, provider: str):
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", audio_url) as response:
            # Process in chunks
            async for chunk in response.aiter_bytes(1024 * 1024):  # 1MB chunks
                # Feed to streaming STT if supported
                # Otherwise accumulate and process
                pass
```

---

## Monitoring Performance

### Key Dashboards

```promql
# API Latency (p50, p95, p99)
histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))
histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))

# STT Provider Latency
histogram_quantile(0.95, sum(rate(stt_duration_seconds_bucket{provider="groq"}[5m])) by (le))

# Cold Start Rate
rate(cold_starts_total[5m])

# Error Rate by Type
sum(rate(http_requests_total{status=~"5.."}[5m])) by (path) / sum(rate(http_requests_total[5m])) by (path)

# Cache Hit Rate
sum(rate(cache_hits_total[5m])) / (sum(rate(cache_hits_total[5m])) + sum(rate(cache_misses_total[5m])))
```

---

## Optimization Checklist

### Before Deploy
- [ ] Audio preprocessing implemented (16kHz mono Opus)
- [ ] STT provider prompts optimized with domain vocabulary
- [ ] Extraction model configured (temp=0.1, structured output)
- [ ] Lazy imports for all heavy dependencies
- [ ] Startup warmup for providers
- [ ] Cache layer configured (Vercel KV)
- [ ] Metrics instrumentation added
- [ ] Load test passed (k6, 50 RPS sustained)

### After Deploy
- [ ] Monitor p95 latency < 10s
- [ ] Monitor cold start rate < 20%
- [ ] Monitor STT provider success rate > 99%
- [ ] Monitor cache hit rate > 30%
- [ ] Monitor memory < 800MB
- [ ] Set up alerts for regressions

### Monthly
- [ ] Review provider performance (Groq vs Gemini vs HF)
- [ ] Analyze cache effectiveness
- [ ] Check for N+1 patterns in extraction
- [ ] Benchmark against new model versions
- [ ] Update domain vocabulary in prompts

---

## Related Notes

- [[Vercel Advanced]]
- [[Architecture]]
- [[STT Benchmark]]
- [[Testing Strategy]]
- [[Deployment Guide]]