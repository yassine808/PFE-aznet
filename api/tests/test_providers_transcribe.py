"""The transcription adapters' happy and unhappy paths.

`test_providers.py` covers the registry and the missing-key guards; this file
covers what each adapter does once it has a key — the Gemini degenerate-loop
detector (one 84 KB clip once produced 222 797 characters), Groq's filename
extension gate, and the local sidecar's cold-start budget.

Every SDK and every HTTP call is faked; the cached clients are cleared around
each test so a fake cannot outlive it.
"""
import sys
import types

import pytest

from app.providers import gemini_audio, groq_whisper, local_darija
from app.providers.base import TranscriptionError


@pytest.fixture(autouse=True)
def _clear_clients():
    gemini_audio._client.cache_clear()
    groq_whisper._client.cache_clear()
    yield
    gemini_audio._client.cache_clear()
    groq_whisper._client.cache_clear()


@pytest.fixture(autouse=True)
def _no_usage_recording(monkeypatch):
    from app import usage

    monkeypatch.setattr(usage, "from_gemini", lambda *a, **k: None)
    monkeypatch.setattr(usage, "from_groq", lambda resp, *a, **k: resp)


# --- gemini: the degenerate-loop detector ----------------------------------

def test_a_short_answer_is_never_degenerate():
    assert gemini_audio._is_degenerate("goulotte posée au RDC") is False


def test_a_long_but_varied_answer_is_not_degenerate():
    text = " ".join(f"segment numero {i} du rapport" for i in range(200))
    assert gemini_audio._is_degenerate(text) is False


def test_a_repeated_tail_is_degenerate():
    """The real failure: the tail repeating one phrase until the token cap."""
    text = "rapport valide. " + "a l'hopital de la ville de Rabat " * 60
    assert gemini_audio._is_degenerate(text) is True


def _fake_genai(monkeypatch, *, text="  transcription  ", error=None):
    calls = {}

    def generate_content(model, contents, config):
        calls.update(model=model, contents=contents, config=config)
        if error is not None:
            raise error
        return types.SimpleNamespace(text=text)

    class Client:
        def __init__(self, api_key):
            calls["key"] = api_key
            self.models = types.SimpleNamespace(generate_content=generate_content)

    sdk_types = types.SimpleNamespace(
        Part=types.SimpleNamespace(
            from_bytes=lambda data, mime_type: calls.setdefault(
                "part", {"data": data, "mime_type": mime_type})),
        GenerateContentConfig=lambda **kw: kw,
    )
    genai = types.SimpleNamespace(Client=Client, types=sdk_types)
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(genai=genai))
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", sdk_types)
    monkeypatch.setattr(gemini_audio.settings, "gemini_api_key", "k")
    return calls


def test_gemini_returns_the_stripped_text_with_no_invented_confidence(monkeypatch):
    calls = _fake_genai(monkeypatch)
    out = gemini_audio.GeminiAudioProvider().transcribe(b"OGG", "audio/ogg")
    assert out.text == "transcription"
    assert out.provider == "gemini"
    assert out.latency_s >= 0
    # No logprob is available for audio, so no score is fabricated.
    assert out.confidence is None
    # Sampling off and the output capped: both guards against the loop.
    assert calls["config"]["temperature"] == 0.0
    assert calls["config"]["max_output_tokens"] == gemini_audio._MAX_OUTPUT_TOKENS
    assert calls["part"] == {"data": b"OGG", "mime_type": "audio/ogg"}


def test_an_empty_gemini_transcription_is_a_failure(monkeypatch):
    _fake_genai(monkeypatch, text="")
    with pytest.raises(TranscriptionError, match="empty transcription"):
        gemini_audio.GeminiAudioProvider().transcribe(b"OGG", "audio/ogg")


def test_a_loop_is_refused_rather_than_summarised(monkeypatch):
    """Returning it would let the extraction chain turn 200k repeated
    characters into a confident lie."""
    _fake_genai(monkeypatch, text="ok. " + "de la ville de Rabat " * 60)
    with pytest.raises(TranscriptionError, match="degenerate repetition loop"):
        gemini_audio.GeminiAudioProvider().transcribe(b"OGG", "audio/ogg")


