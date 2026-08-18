"""Journal row assembly: appended rows and stock reconciliation.

Pure logic, no Sheets and no Postgres — these are the two rules that make the
director's file correct, so they get tested where they can fail fast.
"""
import pytest

from app import journal

from app.journal import (
    HEADERS,
    CHEF_COLUMNS,
    correlation_of,
    reconcile_stock,
    report_cells,
)
from app.schemas import ExtractedReport


def rep(**kw):
    kw.setdefault("resume", "Résumé.")
    return ExtractedReport(**kw)


# --- headers --------------------------------------------------------------


def test_headers_are_unique():
    assert len(HEADERS) == len(set(HEADERS))


def test_director_columns_come_before_pipeline_metadata():
    assert HEADERS[0] == "Date"
    assert HEADERS.index("EQUIPE") < HEADERS.index("Câble installé")
    assert HEADERS.index("Remarques") < HEADERS.index("Correlation id")


# --- report_cells ---------------------------------------------------------


def test_quantities_map_to_the_directors_columns():
    cells = report_cells(rep(cables_installes_m=202, prises_connectees=14,
                             connexions_optiques_brins=48))
    assert cells["Câble installé"] == "202"
    assert cells["Connexion des prises informatiques"] == "14"
    assert cells["Connexion optique"] == "48"


def test_absent_fields_produce_no_cell_at_all():
    """An empty cell and a cell holding 0 are different claims."""
    cells = report_cells(rep(cables_installes_m=100))
    assert "Goulotte installée" not in cells


def test_explicit_zero_is_written():
    assert report_cells(rep(goulotte_m=0))["Goulotte installée"] == "0"


def test_locations_join_as_the_file_writes_them():
    cells = report_cells(rep(etages=["RDC", "E1"], ailes=["Droite", "Gauche"]))
    assert cells["ETAGE"] == "RDC, E1"
    assert cells["AILE"] == "Droite, Gauche"


def test_three_prise_stages_are_three_columns():
    cells = report_cells(rep(prises_connectees=14, panneaux_prises_brassees=17,
                             prises_testees=15))
    assert cells["Connexion des prises informatiques"] == "14"
    assert cells["Connexion des panneaux de brassage"] == "17"
    assert cells["Test et étiquetage"] == "15"


# --- stock reconciliation -------------------------------------------------


def test_stock_computed_from_baseline_when_unreported():
    cells, warnings = reconcile_stock(
        rep(cables_installes_m=179), {"Reste du câble (Stock)": "2274"}
    )
    assert cells["Reste du câble (Stock)"] == "2095"
    assert warnings == []


def test_reported_stock_wins_and_agrees_silently():
    cells, warnings = reconcile_stock(
        rep(cables_installes_m=179, stock_cable_m=2095),
        {"Reste du câble (Stock)": "2274"},
    )
    assert cells["Reste du câble (Stock)"] == "2095"
    assert warnings == []


def test_discrepancy_is_flagged_not_resolved():
    """A delivery or a loss — only a human can say which, so we surface it."""
    cells, warnings = reconcile_stock(
        rep(cables_installes_m=179, stock_cable_m=2400),
        {"Reste du câble (Stock)": "2274"},
    )
    assert cells["Reste du câble (Stock)"] == "2400"
    assert warnings == ["stock_ecart:Reste du câble (Stock):305"]


def test_shortfall_is_flagged_with_a_negative_delta():
    _, warnings = reconcile_stock(
        rep(cables_installes_m=100, stock_cable_m=1900),
        {"Reste du câble (Stock)": "2274"},
    )
    assert warnings == ["stock_ecart:Reste du câble (Stock):-274"]


def test_no_baseline_and_nothing_reported_leaves_the_cell_empty():
    cells, warnings = reconcile_stock(rep(cables_installes_m=100), {})
    assert cells == {}
    assert warnings == []


def test_first_ever_report_sets_the_baseline():
    cells, warnings = reconcile_stock(rep(stock_cable_m=500), {})
    assert cells["Reste du câble (Stock)"] == "500"
    assert warnings == []


