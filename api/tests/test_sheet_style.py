"""The sheet the director opens, styled.

Formatting only — these tests exist to hold two rules that are easy to break
later: styling never raises into the pipeline, and it never adds a second
banding to a tab that already has one (banding is the only request in
`style_tab` that appends rather than sets).
"""
from app import sheets


class FakeExec:
    def __init__(self, result):
        self._result = result

    def execute(self, num_retries=0):
        return self._result


class FakeSpreadsheets:
    def __init__(self, meta):
        self.meta = meta
        self.batches = []

    def get(self, spreadsheetId=None):
        return FakeExec(self.meta)

    def batchUpdate(self, spreadsheetId=None, body=None):
        self.batches.append(body)
        return FakeExec({})


class FakeService:
    def __init__(self, meta):
        self._s = FakeSpreadsheets(meta)

    def spreadsheets(self):
        return self._s


def _meta(banded=False):
    sheet = {"properties": {"title": "DGH", "sheetId": 77}}
    if banded:
        sheet["bandedRanges"] = [{"range": {"sheetId": 77}}]
    return {"sheets": [sheet]}


def test_style_tab_freezes_the_header_and_sizes_the_columns(monkeypatch):
    svc = FakeService(_meta())
    monkeypatch.setattr(sheets, "_service", lambda: svc)

    sheets.style_tab("DGH", ["Date", "Technicien", "Résumé"])

    reqs = svc.spreadsheets().batches[0]["requests"]
    frozen = [r for r in reqs if "updateSheetProperties" in r][0]
    grid = frozen["updateSheetProperties"]["properties"]["gridProperties"]
    assert grid["frozenRowCount"] == 1
    widths = [r["updateDimensionProperties"]["properties"]["pixelSize"]
              for r in reqs if r.get("updateDimensionProperties", {})
              .get("range", {}).get("dimension") == "COLUMNS"]
    # Date is narrow, a free-text column is wide: a transcript in a 90 px
    # column reads as an empty cell.
    # Narrow stays narrow and free text stays wide, but the floor is derived
    # from the header rather than fixed: a column has to be able to show its
    # own title, and 90 px could not fit "ORDRE DU JOUR [Pose de câble cuivre]".
    assert widths[0] == 100
    assert widths[2] == 420


def test_banding_is_added_once(monkeypatch):
    """Re-running the styling must change nothing. Every other request sets a
    property; addBanding appends, so a second copy would stack."""
    svc = FakeService(_meta(banded=True))
    monkeypatch.setattr(sheets, "_service", lambda: svc)

    sheets.style_tab("DGH", ["Date"])

    assert not any("addBanding" in r for r in svc.spreadsheets().batches[0]["requests"])


def test_a_missing_tab_is_not_an_error(monkeypatch):
    svc = FakeService({"sheets": []})
    monkeypatch.setattr(sheets, "_service", lambda: svc)
    sheets.style_tab("nope", ["Date"])
    assert svc.spreadsheets().batches == []


def test_styling_never_raises_into_the_pipeline(monkeypatch):
    """A report that files into an ugly sheet is a working pipeline; a report
    lost because a header could not be tinted is not."""
    def boom():
        raise RuntimeError("google is down")

    monkeypatch.setattr(sheets, "_service", boom)
    sheets.style_tab("DGH", ["Date"])  # must not raise