def test_a_gemini_sdk_failure_is_named(monkeypatch):
    _fake_genai(monkeypatch, error=RuntimeError("503 unavailable"))
    with pytest.raises(TranscriptionError, match="gemini: 503 unavailable"):
        gemini_audio.GeminiAudioProvider().transcribe(b"OGG", "audio/ogg")


# --- groq ------------------------------------------------------------------

def _fake_groq(monkeypatch, *, result=None, error=None):
    calls = {}
    result = result if result is not None else types.SimpleNamespace(
        text="  transcription  ", segments=[{"avg_logprob": -0.2}])

    def create(**kwargs):
        calls.update(kwargs)
        if error is not None:
            raise error
        return result

    class Groq:
        def __init__(self, api_key):
            calls["key"] = api_key
            self.audio = types.SimpleNamespace(
                transcriptions=types.SimpleNamespace(
                    with_raw_response=types.SimpleNamespace(create=create)))

    monkeypatch.setitem(sys.modules, "groq", types.SimpleNamespace(Groq=Groq))
    monkeypatch.setattr(groq_whisper.settings, "groq_api_key", "k")
    return calls


def test_groq_asks_for_arabic_and_verbose_json(monkeypatch):
    calls = _fake_groq(monkeypatch)
    out = groq_whisper.GroqWhisperProvider().transcribe(b"OGG", "audio/ogg")
    assert out.text == "transcription"
    assert out.confidence == pytest.approx(0.8187, abs=1e-3)
    assert calls["language"] == "ar"
    assert calls["response_format"] == "verbose_json"
    # The vocabulary file is sent as `prompt`, without the soul prepended.
    assert "goulotte" in calls["prompt"].lower()


@pytest.mark.parametrize("mime,name", [
    ("audio/ogg", "note.ogg"),
    ("audio/oga", "note.ogg"),          # alias
    ("audio/x-wav", "note.wav"),        # alias
    ("audio/mpeg", "note.mpeg"),
    ("application/octet-stream", "note.ogg"),   # unknown -> pipeline default
    ("audio/ogg; codecs=opus", "note.ogg"),     # parameters stripped
])
def test_the_upload_filename_is_chosen_from_the_mime_type(monkeypatch, mime, name):
    """Groq gates on the extension before it decodes a byte, so an unaccepted
    name is refused whatever the audio actually is."""
    calls = _fake_groq(monkeypatch)
    groq_whisper.GroqWhisperProvider().transcribe(b"OGG", mime)
    assert calls["file"][0] == name


def test_a_plain_string_result_still_yields_a_transcription(monkeypatch):
    _fake_groq(monkeypatch, result="  texte brut  ")
    out = groq_whisper.GroqWhisperProvider().transcribe(b"OGG", "audio/ogg")
    assert (out.text, out.confidence) == ("texte brut", None)


def test_a_dict_result_is_read_the_same_way(monkeypatch):
    _fake_groq(monkeypatch, result={"text": "texte", "segments": [{"avg_logprob": 0.0}]})
    out = groq_whisper.GroqWhisperProvider().transcribe(b"OGG", "audio/ogg")
    assert (out.text, out.confidence) == ("texte", 1.0)


def test_a_groq_sdk_failure_is_named(monkeypatch):
    _fake_groq(monkeypatch, error=RuntimeError("429 rate limited"))
    with pytest.raises(TranscriptionError, match="groq: 429 rate limited"):
        groq_whisper.GroqWhisperProvider().transcribe(b"OGG", "audio/ogg")