def test_stock_never_goes_negative():
    cells, _ = reconcile_stock(
        rep(cables_installes_m=300), {"Reste du câble (Stock)": "100"}
    )
    assert cells["Reste du câble (Stock)"] == "0"


def test_messy_sheet_cell_is_parsed():
    cells, _ = reconcile_stock(
        rep(cables_installes_m=50), {"Reste du câble (Stock)": "2 274 m"}
    )
    assert cells["Reste du câble (Stock)"] == "2224"


def test_unparseable_cell_is_not_treated_as_zero():
    """'68 m + 33 m' appears in the real file — better empty than wrong."""
    cells, _ = reconcile_stock(
        rep(cables_installes_m=50), {"Reste du câble (Stock)": "beaucoup"}
    )
    assert "Reste du câble (Stock)" not in cells


# --- merge: the second report of the day ----------------------------------


def test_blocker_fields_land_in_their_own_columns():
    cells = report_cells(rep(
        temps_arret_min=90, motif_arret="Bureaux fermés",
        besoins="Connecteurs RJ45", prochaines_etapes="E3 demain",
    ))
    assert cells["Arrêt (min)"] == "90"
    assert cells["MOTIF D'ARRÊT"] == "Bureaux fermés"
    assert cells["BESOINS / MATÉRIEL"] == "Connecteurs RJ45"
    assert cells["PROCHAINES ÉTAPES"] == "E3 demain"


# --- the Sheets round trip (fake tab, no Google) --------------------------


class FakeSheet:
    """Minimal stand-in: a tab is a header list plus rows of dicts."""

    def __init__(self, rows=None):
        self.rows = rows or []
        self.created = []
        self.appended = []
        self.written = []
        self.marked = []
        self.mirrored = []
        self.calls = []  # every Google round trip, in order

    def read_tab(self, tab):
        self.calls.append(("read_tab", tab))
        return [dict(r) for r in self.rows]

    def ensure_tab(self, tab, headers):
        self.calls.append(("ensure_tab", tab))
        self.created.append((tab, tuple(headers)))

    def append_row(self, tab, values, headers):
        self.appended.append((tab, values))
        row = dict(values)
        row["_row"] = len(self.rows) + 2
        self.rows.append(row)
        return row["_row"]

    def write_row(self, tab, row, values):
        self.written.append((tab, row, values))

    def mark_increment(self, tab, row, columns):
        self.marked.append((tab, row, list(columns)))

    def read_reports(self):
        """The flat Rapports mirror — read by the sticky-chantier fallback."""
        self.calls.append(("read_reports", None))
        return [dict(r) for r in self.mirrored]

    def append_report(self, values):
        """The Rapports mirror append — file_report calls this best-effort."""
        self.mirrored.append(values)
        return len(self.rows) + 2


@pytest.fixture
def fake(monkeypatch, chantier_table):
    from app import journal as mod

    sheet = FakeSheet()
    monkeypatch.setattr(mod, "sheets", sheet)
    # The JH convention lives in app_settings; without this the row assembly
    # would reach for Postgres, which these tests deliberately do not have.
    monkeypatch.setattr(mod, "jh_limits", dict)
    # `chantier_table` is not optional: since 2026-08-15 a chantier is resolved
    # against the table rather than trusted as a tab name, so without it these
    # rows would all land in `Non affecté` instead of on DGH.
    return sheet


def test_first_report_of_the_day_appends(fake):
    from app.journal import write_report

    row, warnings = write_report("DGH", "2026-08-05", "NAROUZE", "DGH",
                                 rep(cables_installes_m=120))
    assert row == 2
    assert fake.appended[0][0] == "DGH"
    assert fake.appended[0][1]["Câble installé"] == "120"
    assert fake.appended[0][1]["Chantier"] == "DGH"
    assert warnings == []


def test_tab_is_created_on_demand(fake):
    from app.journal import write_report, HEADERS

    write_report("Extralait", "2026-08-05", "DRISS", "Extralait", rep())
    assert fake.created == [("Extralait", HEADERS)]


