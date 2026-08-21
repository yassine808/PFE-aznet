"""The Sheets read/write layer (`app/sheets.py`).

A single in-memory fake stands in for the Google service: it holds `tab ->
list of rows` and answers `values().get/update/batchUpdate/clear` and
`spreadsheets().get/batchUpdate` the way the real API does, including the two
shapes this module has actually been bitten by — `updatedRange` at the top
level, and an unticked checkbox column making column A look thousands of rows
long.

`test_sheets_range.py` and `test_sheet_style.py` cover A1 quoting and
formatting; this file covers everything that moves a value.
"""
import pytest

from app import sheets


# --- the fake --------------------------------------------------------------

class _Exec:
    def __init__(self, result):
        self._result = result

    def execute(self, num_retries=0):
        return self._result


class FakeValues:
    def __init__(self, book):
        self.book = book
        self.writes = []
        self.batches = []
        self.cleared = []

    @staticmethod
    def _parse(rng):
        """`'DGH'!A2:C2` -> ("DGH", "A2:C2"). Quoting is tested elsewhere."""
        tab, _, ref = rng.partition("!")
        return tab.strip("'").replace("''", "'"), ref

    def get(self, spreadsheetId=None, range=None):
        tab, ref = self._parse(range)
        rows = self.book.get(tab, [])
        if ref == "1:1":
            return _Exec({"values": [rows[0]] if rows else [[]]})
        if ref == "A:A":
            return _Exec({"values": [[r[0]] if r else [] for r in rows]})
        return _Exec({"values": [list(r) for r in rows]})

    def update(self, spreadsheetId=None, range=None, valueInputOption=None, body=None):
        tab, ref = self._parse(range)
        self.writes.append({"tab": tab, "ref": ref, "values": body["values"],
                            "option": valueInputOption})
        cols = len(body["values"][0])
        end = sheets._col_letter(cols)
        row = "".join(c for c in ref if c.isdigit()) or "1"
        # `update` reports its range at the TOP level — reading the old nested
        # "updates" shape returned None for every write.
        return _Exec({"updatedRange": f"{tab}!A{row}:{end}{row}"})

    def batchUpdate(self, spreadsheetId=None, body=None):
        self.batches.append(body)
        return _Exec({})

    def clear(self, spreadsheetId=None, range=None, body=None):
        self.cleared.append(range)
        return _Exec({})


class FakeSpreadsheets:
    def __init__(self, book, meta):
        self.book = book
        self.meta = meta
        self._values = FakeValues(book)
        self.batches = []

    def values(self):
        return self._values

    def get(self, spreadsheetId=None):
        return _Exec(self.meta)

    def batchUpdate(self, spreadsheetId=None, body=None):
        self.batches.append(body)
        for req in body.get("requests", []):
            if "addSheet" in req:
                title = req["addSheet"]["properties"]["title"]
                self.book.setdefault(title, [])
                self.meta.setdefault("sheets", []).append(
                    {"properties": {"title": title, "sheetId": 900 + len(self.meta["sheets"]),
                                    "gridProperties": {"columnCount": 26, "rowCount": 1000}}})
        return _Exec({})


class FakeService:
    def __init__(self, book, meta):
        self._s = FakeSpreadsheets(book, meta)

    def spreadsheets(self):
        return self._s


def _meta(*tabs, columns=26, rows=1000):
    return {"sheets": [
        {"properties": {"title": t, "sheetId": 10 + i,
                        "gridProperties": {"columnCount": columns, "rowCount": rows}}}
        for i, t in enumerate(tabs)
    ]}


