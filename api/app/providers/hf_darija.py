import time

import httpx

from app.config import settings
from app.schemas import TranscriptionInfo

from . import register
from .base import TranscriptionError, TranscriptionProvider

# Benchmark candidate — Whisper fine-tuned on Moroccan Darija via HF Inference API.
# Exact checkpoint is pinned during Sprint 1 benchmark; this default is provisional.
MODEL_ID = "BounharAbdelaziz/Morocco-Darija-STT-large-v1.6"
API_URL = f"https://api-inference.huggingface.co/models/{MODEL_ID}"


@register("hf-darija")
class HFDarijaProvider(TranscriptionProvider):
    """Darija fine-tune via Hugging Face Inference API (free, rate-limited, cold starts)."""

    name = "hf-darija"

    def transcribe(self, audio: bytes, mime_type: str) -> TranscriptionInfo:
        if not settings.hf_token:
            raise TranscriptionError("HF_TOKEN not configured")
        headers = {
            "Authorization": f"Bearer {settings.hf_token}",
            "Content-Type": mime_type,
        }
        start = time.perf_counter()
        try:
            r = httpx.post(API_URL, headers=headers, content=audio, timeout=120)
            r.raise_for_status()
            payload = r.json()
        except Exception as exc:  # noqa: BLE001
            raise TranscriptionError(f"hf-darija: {exc}") from exc
        latency = time.perf_counter() - start
        text = payload.get("text") if isinstance(payload, dict) else None
        if not text:
            raise TranscriptionError(f"hf-darija: unexpected payload {payload!r:.200}")
        return TranscriptionInfo(text=text.strip(), provider=self.name, latency_s=latency)
