"""GPU sidecar — serves BounharAbdelaziz/Morocco-Darija-STT-large over HTTP.

Why a separate process instead of an adapter inside the API:

The API ships as a `python:3.11-slim` image with hash-pinned dependencies and
no GPU. Putting torch + this 2 B-parameter model inside it would add ~8 GB to
the image and still run on CPU at 60-180 s per voice note. The weights stay on
the machine that has the card; `api/app/providers/local_darija.py` is a thin
HTTP client. If this process is down the API's STT chain simply falls through
to the next engine — that is what the chain is for.

The model is loaded ONCE — ~4 GB into VRAM and 280-394 s of load time that must
not be paid per voice note. Two shapes, chosen by STT_LOCAL_PRELOAD:

  set    → load at startup, in a background thread. ~4 GB of the card is held
           around the clock; the fallback is present the moment it is needed.
  unset  → load lazily, on the first /transcribe. Costs nothing on a quiet day,
           but the first caller pays the whole load inside their own request —
           and that caller is by definition someone Gemini already failed.

Lazy was the original default, and it was measured wrong: the client budget was
300 s while the load alone took 280 s, so the first call after every restart
failed. Failing warmed the model, so the retry succeeded and the whole thing
read as "slow the first time". The budget is now 420 s (local_darija.py) and
compose sets STT_LOCAL_PRELOAD=1, so neither half depends on the other.

Run it with the isolated venv, from benchmark/:

    .venv-local/Scripts/python.exe stt_server.py
    .venv-local/Scripts/python.exe stt_server.py --port 8100 --cpu

Or as a container, which is what `docker compose up -d` starts (see the
`stt-local` service and benchmark/Dockerfile). Weights are bind-mounted from
benchmark/models/ rather than baked in: the checkpoint is 5.8 GB, one shard of
it 4.7 GB, which exceeds GitHub's 2 GB Git-LFS per-file ceiling — so the
catalogue that reproduces them (download_models.py) is versioned and the
weights themselves stay on the machine that has the card.

Then point the API at it:  STT_LOCAL_URL=http://127.0.0.1:8100
(inside compose: http://stt-local:8100)
"""
import argparse
import io
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

BENCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_DIR))

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

# Reuse the benchmarked decode + generate path verbatim. Sharing the code is the
# point: the sidecar must behave exactly like the run that chose this model, or
# the benchmark stops describing production.
from run_local import MODELS_DIR, SR, WhisperRunner, load_audio  # noqa: E402

MODEL_DIR = MODELS_DIR / "BounharAbdelaziz__Morocco-Darija-STT-large"

_runner = None
_loaded_at = None
_load_error = None
_load_started = False
# Serialises the lazy load. Two voice notes arriving together would otherwise
# both start a ~4 GB load and OOM an 8 GB card.
_load_lock = threading.Lock()


def _warm(runner) -> None:
    """Warm the CUDA kernels on silence, before anyone is waiting.

    Measured: the first real request took 46.1 s and every one after it 5.9 s,
    because the first generate() pays the kernel autotune/JIT cost. A failed
    warm-up is not fatal — it only costs the first technician those seconds.
    """
    try:
        import numpy as np

        runner.transcribe(np.zeros(SR, dtype="float32"))
    except Exception as exc:  # noqa: BLE001
        print(f"[stt] warm-up skipped: {type(exc).__name__}: {exc}", flush=True)


def load_blocking(device: str, dtype) -> None:
    """Load the checkpoint and publish it, or record why it could not be loaded."""
    global _runner, _loaded_at, _load_error
    if not MODEL_DIR.exists():
        _load_error = (
            f"{MODEL_DIR} missing — run download_models.py (the repo is gated: "
            "accept its licence on huggingface.co and set HF_TOKEN)"
        )
        print(f"[stt] ERROR {_load_error}")
        return
    start = time.perf_counter()
    try:
        # use_prompt=False: the chantier vocabulary prompt makes local Whisper
        # collapse into a repetition loop. Measured 2026-08-07, see
        # STT-BENCHMARK-STATUS.md §5b -- audio decode and fp16 were ruled out first.
        # Assigned to _runner only after the warm-up below, so /health does
        # not report "ok" while the first request would still pay 46 s.
        runner = WhisperRunner(MODEL_DIR, device, dtype, use_prompt=False)
    except Exception as exc:  # noqa: BLE001 — a dead model is a state to report
        _load_error = f"{type(exc).__name__}: {exc}"
        print(f"[stt] ERROR loading model: {_load_error}", flush=True)
        return
    _warm(runner)
    _runner = runner
    _loaded_at = time.perf_counter() - start
    print(f"[stt] {MODEL_DIR.name} ready on {device} in {_loaded_at:.1f}s "
          f"(warm)", flush=True)


