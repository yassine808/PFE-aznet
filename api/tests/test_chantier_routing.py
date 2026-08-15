"""Chantier routing — the voice wins, then the org chart, then the last report.

The hazard this covers: `resolve_tab` used to start with
`if chantier: return chantier, chantier, []`, i.e. a passed-in name became a
Google Sheet tab verbatim. Nothing reached that branch while routing came from
the org chart; the moment the voice fills it, "la DGH", "d.g.h" and "DGH" would
be three tabs, three split bordereaux and a totals line scattered across them.
"""
import asyncio

import pytest

from app import journal, logs


class Reports:
    """Stand-in for the Rapports mirror, which is where sticky reads from."""

    def __init__(self, rows=()):
        self.rows = list(rows)

    def read_reports(self):
        return [dict(r) for r in self.rows]


@pytest.fixture
def mirror(monkeypatch):
    reports = Reports()
    monkeypatch.setattr(journal, "sheets", reports)
    return reports


# --- match before create ---------------------------------------------------

@pytest.mark.parametrize("spoken", ["DGH", "la DGH", "d.g.h", " dgh ", "LA D.G.H."])
def test_every_spelling_lands_on_the_existing_chantier(spoken, chantier_table, mirror):
    nom, tab, warnings, source = journal.resolve_site("NAROUZE", spoken)
    assert (nom, tab, warnings, source) == ("DGH", "DGH", [], "voix")
    assert chantier_table.created == []  # no fourth paper for a mis-transcription


def test_normalization_does_not_collapse_two_real_sites(chantier_table, mirror):
    """Conservative on purpose: no edit distance, no prefix matching. Merging
    two genuine sites is a silent wrong row; failing to merge is a visible
    unverified one."""
    assert logs.normalize_site_name("ACAPS") != logs.normalize_site_name("ACAPS 2")
    nom, tab, warnings, source = journal.resolve_site("NAROUZE", "ACAPS 2")
    assert (nom, source) == ("ACAPS 2", "nouveau")
    assert warnings == ["chantier_cree_non_verifie"]


def test_unknown_name_creates_the_site_marked_unverified(chantier_table, mirror):
    nom, tab, warnings, source = journal.resolve_site("NAROUZE", "Villa Nova")
    assert (nom, tab, source) == ("Villa Nova", "Villa Nova", "nouveau")
    assert warnings == ["chantier_cree_non_verifie"]
    assert chantier_table.created[0]["verifie"] is False
    # ...and the row it files is flagged, so the director confirms the site.
    assert "chantier_cree_non_verifie" in journal.REVIEW_WARNINGS


def test_read_only_resolution_never_writes_a_site(chantier_table, mirror):
    """The reply path asks the same question before /journal has committed to
    anything — it must not leave a chantier row behind for a report that may
    never be filed."""
    nom, _tab, warnings, source = journal.resolve_site("NAROUZE", "Villa Nova", create=False)
    assert (nom, source, warnings) == ("Villa Nova", "nouveau", ["chantier_cree_non_verifie"])
    assert chantier_table.created == []


# --- the fallbacks ---------------------------------------------------------

def test_org_chart_routes_when_nothing_was_said(chantier_table, mirror):
    chantier_table.org["NAROUZE"] = "DGH"
    assert journal.resolve_site("NAROUZE") == ("DGH", "DGH", [], "org")


def test_sticky_reuses_the_site_of_the_last_report(chantier_table, mirror):
    """No expiry: a technician silent for a month resumes their last site. The
    reply says so, which is what makes a wrong inheritance visible."""
    mirror.rows = [
        {"technicien": "NAROUZE", "chantier": "DGH", "date": "2026-07-01"},
        {"technicien": "AUTRE", "chantier": "ACAPS", "date": "2026-07-02"},
        {"technicien": "NAROUZE", "chantier": "ACAPS", "date": "2026-07-03"},
    ]
    nom, tab, warnings, source = journal.resolve_site("NAROUZE")
    assert (nom, tab, source) == ("ACAPS", "ACAPS", "repris")
    assert warnings == ["chantier_repris:ACAPS"]


def test_sticky_ignores_unrouted_rows(chantier_table, mirror):
    mirror.rows = [{"technicien": "NAROUZE", "chantier": journal.UNROUTED_TAB}]
    assert journal.resolve_site("NAROUZE")[3] == "aucun"


