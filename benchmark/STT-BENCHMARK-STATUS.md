# STT benchmark — state and plan (2026-08-07)

Handoff so this survives a reboot. Everything below is measured, not assumed.
Source of truth for what is done, what is running, and what to do next.

---

## 1. What changed today

| file | status | note |
|---|---|---|
| `benchmark/run_compare.py` | **new, ran clean** | ground-truth-free runner: transcript + latency + confidence per engine |
| `benchmark/download_models.py` | **new** | 13-checkpoint catalogue, probed live against the Hub API |
| `benchmark/run_local.py` | **new, untested** | GPU runner for the downloaded checkpoints |
| `benchmark/.venv-local/` | **new** | Python 3.11 + torch 2.13.0+cu126, isolated from `api/.venv` |
| `api/app/providers/gemini_audio.py` | **fixed, 257 tests pass** | repetition-loop guards (see §4) |
| `.gitignore` | updated | `benchmark/models/`, `benchmark/.venv-local/` — `.venv/` did **not** match `.venv-local/` |

Deliberately **not** changed: `api/app/prompts/stt-vocabulary.md` (an A/B cleared it, §5),
`api/app/providers/groq_whisper.py`, `run_benchmark.py`.

---

## 2. Environment (rebuild if lost)

```bash
# GPU: RTX 3070, 8.6 GB, sm_86, driver 610.74
cd benchmark
"C:/Users/ysmag/AppData/Local/Programs/Python/Python311/python.exe" -m venv .venv-local
.venv-local/Scripts/python.exe -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126
.venv-local/Scripts/python.exe -m pip install numpy transformers accelerate safetensors peft "huggingface_hub[hf_transfer]" librosa soundfile
.venv-local/Scripts/python.exe -c "import torch; print(torch.cuda.is_available())"   # must print True
```

`api/.venv` (Python 3.9) is untouched and must stay that way — torch there would
let pip upgrade shared pins (`numpy`, `typing-extensions`, `huggingface-hub`)
under the running API. The Docker image is unaffected either way: `api/Dockerfile`
installs from a hash-pinned `requirements.txt`, never from the venv.

---

## 3. Downloads — `benchmark/models/` (28 GB, gitignored)

Folder names are the repo id with `/` → `__`.

| folder | size | family | state |
|---|---|---|---|
| `ychafiqui__whisper-medium-darija` | 2.9 G | whisper | ✅ |
| `ychafiqui__whisper-small-darija` | 925 M | whisper | ✅ |
| `KandirResearch__Whisper-Small-Darija` | 925 M | whisper | ✅ |
| `TaloCreations__whisper-darija-finetuned` | 925 M | whisper | ✅ |
| `C-Ilyas__whisper-base-darija` | 278 M | whisper | ✅ |
| `anaszil__whisper-large-v3-turbo-darija` | 54 M | whisper **LoRA** | ✅ needs merge, §7 |
| `boumehdi__wav2vec2-large-xlsr-moroccan-darija` | 1.2 G | wav2vec2 | ✅ |
| `amineouaki__wav2vec2-darija-combined` | 1.2 G | wav2vec2 | ✅ |
| `openai__whisper-large-v3` | 18 G | whisper | ✅ **bloated**, §6 |
| `openai__whisper-large-v3-turbo` | 1.6 G | whisper | ✅ control / LoRA base |
| `Qwen__Qwen3-ASR-1.7B` | 479 M | other | ⏳ was still downloading |
| `BounharAbdelaziz__Morocco-Darija-STT-large` | **19 K** | whisper | ❌ **GATED — needs your action** |
| `amineouaki__wav2vec2-large-xlsr-53-darija-combined` | **15 K** | wav2vec2 | ❌ **GATED — needs your action** |

### The two failures are gated repos, not dead links

```
GatedRepoError: 401 Client Error
```

Fix requires a human with a browser — it cannot be automated:

1. Log in at huggingface.co.
2. Open each model page and **accept the license / request access**.
3. Put a token with `read` scope in `.env` as `HF_TOKEN`.
4. Re-run `download_models.py`.

This also explains `api/app/providers/hf_darija.py` completely. That adapter had **two** independent faults, not one: `HF_TOKEN` was unset *and* its checkpoint id 401s. The 401 means **gated**, not "does not exist" — same status code, opposite prognosis. A missing repo is unfixable; a gated one is a click away. (`…-large-v1.6` may still be a wrong id — verify after the token is set.)