def test_second_report_same_day_gets_its_own_row(fake):
    """The afternoon note appends; it never rewrites the morning's row.

    This is the whole point of dropping accumulation: 120 then 160 used to
    become a single cell reading 280, and if the 160 was a mis-transcription
    the 120 was gone with no way to tell. Two rows keep both figures, and the
    bordereau still reads 280 because it sums rows.
    """
    from app.journal import write_report

    first, _ = write_report("DGH", "2026-08-05", "NAROUZE", "DGH",
                            rep(cables_installes_m=120))
    second, _ = write_report("DGH", "2026-08-05", "NAROUZE", "DGH",
                             rep(cables_installes_m=160))
    assert (first, second) == (2, 3)
    # Nothing was rewritten in place.
    assert fake.written == []
    assert fake.rows[-1]["Câble installé"] == "160"
    assert fake.rows[-2]["Câble installé"] == "120"


def test_a_different_technician_gets_their_own_row(fake):
    from app.journal import write_report

    write_report("DGH", "2026-08-05", "NAROUZE", "DGH", rep(cables_installes_m=120))
    row, _ = write_report("DGH", "2026-08-05", "HOUCINE", "DGH",
                          rep(cables_installes_m=160))
    assert row == 3
    assert fake.written == []


def test_same_technician_next_day_gets_a_new_row(fake):
    from app.journal import write_report

    write_report("DGH", "2026-08-05", "NAROUZE", "DGH", rep(cables_installes_m=120))
    row, _ = write_report("DGH", "2026-08-06", "NAROUZE", "DGH",
                          rep(cables_installes_m=160))
    assert row == 3


def test_date_format_drift_still_finds_the_row(fake):
    """We write '2026-08-05'; Google hands back '05/08/2026'.

    Rows are appended now, so this no longer decides where a report lands --
    but the day still has to be recognisable to anything asking "did this
    technician report today?", so the normalisation is pinned here.
    """
    from app.journal import find_row

    fake.rows.append({"Date": "05/08/2026", "Technicien": "NAROUZE",
                      "Câble installé": "120", "_row": 2})
    row, cells = find_row("DGH", "2026-08-05", "NAROUZE", fake.rows)
    assert row == 2
    assert cells["Câble installé"] == "120"


def test_technician_name_matching_ignores_case(fake):
    from app.journal import find_row

    fake.rows.append({"Date": "2026-08-05", "Technicien": "narouze", "_row": 2})
    row, _ = find_row("DGH", "2026-08-05", "NAROUZE", fake.rows)
    assert row == 2


def test_stock_baseline_comes_from_the_whole_tab_not_just_this_person(fake):
    """Two technicians cut from the same reel — stock is site-wide."""
    from app.journal import write_report

    fake.rows.append({"Date": "2026-08-04", "Technicien": "DRISS",
                      "Reste du câble (Stock)": "2274", "_row": 2})
    write_report("DGH", "2026-08-05", "NAROUZE", "DGH", rep(cables_installes_m=179))
    assert fake.appended[0][1]["Reste du câble (Stock)"] == "2095"


def test_merge_uses_the_site_latest_reading_not_the_own_staler_row(fake):
    """Merging into today's own row must not resurrect that row's staler stock
    when a colleague wrote a fresher reading behind it — stock is site-wide."""
    from app.journal import write_report

    fake.rows.append({"Date": "2026-08-05", "Technicien": "NAROUZE",
                      "Reste du câble (Stock)": "2274", "_row": 2})
    fake.rows.append({"Date": "2026-08-05", "Technicien": "DRISS",
                      "Reste du câble (Stock)": "2095", "_row": 3})
    _, warnings = write_report("DGH", "2026-08-05", "NAROUZE", "DGH",
                               rep(cables_installes_m=16, stock_cable_m=2043))

    # Baseline = site latest 2095 - 16 installed = 2079 expected; 2043 is a
    # -36 ecart. The own row's 2274 would have claimed -215.
    assert warnings == ["stock_ecart:Reste du câble (Stock):-36"]


