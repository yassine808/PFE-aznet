---
tags: [pfe, stt, benchmark, providers, groq, gemini, huggingface]
type: technical
priority: high
status: pending
---

# STT Benchmark Plan

## Objective

Select default STT provider for production based on **Darija accuracy**, **latency**, and **reliability** on free tiers.

## Providers Under Test

| Provider | Model | API | Free Tier Limits |
|----------|-------|-----|------------------|
| **Groq** | Whisper-large-v3 | `groq` | 14,400 req/day, 6000 tokens/min |
| **Gemini** | gemini-flash-lite-latest | `gemini` | 15 RPM, 1M tokens/day |
| **HF Darija** | custom-darija-model | `hf-darija` | 30,000 req/month |

## Test Dataset

**Source:** `benchmark/dataset/audio/` (excluded from git)
**Format:** 50+ Darija audio samples (technician voice notes)
**Metadata:** `benchmark/dataset/references.csv` (ground truth transcripts)

### Sample Categories
| Category | Count | Description |
|----------|-------|-------------|
| Clean | 15 | Quiet environment, clear speech |
| Noisy | 15 | Background construction noise |
| Accented | 10 | Regional Darija variations |
| Technical | 10 | Cable/trade terminology heavy |
| Short | 5 | < 5 seconds |
| Long | 5 | > 30 seconds |

## Evaluation Metrics

### Primary: Word Error Rate (WER)
```
WER = (Substitutions + Deletions + Insertions) / Total Words in Reference
```

**Target:** WER < 25% for Darija (challenging language)

### Secondary Metrics
| Metric | Target | Weight |
|--------|--------|--------|
| Latency (p95) | < 5s | 20% |
| API Success Rate | > 99% | 15% |
| Cost/Request (proj.) | $0.00 | 10% |
| Technical Term Accuracy | > 80% | 25% |
| Short Audio Handling | No failures | 10% |

### Technical Term List (Must Recognize)
```
goulotte, câble, tirage, pose, chantier, équipement,
fibre, raccordement, boîte, dérivation, gaine,
mètre, mètre linéaire, point de raccordement
```

## Benchmark Script

Location: `benchmark/run_benchmark.py`

```python
# Pseudocode
for provider in ["groq", "gemini", "hf-darija"]:
    for audio_file in dataset:
        start = time()
        result = transcribe(provider, audio_file)
        latency = time() - start
        
        wer = calculate_wer(result.text, reference[audio_file])
        term_acc = calculate_term_accuracy(result.text, TECH_TERMS)
        
        record(provider, audio_file, wer, latency, term_acc)
```

## Execution Plan

### Week 1 (Jul 23-29)
- [ ] Prepare dataset (50 samples + references)
- [ ] Implement benchmark runner
- [ ] Run Groq benchmark
- [ ] Run Gemini benchmark  
- [ ] Run HF Darija benchmark
- [ ] Aggregate results, statistical significance
- [ ] Document decision in `config.py`

### Success Criteria
- One provider clearly wins on WER + technical terms
- Or: Hybrid approach (e.g., Groq default, HF for low-confidence)

## Expected Outcomes

| Scenario | Decision |
|----------|----------|
| One provider dominates | Set as `DEFAULT_PROVIDER` |
| Close WER, diff latency | Pick lower latency |
| HF best but unreliable | Groq default, HF fallback |
| All similar | Groq (best free tier limits) |

## Configuration Update

After benchmark, update `api/app/config.py`:

```python
class Settings(BaseSettings):
    stt_provider: str = "groq"  # Updated post-benchmark (lowercase field, api/app/config.py)
```

## Related Notes

- [[Project Overview]]
- [[Architecture]]
- [[API Providers]]
- [[Extraction Pipeline]]