Resume / repair (idempotent — completed repos are skipped):

```bash
cd benchmark
HF_HUB_ENABLE_HF_TRANSFER=1 .venv-local/Scripts/python.exe download_models.py
```

`BounharAbdelaziz/Morocco-Darija-STT-large` is the one explicitly requested; it is
the only model in the *Moroccan Speech Models & Datasets* collection, ~2 B params,
sharded safetensors, apache-2.0. **Retry it first.** Note the id pinned at
`api/app/providers/hf_darija.py:12` is `…-large-v1.6`, which returns **401** — it
does not exist publicly, which is why that adapter has never run once.

---

## 4. Gemini repetition loop — fixed

**Symptom (measured):** one 84 KB clip → **222 797 characters in 129.2 s**, tail
repeating `à l'hôpital de la ville de Rabat` without end. Groq returned 381 chars
in 1.0 s on the same audio. Gemini also *translated* to French on that clip
despite the prompt's « Ne traduis pas ».

**Fix** in `api/app/providers/gemini_audio.py`:

- `max_output_tokens=4096` — longest legitimate transcript was 1485 chars ≈ 500
  tokens, so this is ~4× the worst real case.
- `temperature=0.0` — transcription is not creative; sampling is what lets the
  decoder leave the audio.
- `_is_degenerate()` → raises `TranscriptionError` (→ 502, n8n flags the row).
  Raising, not truncating: a truncated loop is still 4 K characters of garbage
  that the extraction chain would summarise into a confident fiction, and
  `has_data()` would not catch it because repeated text is not empty.

**Verified:** 257 passed, 3 warnings, 212 s. Caveat — SDKs are mocked at the
boundary, so no test hit the live `generate_content` path with the new `config=`.
Clip `WhatsApp Audio 2026-07-25 at 5.11.10 PM.ogg` is a reproducible trigger;
re-run it against the real API to confirm end to end.

---

## 5. Findings from the first live run

`results/compare_20260807_111634.{csv,md}` — 11 clips × 3 engines.

| engine | clips | errors | mean latency | mean confidence | mean chars |
|---|---|---|---|---|---|
| groq | 11 | 0 | **1.53 s** | 0.483 | 613 |
| gemini | 11 | 0 | 16.94 s | none exposed | 20 651 (skewed by the loop) |
| hf-darija | 11 | **11** | — | — | `HF_TOKEN not configured` |

**Groq mangles quantities.** Same clip, same audio: Gemini produced
`40 كابل`, `8 ديال les panneaux`, `12 پانُو`, `6 مِترو ديال الكابل 3 x 1.5`,
`3ème étage`. Groq produced `mniya dyal panno`, `Pouzina ssimetro`, `3O mietage`,
`ondélique`. Your schema is entirely quantities and locations
(`cables_installes_m`, `goulotte_m`, `prises_*`, `etages`) — an engine that fuses
a digit into the next word gives the extraction chain nothing to extract, and
`has_data()` then returns false on a report that *did* contain data.

**Groq loops too, quietly** — one clip repeats a whole sentence verbatim.

**Confidence does not track correctness.** Groq scored 0.475 on a badly mangled
clip and 0.612 on a repeating one. `exp(avg_logprob)` measures decoder certainty,
not accuracy. Useful to compare Whisper checkpoints against each other; useless as
a correctness proxy, and **not** comparable to wav2vec2's CTC softmax figure.

### A/B: is `stt-vocabulary.md` the cause? — **No. Keep the prompt.**

| | digits | Arabic chars | total chars |
|---|---|---|---|
| WITH prompt (production) | **93** | 6 | **6949** |
| NO prompt | 89 | 3702 | 4639 |

The prompt controls **script** decisively, and does **not** cost digits. Removing
it loses a third of the transcript content and makes repetition worse
(`12 لبرا 12 لبرا 6 لبرا 6 لبرا 70 لبرا 70 لبرا`). Earlier hypothesis that the
prompt destroyed numbers is **refuted** — `mniya` colliding with the prompt's
`miya` was coincidence. Groq's real weakness is transliteration fidelity inside
phrases, which is an acoustic-model problem — exactly what a Darija fine-tune
might fix.

---

## 5b. The vocabulary prompt is fatal to LOCAL Whisper (2026-08-07)

`run_local.py` now runs **without** the prompt by default (`--prompt` opts in).

Measured on one clip, `openai/whisper-large-v3`:

| condition | output |
|---|---|
| prompt ON | `The work, the work, the work, the work…` (degenerate loop, every clip) |
| prompt OFF | `السلام عليكم بالنسبة لخدمة اليوم في نوفيك خدمت انا وعبد الحق…` (clean Darija) |

Both alternative explanations were ruled out first, not assumed away:

- **audio decode**: librosa (audioread fallback for Ogg/Opus) vs ffmpeg → **correlation 1.0000**, same 63.5 s duration, same RMS. Decode is perfect.
- **precision**: fp16 vs fp32 → byte-identical text. Not a half-precision issue.

**Cause.** Groq's API and `transformers` do not treat `prompt` alike. Groq conditions per 30-second segment with its own truncation; `transformers` prepends the raw tokens to the decoder and lets the model *continue* them. Given 180 Latin-script Darija tokens as "preceding transcript", large-v3 keeps writing Latin and collapses. This is the same mechanism as the §5 A/B — survivable through Groq's API, fatal locally.

**Consequence for the comparison.** A prompt on one arm and not the other is a confound. The clean pairing is *both arms unprompted*, and that data already exists: the §5 A/B measured Groq with the prompt off (Arabic script, 89 digits, 4639 chars).

### Three harness bugs found and fixed, in order

| # | bug | how it failed |
|---|---|---|
| 1 | `get_prompt_ids` returned an empty tensor; whisper's `_prepare_segments` does `prompt_ids[0]` unguarded | `IndexError` on every clip — loud |
| 2 | `max_new_tokens=440` vs a **448-token** decoder window shared with the prompt | `ValueError` on every clip — loud |
| 3 | `batch_decode` read the prompt tokens back as the transcript | **silent** — fluent, domain-correct Darija, identical on all 11 clips |

Bug 3 is the one worth remembering. It produced `Kmmalna khamsa dyal bureaux` — exactly what a technician would say — and would have crowned `whisper-large-v3` the winner on a transcript it never generated. Two signals caught it: identical output across different audio, and confidence collapsing to 0.085–0.34 against Groq's 0.48. The confidence number does not track correctness, but a sudden collapse means the harness is lying.

Also fixed: `clean_up_tokenization_spaces` now explicitly `False` — transformers warns it is *destructive for BPE tokenizers* (Whisper is BPE), silently stripping spaces before punctuation and corrupting local transcripts relative to Groq's.

## 5c. First full local run — 9 models × 11 clips (2026-08-07)

`results/local_20260807_181341.csv`. All unprompted (§5b). RTX 3070, fp16.

| model | ok | err | lat s | conf | chars | digits | arab% |
|---|---|---|---|---|---|---|---|
| `openai/whisper-large-v3` | 11 | 0 | 5.7 | 0.582 | 214 | 55 | 79% |
| `openai/whisper-large-v3-turbo` | 11 | 0 | **1.0** | 0.597 | 174 | 30 | 81% |
| `amineouaki/wav2vec2-darija-combined` | 11 | 0 | 4.0 | 0.853 | 439 | 22 | 82% |
| `boumehdi/wav2vec2-…-moroccan-darija` | 11 | 0 | 0.7 | 0.916 | 501 | 0 | 85% |
| `ychafiqui/whisper-medium-darija` | 11 | 0 | 3.7 | 0.843 | 184 | 0 | 83% |
| `ychafiqui/whisper-small-darija` | 11 | 0 | 2.3 | 0.716 | 199 | 0 | 82% |
| `TaloCreations/whisper-darija-finetuned` | 11 | 0 | 2.3 | 0.735 | 198 | 0 | 82% |
| `C-Ilyas/whisper-base-darija` | 11 | 0 | 5.0 | 0.548 | **0** | 0 | — | 
| `KandirResearch/Whisper-Small-Darija` | 0 | 11 | — | — | — | — | `ValueError: generation config is outdated` |

**Confidence is not comparable across families.** wav2vec2's 0.85–0.92 is mean CTC
softmax over emitted frames; Whisper's is `exp(mean token logprob)`. Same 0-1 scale,
different quantity. Compare within a family only.

### The digit column is a red herring

Reading the text (clip `…10.24.37 PM.ogg`, reference content: *Novec, Abdelhak,
40 câbles, 8 panneaux, 12 panneaux*) shows the fine-tunes do capture the numbers —
as Arabic **words**: `تمنية` (8), `طناشر` (12), `ربعين` (40). The extraction chain
reads Darija, so those are recoverable. The digit count measured formatting
convenience, not information loss.

