import time

from app.config import settings
from app.schemas import TranscriptionInfo

from . import register
from .base import TranscriptionError, TranscriptionProvider

_PROMPT = (
    "Transcris fidèlement ce message vocal d'un technicien de câblage marocain. "
    "Le locuteur parle en darija (arabe marocain) mélangée de français technique "
    "(goulotte, câble, panneau de brassage, bureau, étage, mètres). "
    "Rends le texte exactement comme prononcé, en graphie arabe pour la darija "
    "et en latin pour les mots français. Ne traduis pas, ne résume pas. "
    "Si un passage est inaudible, transcris ce que tu entends et laisse la lacune : "
    "n'invente JAMAIS un mot pour compléter. Ne corrige pas la grammaire du locuteur "
    "et ne commente pas l'audio : uniquement le texte prononcé."
)


@register("gemini")
class GeminiAudioProvider(TranscriptionProvider):
    """Gemini native audio input (AI Studio free tier, `gemini_model` = flash-lite-latest)."""

    name = "gemini"

    def transcribe(self, audio: bytes, mime_type: str) -> TranscriptionInfo:
        if not settings.gemini_api_key:
            raise TranscriptionError("GEMINI_API_KEY not configured")
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        start = time.perf_counter()
        try:
            resp = client.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    _PROMPT,
                    types.Part.from_bytes(data=audio, mime_type=mime_type),
                ],
            )
        except Exception as exc:  # noqa: BLE001
            raise TranscriptionError(f"gemini: {exc}") from exc
        latency = time.perf_counter() - start
        if not resp.text:
            raise TranscriptionError("gemini: empty transcription")
        # Gemini's generateContent response carries no per-token/segment
        # logprob for audio transcription -> confidence stays None (schema
        # default), no fabricated score.
        return TranscriptionInfo(text=resp.text.strip(), provider=self.name, latency_s=latency)
