from fastapi.testclient import TestClient

import app.main as main
from app.sheets import SheetsError

client = TestClient(main.app)

ROWS = [{"_row": 2, "date": "2026-07-23", "technicien": "Yassine", "resume": "150 m de goulotte."}]

# PATCH /reports is gated and records who made the edit. Overriding the
# dependency rather than logging in keeps the suite free of a database, which is
# the rule for this whole test suite.
main.app.dependency_overrides[main.auth.require_human] = lambda: {
    "id": 1, "name": "Test", "role": "directeur"
}


def test_reports_ok(monkeypatch):
    monkeypatch.setattr(main.sheets, "read_reports", lambda: ROWS)
    r = client.get("/reports")
    assert r.status_code == 200
    assert r.json()["reports"][0]["technicien"] == "Yassine"


def test_reports_sheets_failure_is_502(monkeypatch):
    def boom():
        raise SheetsError("no key")

    monkeypatch.setattr(main.sheets, "read_reports", boom)
    assert client.get("/reports").status_code == 502


def test_patch_ok(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        main.sheets, "update_report_field", lambda row, f, v: calls.update(row=row, f=f, v=v)
    )
    r = client.patch("/reports/3", json={"field": "chantier", "value": "Atlas"})
    assert r.status_code == 200
    assert calls == {"row": 3, "f": "chantier", "v": "Atlas"}


def test_patch_header_row_rejected():
    assert client.patch("/reports/1", json={"field": "x", "value": "y"}).status_code == 422


def test_patch_unknown_column_is_422(monkeypatch):
    def boom(row, f, v):
        raise SheetsError("unknown column: nope")

    monkeypatch.setattr(main.sheets, "update_report_field", boom)
    assert client.patch("/reports/2", json={"field": "nope", "value": "y"}).status_code == 422


# ── POST /reports/export ───────────────────────────────────────────────────
# The .docx moved into the API on 2026-08-16 so the scheduled mail can attach
# one. What these guard is the period filter and the fact that the figures come
# from the Sheet and not from the request body.

EXPORT_ROWS = [
    {"_row": 2, "date": "2026-08-10", "technicien": "A", "goulottes_m": "10"},
    {"_row": 3, "date": "12/08/2026", "technicien": "B", "goulottes_m": "5"},
    {"_row": 4, "date": "2026-08-20", "technicien": "C", "goulottes_m": "999"},
]


def test_export_returns_a_docx_attachment(monkeypatch):
    monkeypatch.setattr(main.sheets, "read_reports", lambda: EXPORT_ROWS)
    r = client.post("/reports/export", json={
        "title": "Rapport journalier — 2026-08-10",
        "body": "## Synthèse\nUne intervention.",
        "period": "2026-08-10",
    })
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )
    assert "rapport-journalier-2026-08-10.docx" in r.headers["content-disposition"]
    assert r.content[:2] == b"PK"  # a real ZIP, not an error page with a nice header


def test_export_covers_the_whole_week_and_nothing_outside_it(monkeypatch):
    """A range label selects every day between its two ends, in any date spelling.

    Row 3 is written `12/08/2026` because the Sheet hands dates back that way
    once the column is formatted — a plain string compare would silently drop
    it, and the document would disagree with the page that asked for it.
    """
    seen = {}
    monkeypatch.setattr(main.sheets, "read_reports", lambda: EXPORT_ROWS)
    monkeypatch.setattr(
        main.docx_report, "build",
        lambda *a, **kw: seen.update(rows=a[4]) or b"PK\x03\x04",
    )
    r = client.post("/reports/export", json={
        "title": "Hebdo", "body": "x", "period": "2026-08-10 → 2026-08-16",
    })
    assert r.status_code == 200
    assert [row["_row"] for row in seen["rows"]] == [2, 3]


def test_export_502_when_the_sheet_cannot_be_read(monkeypatch):
    def boom():
        raise SheetsError("no key")

    monkeypatch.setattr(main.sheets, "read_reports", boom)
    r = client.post("/reports/export", json={
        "title": "T", "body": "x", "period": "2026-08-10",
    })
    assert r.status_code == 502