def test_stock_discrepancy_surfaces_as_a_warning(fake):
    from app.journal import write_report

    fake.rows.append({"Date": "2026-08-04", "Technicien": "DRISS",
                      "Reste du câble (Stock)": "2274", "_row": 2})
    _, warnings = write_report("DGH", "2026-08-05", "NAROUZE", "DGH",
                               rep(cables_installes_m=179, stock_cable_m=2400))
    assert warnings == ["stock_ecart:Reste du câble (Stock):305"]


def test_metadata_columns_ride_along(fake):
    from app.journal import write_report, COL_CANAL, COL_RESUME

    write_report("DGH", "2026-08-05", "NAROUZE", "DGH", rep(),
                 metadata={COL_CANAL: "telegram", COL_RESUME: "Résumé."})
    assert fake.appended[0][1][COL_CANAL] == "telegram"


# --- the Rapports mirror (the dashboard's flat feed) ------------------------


def test_rapports_cells_map_the_new_schema_onto_old_columns():
    """The mapping the old n8n expressions used to be — testable here."""
    from app.journal import _rapports_cells

    payload = {
        "date": "2026-08-05", "heure": "09:15", "canal": "telegram",
        "technicien": "NAROUZE", "role": "technicien", "chantier": "DGH",
        "rapport_complet": "…", "confidence": 0.92, "lien_audio": "https://x",
        "stt_engine": "groq", "warnings": ["short_transcription"],
        "report": {
            "goulotte_m": 150, "cables_installes_m": 800,
            "prises_connectees": 14, "panneaux_prises_brassees": 12,
            "temps_arret_min": 90, "motif_arret": "Bureaux fermés au RDC.",
            "besoins": "Connecteurs RJ45.", "prochaines_etapes": "On attaque E3.",
            "remarques": "Bureaux fermés au RDC.",
            "resume": "Résumé professionnel.",
        },
    }
    cells = _rapports_cells(payload, "DGH", ["short_transcription"])
    assert cells["goulottes_m"] == 150
    assert cells["cables_m"] == 800
    assert cells["bureaux_termines"] == 14
    assert cells["panneaux_raccordes"] == 12
    assert cells["arrets_min"] == 90
    assert cells["besoins"] == "Connecteurs RJ45."
    assert cells["observations"] == "Bureaux fermés au RDC."
    assert cells["heure"] == "09:15"
    assert cells["chantier"] == "DGH"
    assert cells["STT_model"] == "groq"
    assert cells["flag_review"] is True


def test_rapports_cells_leave_unmapped_fields_blank():
    from app.journal import _rapports_cells

    cells = _rapports_cells(
        {"report": {"cables_prepares_m": 50, "resume": "Résumé."}}, "DGH", []
    )
    # Prepared cable has no old column; absence must not invent one.
    assert "cables_m" not in cells
    assert "goulottes_m" not in cells
    assert cells["flag_review"] is False


def test_file_report_mirrors_to_the_flat_tab(fake):
    """The journal write and the dashboard mirror happen in one call — n8n no
    longer owns the Rapports append, so it can no longer drift."""
    from app.journal import file_report

    result = file_report({
        "date": "2026-08-05", "heure": "09:15", "canal": "telegram",
        "technicien": "NAROUZE", "chantier": "DGH",
        "rapport_complet": "…", "warnings": ["short_transcription"],
        "report": {"goulotte_m": 150, "resume": "Pose de 150 m."},
    })
    assert result["tab"] == "DGH"
    assert fake.appended[0][0] == "DGH"          # journal row
    assert fake.mirrored[-1]["goulottes_m"] == 150  # Rapports row
    assert fake.mirrored[-1]["chantier"] == "DGH"
    assert fake.mirrored[-1]["flag_review"] is True
    assert result["rapports_row"] == 3  # the mirror's row number, for /supprimer