| model | Novec | Abdelhak | 40 | 8 | 12 |
|---|---|---|---|---|---|
| whisper-large-v3 | ✅ | ✅ | ربعين ✅ | ~ | **12** ✅ |
| whisper-large-v3-turbo | ✅ | ✅ | ربعين ✅ | ~ | **12** ✅ |
| ychafiqui/medium-darija | ✅ | ✅ | ربعين ✅ | سمنية ✅ | طناشر ✅ |
| boumehdi/wav2vec2 | ✅ | ✅ | ❌ lost | تمنية ✅ | طناشر ✅ |
| amineouaki/wav2vec2 | ~ | ✅ | ❌ lost | ~ | ~ |
| TaloCreations | ❌ | ~ | ربعين ✅ | ❌ | ❌ |
| ychafiqui/small-darija | ❌ | ~ | ربعين ✅ | ~ | طناشر ✅ |

### The hypothesis did not survive

The two **untuned** OpenAI controls match or beat every Moroccan-Darija fine-tune
on this audio. Without the control in the catalogue the conclusion would have been
"`ychafiqui/medium-darija` is best" with no way to see that generic Whisper equals it.

`whisper-large-v3-turbo` is the standout: same content as full large-v3 at **1.0 s
vs 5.7 s** mean latency — 5.7× faster locally, comparable to Groq's 1.53 s API
latency, with no rate limit and no vendor.

**This ranking is Claude's reading of the Arabic, not a native speaker's.** It needs
confirming by ear before it decides anything.

## 6. Disk waste to reclaim (~15 GB)

`openai__whisper-large-v3` holds the same weights four times: `model.safetensors`
(3.1 G, the only one `transformers` loads), `pytorch_model.bin` (3.1 G),
`model.fp32-*` (6.2 G), `pytorch_model.fp32-*` (6.2 G).

`download_models.py` `IGNORE` has since been extended with `pytorch_model*.bin`,
`*.fp32-*`, `*fp32*.json` — the running batch had already loaded the old list, so
the existing folder still has them. Safe to delete once nothing is writing:

```bash
cd benchmark/models/openai__whisper-large-v3
rm -f pytorch_model*.bin model.fp32-* pytorch_model.fp32-* *fp32*.json
```

---

## 7. Next steps, in order

1. **Resume downloads**, then confirm the two failures repaired (§3).
2. **Reclaim 15 GB** (§6).
3. `` .venv-local/Scripts/python.exe run_local.py --list `` — confirms each folder's
   `config.json` `model_type` resolves to a runner. Anything printing `UNSUPPORTED`
   needs a runner or gets dropped.
4. **Screen fast, then go deep.** 13 models × 11 clips = 143 transcripts to judge
   by ear. Run all models on 2–3 clips first, drop obvious garbage, then run the
   survivors on all 11:
   ```bash
   .venv-local/Scripts/python.exe run_local.py --model <folder>       # one model
   .venv-local/Scripts/python.exe run_local.py                        # all
   ```
5. **Merge the LoRA adapter** — `anaszil__whisper-large-v3-turbo-darija` is
   `adapter_model.safetensors` only. Needs `peft` + `openai__whisper-large-v3-turbo`
   as base. `run_local.py` does **not** handle this yet; it will report a load
   failure, which is recorded as a result rather than crashing the batch.
6. **Qwen3-ASR-1.7B** has no runner in `run_local.py` (`model_type=qwen3_asr`).
   Either add one or drop it.
7. **Re-verify the Gemini fix live** on clip `…5.11.10 PM.ogg` (§4).

### Judging criterion, decided

Not WER. The question is **which engine preserves digits and French technical
borrowings** — `6 mètres`, `3ème étage`, `ondulé`, `panneau de brassage` — because
that is all the Sheet consumes. Read `results/compare_*.md`, which is grouped by
clip precisely for playing the audio alongside the transcripts.

### Still open

- Ground truth was deliberately skipped: `references.csv` is header-only, so
  `run_benchmark.py` still raises and WER/CER/extraction-accuracy are unavailable.
  Reversible at any time — the audio and the harness are both in place.
- Whether a local-GPU winner is deployable at all. Decided *after* the numbers.
- `CLAUDE.md` says "53 tests"; the actual suite is **257**. Doc drift.