def _health_status() -> str:
    """Four states, not two. A model that failed to load is neither ready nor
    still coming, and reporting it as "loading" forever would hide the reason
    from the dashboard. Since the load became lazy there is also a fourth,
    normal-and-healthy state: nothing loaded because nothing has asked yet.
    Calling that "loading" would show a permanent false alarm on a container
    that is behaving exactly as designed."""
    if _runner is not None:
        return "ok"
    if _load_error:
        return "error"
    return "loading" if _load_started else "idle"


def _spool(blob: bytes, filename: Optional[str]) -> Path:
    """The upload on disk: load_audio takes a path, librosa and ffmpeg both do."""
    import tempfile

    suffix = Path(filename or "note.ogg").suffix or ".ogg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(blob)
        return Path(tmp.name)


def build_app(device: str, dtype):
    from typing import Annotated

    from fastapi import FastAPI, File, HTTPException, UploadFile

    app = FastAPI(title="aznet local STT", version="1.0")

    def _ensure_loaded() -> None:
        """Load on the first /transcribe, not at startup.

        This engine sits at position 2 of the `gemini,local,groq` chain, so it
        answers only when Gemini fails — which can be a whole quiet day.
        Loading at startup held ~4 GB of an 8 GB card permanently to serve that.
        Lazy, the container costs nothing until it is actually called.

        The first caller pays the load (measured 235.6 s) inside its own
        request. That is affordable because `local_darija._http()` allows 300 s
        precisely for this engine, and because it is paid once per container
        lifetime, not once per note. Callers after it pay nothing.

        The lock — not a bare `if` — because two voice notes arriving together
        would otherwise both start a 4 GB load and OOM the card.
        """
        global _load_started
        if _runner is not None or _load_error:
            return
        with _load_lock:
            if _runner is not None or _load_error:
                return
            _load_started = True
            print(f"[stt] first call — loading {MODEL_DIR.name} on {device}, "
                  "this takes minutes", flush=True)
            load_blocking(device, dtype)

    # STT_LOCAL_PRELOAD=1 loads at startup instead of on the first call.
    # The lazy default was chosen before we knew the first call ALWAYS failed:
    # the load is paid inside that request (measured 280-394 s on the 3070) and
    # it lands on the one caller who deserves it least — the one for whom both
    # cloud engines already failed. Preloading trades ~4 GB of idle VRAM for a
    # fallback that is actually present when it is needed. Same lock, same
    # function, so a /transcribe arriving mid-load waits rather than starting a
    # second 4 GB load.
    if os.getenv("STT_LOCAL_PRELOAD", "").strip().lower() in ("1", "true", "yes"):
        print("[stt] STT_LOCAL_PRELOAD set — loading at startup", flush=True)
        threading.Thread(target=_ensure_loaded, daemon=True).start()

    @app.get("/health")
    def health() -> dict:
        return {
            "status": _health_status(),
            "model": MODEL_DIR.name,
            "device": device,
            "load_seconds": round(_loaded_at, 1) if _loaded_at else None,
            "error": _load_error,
        }

    @app.post(
        "/transcribe",
        responses={
            422: {"description": "Empty audio"},
            502: {"description": "Transcription failed"},
            503: {"description": "Model still loading"},
        },
    )
    # A sync endpoint on purpose: FastAPI runs it in the threadpool, so the
    # blocking parts — spooling the upload and the GPU generate() itself —
    # never sit on the event loop. As `async def` a single 6 s transcription
    # froze /health for every other caller.
    def transcribe(audio: Annotated[UploadFile, File()]) -> dict:
        _ensure_loaded()
        if _runner is None:
            # Only reachable when the load itself failed (weights missing, no
            # VRAM). 503 keeps the API's chain semantics: this engine is down,
            # not this request malformed.
            raise HTTPException(503, _load_error or "model unavailable")
        blob = audio.file.read()
        if not blob:
            raise HTTPException(422, "empty audio")
        tmp_path = _spool(blob, audio.filename)
        try:
            start = time.perf_counter()
            text, confidence = _runner.transcribe(load_audio(tmp_path))
            latency = time.perf_counter() - start
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"transcription failed: {exc}") from exc
        finally:
            tmp_path.unlink(missing_ok=True)
        # confidence is already exp(mean avg_logprob), the same quantity Groq
        # reports -- so the API can store it in the same field with no rescaling.
        return {
            "text": text,
            "confidence": confidence,
            "latency_s": round(latency, 2),
            "model": MODEL_DIR.name,
        }

    return app


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1",
                   help="127.0.0.1 by default: this speaks to the API on the same "
                        "machine and has no auth of its own")
    p.add_argument("--port", type=int, default=8100)
    p.add_argument("--cpu", action="store_true", help="force CPU (default: cuda when available)")
    args = p.parse_args()

    import torch
    import uvicorn

    device = "cpu" if args.cpu or not torch.cuda.is_available() else "cuda"
    dtype = torch.float16 if device == "cuda" else torch.float32
    print(f"[stt] device={device}"
          + (f" ({torch.cuda.get_device_name(0)})" if device == "cuda" else ""))
    uvicorn.run(build_app(device, dtype), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
