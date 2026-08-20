"""One message, several floors, several rows — and the totals still add up.

Until 2026-08-20 a report covering three floors was stored as one row with one
combined figure: "30 au premier, 50 au deuxième" became `cables_installes_m =
80` and `etages = [E1, E2]`. The 80 was arithmetic the technician never did, and
the per-floor figures were gone — which is exactly what the director opens this
file to see.

The split is only safe because of one existing property: `qte_installee` and the
totals line sum every row on the tab. So N rows carrying a share each add to the
same figure one row carrying the whole would have — *provided* the split
REPLACES the quantities rather than sitting beside them. That is the invariant
most of these tests defend, because breaking it doubles every metre on the site
and nothing about the sheet would look wrong.
"""
import pytest

from app import journal
from app.schemas import ExtractedReport

from tests.test_journal import FakeSheet  # the shared stand-in


def _report(**fields):
    fields.setdefault("resume", "Résumé.")
    return ExtractedReport(**fields)


def _write(fake, report, monkeypatch, technicien="NAROUZE", metadata=None):
    monkeypatch.setattr(journal, "sheets", fake)
    monkeypatch.setattr(journal, "jh_limits", dict)
    return journal.write_report("DGH", "2026-08-20", technicien, "DGH", report,
                                metadata or {}, [])


def _appended(fake):
    """The rows written to the journal tab, in order."""
    return [values for _tab, values in fake.appended]


CABLE = journal.NUMERIC_COLUMNS["cables_installes_m"]
PRISES = journal.NUMERIC_COLUMNS["prises_connectees"]
ARRET = journal.NUMERIC_COLUMNS["temps_arret_min"]


# ── the split itself ───────────────────────────────────────────────────────

def test_two_floors_become_two_rows(monkeypatch):
    fake = FakeSheet()
    _write(fake, _report(ventilation=[
        {"zone": "E1", "libelle": "premier étage", "quantites": {"cables_installes_m": 30}},
        {"zone": "E2", "libelle": "deuxième", "quantites": {"cables_installes_m": 50}},
    ]), monkeypatch)
    rows = _appended(fake)
    assert len(rows) == 2
    assert [r[CABLE] for r in rows] == ["30", "50"]


def test_each_row_names_its_own_zone_in_the_technicians_words(monkeypatch):
    """The label is what was said; the canonical code is only the grouping key."""
    fake = FakeSheet()
    _write(fake, _report(ventilation=[
        {"zone": "E1", "libelle": "premier étage", "quantites": {"cables_installes_m": 30}},
        {"zone": "E2", "quantites": {"cables_installes_m": 50}},
    ]), monkeypatch)
    rows = _appended(fake)
    assert rows[0][journal.COL_ZONE] == "premier étage"
    # No label given: the code stands in rather than leaving the cell blank.
    assert rows[1][journal.COL_ZONE] == "E2"


def test_the_etage_column_names_this_row_not_the_whole_message(monkeypatch):
    """A row saying 'E1, E2' while carrying only E1's metres is the combining
    this split exists to end."""
    fake = FakeSheet()
    _write(fake, _report(etages=["E1", "E2"], ventilation=[
        {"zone": "E1", "quantites": {"cables_installes_m": 30}},
        {"zone": "E2", "quantites": {"cables_installes_m": 50}},
    ]), monkeypatch)
    col = journal.LIST_COLUMNS["etages"]
    assert [r[col] for r in _appended(fake)] == ["E1", "E2"]


def test_a_single_zone_still_splits(monkeypatch):
    """Naming the floor is information the combined row never carried."""
    fake = FakeSheet()
    _write(fake, _report(ventilation=[
        {"zone": "E2", "libelle": "deuxième étage", "quantites": {"cables_installes_m": 40}},
    ]), monkeypatch)
    rows = _appended(fake)
    assert len(rows) == 1 and rows[0][journal.COL_ZONE] == "deuxième étage"


def test_no_ventilation_writes_one_row_as_before(monkeypatch):
    fake = FakeSheet()
    _write(fake, _report(cables_installes_m=80), monkeypatch)
    rows = _appended(fake)
    assert len(rows) == 1 and rows[0][CABLE] == "80"


# ── the invariant: nothing is counted twice ────────────────────────────────

def test_the_split_replaces_the_stated_total(monkeypatch):
    """THE load-bearing test. A stated 80 plus rows of 30 and 50 would make the
    bordereau read 160 for a day that installed 80, and no cell would look wrong."""
    fake = FakeSheet()
    _write(fake, _report(cables_installes_m=80, ventilation=[
        {"zone": "E1", "quantites": {"cables_installes_m": 30}},
        {"zone": "E2", "quantites": {"cables_installes_m": 50}},
    ]), monkeypatch)
    rows = _appended(fake)
    assert sum(float(r[CABLE]) for r in rows) == 80.0


