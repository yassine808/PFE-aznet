from fastapi.testclient import TestClient

import app.main as main
from app.extraction import ExtractionError
from app.providers.base import TranscriptionError, TranscriptionProvider
from app.schemas import ExtractedReport, TranscriptionInfo

client = TestClient(main.app)

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
    monkeypatch.setattr(main.extraction, "extract_report", lambda t: REPORT)
    r = client.post("/process", data={"text": "Installation de 150m de goulotte"})
    assert r.status_code == 200
    body = r.json()
    assert body["report"]["goulottes_m"] == 150
    assert body["transcription"] is None
    assert body["warnings"] == []


def test_voice_mode(monkeypatch):
    monkeypatch.setattr(main, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(main.extraction, "extract_report", lambda t: REPORT)
    r = client.post("/process", files={"audio": ("note.ogg", b"fake-bytes", "audio/ogg")})
    assert r.status_code == 200
    body = r.json()
    assert body["transcription"]["provider"] == "fake"
    assert body["rapport_complet"].startswith("نصبنا")


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
    def boom(t):
        raise ExtractionError("both engines down")

    monkeypatch.setattr(main.extraction, "extract_report", boom)
    r = client.post("/process", data={"text": "rapport"})
    assert r.status_code == 502
    assert "extraction failed" in r.json()["detail"]


def test_short_transcription_flagged(monkeypatch):
    class Short(FakeProvider):
        def transcribe(self, audio, mime_type):
            return TranscriptionInfo(text="سلام", provider="fake", latency_s=0.1)

    monkeypatch.setattr(main, "get_provider", lambda name: Short())
    monkeypatch.setattr(main.extraction, "extract_report", lambda t: REPORT)
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
    monkeypatch.setattr(main.extraction, "extract_report", lambda t: REPORT)
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
    monkeypatch.setattr(main.extraction, "extract_report", lambda t: REPORT)
    r = client.post("/process", files={"audio": ("note.ogg", b"q", "audio/ogg")})
    assert r.status_code == 200
    assert "low_confidence_transcription" not in r.json()["warnings"]


def test_missing_confidence_not_flagged(monkeypatch):
    """Providers with no confidence signal (gemini, hf-darija) must not be
    falsely flagged — None means 'unknown', not 'low'."""
    monkeypatch.setattr(main, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(main.extraction, "extract_report", lambda t: REPORT)
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