@pytest.mark.parametrize("segments,expected", [
    ([], None),
    (None, None),
    ([{"nothing": 1}], None),                       # no avg_logprob anywhere
    ([types.SimpleNamespace(avg_logprob=0.0)], 1.0),  # object segments too
    ([{"avg_logprob": -100}], pytest.approx(0.0, abs=1e-30)),  # never negative
])
def test_confidence_is_derived_only_when_there_is_something_to_derive_from(
    segments, expected
):
    assert groq_whisper._confidence_from_segments(segments) == expected


# --- local sidecar ---------------------------------------------------------

class FakeHTTP:
    """One-call httpx.Client stand-in."""

    def __init__(self, *, payload=None, error=None, status_error=None):
        self.payload = payload if payload is not None else {"text": "  texte  "}
        self.error = error
        self.status_error = status_error
        self.calls = []

    def post(self, url, files):
        self.calls.append({"url": url, "files": files})
        if self.error is not None:
            raise self.error
        return self

    def raise_for_status(self):
        if self.status_error is not None:
            raise self.status_error

    def json(self):
        return self.payload


def test_the_local_engine_needs_its_url(monkeypatch):
    monkeypatch.setattr(local_darija.settings, "stt_local_url", "")
    with pytest.raises(TranscriptionError, match="STT_LOCAL_URL not configured"):
        local_darija.LocalDarijaProvider().transcribe(b"OGG", "audio/ogg")


def test_the_local_engine_posts_the_bytes_and_reads_the_answer(monkeypatch):
    http = FakeHTTP(payload={"text": "  texte  ", "confidence": "0.82"})
    monkeypatch.setattr(local_darija, "_http", lambda: http)
    monkeypatch.setattr(local_darija.settings, "stt_local_url",
                        "http://stt-local:8100/")
    out = local_darija.LocalDarijaProvider().transcribe(b"OGG", "audio/ogg")
    assert (out.text, out.provider) == ("texte", "local")
    assert out.confidence == pytest.approx(0.82)
    # The trailing slash is stripped, so the path never doubles up.
    assert http.calls[0]["url"] == "http://stt-local:8100/transcribe"


def test_a_missing_confidence_stays_none_rather_than_becoming_zero(monkeypatch):
    monkeypatch.setattr(local_darija, "_http", lambda: FakeHTTP())
    monkeypatch.setattr(local_darija.settings, "stt_local_url", "http://x:8100")
    assert local_darija.LocalDarijaProvider().transcribe(
        b"OGG", "audio/ogg").confidence is None


@pytest.mark.parametrize("payload", [{"text": "   "}, {}])
def test_an_empty_local_transcription_is_a_failure(monkeypatch, payload):
    monkeypatch.setattr(local_darija, "_http", lambda: FakeHTTP(payload=payload))
    monkeypatch.setattr(local_darija.settings, "stt_local_url", "http://x:8100")
    with pytest.raises(TranscriptionError, match="empty transcription"):
        local_darija.LocalDarijaProvider().transcribe(b"OGG", "audio/ogg")


def test_the_sidecar_being_down_is_a_normal_engine_failure(monkeypatch):
    """It has to raise like any other engine so the chain moves on."""
    monkeypatch.setattr(local_darija, "_http",
                        lambda: FakeHTTP(error=OSError("connection refused")))
    monkeypatch.setattr(local_darija.settings, "stt_local_url", "http://x:8100")
    with pytest.raises(TranscriptionError, match="local: connection refused"):
        local_darija.LocalDarijaProvider().transcribe(b"OGG", "audio/ogg")


def test_the_client_budget_stays_above_the_measured_cold_start(monkeypatch):
    """280 s to load plus ~32 s to transcribe; at 300 s every first call after
    a restart timed out, and failing warmed the model so the retry passed."""
    assert local_darija.COLD_START_BUDGET_S >= 320
    built = {}
    monkeypatch.setitem(
        sys.modules, "httpx",
        types.SimpleNamespace(Client=lambda timeout: built.setdefault("timeout", timeout)))
    local_darija._http.cache_clear()
    try:
        local_darija._http()
        assert built["timeout"] == local_darija.COLD_START_BUDGET_S
    finally:
        local_darija._http.cache_clear()
