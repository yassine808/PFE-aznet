import io
import time

from app.config import settings
from app.schemas import TranscriptionInfo

from . import register
from .base import TranscriptionError, TranscriptionProvider


@register("groq")
class GroqWhisperProvider(TranscriptionProvider):
    """Whisper-large-v3 served by Groq (free tier)."""

    name = "groq"

    def transcribe(self, audio: bytes, mime_type: str) -> TranscriptionInfo:
        if not settings.groq_api_key:
            raise TranscriptionError("GROQ_API_KEY not configured")
        from groq import Groq  # lazy: keeps unit tests dependency-free

        client = Groq(api_key=settings.groq_api_key)
        ext = "ogg" if "ogg" in mime_type else mime_type.split("/")[-1]
        buf = io.BytesIO(audio)
        start = time.perf_counter()
        try:
            result = client.audio.transcriptions.create(
                file=(f"note.{ext}", buf),
                model=settings.groq_whisper_model,
                # Darija has no ISO tag Whisper knows; 'ar' beats autodetect
                language="ar",
                response_format="text",
            )
        except Exception as exc:  # noqa: BLE001 — surface as domain error
            raise TranscriptionError(f"groq: {exc}") from exc
        latency = time.perf_counter() - start
        text = result if isinstance(result, str) else getattr(result, "text", str(result))
        return TranscriptionInfo(text=text.strip(), provider=self.name, latency_s=latency)
