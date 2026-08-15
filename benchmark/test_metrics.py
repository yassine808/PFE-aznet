import pytest

from metrics import extraction_accuracy, normalize_text, wer_cer


def test_normalize_strips_diacritics_and_unifies_alef():
    assert normalize_text("أَلْبِيرُو") == normalize_text("البيرو")


def test_normalize_punct_and_case():
    assert normalize_text("Goulotte, 150 M!") == "goulotte 150 m"


def test_wer_identical_is_zero():
    wer, cer = wer_cer("نصبنا goulotte 150 متر", "نصبنا goulotte 150 متر.")
    assert wer == 0.0
    assert cer == 0.0


def test_wer_counts_substitution():
    wer, _ = wer_cer("goulotte 150 metre", "goulotte 200 metre")
    assert wer == pytest.approx(1 / 3)


def test_wer_empty_reference_raises():
    with pytest.raises(ValueError):
        wer_cer("", "x")


def test_extraction_all_correct():
    expected = {"goulottes_m": 150, "chantier": "Tour Atlas", "observations": None}
    actual = {"goulottes_m": 150.0, "chantier": "tour atlas", "observations": None, "resume": "..."}
    acc, detail = extraction_accuracy(expected, actual)
    assert acc == 1.0
    assert all(detail.values())


def test_extraction_partial():
    expected = {"goulottes_m": 150, "cables_m": 800}
    actual = {"goulottes_m": 150, "cables_m": None}
    acc, detail = extraction_accuracy(expected, actual)
    assert acc == 0.5
    assert detail == {"goulottes_m": True, "cables_m": False}


def test_extraction_resume_never_graded():
    acc, detail = extraction_accuracy({"resume": "x", "cables_m": 800}, {"cables_m": 800})
    assert acc == 1.0
    assert "resume" not in detail


def test_extraction_no_gradable_fields_raises():
    with pytest.raises(ValueError):
        extraction_accuracy({"resume": "only free text"}, {})


def test_location_lists_grade_regardless_of_order():
    """Same floors, different order, is a right answer.

    `schemas._canon` preserves the order the model emitted, so a key written
    ["RDC", "E1"] used to mark ["E1", "RDC"] wrong — penalising a model for
    word order on every multi-floor case.
    """
    score, detail = extraction_accuracy(
        {"etages": ["RDC", "E1"]}, {"etages": ["E1", "RDC"]}
    )
    assert score == 1.0
    assert detail["etages"] is True


def test_a_different_floor_is_still_wrong():
    """Order-insensitive must not become content-insensitive."""
    score, _ = extraction_accuracy({"etages": ["RDC", "E1"]}, {"etages": ["E1", "E2"]})
    assert score == 0.0


def test_a_missing_floor_is_still_wrong():
    score, _ = extraction_accuracy({"etages": ["RDC", "E1"]}, {"etages": ["RDC"]})
    assert score == 0.0
