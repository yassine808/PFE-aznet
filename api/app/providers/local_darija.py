"""Local Darija STT — thin HTTP client for the GPU sidecar.

The model is `BounharAbdelaziz/Morocco-Darija-STT-large`, the winner of the
2026-08-07 benchmark (see benchmark/STT-BENCHMARK-STATUS.md). It is ~2 B
parameters and needs torch + CUDA, so it does NOT live in this process: the API
is a `python:3.11-slim` image with hash-pinned dependencies and no GPU. Baking
torch in would add ~8 GB to the image and still run on CPU at 60-180 s per
voice note.

Instead the weights stay on the machine that has the card, behind
`benchmark/stt_server.py`, and this adapter is an HTTP call. Consequences worth
knowing:

- **No new dependency.** httpx is already in requirements.txt for the HF path
  this file replaces.
- **The sidecar being down is a normal outcome, not a crash.** It raises
  TranscriptionError like any other engine, so `_transcribe_engine` moves to the
  next entry in the chain. That is the whole point of the chain.
- **Position 2 of `gemini,local,groq`, not last.** It was last while the chain
  was ordered by latency; the 2026-08-08 accuracy review (a native Darija
  speaker judging output against the audio) reordered it, and groq took the
  final slot as the fast always-available floor. So this engine answers
  whenever Gemini alone fails — its evening 503s included — not only when both
  free tiers are exhausted. At ~19 s on a 3070 that is the deliberate price of
  accuracy. Source of truth for the order is `config.stt_chain`, overridden
  live from `app_settings`.
- **Loaded lazily.** The sidecar holds no VRAM until its first call
  (`stt_server._ensure_loaded`), so the first request after a container start
  pays ~235 s of model load on top of transcription — which is why the timeout
  below is 300 s and not merely generous.
"""
import time
from functools import lru_cache

from app.config import settings
from app.schemas import TranscriptionInfo

from . import register
from .base import TranscriptionError, TranscriptionProvider


@lru_cache(maxsize=1)
def _http():
    """One shared transport (keep-alive) instead of httpx.post, which builds a
    fresh client — and a fresh TCP handshake — on every transcription.

    The timeout is generous on purpose: this engine is the last resort, and a
    long voice note on a busy GPU legitimately takes a while. Cutting it off at
    the usual 30 s would turn a slow success into a failure precisely when the
    faster engines have already failed."""
    import httpx

    return httpx.Client(timeout=300)


@register("local")
class LocalDarijaProvider(TranscriptionProvider):
    """Morocco-Darija-STT-large on the GPU sidecar (`STT_LOCAL_URL`)."""

    name = "local"

    def transcribe(self, audio: bytes, mime_type: str) -> TranscriptionInfo:
        if not settings.stt_local_url:
            raise TranscriptionError("STT_LOCAL_URL not configured")
        start = time.perf_counter()
        try:
            r = _http().post(
                settings.stt_local_url.rstrip("/") + "/transcribe",
                files={"audio": ("note", audio, mime_type)},
            )
            r.raise_for_status()
            payload = r.json()
        except Exception as exc:  # noqa: BLE001
            raise TranscriptionError(f"local: {exc}") from exc
        latency = time.perf_counter() - start
        text = (payload.get("text") or "").strip()
        if not text:
            raise TranscriptionError("local: empty transcription")
        # Whisper's own avg_logprob, forwarded by the sidecar and already
        # exponentiated there so it matches groq_whisper._confidence_from_segments.
        # None when the model exposed nothing — never a fabricated score.
        confidence = payload.get("confidence")
        return TranscriptionInfo(
            text=text,
            provider=self.name,
            latency_s=latency,
            confidence=float(confidence) if confidence is not None else None,
        )
