import abc

from app.schemas import TranscriptionInfo


class TranscriptionError(RuntimeError):
    """Raised when an engine fails — caller decides fallback/flagging."""


class TranscriptionProvider(abc.ABC):
    """One speech-to-text engine. Stateless; safe to instantiate per request."""

    name: str = "abstract"

    @abc.abstractmethod
    def transcribe(self, audio: bytes, mime_type: str) -> TranscriptionInfo:
        """Audio bytes (WhatsApp sends ogg/opus) -> transcription + timing."""
        raise NotImplementedError