def test_mirror_failure_never_costs_the_journal_row(fake, monkeypatch):
    """The mirror is best-effort: a rejected flat append must not 502 a report
    that already landed on the journal tab."""
    from app import journal as mod

    def boom(values):
        raise ValueError("google says no")

    monkeypatch.setattr(mod.sheets, "append_report", boom)
    result = mod.file_report({
        "date": "2026-08-05", "technicien": "NAROUZE", "chantier": "DGH",
        "report": {"cables_installes_m": 120, "resume": "Résumé."},
    })
    assert result["row"] == 2
    assert fake.appended[0][1]["Câble installé"] == "120"
    assert result["rapports_row"] is None  # nothing to clear later


# --- the tab round trip ----------------------------------------------------
# Two properties of the Google traffic itself, both invisible to the assertions
# above because FakeSheet answers anything instantly.


def test_the_tab_is_created_before_it_is_read(fake):
    """`read_tab` on a tab Google has never heard of is a 400, not an empty
    list, so a chantier added in the dashboard would 502 on its first message
    and fail identically on every retry after that."""
    from app.journal import file_report

    file_report({
        "date": "2026-08-05", "technicien": "NAROUZE", "chantier": "Nouveau",
        "report": {"cables_installes_m": 120, "resume": "Résumé."},
    })
    kinds = [name for name, _ in fake.calls]
    assert kinds.index("ensure_tab") < kinds.index("read_tab")


def test_filing_a_report_reads_the_tab_once(fake):
    """The row lookup, the duplicate check and the stock baseline all want the
    same rows. Reading per question costs a full-tab round trip each time, on
    the path a technician is waiting on."""
    from app.journal import file_report

    file_report({
        "date": "2026-08-05", "technicien": "NAROUZE", "chantier": "DGH",
        "report": {"cables_installes_m": 120, "resume": "Résumé."},
    })
    assert [c for c in fake.calls if c[0] == "read_tab"] == [("read_tab", "DGH")]


# --- retry idempotency -----------------------------------------------------
# A Sheets failure that Google actually committed (5xx after write, lost
# response) leaves the parked payload re-filing onto the row that exists. The
# correlation cell records every message that touched the row, so membership
# means "already filed" and the merge is skipped instead of double-counting.


def test_refiling_the_same_message_merges_nothing(fake):
    """The drain re-files a parked payload with its original correlation_id —
    the row already has it, so the retry must not add the numbers twice."""
    from app.journal import file_report

    first = file_report({
        "date": "2026-08-05", "technicien": "NAROUZE", "chantier": "DGH",
        "correlation_id": "corr-abc",
        "report": {"cables_installes_m": 120, "resume": "Résumé."},
    })
    retry = file_report({
        "date": "2026-08-05", "technicien": "NAROUZE", "chantier": "DGH",
        "correlation_id": "corr-abc",
        "report": {"cables_installes_m": 120, "resume": "Résumé."},
    })
    assert retry["row"] == first["row"]
    assert retry["duplicate"] is True
    assert retry["rapports_row"] is not None  # mirror re-appended for the feed
    assert len(fake.mirrored) == 2  # exactly one Rapports row per file_report
    assert len(fake.appended) == 1  # journal row appended once, never twice
    assert fake.written == []  # no merge write, so the total stays 120


def test_a_second_message_the_same_day_appends_its_own_row(fake):
    """A real second report is not a duplicate: it gets its own row.

    Both rows keep their own correlation id, which is what makes the retry
    check below able to tell a replay from a genuine follow-up.
    """
    from app.journal import file_report

    first = file_report({
        "date": "2026-08-05", "technicien": "NAROUZE", "chantier": "DGH",
        "correlation_id": "corr-abc",
        "report": {"cables_installes_m": 120, "resume": "Résumé."},
    })
    second = file_report({
        "date": "2026-08-05", "technicien": "NAROUZE", "chantier": "DGH",
        "correlation_id": "corr-def",
        "report": {"cables_installes_m": 160, "resume": "Suite."},
    })
    assert second["duplicate"] is False
    assert second["row"] != first["row"]
    assert fake.written == []          # nothing rewritten in place
    # The cell is a link to the message in the inbox; the id is its text.
    assert correlation_of(fake.rows[-1]["Correlation id"]) == "corr-def"
    assert fake.rows[-1]["Câble installé"] == "160"
    assert fake.rows[-2]["Câble installé"] == "120"


