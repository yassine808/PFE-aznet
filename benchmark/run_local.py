"""Run the locally downloaded Darija STT models over dataset/audio/ on the GPU.

Companion to run_compare.py: same columns, same results/ folder, so a local CSV
and an API CSV can be read side by side. No ground truth, no score -- it reports
what each checkpoint heard, how long it took, and the confidence it exposes.

Run with the ISOLATED venv, never api/.venv:
    .venv-local/Scripts/python.exe run_local.py --list
    .venv-local/Scripts/python.exe run_local.py --model BounharAbdelaziz__Morocco-Darija-STT-large
    .venv-local/Scripts/python.exe run_local.py            # every downloaded model

Confidence is computed to match app/providers/groq_whisper._confidence_from_segments:
exp(mean token log-probability), clamped to 0-1. Same formula on both sides, so the
number is comparable to Groq's -- a different formula would make the column a lie.
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

BENCH_DIR = Path(__file__).resolve().parent
MODELS_DIR = BENCH_DIR / "models"
AUDIO_DIR = BENCH_DIR / "dataset" / "audio"
RESULTS_DIR = BENCH_DIR / "results"
PROMPT_FILE = BENCH_DIR.parent / "api" / "app" / "prompts" / "stt-vocabulary.md"

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

COLUMNS = ["file", "provider", "latency_s", "confidence", "chars", "transcript", "error"]
AUDIO_EXT = {".ogg", ".opus", ".oga", ".mp3", ".wav", ".m4a"}
SR = 16_000  # every model here was trained at 16 kHz

# Whisper's decoder window: prompt + special tokens + transcript must all fit.
DECODER_CONTEXT = 448
SPECIAL_TOKEN_SLACK = 8   # <|startoftranscript|>, language, task, timestamps, EOT
# Leaves ~250 tokens of transcript, well above the longest real report seen
# (1485 chars ~ 500 tokens is the Gemini worst case; Groq's clips run far shorter).
PROMPT_TOKEN_BUDGET = 180


def load_audio(path: Path):
    """Decode to a 16 kHz mono float32 array. WhatsApp clips are Ogg/Opus, which
    older libsndfile builds cannot read -- ffmpeg is the fallback, not the default,
    because shelling out per clip is slower and needs ffmpeg on PATH."""
    import numpy as np

    try:
        import librosa

        audio, _ = librosa.load(str(path), sr=SR, mono=True)
        return audio.astype("float32")
    except Exception:  # noqa: BLE001 — fall through to ffmpeg
        pass
    import subprocess

    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-i", str(path), "-f", "f32le", "-ac", "1",
         "-ar", str(SR), "-"],
        capture_output=True, check=True,
    )
    return np.frombuffer(proc.stdout, dtype="float32").copy()


def vocabulary_prompt() -> Optional[str]:
    """The same chantier vocabulary Groq gets, loaded through the API's own
    prompt_loader so it is byte-identical -- a local model fed the raw file
    would also receive the markdown title and the long HTML rationale comment,
    which is not what the production path sends and would invalidate the
    comparison. (It also produced an empty token tensor and crashed
    transformers' whisper generate at generation_whisper.py:1122.)

    prompt_loader is stdlib-only (functools, pathlib), so importing it from
    this 3.11 venv pulls in nothing from api/.venv."""
    api_dir = str(BENCH_DIR.parent / "api")
    if api_dir not in sys.path:
        sys.path.insert(0, api_dir)
    try:
        from app import prompt_loader

        return prompt_loader.load(prompt_loader.STT_VOCABULARY, with_soul=False) or None
    except Exception as exc:  # noqa: BLE001 — no prompt is a valid run, a wrong one is not
        print(f"[warn] vocabulary prompt unavailable ({exc}); running without it")
        return None


def _confidence(scores_mean_logprob: Optional[float]) -> Optional[float]:
    import math

    if scores_mean_logprob is None:
        return None
    return max(0.0, min(1.0, math.exp(scores_mean_logprob)))


class WhisperRunner:
    """transformers seq2seq Whisper. Accepts the vocabulary prompt; token
    log-probs come from compute_transition_scores, the closest analogue to the
    avg_logprob Groq returns per segment."""

    family = "whisper"

    def __init__(self, path: Path, device: str, dtype, use_prompt: bool = False):
        import torch
        from transformers import WhisperForConditionalGeneration, WhisperProcessor

        self.torch = torch
        self.processor = WhisperProcessor.from_pretrained(str(path))
        self.model = WhisperForConditionalGeneration.from_pretrained(
            str(path), torch_dtype=dtype
        ).to(device).eval()
        self.device = device
        self.dtype = dtype
        # Default OFF, and measured rather than assumed (2026-08-07): Groq's API
        # and transformers do not treat `prompt` alike. Groq conditions per
        # 30 s segment with its own truncation; transformers prepends the raw
        # tokens and lets the model CONTINUE them. Fed 180 Latin-script Darija
        # tokens, whisper-large-v3 collapsed into "The work, the work, the
        # work..." on every clip. The same audio with no prompt transcribed
        # cleanly in Arabic script. Audio decode was ruled out first: librosa
        # and ffmpeg correlate at 1.0000, and fp16/fp32 agree exactly.
        prompt = vocabulary_prompt() if use_prompt else None
        # A prompt longer than half the 448-token context starves the decoder of
        # room for the actual transcript, so it is truncated rather than dropped.
        self.prompt_ids = None
        if prompt:
            try:
                ids = self.processor.get_prompt_ids(prompt, return_tensors="pt")
                # Whisper's decoder window is DECODER_CONTEXT tokens for prompt +
                # special tokens + transcript combined. Whisper reads only the TAIL
                # of a prompt anyway (it is treated as preceding transcript), so
                # trimming from the left keeps the domain vocabulary closest to the
                # audio and drops the oldest words instead of the newest.
                if ids.numel() > PROMPT_TOKEN_BUDGET:
                    ids = ids[-PROMPT_TOKEN_BUDGET:]
                # An empty tensor is not "no prompt" to transformers: whisper's
                # _prepare_segments does prompt_ids[0] unguarded and raises
                # IndexError on every clip. Treat empty as absent here instead.
                self.prompt_ids = ids.to(device) if ids.numel() else None
            except Exception:  # noqa: BLE001 — some fine-tunes ship no prompt tokens
                self.prompt_ids = None
            if self.prompt_ids is None:
                print("  [warn] no usable prompt tokens — running without vocabulary bias")
            else:
                print(f"  prompt: {self.prompt_ids.numel()} tokens")
        # Budget the rest of the window for the transcript. Hardcoding 440 left
        # 8 tokens for the prompt and made large-v3 raise ValueError on every clip.
        used = self.prompt_ids.numel() if self.prompt_ids is not None else 0
        self.max_new_tokens = DECODER_CONTEXT - used - SPECIAL_TOKEN_SLACK

    def transcribe(self, audio) -> Tuple[str, Optional[float]]:
        torch = self.torch
        feats = self.processor(
            audio, sampling_rate=SR, return_tensors="pt"
        ).input_features.to(self.device, self.dtype)
        kwargs = dict(
            # Darija has no Whisper language tag; 'ar' beats autodetect, same
            # choice as the Groq adapter.
            language="ar",
            task="transcribe",
            max_new_tokens=self.max_new_tokens,
            # Without this the model loops: gemini produced 222k characters for
            # one 84 KB clip in the API run. no_repeat_ngram_size is the guard a
            # generateContent call does not have.
            no_repeat_ngram_size=4,
            return_dict_in_generate=True,
            output_scores=True,
        )
        if self.prompt_ids is not None:
            kwargs["prompt_ids"] = self.prompt_ids
        with torch.no_grad():
            out = self.model.generate(feats, **kwargs)
        # generate() returns the prompt tokens PREPENDED to the transcript, so
        # decoding the whole sequence hands back the chantier vocabulary itself.
        # It looked plausible -- every clip returned the same fluent Darija --
        # which is exactly why it has to be sliced off, not eyeballed.
        seq = out.sequences
        if self.prompt_ids is not None:
            seq = seq[:, self.prompt_ids.numel():]
        text = self.processor.batch_decode(
            seq, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0].strip()
        mean_lp = None
        try:
            trans = self.model.compute_transition_scores(
                out.sequences, out.scores, normalize_logits=True
            )[0]
            valid = trans[torch.isfinite(trans)]
            if len(valid):
                mean_lp = float(valid.mean())
        except Exception:  # noqa: BLE001 — no scores is None, never a fake number
            mean_lp = None
        return text, _confidence(mean_lp)


class Wav2Vec2Runner:
    """CTC. No prompt, no punctuation. Confidence is the mean top-1 softmax
    probability over emitted frames -- a different quantity from Whisper's
    avg_logprob, so the two columns are NOT directly comparable."""

    family = "wav2vec2"

    def __init__(self, path: Path, device: str, dtype, use_prompt: bool = False):
        # use_prompt accepted and ignored: CTC has no prompt mechanism at all.
        import torch
        from transformers import AutoModelForCTC, AutoProcessor

        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(str(path))
        self.model = AutoModelForCTC.from_pretrained(str(path)).to(device).eval()
        self.device = device

    def transcribe(self, audio) -> Tuple[str, Optional[float]]:
        torch = self.torch
        inputs = self.processor(audio, sampling_rate=SR, return_tensors="pt")
        values = inputs.input_values.to(self.device)
        with torch.no_grad():
            logits = self.model(values).logits
        probs = torch.softmax(logits, dim=-1)
        best, ids = probs.max(dim=-1)
        blank = getattr(self.model.config, "pad_token_id", 0)
        emitted = best[ids != blank]
        conf = float(emitted.mean()) if len(emitted) else None
        text = self.processor.batch_decode(ids)[0].strip()
        return text, conf


RUNNERS = {"whisper": WhisperRunner, "wav2vec2": Wav2Vec2Runner}


def detect_family(path: Path) -> Optional[str]:
    """Read config.json rather than the folder name: the catalogue's family label
    is a human note, the config is what transformers will actually instantiate."""
    cfg = path / "config.json"
    if not cfg.exists():
        return None
    try:
        model_type = json.loads(cfg.read_text(encoding="utf-8")).get("model_type", "")
    except Exception:  # noqa: BLE001
        return None
    return model_type if model_type in RUNNERS else None


def discover() -> List[Tuple[Path, Optional[str]]]:
    if not MODELS_DIR.exists():
        raise FileNotFoundError(f"{MODELS_DIR} not found — run download_models.py first")
    # skip dot-dirs: tooling drops .ruff_cache / .cache next to the checkpoints
    return sorted(((p, detect_family(p)) for p in MODELS_DIR.iterdir()
                   if p.is_dir() and not p.name.startswith(".")),
                  key=lambda t: t[0].name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="show downloaded models, run nothing")
    parser.add_argument("--model", default=None, help="folder name under models/ (repeatable via comma)")
    parser.add_argument("--cpu", action="store_true", help="force CPU (default: cuda when available)")
    parser.add_argument("--prompt", action="store_true",
                        help="feed stt-vocabulary.md as Whisper's prompt. OFF by default: "
                             "it makes local Whisper loop (see WhisperRunner.__init__)")
    args = parser.parse_args()

    found = discover()
    if args.list:
        for path, family in found:
            print(f"{(family or 'UNSUPPORTED'):<12} {path.name}")
        print(f"\n{len(found)} folders in {MODELS_DIR}")
        return

    import torch

    device = "cpu" if args.cpu or not torch.cuda.is_available() else "cuda"
    dtype = torch.float16 if device == "cuda" else torch.float32
    print(f"device: {device}"
          + (f" ({torch.cuda.get_device_name(0)})" if device == "cuda" else ""))

    targets = found
    if args.model:
        wanted = set(args.model.split(","))
        targets = [t for t in found if t[0].name in wanted]
        if not targets:
            raise SystemExit(f"no match for {sorted(wanted)}; try --list")

    clips = sorted(p for p in AUDIO_DIR.iterdir() if p.suffix.lower() in AUDIO_EXT)
    print(f"{len(clips)} clips × {len(targets)} models\n")
    decoded = {c.name: load_audio(c) for c in clips}

    results = []
    for path, family in targets:
        if family is None:
            print(f"-- {path.name}: unsupported (no config.json / unknown model_type), skipped")
            continue
        print(f"\n=== {path.name}  [{family}] ===")
        try:
            runner = RUNNERS[family](path, device, dtype, use_prompt=args.prompt)
        except Exception as exc:  # a model that will not load is a result  # noqa: BLE001
            print(f"  !! load failed: {type(exc).__name__}: {exc}")
            for clip in clips:
                results.append({"file": clip.name, "provider": path.name,
                                "error": f"load: {type(exc).__name__}: {exc}",
                                "latency_s": None, "confidence": None,
                                "chars": None, "transcript": None})
            continue
        for clip in clips:
            record = dict.fromkeys(COLUMNS)
            record.update({"file": clip.name, "provider": path.name})
            try:
                start = time.perf_counter()
                text, conf = runner.transcribe(decoded[clip.name])
                record["latency_s"] = round(time.perf_counter() - start, 2)
                record["transcript"] = text
                record["chars"] = len(text)
                record["confidence"] = round(conf, 4) if conf is not None else None
            except Exception as exc:  # noqa: BLE001
                record["error"] = f"{type(exc).__name__}: {exc}"
            results.append(record)
            if record["error"]:
                print(f"  {clip.name[:34]:<36} !! {record['error'][:80]}")
            else:
                c = "—" if record["confidence"] is None else f"{record['confidence']:.3f}"
                print(f"  {clip.name[:34]:<36} {record['latency_s']:>6.2f}s  conf {c:>6}  "
                      f"{(record['transcript'] or '')[:50]}")
        del runner
        if device == "cuda":
            torch.cuda.empty_cache()  # 8 GB card: free before the next checkpoint loads

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    out = RESULTS_DIR / f"local_{stamp}.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(results)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
