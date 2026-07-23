from fastapi.testclient import TestClient

import app.main as main
from app.sheets import SheetsError

client = TestClient(main.app)

ROWS = [{"_row": 2, "date": "2026-07-23", "technicien": "Yassine", "resume": "150 m de goulotte."}]


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