def test_refile_without_correlation_cannot_be_deduplicated(fake):
    """No correlation_id (e.g. a dashboard submission) cannot be proven a
    duplicate, so it lands as its own row rather than being silently dropped.

    Appending is the safe failure here: a spurious extra row is visible and
    deletable, where a swallowed report is neither.
    """
    from app.journal import file_report

    first = file_report({
        "date": "2026-08-05", "technicien": "NAROUZE", "chantier": "DGH",
        "report": {"cables_installes_m": 120, "resume": "Résumé."},
    })
    again = file_report({
        "date": "2026-08-05", "technicien": "NAROUZE", "chantier": "DGH",
        "report": {"cables_installes_m": 160, "resume": "Suite."},
    })
    assert again["duplicate"] is False
    assert again["row"] != first["row"]


def test_excel_serial_date_matches_the_same_day(fake):
    """The director's own file stores 46174, not a date string."""
    from app.journal import find_row

    fake.rows.append({"Date": "46174", "Technicien": "NAROUZE", "_row": 2})
    row, _ = find_row("DGH", "2026-06-01", "NAROUZE", fake.rows)
    assert row == 2


def test_unreadable_date_never_merges(fake):
    """An unmatched row appends (visible); a wrongly matched one merges (not)."""
    from app.journal import write_report

    fake.rows.append({"Date": "la semaine derniere", "Technicien": "NAROUZE", "_row": 2})
    row, _ = write_report("DGH", "2026-08-05", "NAROUZE", "DGH", rep())
    assert row == 3


# --- bordereau projection -------------------------------------------------


def test_totals_sum_each_column():
    from app.journal import totals

    out = totals([
        {"Câble installé": "120", "Goulotte installée": "20"},
        {"Câble installé": "160", "Goulotte installée": ""},
        {"Câble installé": "292"},
    ])
    assert out["cables_installes_m"] == 572
    assert out["goulotte_m"] == 20


def test_totals_skip_untouched_columns_entirely():
    """A column nobody ever filled is 'not tracked', not 'zero installed'."""
    from app.journal import totals

    out = totals([{"Câble installé": "120"}])
    assert "fibre_m" not in out


def test_totals_ignore_unparseable_cells():
    from app.journal import totals

    out = totals([{"Câble installé": "120"}, {"Câble installé": "n/a"}])
    assert out["cables_installes_m"] == 120


def test_totals_never_count_arret_minutes():
    """`Arrêt (min)` accumulates on a merge but is not an installed quantity:
    the bordereau must not present it as one."""
    from app.journal import totals

    out = totals([{"Câble installé": "120", "Arrêt (min)": "90"},
                  {"Câble installé": "", "Arrêt (min)": "40"}])
    assert out["cables_installes_m"] == 120
    assert "temps_arret_min" not in out


def test_audio_link_points_at_the_inbox_when_the_dashboard_has_an_origin(monkeypatch):
    """The Sheet cell should open the message, not a bare Drive file."""
    monkeypatch.setattr(journal.settings, "dashboard_base_url", "https://aznet.example.com/")
    link = journal.audio_link({"lien_audio": "https://drive.google.com/uc?id=abc",
                               "correlation_id": "tg:1:2"})
    # A HYPERLINK formula, not a bare URL: the cell shows a label instead of
    # 120 characters of encoded id, and USER_ENTERED turns the leading `=`
    # into a live link.
    assert link == ('=HYPERLINK("https://aznet.example.com/#/inbox?msg=tg%3A1%3A2"; '
                    '"▶ Écouter")')


def test_audio_link_uses_dashboard_url_when_the_base_is_unset(monkeypatch):
    """`dashboard_base_url` is optional and on the live install was never set,
    so this branch had never once run and every cell took the fallback. The
    origin the report mail already has to get right is the origin here too."""
    monkeypatch.setattr(journal.settings, "dashboard_base_url", None)
    monkeypatch.setattr(journal.settings, "dashboard_url", "https://aznet.example.com")
    link = journal.audio_link({"lien_audio": "https://drive.google.com/uc?id=abc",
                               "correlation_id": "tg:1:2"})
    assert link.startswith('=HYPERLINK("https://aznet.example.com/#/inbox?msg=')


