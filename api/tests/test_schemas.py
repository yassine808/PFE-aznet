import pytest
from pydantic import ValidationError

from app.schemas import ExtractedReport, ProcessResponse, TranscriptionInfo


def test_full_report_valid():
    r = ExtractedReport(
        cables_prepares_m=268,
        cables_installes_m=202.5,
        goulotte_m=27,
        prises_connectees=14,
        panneaux_prises_brassees=17,
        prises_testees=15,
        fibre_m=794,
        interconnexions=6,
        connexions_optiques_brins=48,
        etages=["RDC", "E1"],
        ailes=["Droite"],
        locaux_techniques=["SR4"],
        stock_cable_m=2274,
        remarques="Deux bureaux fermés jusqu'à lundi.",
        resume="Pose de 202 m de câble et raccordement de 14 prises.",
    )
    assert r.cables_installes_m == 202.5
    assert r.prises_testees == 15
    assert r.etages == ["RDC", "E1"]


def test_minimal_report_only_resume():
    r = ExtractedReport(resume="Journée de préparation du chantier.")
    assert r.cables_installes_m is None
    assert r.etages is None
    assert not r.has_data()


def test_resume_required():
    with pytest.raises(ValidationError):
        ExtractedReport()


def test_negative_quantity_rejected():
    with pytest.raises(ValidationError):
        ExtractedReport(resume="x", cables_installes_m=-10)


def test_numeric_string_coerced():
    r = ExtractedReport(resume="x", goulotte_m="150")
    assert r.goulotte_m == 150.0


def test_null_string_becomes_none():
    r = ExtractedReport(resume="x", fibre_m="null", remarques="none")
    assert r.fibre_m is None
    assert r.remarques is None


# --- has_data: the gate between a report and a greeting -------------------


def test_remarks_only_report_counts_as_data():
    """A blocked day is the report the director most needs to read."""
    r = ExtractedReport(
        remarques="Arrêtés 1h30 sur instruction. Bureaux fermés.",
        resume="Intervention interrompue, aucun mètre posé.",
    )
    assert r.has_data()


def test_location_only_report_counts_as_data():
    r = ExtractedReport(etages=["E2"], resume="Présence sur site au 2e étage.")
    assert r.has_data()


def test_arret_only_report_counts_as_data():
    """90 minutes lost are a report even when not a metre was laid."""
    r = ExtractedReport(
        temps_arret_min=90, motif_arret="Sur instruction",
        resume="Arrêt de 90 minutes, aucun mètre posé.",
    )
    assert r.has_data()


def test_needs_only_report_counts_as_data():
    """A message that only asks for material is the report of the day."""
    r = ExtractedReport(
        besoins="Il manque des connecteurs RJ45.",
        resume="Pose terminée au 3e, matériel manquant.",
    )
    assert r.has_data()


def test_zero_is_data_not_absence():
    r = ExtractedReport(goulotte_m=0, resume="Aucune goulotte posée aujourd'hui.")
    assert r.has_data()


# --- location normalization ----------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("rdc", "RDC"),
        ("Rez-de-chaussee", "RDC"),
        ("e1", "E1"),
        ("1er etage", "E1"),
        ("2ème étage", "E2"),
        ("E4", "E4"),
    ],
)
def test_etage_aliases_normalized(raw, expected):
    assert ExtractedReport(resume="x", etages=[raw]).etages == [expected]


def test_comma_string_splits_into_list():
    r = ExtractedReport(resume="x", etages="RDC, E1, E2", ailes="Droite, Gauche")
    assert r.etages == ["RDC", "E1", "E2"]
    assert r.ailes == ["Droite", "Gauche"]


def test_duplicate_locations_collapse():
    assert ExtractedReport(resume="x", etages=["E1", "e1", "E1"]).etages == ["E1"]


def test_aile_normalized_from_prefix():
    assert ExtractedReport(resume="x", ailes=["droit"]).ailes == ["Droite"]
    assert ExtractedReport(resume="x", ailes=["GAUCHE"]).ailes == ["Gauche"]


def test_local_technique_tolerates_spacing():
    assert ExtractedReport(resume="x", locaux_techniques=["SR 4"]).locaux_techniques == ["SR4"]


def test_unknown_location_raises_loudly():
    """An invented floor is a wrong row — the chain must retry, not write it."""
    with pytest.raises(ValidationError):
        ExtractedReport(resume="x", etages=["E9"])
    with pytest.raises(ValidationError):
        ExtractedReport(resume="x", locaux_techniques=["SR42"])
    with pytest.raises(ValidationError):
        ExtractedReport(resume="x", ailes=["Nord"])


# --- ProcessResponse ------------------------------------------------------


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


# --- "null" as a string, inside the list fields -----------------------------
#
# Found by the 2026-08-15 text benchmark: both Llama models failed 13 of 20
# cases with "étage inconnu: 'null'". `_null_strings_to_none` is a wildcard
# validator, but pydantic runs the field-specific `_wrap_single` first, so the
# three list fields were never covered by it.


def test_null_string_in_a_list_field_is_absence():
    r = ExtractedReport(resume="x", etages="null", ailes="null",
                        locaux_techniques="none")
    assert r.etages is None and r.ailes is None and r.locaux_techniques is None


def test_null_string_inside_a_list_is_dropped():
    assert ExtractedReport(resume="x", etages=["null"]).etages is None


def test_a_real_value_beside_a_null_string_survives():
    """The absent marker is dropped; the floor the technician named is not."""
    assert ExtractedReport(resume="x", etages=["RDC", "null", "E1"]).etages == ["RDC", "E1"]


def test_an_invented_floor_still_raises():
    """The fix must not turn an unknown value into a silent None — an invented
    floor is a wrong row and the chain must retry."""
    with pytest.raises(ValueError):
        ExtractedReport(resume="x", etages=["E9"])