@pytest.fixture
def svc(monkeypatch):
    book = {
        sheets.RAPPORTS_TAB: [["Date", "Technicien", "Résumé"],
                              ["2026-08-20", "Yassine", "Pose de goulottes"]],
        "DGH": [["DATE", "TECHNICIEN", "GOULOTTE"], ["2026-08-20", "Yassine", "40"]],
    }
    service = FakeService(book, _meta(sheets.RAPPORTS_TAB, "DGH"))
    monkeypatch.setattr(sheets, "_service", lambda: service)
    monkeypatch.setattr(sheets.settings, "sheet_id", "SHEET")
    # Styling is covered by test_sheet_style.py and would only add noise here.
    monkeypatch.setattr(sheets, "style_tab", lambda *a, **k: None)
    service.book = book
    return service


# --- small pure helpers ----------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (None, ""),          # absence is not zero
    (True, "TRUE"),
    (False, "FALSE"),
    (0, "0"),
    (40.5, "40.5"),
    ("texte", "texte"),
])
def test_a_cell_is_a_string_and_none_is_empty(value, expected):
    assert sheets._cell(value) == expected


@pytest.mark.parametrize("n,letter", [(1, "A"), (26, "Z"), (27, "AA"), (62, "BJ")])
def test_column_letters(n, letter):
    assert sheets._col_letter(n) == letter


@pytest.mark.parametrize("rng,row", [
    ("Rapports!A15:H15", 15),
    ("'Non affecté'!A3:B3", 3),
    (None, None),
    ("no-bang", None),
])
def test_the_written_row_number_is_read_back_from_the_range(rng, row):
    assert sheets._row_from_range(rng) == row


# --- read_reports and its cache --------------------------------------------

def test_reports_are_read_as_dicts_with_their_row_number(svc):
    rows = sheets.read_reports()
    assert rows == [{"Date": "2026-08-20", "Technicien": "Yassine",
                     "Résumé": "Pose de goulottes", "_row": 2}]


def test_a_short_row_is_padded_rather_than_losing_its_columns(svc):
    svc.book[sheets.RAPPORTS_TAB].append(["2026-08-21"])
    assert sheets.read_reports()[-1] == {"Date": "2026-08-21", "Technicien": "",
                                         "Résumé": "", "_row": 3}


def test_an_empty_tab_reads_as_no_rows(svc):
    svc.book[sheets.RAPPORTS_TAB] = []
    assert sheets.read_reports() == []


def test_the_cached_list_is_a_copy_so_a_caller_cannot_corrupt_it(svc):
    first = sheets.read_reports()
    first.reverse()
    assert sheets.read_reports()[0]["_row"] == 2


def test_a_write_drops_the_cache(svc):
    sheets.read_reports()
    svc.book[sheets.RAPPORTS_TAB].append(["2026-08-21", "Sara", "RAS"])
    assert len(sheets.read_reports()) == 1        # still the cached answer
    sheets.invalidate_reports()
    assert len(sheets.read_reports()) == 2


def test_a_google_failure_becomes_one_error_type(monkeypatch):
    def boom():
        raise RuntimeError("403 forbidden")

    monkeypatch.setattr(sheets, "_service", boom)
    sheets.invalidate_reports()
    with pytest.raises(sheets.SheetsError, match="sheets read failed"):
        sheets.read_reports()


# --- read_tab / read_tab_cached --------------------------------------------

def test_any_tab_reads_the_same_way(svc):
    assert sheets.read_tab("DGH")[0]["GOULOTTE"] == "40"


def test_an_unknown_tab_reads_as_no_rows(svc):
    assert sheets.read_tab("Inconnu") == []


def test_the_tab_cache_serves_the_second_reader_and_dies_on_a_write(svc):
    sheets.read_tab_cached("DGH")
    svc.book["DGH"].append(["2026-08-21", "Sara", "80"])
    assert len(sheets.read_tab_cached("DGH")) == 1
    sheets.invalidate_tab("DGH")
    assert len(sheets.read_tab_cached("DGH")) == 2
    # …and the whole cache can be dropped at once.
    svc.book["DGH"].append(["2026-08-22", "Sara", "10"])
    sheets.invalidate_tab()
    assert len(sheets.read_tab_cached("DGH")) == 3


