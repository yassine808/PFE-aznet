from fastapi.testclient import TestClient

import app.main as main
from app.daily_report import DailyReportContent, DailyReportError

client = TestClient(main.app)

# Endpoints are gated now. Overriding the dependency keeps this suite free of a
# database and of real credentials, which is the rule for the whole suite.
main.app.dependency_overrides[main.auth.require_user] = lambda: {
    "id": 1, "name": "Test", "role": "directeur"
}

ROWS = [
    {
        "technicien": "Yassine",
        "chantier": "Tour Atlas",
        "goulottes_m": 150,
        "cables_m": 800,
        "resume": "Installation de 150 m de goulotte.",
    }
]

CONTENT = DailyReportContent(
    objet="Rapport journalier — 2026-07-23 — 1 intervention",
    corps="Synthèse : 150 m de goulotte, 800 m de câble posés sur Tour Atlas.",
)


def test_daily_report_ok(monkeypatch):
    monkeypatch.setattr(main.daily_report, "generate_daily_report", lambda d, r: CONTENT)
    r = client.post("/daily-report", json={"date": "2026-07-23", "rows": ROWS})
    assert r.status_code == 200
    body = r.json()
    assert body["objet"].startswith("Rapport journalier")
    assert "150" in body["corps"]


def test_daily_report_empty_rows_rejected():
    r = client.post("/daily-report", json={"date": "2026-07-23", "rows": []})
    assert r.status_code == 422


def test_daily_report_missing_date_rejected():
    r = client.post("/daily-report", json={"rows": ROWS})
    assert r.status_code == 422


def test_daily_report_engine_failure_is_502(monkeypatch):
    def boom(d, r):
        raise DailyReportError("both engines down")

    monkeypatch.setattr(main.daily_report, "generate_daily_report", boom)
    r = client.post("/daily-report", json={"date": "2026-07-23", "rows": ROWS})
    assert r.status_code == 502
    assert "both engines down" in r.json()["detail"]
