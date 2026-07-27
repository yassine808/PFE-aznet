import io
import math
import time

from app import prompt_loader
from app.config import settings
from app.schemas import TranscriptionInfo

from . import register
from .base import TranscriptionError, TranscriptionProvider


def _confidence_from_segments(segments) -> "float | None":
    """Whisper doesn't expose a direct confidence score; avg_logprob per
    segment is the closest proxy (log-probability the model assigned its
    own output). exp(avg_logprob) rescales it into a rough 0-1 confidence.
    Returns None if no segments are available (nothing to derive from).
    """
    if not segments:
        return None
    logprobs = []
    for seg in segments:
        val = seg.get("avg_logprob") if isinstance(seg, dict) else getattr(seg, "avg_logprob", None)
        if val is not None:
            logprobs.append(val)
    if not logprobs:
        return None
    avg = sum(logprobs) / len(logprobs)
    return max(0.0, min(1.0, math.exp(avg)))


@register("groq")
class GroqWhisperProvider(TranscriptionProvider):
    """Whisper-large-v3 served by Groq (free tier)."""

    name = "groq"

    def transcribe(self, audio: bytes, mime_type: str) -> TranscriptionInfo:
        if not settings.groq_api_key:
            raise TranscriptionError("GROQ_API_KEY not configured")
        from groq import Groq  # lazy: keeps unit tests dependency-free

        client = Groq(api_key=settings.groq_api_key)
        # Groq gates uploads on filename extension before decoding the bytes,
        # so the name must land in its accepted set. Telegram voice notes are
        # ogg/opus ("audio/ogg" or ".oga"); n8n/curl may send octet-stream.
        accepted = {"flac", "mp3", "mp4", "mpeg", "mpga", "m4a", "ogg", "opus", "wav", "webm"}
        alias = {"oga": "ogg", "x-wav": "wav", "wave": "wav", "x-m4a": "m4a"}
        raw = mime_type.split("/")[-1].split(";")[0].strip().lower()
        ext = alias.get(raw, raw)
        if ext not in accepted:
            ext = "ogg"  # pipeline default (voice notes); Groq still rejects undecodable bytes
        buf = io.BytesIO(audio)
        start = time.perf_counter()
        try:
            result = client.audio.transcriptions.create(
                file=(f"note.{ext}", buf),
                model=settings.groq_whisper_model,
                # Darija has no ISO tag Whisper knows; 'ar' beats autodetect
                language="ar",
                # Whisper reads `prompt` as the transcript of the audio just
                # before this clip, not as instructions — so the file is a
                # sample of chantier vocabulary and code-switching, which biases
                # decoding towards "goulotte"/"brassage" instead of the
                # phonetic soup a generic Whisper produces. See
                # app/prompts/stt-vocabulary.md.
                prompt=prompt_loader.load(prompt_loader.STT_VOCABULARY, with_soul=False),
                # verbose_json (vs plain "text") also returns per-segment
                # avg_logprob, which we use to derive a confidence score.
                response_format="verbose_json",
            )
        except Exception as exc:  # noqa: BLE001 — surface as domain error
            raise TranscriptionError(f"groq: {exc}") from exc
        latency = time.perf_counter() - start
        text = result if isinstance(result, str) else getattr(result, "text", str(result))
        segments = result.get("segments") if isinstance(result, dict) else getattr(result, "segments", None)
        confidence = _confidence_from_segments(segments or [])
        return TranscriptionInfo(
            text=text.strip(), provider=self.name, latency_s=latency, confidence=confidence
        )
