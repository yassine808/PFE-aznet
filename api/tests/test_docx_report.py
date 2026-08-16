"""The Word renderer that replaced the browser one.

The point of these tests is parity and survivability, not layout: the document
is now produced by the scheduler, where nobody is watching, so what has to hold
is that the figures match the arithmetic the dashboard shows and that the bytes
are a real .docx rather than a plausible-looking blob.
"""
import io
import zipfile

import pytest

from app import docx_report


ROWS = [
    {
        "date": "2026-08-16", "technicien": "Yassine", "chantier": "DGH",
        "goulottes_m": "40", "cables_m": "120,5", "bureaux_termines": "3",
        "panneaux_raccordes": "1", "flag_review": "TRUE",
    },
    {
        "date": "2026-08-16", "technicien": "Yassine", "chantier": "DGH",
        "goulottes_m": "10", "cables_m": "", "bureaux_termines": "",
        "panneaux_raccordes": "", "flag_review": "",
    },
    {
        "date": "2026-08-16", "technicien": "", "chantier": "",
        "goulottes_m": "abc", "cables_m": "60", "bureaux_termines": "2",
        "panneaux_raccordes": "0", "flag_review": "oui",
    },
]

BODY = (
    "## Synthèse\nDeux interventions.\n\n"
    "## Détail par chantier\n- DGH — Yassine : 40 m de goulottes.\n\n"
    "## Problèmes et besoins\n- Aucun problème signalé.\n"
)


def test_figures_match_the_dashboards_arithmetic():
    figures = docx_report.compute_figures(ROWS)
    # A comma decimal is a number (the Sheet writes both forms); "abc" is 0,
    # not a crash — a malformed cell must not cost the whole report.
    assert figures["Goulottes"] == "50 m"
    assert figures["Câbles"] == "180.5 m"
    assert figures["Rapports"] == "3"
    # A blank technicien/chantier is not a person or a site, so it is not
    # counted as one — the same rule `metrics.ts` applies on the page.
    assert figures["Techniciens"] == "1"
    assert figures["Chantiers"] == "1"
    # "TRUE" and "oui" both mean flagged; an empty cell does not.
    assert figures["À vérifier"] == "2"


def test_by_technician_groups_and_sorts_by_volume():
    rows = docx_report.by_technician(ROWS)
    assert [r["name"] for r in rows] == ["Yassine", "—"]
    assert rows[0] == {"name": "Yassine", "count": 2, "goulottes": 50.0, "flagged": 1}
    # An unattributed row keeps its own line rather than being dropped: it is
    # still work that was reported, and hiding it would make the table's
    # rapport count disagree with the figure above it.
    assert rows[1]["count"] == 1


def test_build_produces_a_real_docx_carrying_the_report():
    blob = docx_report.build(
        "Rapport journalier — 2026-08-16", BODY,
        "Rapport journalier", "2026-08-16", ROWS, author="Yassine",
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = archive.namelist()
        assert "word/document.xml" in names
        assert "word/header1.xml" in names  # the running AZNET header
        assert "word/footer1.xml" in names  # period + page numbers
        document = archive.read("word/document.xml").decode("utf-8")
        footer = archive.read("word/footer1.xml").decode("utf-8")
    assert "Synthèse" in document
    assert "Activité par technicien" in document
    # A live field, not a frozen page count: the footer stays right after the
    # document is edited or printed to another paper size.
    assert "NUMPAGES" in footer and "2026-08-16" in footer
    # The `## ` and `- ` markers are structure, not literal text: shipping them
    # verbatim is exactly what the mail did before `render_rich_text`.
    assert "## " not in document
    assert "Aucun problème signalé" in document


def test_build_without_rows_still_writes_the_report():
    """A report whose rows vanished underneath it is still the report.

    The figures grid and the per-technician table simply do not appear; the
    prose someone wrote must never be lost to an empty aggregate.
    """
    blob = docx_report.build("Rapport", BODY, "Rapport journalier", "2026-08-16", [])
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        document = archive.read("word/document.xml").decode("utf-8")
    assert "Synthèse" in document
    assert "Activité par technicien" not in document


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Rapport journalier — 2026-07-25", "rapport-journalier-2026-07-25"),
        ("  ÉTÉ / hiver  ", "ete-hiver"),
        ("———", "rapport"),  # never an empty filename
    ],
)
def test_slug(title, expected):
    assert docx_report.slug(title) == expected
