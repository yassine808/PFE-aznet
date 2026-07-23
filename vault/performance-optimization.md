---
tags: [pfe, performance, optimization, latency]
type: technical
priority: medium
status: partial
---

> **Note on status:** nothing has been measured yet — no profiling, no load testing, no caching layer exists. Targets below are PLAN.md's stated success metrics, not achieved numbers. A prior version of this doc described audio preprocessing, Vercel KV caching, Prometheus-based dashboards, and load-test scripts as if implemented — none of that exists; it has been removed.

# Performance (Plan / Targets)

## Targets (from PLAN.md §8, "success metrics")

| Metric | Target |
|---|---|
| E2E latency, voice note → Sheet row | < 60s |
| Report submission time (cahier's own KPI) | < 2 min |
| Extraction accuracy on golden set | > 90% fields correct |
| STT WER per engine | measured and compared (benchmark deliverable) |

No p95/p99 latency numbers, cold-start rate, or throughput figures have been measured — there is no deployed instance to measure against yet, and no load-testing tool (locust/k6) is wired into this repo.

## What's actually in the code today relevant to performance

- **Lazy imports**: every STT provider (`api/app/providers/*.py`) and the extraction module (`api/app/extraction.py`) import their SDKs (`groq`, `google.genai`, `httpx`) *inside* the function body, not at module top-level. This keeps tests dependency-free and avoids paying import cost until a request actually needs that provider — the one deliberate performance-adjacent design choice made so far.
- **`TranscriptionInfo.latency_s`**: every STT provider times its own call with `time.perf_counter()` and returns it — the only latency instrumentation that exists in the codebase.

## Not built

- Audio preprocessing (resampling, silence trimming, normalization) — no `soundfile`/`resampy` dependency exists in `api/requirements.txt`
- Any caching layer (no Redis/Vercel KV, no `functools.lru_cache` on prompts)
- Load testing (no `locust`/`k6` script in the repo)
- Cold-start mitigation (no deployment target yet to have cold starts on)

## Where this belongs

The Week-1 STT benchmark (`benchmark/`, per PLAN.md) is where WER/latency-per-engine numbers will actually get produced — see [[STT Benchmark]] for the real methodology once it exists. This doc should not anticipate results before the benchmark runs.

## Related Notes

- [[Architecture]]
- [[STT Benchmark]]
- [[Testing Strategy]]
- [[Deployment Guide]]