def test_a_day_level_quantity_lands_once_not_per_floor(monkeypatch):
    """Ninety minutes lost belongs to the day. Repeated on three rows it becomes
    four and a half hours; dropped because a ventilation exists, it is gone."""
    fake = FakeSheet()
    _write(fake, _report(temps_arret_min=90, ventilation=[
        {"zone": "E1", "quantites": {"cables_installes_m": 30}},
        {"zone": "E2", "quantites": {"cables_installes_m": 50}},
    ]), monkeypatch)
    rows = _appended(fake)
    assert rows[0][ARRET] == "90"
    assert ARRET not in rows[1] or not rows[1].get(ARRET)


def test_a_quantity_split_on_one_field_does_not_drag_another(monkeypatch):
    """Cable is per floor, prises were stated for the day: both survive, once."""
    fake = FakeSheet()
    _write(fake, _report(prises_connectees=14, ventilation=[
        {"zone": "E1", "quantites": {"cables_installes_m": 30}},
        {"zone": "E2", "quantites": {"cables_installes_m": 50}},
    ]), monkeypatch)
    rows = _appended(fake)
    assert rows[0][PRISES] == "14"
    assert not rows[1].get(PRISES)


def test_the_transcript_is_written_once(monkeypatch):
    """Three rows repeating the whole message read as three reports."""
    fake = FakeSheet()
    # The transcript reaches write_report as metadata, the way file_report
    # passes it — report_cells never carries it.
    _write(fake, _report(ventilation=[
        {"zone": "E1", "quantites": {"cables_installes_m": 30}},
        {"zone": "E2", "quantites": {"cables_installes_m": 50}},
    ]), monkeypatch, metadata={journal.COL_RESUME: "Résumé.",
                               journal.COL_RAPPORT: "Le message entier."})
    rows = _appended(fake)
    assert rows[0].get(journal.COL_RESUME) == "Résumé."
    assert rows[0].get(journal.COL_RAPPORT) == "Le message entier."
    assert not rows[1].get(journal.COL_RESUME)
    assert not rows[1].get(journal.COL_RAPPORT)


# ── the disagreement ───────────────────────────────────────────────────────

def test_a_total_that_disagrees_with_its_breakdown_warns(monkeypatch):
    """Breakdown wins, but the gap is reported: one of the two is wrong and only
    the person who was there can say which. Same contract as stock_ecart."""
    fake = FakeSheet()
    _row, warnings = _write(fake, _report(cables_installes_m=100, ventilation=[
        {"zone": "E1", "quantites": {"cables_installes_m": 30}},
        {"zone": "E2", "quantites": {"cables_installes_m": 50}},
    ]), monkeypatch)
    gaps = [w for w in warnings if w.startswith("ventilation_ecart")]
    assert gaps and "cables_installes_m" in gaps[0]
    # The rows still carry the breakdown, not the disputed total.
    assert sum(float(r[CABLE]) for r in _appended(fake)) == 80.0


def test_agreement_raises_nothing(monkeypatch):
    fake = FakeSheet()
    _row, warnings = _write(fake, _report(cables_installes_m=80, ventilation=[
        {"zone": "E1", "quantites": {"cables_installes_m": 30}},
        {"zone": "E2", "quantites": {"cables_installes_m": 50}},
    ]), monkeypatch)
    assert not [w for w in warnings if w.startswith("ventilation_ecart")]


def test_the_gap_warning_has_a_human_label():
    """An unlabelled key prints raw in Motif du flag, which is what that column
    exists to avoid."""
    assert journal.WARNING_LABELS["ventilation_ecart"]
    assert "ventilation_ecart" in journal.flag_reason(["ventilation_ecart:x:1"]) or \
        journal.WARNING_LABELS["ventilation_ecart"] in journal.flag_reason(["ventilation_ecart:x:1"])


# ── the schema contract ────────────────────────────────────────────────────

def test_an_unknown_quantity_field_raises(monkeypatch):
    """The chain retries rather than filing a figure nothing can join to a
    contract line — the rule livraisons and etages already follow."""
    with pytest.raises(Exception):
        _report(ventilation=[{"zone": "E1", "quantites": {"pas_un_champ": 3}}])


def test_a_zone_with_no_quantities_is_not_a_row(monkeypatch):
    """'On est passés au troisième' is not a report about the third floor."""
    fake = FakeSheet()
    _write(fake, _report(cables_installes_m=40, ventilation=[
        {"zone": "E3", "quantites": {}},
    ]), monkeypatch)
    rows = _appended(fake)
    assert len(rows) == 1 and rows[0][CABLE] == "40"
