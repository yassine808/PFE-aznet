"""The Word renderer that replaced the browser one.

The point of these tests is coverage and survivability, not layout: the document
is now produced by the scheduler, where nobody is watching, so what has to hold
is that every column the period carries reaches the page — including the ones no
line of the renderer names — and that the bytes are a real .docx rather than a
plausible-looking blob.
"""
import io
import re
import zipfile

import pytest

from app import docx_report, journal


ROWS = [
    {
        "date": "2026-08-16", "technicien": "Yassine", "chantier": "DGH",
        "goulottes_m": "40", "cables_m": "120,5", "bureaux_termines": "3",
        "panneaux_raccordes": "1", "flag_review": "TRUE",
        # Two columns the pre-2026-08-16 renderer could not name, and so could
        # never print however much of them was installed.
        "fibre_m": "210", "pigtail_sc_u": "12",
    },
    {
        "date": "2026-08-16", "technicien": "Yassine", "chantier": "DGH",
        "goulottes_m": "10", "cables_m": "", "bureaux_termines": "",
        "panneaux_raccordes": "", "flag_review": "",
    },
    {
        "date": "2026-08-16", "technicien": "", "chantier": "ACAPS",
        "goulottes_m": "abc", "cables_m": "60", "bureaux_termines": "2",
        "panneaux_raccordes": "0", "flag_review": "oui", "fibre_m": "40",
    },
]

BODY = (
    "## Synthèse\nDeux interventions.\n\n"
    "## Détail par chantier\n- DGH — Yassine : 40 m de goulottes.\n\n"
    "## Problèmes et besoins\n- Aucun problème signalé.\n"
)


def test_headline_tiles_are_meta_only():
    """The tiles count what came in; the quantities have their own table.

    They used to name four Sheet columns, which fixed the report's vocabulary
    at the four quantities that existed in July.
    """
    figures = docx_report.compute_figures(ROWS)
    assert figures["Rapports"] == "3"
    # A blank technicien is not a person, so it is not counted as one — the
    # same rule `metrics.ts` applies on the page.
    assert figures["Techniciens"] == "1"
    assert figures["Chantiers"] == "2"
    # "TRUE" and "oui" both mean flagged; an empty cell does not.
    assert figures["À vérifier"] == "2"
    assert not any("m" == v[-1:] for v in figures.values())


def test_totals_cover_every_column_the_period_carries():
    """Including the ones no line of this renderer names."""
    totals = {label: (unit, total) for _c, label, unit, total in journal.rapports_totals(ROWS)}
    # A comma decimal is a number (the Sheet writes both forms); "abc" is
    # skipped rather than crashing or counting as zero.
    assert totals["Goulotte installée"] == ("m", 50.0)
    assert totals["Câble installé"] == ("m", 180.5)
    # Neither of these could appear in the document before 2026-08-16.
    assert totals["Fibre installée"] == ("m", 250.0)
    assert totals["Pigtail SC"] == ("u", 12.0)
    # A quantity nobody reported is absent, not a row of "0".
    assert "Onduleur" not in totals


def test_by_technician_groups_and_carries_its_own_totals():
    rows = docx_report.by_technician(ROWS)
    assert [r["name"] for r in rows] == ["Yassine", "—"]
    assert rows[0]["count"] == 2
    assert rows[0]["flagged"] == 1
    assert rows[0]["others"] == {"DGH"}
    # The split under a total is computed by the same call as the total, so the
    # two can never come from two different sums.
    assert rows[0]["totals"]["goulottes_m"] == 50.0
    assert rows[0]["totals"]["fibre_m"] == 210.0
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
    # The quantity table, with the director's own labels — and specifically the
    # ones the four hardcoded columns could never have produced.
    assert "Quantités déclarées" in document
    assert "Fibre installée" in document and "Pigtail SC" in document
    assert "Yassine 210" in document  # the per-technician split of that total
    # Two sites in ROWS, so the per-site rollup earns its place.
    assert "Activité par chantier" in document
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
    assert "Quantités déclarées" not in document


def test_flagged_rows_carry_their_reason_and_are_marked_red():
    """`motif_flag` has been written since 2026-08-09 and never shown anywhere.

    A count with no reason is a number the reader can only believe or ignore.
    """
    rows = [{**ROWS[0], "heure": "08:12", "motif_flag": "transcription courte"},
            ROWS[1], ROWS[2]]
    review = docx_report.flagged(rows)
    assert [r["motif"] for r in review] == ["transcription courte", "non précisé"]
    assert review[0]["heure"] == "08:12"

    blob = docx_report.build("R", BODY, "Rapport journalier", "2026-08-16", rows)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        document = archive.read("word/document.xml").decode("utf-8")
    assert "Points à vérifier" in document
    assert "transcription courte" in document
    # A flag is marked and drawn in the alert colour wherever it appears; the
    # marker is U+25B2, which Calibri itself carries, so it can never render as
    # an empty box the way a fallback-dependent glyph can.
    reds = re.findall(r"<w:r>(?:(?!</w:r>).)*DC2626(?:(?!</w:r>).)*</w:r>", document, re.S)
    assert reds, "no alert-coloured run in a report with two flagged rows"
    assert docx_report.ALERT_MARK in document


def test_provenance_separates_who_wrote_it_from_when_it_was_rendered():
    """The export button can render a document days after the text was written,
    so one timestamp cannot honestly stand for both facts."""
    auto = docx_report.build("R", BODY, "Rapport journalier", "2026-08-16", ROWS)
    hand = docx_report.build("R", BODY, "Rapport journalier", "2026-08-16", ROWS,
                             author="Yassine")
    read = lambda b: zipfile.ZipFile(io.BytesIO(b)).read("word/document.xml").decode()
    assert "rapport automatique" in read(auto)
    assert "établi par Yassine" in read(hand)
    for blob in (auto, hand):
        assert "document généré le" in read(blob)


def test_no_flags_means_no_review_section():
    """An empty heading reads as an unanswered question, not as 'nothing to do'."""
    clean = [{**r, "flag_review": ""} for r in ROWS]
    blob = docx_report.build("R", BODY, "Rapport journalier", "2026-08-16", clean)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        document = archive.read("word/document.xml").decode("utf-8")
    assert "Points à vérifier" not in document
    assert "DC2626" not in document  # and no stray alert colour anywhere


def test_single_site_skips_the_per_chantier_table():
    """One row restating the tile above it is not worth a heading."""
    one_site = [r for r in ROWS if r["chantier"] == "DGH"]
    blob = docx_report.build("R", BODY, "Rapport journalier", "2026-08-16", one_site)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        document = archive.read("word/document.xml").decode("utf-8")
    assert "Activité par technicien" in document
    assert "Activité par chantier" not in document


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
