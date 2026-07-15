import pytest
from pydantic import ValidationError

from app.schemas import ExtractedReport, ProcessResponse, TranscriptionInfo


def test_full_report_valid():
    r = ExtractedReport(
        chantier="Tour Atlas",
        client="Banque X",
        type_activite="câblage",
        goulottes_m=150,
        cables_m=800.5,
        bureaux_termines=5,
        panneaux_raccordes=2,
        autres_travaux=None,
        observations="manque de connecteurs RJ45",
        resume="Installation de 150 m de goulotte et pose de 800 m de câble.",
    )
    assert r.goulottes_m == 150.0
    assert r.bureaux_termines == 5


def test_minimal_report_only_resume():
    r = ExtractedReport(resume="Journée de préparation du chantier.")
    assert r.chantier is None
    assert r.goulottes_m is None


def test_resume_required():
    with pytest.raises(ValidationError):
        ExtractedReport()


def test_negative_quantity_rejected():
    with pytest.raises(ValidationError):
        ExtractedReport(resume="x", cables_m=-10)


def test_numeric_string_coerced():
    r = ExtractedReport(resume="x", goulottes_m="150")
    assert r.goulottes_m == 150.0


def test_process_response_text_mode_has_no_transcription():
    resp = ProcessResponse(
        rapport_complet="texte saisi au formulaire",
        report=ExtractedReport(resume="Résumé."),
    )
    assert resp.transcription is None
    assert resp.warnings == []


def test_process_response_voice_mode():
    resp = ProcessResponse(
        rapport_complet="transcription brute",
        report=ExtractedReport(resume="Résumé."),
        transcription=TranscriptionInfo(text="transcription brute", provider="groq", latency_s=1.2),
        warnings=["low_confidence"],
    )
    assert resp.transcription is not None
    assert resp.transcription.provider == "groq"
