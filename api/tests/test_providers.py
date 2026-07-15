import pytest

from app.providers import available_providers, get_provider
from app.providers.base import TranscriptionError, TranscriptionProvider


def test_all_three_adapters_registered():
    assert available_providers() == ["gemini", "groq", "hf-darija"]


@pytest.mark.parametrize("name", ["groq", "gemini", "hf-darija"])
def test_registry_returns_provider_instances(name):
    p = get_provider(name)
    assert isinstance(p, TranscriptionProvider)
    assert p.name == name


def test_unknown_provider_raises_with_available_list():
    with pytest.raises(ValueError) as exc:
        get_provider("whisper-x")
    assert "gemini" in str(exc.value)


@pytest.mark.parametrize("name", ["groq", "gemini", "hf-darija"])
def test_missing_api_key_fails_loudly(name, monkeypatch):
    """No silent fallbacks: unconfigured engine must raise, not return junk."""
    from app import config

    monkeypatch.setattr(config.settings, "groq_api_key", None)
    monkeypatch.setattr(config.settings, "gemini_api_key", None)
    monkeypatch.setattr(config.settings, "hf_token", None)
    with pytest.raises(TranscriptionError, match="not configured"):
        get_provider(name).transcribe(b"fake-audio", "audio/ogg")
