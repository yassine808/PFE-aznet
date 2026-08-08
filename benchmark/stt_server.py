"""GPU sidecar — serves BounharAbdelaziz/Morocco-Darija-STT-large over HTTP.

Why a separate process instead of an adapter inside the API:

The API ships as a `python:3.11-slim` image with hash-pinned dependencies and
no GPU. Putting torch + this 2 B-parameter model inside it would add ~8 GB to
the image and still run on CPU at 60-180 s per voice note. The weights stay on
the machine that has the card; `api/app/providers/local_darija.py` is a thin
HTTP client. If this process is down the API's STT chain simply falls through
to the next engine — that is what the chain is for.

The model is loaded ONCE at startup, not per request: ~4 GB into VRAM and
several seconds of load time that must not be paid per voice note.

Run it with the isolated venv, from benchmark/:

    .venv-local/Scripts/python.exe stt_server.py
    .venv-local/Scripts/python.exe stt_server.py --port 8100 --cpu

Then point the API at it:  STT_LOCAL_URL=http://127.0.0.1:8100
"""
import argparse
import io
import sys
import time
from pathlib import Path

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


def build_app(device: str, dtype):
    from fastapi import FastAPI, File, HTTPException, UploadFile

    app = FastAPI(title="aznet local STT", version="1.0")

    @app.on_event("startup")
    def _load() -> None:
        global _runner, _loaded_at
        if not MODEL_DIR.exists():
            raise RuntimeError(
                f"{MODEL_DIR} missing — run download_models.py (the repo is gated: "
                "accept its licence on huggingface.co and set HF_TOKEN)"
            )
        start = time.perf_counter()
        # use_prompt=False: the chantier vocabulary prompt makes local Whisper
        # collapse into a repetition loop. Measured 2026-08-07, see
        # STT-BENCHMARK-STATUS.md §5b -- audio decode and fp16 were ruled out first.
        _runner = WhisperRunner(MODEL_DIR, device, dtype, use_prompt=False)
        _loaded_at = time.perf_counter() - start
        print(f"[stt] {MODEL_DIR.name} loaded on {device} in {_loaded_at:.1f}s")

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok" if _runner is not None else "loading",
            "model": MODEL_DIR.name,
            "device": device,
            "load_seconds": round(_loaded_at, 1) if _loaded_at else None,
        }

    @app.post("/transcribe")
    async def transcribe(audio: UploadFile = File(...)) -> dict:
        if _runner is None:
            raise HTTPException(503, "model still loading")
        blob = await audio.read()
        if not blob:
            raise HTTPException(422, "empty audio")
        # load_audio takes a path (librosa/ffmpeg both want one), so the upload
        # is spooled to a temp file rather than decoded from memory.
        import tempfile

        suffix = Path(audio.filename or "note.ogg").suffix or ".ogg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(blob)
            tmp_path = Path(tmp.name)
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