def test_audio_link_falls_back_to_drive_with_no_origin_at_all(monkeypatch):
    """A relative path in a spreadsheet cell opens nothing, so with no origin
    anywhere the Drive link is kept rather than an address going nowhere."""
    monkeypatch.setattr(journal.settings, "dashboard_base_url", None)
    monkeypatch.setattr(journal.settings, "dashboard_url", "")
    payload = {"lien_audio": "https://drive.google.com/uc?id=abc", "correlation_id": "tg:1:2"}
    assert journal.audio_link(payload) == "https://drive.google.com/uc?id=abc"
    # Same rule when the message has no correlation id to resolve against.
    monkeypatch.setattr(journal.settings, "dashboard_base_url", "https://aznet.example.com")
    assert journal.audio_link({**payload, "correlation_id": ""}) == payload["lien_audio"]


def test_audio_link_refuses_to_write_something_that_is_not_a_link(monkeypatch):
    """The live Sheet had 22 cells in a column called "Lien audio" holding a
    bare message id — `1115179874166528` — which opens nothing while looking
    like it should. An empty cell says "no recording"; an id lies."""
    monkeypatch.setattr(journal.settings, "dashboard_base_url", None)
    monkeypatch.setattr(journal.settings, "dashboard_url", "")
    assert journal.audio_link({"lien_audio": "1115179874166528"}) is None
    assert journal.audio_link({"lien_audio": ""}) is None
    assert journal.audio_link({}) is None


# --- the day's hours and crew, dictated rather than typed ------------------
#
# EQUIPE and the two hour columns were CHEF_COLUMNS until 2026-08-18: declared
# chef-only, so extraction never wrote them and the schema had no field for
# them. Technicians say the hours out loud in almost every note, so the columns
# stayed empty while the information sat unreachable in the transcript.


def test_spoken_hours_and_crew_reach_their_columns():
    from app.journal import report_cells

    cells = report_cells(rep(heure_entree="07:00", heure_sortie="20:00",
                             equipe="Hamid, Abdelhaq"))
    assert cells["HEURE D'ENTREE"] == "07:00"
    assert cells["HEURE DE SORTIE"] == "20:00"
    assert cells["EQUIPE"] == "Hamid, Abdelhaq"


def test_unspoken_hours_write_no_cell():
    """Silence is not a shift. An absent hour leaves the cell empty rather
    than guessing a working day."""
    from app.journal import report_cells

    cells = report_cells(rep(cables_installes_m=120))
    assert "HEURE D'ENTREE" not in cells
    assert "HEURE DE SORTIE" not in cells
    assert "EQUIPE" not in cells


def test_only_five_columns_are_left_for_a_human_to_type():
    """What a chef still fills by hand, pinned so it cannot grow back.

    Every other column on the tab now comes from the voice note. These five
    cannot: JH is arithmetic over the hours and the crew, the four ORDRE DU
    JOUR cells are the plan (set before the day, not reported after it), and
    the completion rate is a judgement against that plan.

    If a column joins this list, something became untypeable-by-voice and the
    project lost ground; if one leaves it, the technician gained it. Either way
    it should be a deliberate edit here rather than a silent drift.
    """
    from app.journal import DAY_COLUMNS, report_cells

    from app.journal import COL_JH

    derived = set(DAY_COLUMNS.values()) | {COL_JH}
    manual = [c for c in CHEF_COLUMNS if c not in derived]
    assert manual == [
        "ORDRE DU JOUR [Pose de câble cuivre]",
        "ORDRE DU JOUR [Connectiques cuivre]",
        "ORDRE DU JOUR [Test et etiquetage cuivre]",
        "ORDRE DU JOUR [Pose de goulotte]",
        "Taux de réalisation",
    ]
    # And the dictated three, plus the derived JH, really are written now.
    cells = report_cells(rep(heure_entree="07:00", heure_sortie="20:00",
                             equipe="Hamid"))
    assert derived <= set(cells)