def test_no_site_and_no_history_still_lands_in_non_affecte(chantier_table, mirror):
    nom, tab, warnings, source = journal.resolve_site("INCONNU")
    assert (nom, tab, source) == (journal.UNROUTED_TAB, journal.UNROUTED_TAB, "aucun")
    assert warnings == ["chantier_non_defini"]


def test_a_spoken_name_is_not_a_tab_when_the_table_is_unreachable(monkeypatch, mirror):
    """With Postgres down we cannot tell a known site from a mis-transcription,
    so the name must NOT become a tab — that is the whole hazard."""
    def down(*_a, **_k):
        raise RuntimeError("postgres is down")

    monkeypatch.setattr(logs, "find_chantier_by_name", down)
    nom, tab, warnings, source = journal.resolve_site("NAROUZE", "la DGH")
    assert (nom, tab, warnings, source) == (
        journal.UNROUTED_TAB, journal.UNROUTED_TAB, ["chantier_non_resolu"], "aucun"
    )


# --- end to end through file_report ---------------------------------------

class FakeSheet:
    def __init__(self):
        self.rows = []
        self.appended = []
        self.mirrored = []

    def read_tab(self, tab):
        return [dict(r) for r in self.rows]

    def ensure_tab(self, tab, headers):
        pass

    def append_row(self, tab, values, headers):
        self.appended.append((tab, values))
        return len(self.appended) + 1

    def write_row(self, tab, row, values):
        pass

    def read_reports(self):
        return [dict(r) for r in self.mirrored]

    def append_report(self, values):
        self.mirrored.append(values)
        return len(self.mirrored) + 1


def test_file_report_routes_on_what_the_technician_said(chantier_table, monkeypatch):
    sheet = FakeSheet()
    monkeypatch.setattr(journal, "sheets", sheet)
    chantier_table.org["NAROUZE"] = "ACAPS"   # the org chart says otherwise
    result = journal.file_report({
        "date": "2026-08-15", "technicien": "NAROUZE",
        "report": {"cables_installes_m": 120, "resume": "Résumé.",
                   "chantier_mentionne": "la D.G.H"},
    })
    assert result["tab"] == "DGH" and result["chantier"] == "DGH"
    assert sheet.appended[0][0] == "DGH"


def test_file_report_flags_a_site_nobody_confirmed(chantier_table, monkeypatch):
    sheet = FakeSheet()
    monkeypatch.setattr(journal, "sheets", sheet)
    result = journal.file_report({
        "date": "2026-08-15", "technicien": "NAROUZE",
        "report": {"cables_installes_m": 120, "resume": "Résumé.",
                   "chantier_mentionne": "Villa Nova"},
    })
    assert result["tab"] == "Villa Nova"
    assert "chantier_cree_non_verifie" in result["warnings"]
    assert sheet.appended[0][1][journal.COL_FLAG] == "TRUE"


# --- the reply says which site was used ------------------------------------

def test_the_reply_says_when_the_site_was_inherited(chantier_table, monkeypatch):
    """n8n builds the reply out of `report.resume` and the routing decision is
    only taken later (reply-first ordering), so the note has to be added here
    or the technician never learns which site their report went to."""
    from app import main
    from app.schemas import ExtractedReport

    sheet = FakeSheet()
    sheet.mirrored = [{"technicien": "NAROUZE", "chantier": "ACAPS"}]
    monkeypatch.setattr(journal, "sheets", sheet)

    report = ExtractedReport(cables_installes_m=120, resume="120 m posés.")
    asyncio.run(main._note_inherited_chantier(report, "NAROUZE"))
    assert "ACAPS (repris du dernier rapport)" in report.resume


def test_a_stated_site_adds_no_note(chantier_table, monkeypatch):
    from app import main
    from app.schemas import ExtractedReport

    sheet = FakeSheet()
    monkeypatch.setattr(journal, "sheets", sheet)
    report = ExtractedReport(cables_installes_m=120, resume="120 m posés.",
                             chantier_mentionne="DGH")
    asyncio.run(main._note_inherited_chantier(report, "NAROUZE"))
    assert report.resume == "120 m posés."


# --- has_data: naming a site is not a report -------------------------------

def test_naming_a_site_alone_is_not_a_report():
    """`has_data` answers "is this a report?". "je suis à la DGH" reports no
    work, so it must stay `no_report_content` rather than opening a journal row
    of blanks — which is why chantier_mentionne is not in DATA_FIELDS."""
    from app.schemas import ExtractedReport

    assert not ExtractedReport(resume="Le technicien indique être à la DGH.",
                               chantier_mentionne="DGH").has_data()