def test_the_cached_tab_list_is_a_copy_too(svc):
    rows = sheets.read_tab_cached("DGH")
    rows.clear()
    assert len(sheets.read_tab_cached("DGH")) == 1


# --- headers ---------------------------------------------------------------

def test_a_non_rapports_header_row_is_read_live(svc):
    assert sheets._headers(svc, "DGH") == ["DATE", "TECHNICIEN", "GOULOTTE"]


def test_the_rapports_header_is_cached_between_writes(svc):
    assert sheets._headers(svc) == ["Date", "Technicien", "Résumé"]
    svc.book[sheets.RAPPORTS_TAB][0] = ["Date", "Technicien", "Résumé", "Chantier"]
    assert sheets._headers(svc) == ["Date", "Technicien", "Résumé"]
    sheets.invalidate_reports()
    assert sheets._headers(svc)[-1] == "Chantier"


# --- ensure_columns --------------------------------------------------------

def test_a_missing_column_is_appended_after_the_last_one(svc):
    out = sheets.ensure_columns("DGH", ["GOULOTTE", "FIBRE"])
    assert out == ["DATE", "TECHNICIEN", "GOULOTTE", "FIBRE"]
    write = svc.spreadsheets().values().writes[-1]
    assert write["ref"] == "D1:D1"
    assert write["values"] == [["FIBRE"]]


def test_two_spellings_of_one_new_column_add_it_once(svc):
    """Both passed the "not in the header" filter and the tab grew two columns
    with identical titles, splitting that article's quantities silently."""
    out = sheets.ensure_columns("DGH", ["FIBRE", "FIBRE", "", None])
    assert out == ["DATE", "TECHNICIEN", "GOULOTTE", "FIBRE"]


def test_nothing_missing_writes_nothing(svc):
    before = len(svc.spreadsheets().values().writes)
    assert sheets.ensure_columns("DGH", ["DATE"]) == ["DATE", "TECHNICIEN", "GOULOTTE"]
    assert len(svc.spreadsheets().values().writes) == before


def test_the_grid_is_widened_before_a_column_is_written_into_it(monkeypatch):
    """Writing past a tab's allocated width is a 400, not an auto-extend — hit
    for real adding `motif_flag` to a 61-column tab."""
    book = {"DGH": [["A", "B"]]}
    service = FakeService(book, _meta("DGH", columns=2))
    monkeypatch.setattr(sheets, "_service", lambda: service)
    monkeypatch.setattr(sheets.settings, "sheet_id", "SHEET")

    sheets.ensure_columns("DGH", ["C"])

    grow = service.spreadsheets().batches[0]["requests"][0]["appendDimension"]
    assert grow["dimension"] == "COLUMNS"
    assert grow["length"] == 1


def test_growing_an_unknown_tab_is_an_error_not_a_silent_skip(svc):
    with pytest.raises(sheets.SheetsError, match="not found"):
        sheets._grow_columns(svc, "Inconnu", 99)
    with pytest.raises(sheets.SheetsError, match="not found"):
        sheets._grow_rows(svc, "Inconnu", 99)


def test_a_tab_that_is_already_wide_enough_is_left_alone(svc):
    sheets._grow_columns(svc, "DGH", 3)
    sheets._grow_rows(svc, "DGH", 3)
    assert svc.spreadsheets().batches == []


def test_rows_grow_by_a_comfortable_margin_not_by_one(monkeypatch):
    """Reports arrive one at a time all day; growing the grid costs a round
    trip each time."""
    service = FakeService({"DGH": [["A"]]}, _meta("DGH", rows=2))
    monkeypatch.setattr(sheets, "_service", lambda: service)
    monkeypatch.setattr(sheets.settings, "sheet_id", "SHEET")
    sheets._grow_rows(service, "DGH", 3)
    assert service.spreadsheets().batches[0]["requests"][0]["appendDimension"]["length"] == 200


# --- writes ----------------------------------------------------------------