# --- jours-homme, derived rather than typed --------------------------------


def test_jh_is_hours_times_people_over_a_working_day():
    """07:00 to 20:00 with one colleague: 13 h x 2 people / 8 h = 3.25."""
    from app.journal import compute_jh

    assert compute_jh(rep(heure_entree="07:00", heure_sortie="20:00",
                          equipe="Hamid")) == 3.25


def test_jh_alone_counts_one_person():
    from app.journal import compute_jh

    assert compute_jh(rep(heure_entree="08:00", heure_sortie="16:00")) == 1.0


def test_jh_is_none_when_an_hour_is_missing():
    """Unknown is not zero: a day nobody timed has no man-days, and writing 0
    would claim nobody worked."""
    from app.journal import compute_jh

    assert compute_jh(rep(heure_entree="08:00")) is None
    assert compute_jh(rep(heure_sortie="16:00")) is None
    assert compute_jh(rep(cables_installes_m=120)) is None


def test_jh_spans_midnight_rather_than_going_negative():
    """22:00 to 06:00 is an eight-hour night shift, not minus sixteen hours."""
    from app.journal import compute_jh

    assert compute_jh(rep(heure_entree="22:00", heure_sortie="06:00")) == 1.0


def test_jh_honours_the_configured_working_day_and_break():
    from app.journal import compute_jh

    limits = {"heures_jour": 10.0, "pause_min": 60.0}
    # 07:00-20:00 = 13 h, minus an hour of break = 12 h, alone, over a 10 h day
    assert compute_jh(rep(heure_entree="07:00", heure_sortie="20:00"),
                      limits) == 1.2


def test_jh_reaches_its_column(monkeypatch):
    from app import journal as mod

    monkeypatch.setattr(mod, "jh_limits", lambda: {})
    cells = mod.report_cells(rep(heure_entree="07:00", heure_sortie="15:00"))
    assert cells["JH"] == "1"


def test_a_row_without_hours_writes_no_jh(monkeypatch):
    from app import journal as mod

    monkeypatch.setattr(mod, "jh_limits", lambda: {})
    assert "JH" not in mod.report_cells(rep(cables_installes_m=120))


# --- a follow-up row says so ----------------------------------------------


def test_first_report_of_the_day_is_not_marked(fake):
    """50 is 50. Only a row that ADDS to an existing day gets the plus."""
    from app.journal import write_report

    write_report("DGH", "2026-08-05", "NAROUZE", "DGH", rep(cables_installes_m=50))
    assert fake.marked == []


def test_second_report_of_the_day_is_marked_as_an_increment(fake):
    """50 then +80 reads as ninety more metres; 50 then 80 reads as a
    contradiction someone has to open two messages to resolve."""
    from app.journal import write_report, NUMERIC_COLUMNS

    write_report("DGH", "2026-08-05", "NAROUZE", "DGH", rep(cables_installes_m=50))
    row, _ = write_report("DGH", "2026-08-05", "NAROUZE", "DGH",
                          rep(cables_installes_m=80))
    assert len(fake.marked) == 1
    tab, marked_row, columns = fake.marked[0]
    assert (tab, marked_row) == ("DGH", row)
    # Named columns, never indexes: an index computed from the wrong mapping is
    # what put "+46252" in the Rapports date column on 2026-08-18.
    assert columns == list(NUMERIC_COLUMNS.values())
    assert "Reste du câble (Stock)" not in columns


def test_another_technician_the_same_day_is_not_a_follow_up(fake):
    """The plus means 'this technician already reported today', not 'the tab
    already has a row'."""
    from app.journal import write_report

    write_report("DGH", "2026-08-05", "NAROUZE", "DGH", rep(cables_installes_m=50))
    write_report("DGH", "2026-08-05", "HOUCINE", "DGH", rep(cables_installes_m=80))
    assert fake.marked == []
