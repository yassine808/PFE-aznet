from fastapi.testclient import TestClient

import pytest

import app.main as main
from app.extraction import ExtractionError
from app.providers.base import TranscriptionError, TranscriptionProvider
from app.schemas import ExtractedReport, TranscriptionInfo

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _silence_bell(monkeypatch):
    """The bell is exercised in test_tasks_notifications.py. These tests are
    about transcription/extraction — the real notification store would hit the
    dev DB (or, worse, an unreachable one) for no assertion here."""
    monkeypatch.setattr(main.logs, "notify_technician_manager", lambda *a, **k: None)
    monkeypatch.setattr(main.logs, "notify_managers", lambda *a, **k: 0)

# /generate-image is gated by require_human. Overriding the dependency rather
# than logging in keeps the suite free of a database, same as the other modules.
main.app.dependency_overrides[main.auth.require_human] = lambda: {
    "id": 1, "name": "Test", "role": "directeur"
}
# /process, GET /logs, /service-samples and /sheet-queue are gated by
# require_user. Same override, declared here so this module stays hermetic —
# relying on another module's module-level override would silently pass when
# the real gate is broken (the full suite used to mask it by import order).
main.app.dependency_overrides[main.auth.require_user] = lambda: {
    "id": 1, "name": "Test", "role": "directeur"
}

# The /process audio path uploads to Google Drive for the durable lien_audio.
# The real key exists on this machine and would trigger a network discovery
# fetch on every voice test — these tests are about transcription, not Drive.
# Drive behavior itself is covered in test_media_and_modify.py.
main.drive.upload_audio = lambda filename, mime, data: "https://drive.google.com/uc?id=test"

REPORT = ExtractedReport(
    chantier="Tour Atlas",
    goulottes_m=150,
    cables_m=800,
    bureaux_termines=5,
    panneaux_raccordes=2,
    resume="Installation de 150 m de goulotte et pose de 800 m de câble réseau.",
)


class FakeProvider(TranscriptionProvider):
    name = "fake"

    def transcribe(self, audio, mime_type):
        return TranscriptionInfo(text="نصبنا goulotte 150 متر وجرّينا 800 متر ديال الكابل", provider="fake", latency_s=0.1)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert set(r.json()["stt_providers"]) == {"gemini", "groq", "hf-darija"}


def test_text_mode(monkeypatch):
    monkeypatch.setattr(main.extraction, "extract_report_with_model", lambda t, profile=None: (REPORT, "test/stub"))
    r = client.post("/process", data={"text": "Installation de 150m de goulotte"})
    assert r.status_code == 200
    body = r.json()
    assert body["report"]["goulottes_m"] == 150
    assert body["transcription"] is None
    assert body["warnings"] == []