def test_a_field_is_written_to_the_column_its_header_names(svc):
    sheets.update_report_field(2, "Technicien", "Sara")
    data = svc.spreadsheets().values().batches[-1]["data"]
    assert data == [{"range": "'Rapports'!B2", "values": [["Sara"]]}]


def test_a_none_is_written_as_an_empty_cell(svc):
    sheets.update_report_field(2, "Résumé", None)
    assert svc.spreadsheets().values().batches[-1]["data"][0]["values"] == [[""]]


def test_writing_an_unknown_column_is_refused(svc):
    with pytest.raises(sheets.SheetsError, match="unknown column: Inconnue"):
        sheets.update_report_fields(2, {"Inconnue": "x"})


def test_writing_nothing_calls_google_at_all(svc):
    before = len(svc.spreadsheets().values().batches)
    sheets.update_report_fields(2, {})
    assert len(svc.spreadsheets().values().batches) == before


def test_clearing_a_row_empties_its_whole_width_and_keeps_its_number(svc):
    sheets.clear_row(2)
    assert svc.spreadsheets().values().cleared == ["'Rapports'!A2:C2"]


def test_write_row_skips_columns_the_tab_does_not_have(svc):
    sheets.write_row("DGH", 2, {"GOULOTTE": 80, "INCONNUE": "x"})
    data = svc.spreadsheets().values().batches[-1]["data"]
    assert data == [{"range": "'DGH'!C2", "values": [["80"]]}]


def test_write_row_with_nothing_to_write_calls_nothing(svc):
    before = len(svc.spreadsheets().values().batches)
    sheets.write_row("DGH", 2, {"INCONNUE": "x"})
    assert len(svc.spreadsheets().values().batches) == before


def test_a_failed_row_write_names_the_tab_and_the_row(svc, monkeypatch):
    monkeypatch.setattr(svc.spreadsheets().values(), "batchUpdate",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("500")))
    with pytest.raises(sheets.SheetsError, match=r"sheets row write failed \(DGH!2\)"):
        sheets.write_row("DGH", 2, {"GOULOTTE": 80})


# --- append ----------------------------------------------------------------

def test_appending_a_report_places_cells_by_header_and_returns_its_row(svc):
    row = sheets.append_report({"Technicien": "Sara", "Date": "2026-08-21"})
    assert row == 3
    write = svc.spreadsheets().values().writes[-1]
    assert write["ref"] == "A3"
    assert write["values"] == [["2026-08-21", "Sara", ""]]


def test_a_new_schema_field_grows_the_header_rather_than_being_dropped(svc):
    sheets.append_report({"Date": "2026-08-21", "motif_flag": "quantité douteuse"})
    header_write, row_write = svc.spreadsheets().values().writes[-2:]
    assert header_write["values"] == [["motif_flag"]]
    assert row_write["values"][0][-1] == "quantité douteuse"


def test_appending_to_a_tab_with_no_header_row_is_refused(svc):
    svc.book[sheets.RAPPORTS_TAB] = []
    sheets.invalidate_reports()
    with pytest.raises(sheets.SheetsError, match="no header row"):
        sheets.append_report({"Date": "x"})


def test_append_row_places_cells_by_the_headers_it_is_given(svc):
    row = sheets.append_row("DGH", {"GOULOTTE": 80, "DATE": "2026-08-21"},
                            ["DATE", "TECHNICIEN", "GOULOTTE"])
    assert row == 3
    assert svc.spreadsheets().values().writes[-1]["values"] == [
        ["2026-08-21", "", "80"]]


def test_a_failed_append_names_the_tab(svc, monkeypatch):
    monkeypatch.setattr(svc.spreadsheets().values(), "update",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("500")))
    with pytest.raises(sheets.SheetsError, match=r"sheets append failed \(DGH\)"):
        sheets.append_row("DGH", {"DATE": "x"}, ["DATE"])


# --- _next_row -------------------------------------------------------------

