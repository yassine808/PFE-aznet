"""Benchmark metrics: WER/CER on normalized text + field-level extraction accuracy.

Pure functions — no API calls, fully unit-testable. Arabic normalization matters:
without it, alef/ya variants and diacritics inflate WER for engines that are
semantically correct but orthographically different (no standard Darija spelling).
"""
import re
import unicodedata
from typing import Any, Dict, Optional, Tuple

# Arabic diacritics (tashkeel) + tatweel
_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭـ]")
# Punctuation from both scripts (includes Arabic comma/question mark)
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)

_ARABIC_EQUIV = {
    "أ": "ا", "إ": "ا", "آ": "ا",  # alef variants
    "ى": "ي",                      # alef maqsura → ya
    "ة": "ه",                      # ta marbuta → ha
    "ؤ": "و", "ئ": "ي",            # hamza carriers
}


def normalize_text(text: str) -> str:
    """Normalize a transcription for fair WER comparison across engines."""
    text = unicodedata.normalize("NFC", text)
    text = _DIACRITICS.sub("", text)
    for src, dst in _ARABIC_EQUIV.items():
        text = text.replace(src, dst)
    text = _PUNCT.sub(" ", text)
    text = text.lower()
    return " ".join(text.split())


def wer_cer(reference: str, hypothesis: str) -> Tuple[float, float]:
    """Word and character error rates on normalized text."""
    # Lazy, like every optional dependency in this project: `jiwer` is used by
    # this function alone, and the STT benchmark deliberately never computed
    # WER/CER (`references.csv` is header-only — the criterion is preservation
    # of digits and French loanwords). A module-level import made the whole
    # metrics module — and therefore the text and image benchmarks, which only
    # need `extraction_accuracy` — unimportable without it.
    import jiwer

    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)
    if not ref:
        raise ValueError("empty reference transcription")
    return jiwer.wer(ref, hyp), jiwer.cer(ref, hyp)


def _field_matches(expected: Any, actual: Any) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual)) < 1e-6
    if isinstance(expected, str) and isinstance(actual, str):
        return normalize_text(expected) == normalize_text(actual)
    if isinstance(expected, list) and isinstance(actual, list):
        # The location fields (etages, ailes, locaux_techniques) are lists, and
        # `schemas._canon` keeps whatever order the model emitted — the journal
        # wants that order because it reads as a route through the building.
        # Grading is a different question: a model answering ["E1", "RDC"] to a
        # key of ["RDC", "E1"] named the same two floors and is right. Comparing
        # with `==` marked it wrong and quietly depressed every model's score on
        # every case with more than one floor.
        return sorted(map(str, expected)) == sorted(map(str, actual))
    return expected == actual


def extraction_accuracy(expected: Dict[str, Any], actual: Dict[str, Any]) -> Tuple[float, Dict[str, bool]]:
    """Fraction of expected fields the pipeline got right, plus per-field detail.

    Only fields present in `expected` are graded (the CSV author decides what
    counts); `resume` is free text and never graded.
    """
    graded = {k: v for k, v in expected.items() if k != "resume"}
    if not graded:
        raise ValueError("expected_json has no gradable fields")
    detail = {k: _field_matches(v, actual.get(k)) for k, v in graded.items()}
    return sum(detail.values()) / len(detail), detail
