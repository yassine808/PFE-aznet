"""Journal row assembly: accumulation and stock reconciliation.

Pure logic, no Sheets and no Postgres — these are the two rules that make the
director's file correct, so they get tested where they can fail fast.
"""
import pytest

from app import journal

from app.journal import (
    HEADERS,
    CHEF_COLUMNS,
    merge_rows,
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


def test_quantities_accumulate():
    merged = merge_rows({"Câble installé": "120"}, {"Câble installé": "160"})
    assert merged["Câble installé"] == "280"


def test_arret_minutes_accumulate():
    """Two stops in one day are two stops: minutes add like any quantity."""
    merged = merge_rows({"Arrêt (min)": "60"}, {"Arrêt (min)": "90"})
    assert merged["Arrêt (min)"] == "150"


def test_blocker_fields_land_in_their_own_columns():
    cells = report_cells(rep(
        temps_arret_min=90, motif_arret="Bureaux fermés",
        besoins="Connecteurs RJ45", prochaines_etapes="E3 demain",
    ))
    assert cells["Arrêt (min)"] == "90"
    assert cells["MOTIF D'ARRÊT"] == "Bureaux fermés"
    assert cells["BESOINS / MATÉRIEL"] == "Connecteurs RJ45"
    assert cells["PROCHAINES ÉTAPES"] == "E3 demain"


def test_empty_existing_cell_takes_the_new_value():
    merged = merge_rows({"Câble installé": ""}, {"Câble installé": "160"})
    assert merged["Câble installé"] == "160"


def test_locations_union_without_duplicates():
    merged = merge_rows({"ETAGE": "RDC, E1"}, {"ETAGE": "E1, E2"})
    assert merged["ETAGE"] == "RDC, E1, E2"


def test_remarks_append_rather_than_replace():
    merged = merge_rows({"Remarques": "Bureaux fermés."},
                        {"Remarques": "Arrêt de 1h30."})
    assert merged["Remarques"] == "Bureaux fermés.\nArrêt de 1h30."


def test_need_fields_append_like_remarks():
    """A second list of needs joins the first; a repeated motive is not
    repeated twice — same rules as Remarques."""
    merged = merge_rows(
        {"MOTIF D'ARRÊT": "Attente d'instruction.",
         "BESOINS / MATÉRIEL": "Connecteurs RJ45.",
         "PROCHAINES ÉTAPES": "On attaque E3."},
        {"MOTIF D'ARRÊT": "Attente d'instruction.",
         "BESOINS / MATÉRIEL": "2 boîtes de vis.",
         "PROCHAINES ÉTAPES": "On attaque E3."},
    )
    assert merged["MOTIF D'ARRÊT"] == "Attente d'instruction."
    assert merged["BESOINS / MATÉRIEL"] == "Connecteurs RJ45.\n2 boîtes de vis."
    assert merged["PROCHAINES ÉTAPES"] == "On attaque E3."


def test_identical_remark_is_not_duplicated():
    merged = merge_rows({"Remarques": "Bureaux fermés."},
                        {"Remarques": "Bureaux fermés."})
    assert merged["Remarques"] == "Bureaux fermés."


def test_stock_is_a_level_so_the_latest_reading_replaces():
    merged = merge_rows({"Reste du câble (Stock)": "2274"},
                        {"Reste du câble (Stock)": "2095"})
    assert merged["Reste du câble (Stock)"] == "2095"


@pytest.mark.parametrize("column", CHEF_COLUMNS)
def test_chef_columns_survive_a_merge(column):
    """The dashboard owns these; a second voice note must not undo a human."""
    merged = merge_rows({column: "DRISS, BRAHIM"}, {column: "écrasé"})
    assert merged[column] == "DRISS, BRAHIM"


# --- the Sheets round trip (fake tab, no Google) --------------------------


class FakeSheet:
    """Minimal stand-in: a tab is a header list plus rows of dicts."""

    def __init__(self, rows=None):
        self.rows = rows or []
        self.created = []
        self.appended = []
        self.written = []
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


def test_second_report_same_day_merges_into_the_same_row(fake):
    from app.journal import write_report

    write_report("DGH", "2026-08-05", "NAROUZE", "DGH", rep(cables_installes_m=120))
    row, _ = write_report("DGH", "2026-08-05", "NAROUZE", "DGH",
                          rep(cables_installes_m=160))
    assert row == 2
    assert fake.written[-1][1] == 2
    assert fake.written[-1][2]["Câble installé"] == "280"


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
    """We write '2026-08-05'; Google hands back '05/08/2026'."""
    from app.journal import write_report

    fake.rows.append({"Date": "05/08/2026", "Technicien": "NAROUZE",
                      "Câble installé": "120", "_row": 2})
    row, _ = write_report("DGH", "2026-08-05", "NAROUZE", "DGH",
                          rep(cables_installes_m=160))
    assert row == 2


def test_technician_name_matching_ignores_case(fake):
    from app.journal import write_report

    fake.rows.append({"Date": "2026-08-05", "Technicien": "narouze", "_row": 2})
    row, _ = write_report("DGH", "2026-08-05", "NAROUZE", "DGH", rep())
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


def test_refiling_a_different_message_still_merges(fake):
    """A second report from the same technician the same day has its own
    correlation: it is a real message, so it merges and the cell logs both."""
    from app.journal import file_report

    file_report({
        "date": "2026-08-05", "technicien": "NAROUZE", "chantier": "DGH",
        "correlation_id": "corr-abc",
        "report": {"cables_installes_m": 120, "resume": "Résumé."},
    })
    retry = file_report({
        "date": "2026-08-05", "technicien": "NAROUZE", "chantier": "DGH",
        "correlation_id": "corr-def",
        "report": {"cables_installes_m": 160, "resume": "Suite."},
    })
    assert retry["duplicate"] is False
    assert fake.written[-1][1] == retry["row"]
    assert "corr-abc" in fake.written[-1][2]["Correlation id"]
    assert "corr-def" in fake.written[-1][2]["Correlation id"]
    assert fake.written[-1][2]["Câble installé"] == "280"


def test_refile_without_correlation_merges_unchecked(fake):
    """No correlation_id (e.g. a dashboard submission) cannot be proven a
    duplicate, so it still merges — the pre-journal behavior."""
    from app.journal import file_report

    first = file_report({
        "date": "2026-08-05", "technicien": "NAROUZE", "chantier": "DGH",
        "report": {"cables_installes_m": 120, "resume": "Résumé."},
    })
    retry = file_report({
        "date": "2026-08-05", "technicien": "NAROUZE", "chantier": "DGH",
        "report": {"cables_installes_m": 160, "resume": "Suite."},
    })
    assert retry["duplicate"] is False
    assert fake.written[-1][1] == first["row"]
    assert fake.written[-1][2]["Câble installé"] == "280"


def test_excel_serial_date_matches_the_same_day(fake):
    """The director's own file stores 46174, not a date string."""
    from app.journal import write_report

    fake.rows.append({"Date": "46174", "Technicien": "NAROUZE", "_row": 2})
    row, _ = write_report("DGH", "2026-06-01", "NAROUZE", "DGH", rep())
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


def test_flag_review_merges_as_a_state_not_as_prose():
    """Once any message of the day needs checking, the row does.

    Merging the flag through the text branch produced `FALSE\nTrue` in the one
    column the director filters on. The sheet hands the cell back as the string
    `TRUE`, so both shapes have to mean the same thing.
    """
    from app.journal import COL_FLAG, merge_rows

    assert merge_rows({COL_FLAG: "FALSE"}, {COL_FLAG: "TRUE"})[COL_FLAG] == "TRUE"
    # A flag already set is never cleared by a clean second message.
    assert merge_rows({COL_FLAG: "TRUE"}, {COL_FLAG: "FALSE"})[COL_FLAG] == "TRUE"
    assert merge_rows({COL_FLAG: "FALSE"}, {COL_FLAG: "FALSE"})[COL_FLAG] == "FALSE"


def test_stt_engine_merges_to_the_latest_engine():
    """Which engine answered last, not a transcript of the chain's history."""
    from app.journal import COL_STT, merge_rows

    assert merge_rows({COL_STT: "gemini"}, {COL_STT: "local"})[COL_STT] == "local"
    # A text report carries no engine and must not blank the audio one.
    assert merge_rows({COL_STT: "gemini"}, {COL_STT: ""})[COL_STT] == "gemini"


def test_audio_link_points_at_the_inbox_when_the_dashboard_has_an_origin(monkeypatch):
    """The Sheet cell should open the message, not a bare Drive file."""
    monkeypatch.setattr(journal.settings, "dashboard_base_url", "https://aznet.example.com/")
    link = journal.audio_link({"lien_audio": "https://drive.google.com/uc?id=abc",
                               "correlation_id": "tg:1:2"})
    assert link == "https://aznet.example.com/#/inbox?msg=tg%3A1%3A2"


def test_audio_link_falls_back_to_drive_without_an_origin(monkeypatch):
    """A relative path in a spreadsheet cell opens nothing, so an unset base
    keeps the Drive link rather than writing an address that goes nowhere."""
    monkeypatch.setattr(journal.settings, "dashboard_base_url", None)
    payload = {"lien_audio": "https://drive.google.com/uc?id=abc", "correlation_id": "tg:1:2"}
    assert journal.audio_link(payload) == "https://drive.google.com/uc?id=abc"
    # Same rule when the message has no correlation id to resolve against.
    monkeypatch.setattr(journal.settings, "dashboard_base_url", "https://aznet.example.com")
    assert journal.audio_link({**payload, "correlation_id": ""}) == payload["lien_audio"]
