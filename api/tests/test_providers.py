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
    provider_instance = get_provider(name)
    with pytest.raises(TranscriptionError, match="not configured"):
        provider_instance.transcribe(b"fake-audio", "audio/ogg")


class TestConfidenceFromSegments:
    """Groq's Whisper verbose_json gives per-segment avg_logprob — the only
    provider with a usable confidence signal. exp(avg_logprob) rescales it
    into a rough 0-1 confidence."""

    def test_no_segments_returns_none(self):
        from app.providers.groq_whisper import _confidence_from_segments

        assert _confidence_from_segments([]) is None

    def test_dict_segments(self):
        from app.providers.groq_whisper import _confidence_from_segments

        segments = [{"avg_logprob": -0.1}, {"avg_logprob": -0.2}]
        conf = _confidence_from_segments(segments)
        assert conf is not None
        assert 0.0 <= conf <= 1.0

    def test_object_segments(self):
        from app.providers.groq_whisper import _confidence_from_segments

        class Seg:
            avg_logprob = -0.05

        conf = _confidence_from_segments([Seg(), Seg()])
        assert conf is not None
        assert 0.0 <= conf <= 1.0

    def test_very_negative_logprob_near_zero(self):
        from app.providers.groq_whisper import _confidence_from_segments

        conf = _confidence_from_segments([{"avg_logprob": -50}])
        assert conf < 0.001

    def test_positive_logprob_clamped_to_one(self):
        from app.providers.groq_whisper import _confidence_from_segments

        # avg_logprob shouldn't exceed 0 in practice, but the clamp guards
        # against exp() pushing confidence above 1 either way.
        conf = _confidence_from_segments([{"avg_logprob": 5}])
        assert conf == 1.0

    def test_segments_missing_avg_logprob_returns_none(self):
        from app.providers.groq_whisper import _confidence_from_segments

        assert _confidence_from_segments([{"no_speech_prob": 0.1}]) is None