def test_the_next_free_row_is_the_last_one_with_a_date_plus_one(svc):
    assert sheets._next_row(svc, "DGH") == 3


def test_trailing_checkbox_rows_do_not_push_the_write_off_the_grid(svc):
    """An unticked checkbox is the value FALSE, so Google reports thousands of
    used rows; counting them made the next free row A5076 and every write 400."""
    svc.book["DGH"] += [[""], [], [""]]
    assert sheets._next_row(svc, "DGH") == 3


def test_a_tab_with_nothing_in_column_a_starts_at_row_two(svc):
    svc.book["DGH"] = []
    assert sheets._next_row(svc, "DGH") == 2


def test_a_tab_whose_column_a_is_entirely_blank_appends_past_the_blanks(svc):
    svc.book["DGH"] = [[""], [""]]
    assert sheets._next_row(svc, "DGH") == 3


# --- ensure_tab ------------------------------------------------------------

def test_a_new_tab_is_created_with_its_header_row(svc):
    sheets.ensure_tab("ACAPS", ["DATE", "TECHNICIEN"])
    assert any("addSheet" in r for b in svc.spreadsheets().batches
               for r in b["requests"])
    assert svc.spreadsheets().values().writes[-1]["values"] == [["DATE", "TECHNICIEN"]]


def test_an_existing_header_row_is_never_rewritten(svc):
    """The director renaming a column of his own is a decision, not drift."""
    before = len(svc.spreadsheets().values().writes)
    sheets.ensure_tab("DGH", ["OTHER", "HEADERS"])
    assert len(svc.spreadsheets().values().writes) == before
    assert svc.book["DGH"][0] == ["DATE", "TECHNICIEN", "GOULOTTE"]


def test_a_failed_tab_setup_names_the_tab(svc, monkeypatch):
    monkeypatch.setattr(svc.spreadsheets(), "get",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("500")))
    with pytest.raises(sheets.SheetsError, match=r"sheets tab setup failed \(ACAPS\)"):
        sheets.ensure_tab("ACAPS", ["DATE"])


# --- mark_increment --------------------------------------------------------

def test_the_plus_marker_is_a_number_format_not_a_written_plus():
    """USER_ENTERED parses a leading + as a formula, and forcing it in as text
    would break every SUM on the tab."""
    assert sheets._PLUS_FORMAT["type"] == "NUMBER"
    assert "+" in sheets._PLUS_FORMAT["pattern"]


def test_increment_formatting_spans_the_reported_columns(svc):
    sheets.mark_increment("DGH", 2, ["GOULOTTE"])
    rng = svc.spreadsheets().batches[-1]["requests"][0]["repeatCell"]["range"]
    # Resolved against the tab's OWN header row: an index taken from elsewhere
    # once landed on the date and time columns and rendered them as "+46252".
    assert (rng["startColumnIndex"], rng["endColumnIndex"]) == (2, 3)
    assert (rng["startRowIndex"], rng["endRowIndex"]) == (1, 2)


def test_increment_formatting_is_skipped_for_columns_the_tab_lacks(svc):
    before = len(svc.spreadsheets().batches)
    sheets.mark_increment("DGH", 2, ["INCONNUE"])
    assert len(svc.spreadsheets().batches) == before


def test_increment_formatting_never_raises_into_the_pipeline(svc, monkeypatch, capsys):
    """A row that failed to be marked is a cosmetic loss; a row that failed to
    be written is a report lost."""
    monkeypatch.setattr(sheets, "_sheet_id",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("500")))
    sheets.mark_increment("DGH", 2, ["GOULOTTE"])
    assert "increment format skipped" in capsys.readouterr().out


def test_an_unknown_tab_is_simply_not_formatted(svc):
    before = len(svc.spreadsheets().batches)
    sheets.mark_increment("Inconnu", 2, ["GOULOTTE"])
    assert len(svc.spreadsheets().batches) == before
