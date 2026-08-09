"""STT provider registry — Strategy pattern.

Each engine implements TranscriptionProvider; the benchmark (and .env) decide
which one serves production traffic. Adding an engine = one module + one
registry line, nothing else changes.
"""
from typing import Callable, Dict

from .base import TranscriptionProvider

_REGISTRY: Dict[str, Callable[[], TranscriptionProvider]] = {}


def register(name: str) -> Callable:
    def deco(factory: Callable[[], TranscriptionProvider]) -> Callable:
        _REGISTRY[name] = factory
        return factory
    return deco


def get_provider(name: str) -> TranscriptionProvider:
    try:
        factory = _REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Unknown STT provider '{name}'. Available: {sorted(_REGISTRY)}"
        )
    return factory()


def available_providers() -> list:
    return sorted(_REGISTRY)


# import adapters so their @register decorators run.
# hf_darija was deleted on 2026-08-08: its endpoint no longer resolves
# (getaddrinfo failed) and the checkpoint it pinned, Morocco-Darija-STT-large-v1.6,
# returns 404 with a valid token — it does not exist. It had never executed once.
# The Darija model it was meant to reach now runs on the GPU sidecar: local_darija.
from . import gemini_audio, groq_whisper, local_darija  # noqa: E402,F401