def test_voice_mode(monkeypatch):
    monkeypatch.setattr(main, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(main.extraction, "extract_report_with_model", lambda t, profile=None: (REPORT, "test/stub"))
    r = client.post("/process", files={"audio": ("note.ogg", b"fake-bytes", "audio/ogg")})
    assert r.status_code == 200
    body = r.json()
    assert body["transcription"]["provider"] == "fake"
    assert body["rapport_complet"].startswith("نصبنا")


def test_greeting_flagged_as_no_report_content(monkeypatch):
    """"Salut" extracts cleanly with every field null — n8n must not call that a report."""
    greeting = ExtractedReport(resume="Le technicien salue l'équipe.")
    monkeypatch.setattr(main.extraction, "extract_report_with_model", lambda t, profile=None: (greeting, "test/stub"))
    r = client.post("/process", data={"text": "salam"})
    assert r.status_code == 200
    assert r.json()["warnings"] == ["no_report_content"]


def test_neither_input_rejected():
    assert client.post("/process").status_code == 422


def test_both_inputs_rejected():
    r = client.post(
        "/process",
        data={"text": "x"},
        files={"audio": ("note.ogg", b"y", "audio/ogg")},
    )
    assert r.status_code == 422


def test_transcription_failure_maps_to_502(monkeypatch):
    class Failing(FakeProvider):
        def transcribe(self, audio, mime_type):
            raise TranscriptionError("engine down")

    monkeypatch.setattr(main, "get_provider", lambda name: Failing())
    r = client.post("/process", files={"audio": ("note.ogg", b"z", "audio/ogg")})
    assert r.status_code == 502
    assert "transcription failed" in r.json()["detail"]


def test_extraction_failure_maps_to_502(monkeypatch):
    def boom(t, profile=None):
        raise ExtractionError("both engines down")

    monkeypatch.setattr(main.extraction, "extract_report_with_model", boom)
    r = client.post("/process", data={"text": "rapport"})
    assert r.status_code == 502
    assert "extraction failed" in r.json()["detail"]


def test_short_transcription_flagged(monkeypatch):
    class Short(FakeProvider):
        def transcribe(self, audio, mime_type):
            return TranscriptionInfo(text="سلام", provider="fake", latency_s=0.1)

    monkeypatch.setattr(main, "get_provider", lambda name: Short())
    monkeypatch.setattr(main.extraction, "extract_report_with_model", lambda t, profile=None: (REPORT, "test/stub"))
    r = client.post("/process", files={"audio": ("note.ogg", b"q", "audio/ogg")})
    assert r.status_code == 200
    assert "short_transcription" in r.json()["warnings"]


def test_low_confidence_flagged(monkeypatch):
    class LowConfidence(FakeProvider):
        def transcribe(self, audio, mime_type):
            return TranscriptionInfo(
                text="نصبنا goulotte 150 متر", provider="fake", latency_s=0.1, confidence=0.3
            )

    monkeypatch.setattr(main, "get_provider", lambda name: LowConfidence())
    monkeypatch.setattr(main.extraction, "extract_report_with_model", lambda t, profile=None: (REPORT, "test/stub"))
    r = client.post("/process", files={"audio": ("note.ogg", b"q", "audio/ogg")})
    assert r.status_code == 200
    body = r.json()
    assert "low_confidence_transcription" in body["warnings"]
    assert body["transcription"]["confidence"] == 0.3


def test_high_confidence_not_flagged(monkeypatch):
    class HighConfidence(FakeProvider):
        def transcribe(self, audio, mime_type):
            return TranscriptionInfo(
                text="نصبنا goulotte 150 متر وجرّينا 800 متر ديال الكابل",
                provider="fake",
                latency_s=0.1,
                confidence=0.92,
            )

    monkeypatch.setattr(main, "get_provider", lambda name: HighConfidence())
    monkeypatch.setattr(main.extraction, "extract_report_with_model", lambda t, profile=None: (REPORT, "test/stub"))
    r = client.post("/process", files={"audio": ("note.ogg", b"q", "audio/ogg")})
    assert r.status_code == 200
    assert "low_confidence_transcription" not in r.json()["warnings"]


def test_missing_confidence_not_flagged(monkeypatch):
    """Providers with no confidence signal (gemini, hf-darija) must not be
    falsely flagged — None means 'unknown', not 'low'."""
    monkeypatch.setattr(main, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(main.extraction, "extract_report_with_model", lambda t, profile=None: (REPORT, "test/stub"))
    r = client.post("/process", files={"audio": ("note.ogg", b"q", "audio/ogg")})
    assert r.status_code == 200
    body = r.json()
    assert body["transcription"]["confidence"] is None
    assert "low_confidence_transcription" not in body["warnings"]


def test_unknown_provider_rejected(monkeypatch):
    r = client.post(
        "/process",
        data={"provider": "does-not-exist"},
        files={"audio": ("note.ogg", b"q", "audio/ogg")},
    )
    assert r.status_code == 422
    assert "Unknown STT provider" in r.json()["detail"]


# ── upload caps (2026-08-03) ────────────────────────────────────────────────
# A misdirected file must cost nothing: no engine call, no quota, no Sheet row.

def test_audio_too_large_rejected(monkeypatch):
    calls = []

    def spy(name):
        calls.append(name)
        return FakeProvider()

    monkeypatch.setattr(main, "get_provider", spy)
    blob = b"\x00" * (main.MAX_AUDIO_BYTES + 1)
    r = client.post("/process", files={"audio": ("big.ogg", blob, "audio/ogg")})
    assert r.status_code == 422
    assert "too large" in r.json()["detail"].lower()
    assert calls == []  # the cap sits before any engine is touched


def test_image_too_large_rejected(monkeypatch):
    reached = []

    def boom(blob, mime, profile=None, caption=None):
        reached.append(1)
        raise AssertionError("vision must not be reached")

    monkeypatch.setattr(main.extraction, "extract_report_from_image", boom)
    blob = b"\x00" * (main.MAX_IMAGE_BYTES + 1)
    r = client.post("/process", files={"image": ("big.jpg", blob, "image/jpeg")})
    assert r.status_code == 422
    assert "too large" in r.json()["detail"].lower()
    assert reached == []


def test_right_at_the_cap_is_still_accepted(monkeypatch):
    monkeypatch.setattr(main, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(main.extraction, "extract_report_with_model", lambda t, profile=None: (REPORT, "test/stub"))
    blob = b"\x00" * main.MAX_AUDIO_BYTES
    r = client.post("/process", files={"audio": ("cap.ogg", blob, "audio/ogg")})
    assert r.status_code == 200


# ── STT fallback chain (2026-08-03) ─────────────────────────────────────────
# Mirror of the extraction chain: ordered engines, first success wins, every
# engine failing raises one combined error — a Groq outage must fall through
# to Gemini instead of costing the technician their report.

def _chain_providers():
    class GroqDown(FakeProvider):
        def transcribe(self, audio, mime_type):
            raise TranscriptionError("groq quota exhausted")

    class GeminiUp(FakeProvider):
        def transcribe(self, audio, mime_type):
            return TranscriptionInfo(text="نصبنا goulotte 150 متر", provider="gemini", latency_s=0.1)

    return {"groq": GroqDown(), "gemini": GeminiUp()}


def test_stt_chain_falls_back_to_next_engine(monkeypatch):
    monkeypatch.setattr(main.settings, "stt_chain", "groq,gemini")
    monkeypatch.setattr(main, "get_provider", lambda name: _chain_providers()[name])
    monkeypatch.setattr(main.extraction, "extract_report_with_model", lambda t, profile=None: (REPORT, "test/stub"))
    r = client.post("/process", files={"audio": ("note.ogg", b"q", "audio/ogg")})
    assert r.status_code == 200, r.text
    assert r.json()["transcription"]["provider"] == "gemini"


def test_stt_chain_all_engines_failing_502(monkeypatch):
    monkeypatch.setattr(main.settings, "stt_chain", "groq,gemini")

    class Down(FakeProvider):
        def transcribe(self, audio, mime_type):
            raise TranscriptionError("engine down")

    monkeypatch.setattr(main, "get_provider", lambda name: Down())
    r = client.post("/process", files={"audio": ("note.ogg", b"q", "audio/ogg")})
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert "groq" in detail and "gemini" in detail  # both failures named, no silent fallback


def test_forced_provider_bypasses_the_chain(monkeypatch):
    """The benchmark override (`provider=` form field) stays single-engine."""
    seen = []

    def spy(name):
        seen.append(name)
        return _chain_providers()[name]

    monkeypatch.setattr(main.settings, "stt_chain", "groq,gemini")
    monkeypatch.setattr(main, "get_provider", spy)
    monkeypatch.setattr(main.extraction, "extract_report_with_model", lambda t, profile=None: (REPORT, "test/stub"))
    r = client.post(
        "/process",
        data={"provider": "gemini"},
        files={"audio": ("note.ogg", b"q", "audio/ogg")},
    )
    assert r.status_code == 200, r.text
    assert seen == ["gemini"]  # only the forced engine was consulted


def test_image_mode(monkeypatch):
    """Vision path returns the report directly — no transcription, and the
    rapport_complet column is marked so nobody reads it as a verbatim quote."""
    monkeypatch.setattr(
        main.extraction, "extract_report_from_image",
        lambda blob, mime, profile=None, caption=None: (REPORT, "gemini/test"),
    )
    r = client.post("/process", files={"image": ("note.jpg", b"\xff\xd8fake", "image/jpeg")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transcription"] is None
    assert body["rapport_complet"].startswith("[photo] ")
    assert "image_input" in body["warnings"]


def test_image_extraction_failure_maps_to_502(monkeypatch):
    def boom(blob, mime, profile=None, caption=None):
        raise ExtractionError("no vision model reachable")

    monkeypatch.setattr(main.extraction, "extract_report_from_image", boom)
    r = client.post("/process", files={"image": ("note.jpg", b"\xff\xd8fake", "image/jpeg")})
    assert r.status_code == 502
    assert "image extraction failed" in r.json()["detail"]


def test_audio_caption_merged_before_extraction(monkeypatch):
    """A Telegram voice note with a caption: the caption rides along into the
    extraction input and the transcript column."""
    seen = {}

    def fake_extract(t, profile=None):
        seen["text"] = t
        return REPORT, "test/stub"

    monkeypatch.setattr(main, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(main.extraction, "extract_report_with_model", fake_extract)
    r = client.post(
        "/process",
        data={"caption": "On a fini la salle 3"},
        files={"audio": ("note.ogg", b"fake-bytes", "audio/ogg")},
    )
    assert r.status_code == 200
    assert "On a fini la salle 3" in seen["text"]
    assert seen["text"].startswith("نصبنا")
    assert "On a fini la salle 3" in r.json()["rapport_complet"]


def test_image_caption_passed_to_vision(monkeypatch):
    """A photo with a caption: the caption is fed to the vision model too."""
    seen = {}

    def fake_vision(blob, mime, profile=None, caption=None):
        seen["caption"] = caption
        return REPORT, "gemini/test"

    monkeypatch.setattr(main.extraction, "extract_report_from_image", fake_vision)
    r = client.post(
        "/process",
        data={"caption": "plan du 2e étage"},
        files={"image": ("note.jpg", b"\xff\xd8fake", "image/jpeg")},
    )
    assert r.status_code == 200
    assert seen["caption"] == "plan du 2e étage"


def test_caption_without_input_rejected():
    """A caption is auxiliary — it never satisfies the exactly-one-input rule."""
    r = client.post("/process", data={"caption": "rien d'autre"})
    assert r.status_code == 422
    assert "exactly one" in r.json()["detail"]


def test_text_plus_caption_merged(monkeypatch):
    seen = {}

    def fake_extract(t, profile=None):
        seen["text"] = t
        return REPORT, "test/stub"

    monkeypatch.setattr(main.extraction, "extract_report_with_model", fake_extract)
    r = client.post(
        "/process", data={"text": "Installation de 150m de goulotte", "caption": "urgence"}
    )
    assert r.status_code == 200
    assert seen["text"].endswith("urgence")


def test_empty_image_rejected():
    r = client.post("/process", files={"image": ("note.jpg", b"", "image/jpeg")})
    assert r.status_code == 422


def test_image_plus_text_rejected():
    r = client.post(
        "/process",
        data={"text": "rapport"},
        files={"image": ("note.jpg", b"\xff\xd8fake", "image/jpeg")},
    )
    assert r.status_code == 422
    assert "exactly one" in r.json()["detail"]


def test_health_reports_prompts_and_chains():
    """A prompt that fails to load must be visible, not silently empty."""
    body = client.get("/health").json()
    assert "00-soul.md" in body["prompts"]
    assert all(isinstance(v, int) and v > 0 for v in body["prompts"].values()), body["prompts"]
    assert set(body["chains"]) == {"text", "image", "image_generation"}


def test_soul_is_prepended_to_model_prompts():
    from app import prompt_loader

    soul = prompt_loader.load(prompt_loader.SOUL)
    for name in (prompt_loader.TEXT_EXTRACTION, prompt_loader.IMAGE_EXTRACTION,
                 prompt_loader.IMAGE_GENERATION):
        assert prompt_loader.load(name).startswith(soul)
    # Whisper reads its prompt as preceding transcript, so the soul must NOT
    # be there — it would end up echoed into the transcription.
    assert not prompt_loader.load(prompt_loader.STT_VOCABULARY, with_soul=False).startswith(soul)


def test_prompts_forbid_vendor_identity():
    from app import prompt_loader

    soul = prompt_loader.load(prompt_loader.SOUL).lower()
    assert "assistant aznet" in soul
    for vendor in ("claude", "chatgpt", "gemini"):
        assert vendor in soul, f"{vendor} must be named in the do-not-claim list"


def test_missing_prompt_raises():
    from app import prompt_loader

    try:
        prompt_loader.load("does-not-exist.md")
    except prompt_loader.PromptError as exc:
        assert "unreadable" in str(exc)
    else:
        raise AssertionError("a missing prompt must raise, not return empty")


def test_generate_image(monkeypatch):
    monkeypatch.setattr(
        main.imagegen, "generate_card", lambda rows, title, extra: (b"\x89PNG", "image/png", "gemini/test")
    )
    r = client.post("/generate-image", json={"title": "Semaine 30", "rows": [{"goulottes_m": "150"}]})
    assert r.status_code == 200, r.text
    assert r.json()["data_uri"].startswith("data:image/png;base64,")


def test_generate_image_needs_rows():
    assert client.post("/generate-image", json={"title": "x", "rows": []}).status_code == 422


def test_image_card_totals_are_computed_locally():
    """Arithmetic stays in Python — a model that sums rows on its way to
    drawing will eventually draw a total nobody measured."""
    from app import imagegen

    summary = imagegen.summarise([
        {"goulottes_m": "150", "cables_m": "800", "chantier": "Marina", "technicien": "Ali"},
        {"goulottes_m": "50.5", "cables_m": "", "chantier": "Marina", "technicien": "Sara"},
        {"goulottes_m": "n/a", "bureaux_termines": "3", "technicien": "Ali"},
    ])
    assert "Goulottes (m): 200.5" in summary
    assert "Câbles (m): 800" in summary
    assert "Bureaux terminés: 3" in summary
    assert "Techniciens: 2" in summary
    assert "Chantiers: 1" in summary
