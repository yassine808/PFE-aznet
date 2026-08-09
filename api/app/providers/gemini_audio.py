import time
from functools import lru_cache

from app.config import settings
from app.schemas import TranscriptionInfo

from . import register
from .base import TranscriptionError, TranscriptionProvider


@lru_cache(maxsize=1)
def _client():
    """One SDK client per process (keep-alive pool; see groq_whisper._client).
    Lazy import keeps unit tests dependency-free; the API-key check stays
    per-call in transcribe()."""
    from google import genai  # lazy: keeps unit tests dependency-free

    return genai.Client(api_key=settings.gemini_api_key)

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


# A 40-second voice note transcribes to ~1.5k characters; the longest real
# report in the 2026-08-07 benchmark was 1485. 4096 output tokens is roughly
# 4x the worst legitimate case -- generous enough never to truncate a technician,
# tight enough that a degenerate loop cannot run for two minutes.
_MAX_OUTPUT_TOKENS = 4096

# generateContent has no no_repeat_ngram guard, so it can loop until it hits the
# token cap. On 2026-08-07 one 84 KB clip produced 222_797 characters in 129 s,
# the tail repeating "a l'hopital de la ville de Rabat" forever. The cap bounds
# the damage; this detector turns what is left into a loud failure instead of
# 200k characters of garbage flowing into the extraction chain.
_LOOP_WINDOW = 60      # characters of tail to test
_LOOP_REPEATS = 4      # consecutive identical repeats = degenerate


def _is_degenerate(text: str) -> bool:
    """True when the tail is the same short phrase repeated back to back."""
    if len(text) < _LOOP_WINDOW * _LOOP_REPEATS:
        return False
    tail = text[-_LOOP_WINDOW * _LOOP_REPEATS:]
    for size in range(8, _LOOP_WINDOW + 1):
        chunk = tail[-size:]
        if chunk * _LOOP_REPEATS == tail[-size * _LOOP_REPEATS:]:
            return True
    return False


@register("gemini")
class GeminiAudioProvider(TranscriptionProvider):
    """Gemini native audio input (AI Studio free tier, `gemini_model` = flash-lite-latest)."""

    name = "gemini"

    def transcribe(self, audio: bytes, mime_type: str) -> TranscriptionInfo:
        if not settings.gemini_api_key:
            raise TranscriptionError("GEMINI_API_KEY not configured")
        from google.genai import types

        client = _client()
        start = time.perf_counter()
        try:
            resp = client.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    _PROMPT,
                    types.Part.from_bytes(data=audio, mime_type=mime_type),
                ],
                config=types.GenerateContentConfig(
                    max_output_tokens=_MAX_OUTPUT_TOKENS,
                    # Transcription is not a creative task: sampling is what lets
                    # the model wander off the audio and into a loop.
                    temperature=0.0,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise TranscriptionError(f"gemini: {exc}") from exc
        latency = time.perf_counter() - start
        if not resp.text:
            raise TranscriptionError("gemini: empty transcription")
        if _is_degenerate(resp.text):
            # 502 to n8n, which flags the row -- deliberately louder than
            # returning the loop, because 200k repeated characters would be
            # summarised by the extraction chain into a confident lie.
            raise TranscriptionError(
                f"gemini: degenerate repetition loop ({len(resp.text)} chars)"
            )
        # Gemini's generateContent response carries no per-token/segment
        # logprob for audio transcription -> confidence stays None (schema
        # default), no fabricated score.
        return TranscriptionInfo(text=resp.text.strip(), provider=self.name, latency_s=latency)
