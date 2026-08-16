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
  pays the model load ON TOP OF transcription. Measured 2026-08-16 on the 3070:
  `load_seconds = 280.4`, then ~32 s to transcribe. The old 300 s timeout
  covered the load and left nothing for the work, so **the first call after a
  restart always failed** — and failing warmed the model, so the retry
  succeeded. From the outside that reads as "slow the first time", which is why
  it went unnoticed; in reality this engine had never once answered its first
  request. The budget below is now load + transcribe + headroom.
"""
import time
from functools import lru_cache

from app.config import settings
from app.schemas import TranscriptionInfo

from . import register
from .base import TranscriptionError, TranscriptionProvider

# Load + transcribe + headroom. See `_http` for the measurement behind it.
COLD_START_BUDGET_S = 420


@lru_cache(maxsize=1)
def _http():
    """One shared transport (keep-alive) instead of httpx.post, which builds a
    fresh client — and a fresh TCP handshake — on every transcription.

    The timeout is generous on purpose: this engine is the last resort, and a
    long voice note on a busy GPU legitimately takes a while. Cutting it off at
    the usual 30 s would turn a slow success into a failure precisely when the
    faster engines have already failed.

    420 s = 280 s measured cold start + ~32 s transcription + headroom for a
    longer note and a busier card. Sized on measurement, not taste: at 300 s the
    arithmetic did not close and every first call timed out. Anything in front
    of this — nginx `proxy_read_timeout` in `Dashboard/nginx.conf` — must stay
    ABOVE it, or the proxy silently caps a budget this client thinks it owns.
    """
    import httpx

    return httpx.Client(timeout=COLD_START_BUDGET_S)


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
