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
    monkeypatch.setattr(main.daily_report, "generate_daily_report", lambda d, r, a=None: CONTENT)
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


def _capture_store(monkeypatch):
    """Record what the endpoint files in `manager_reports`, without a database.

    The override above is set at import time on a *shared* `main.app`, and five
    test modules do the same with four different identities — whichever imports
    last wins for the whole session. These two tests assert on the caller, so
    they pin their own and let monkeypatch put the previous one back.
    """
    monkeypatch.setitem(
        main.app.dependency_overrides,
        main.auth.require_user,
        lambda: {"id": 1, "name": "Test", "role": "directeur"},
    )
    calls = []
    monkeypatch.setattr(main.daily_report, "generate_daily_report", lambda d, r, a=None: CONTENT)
    monkeypatch.setattr(main.logs, "save_manager_report", lambda *a: calls.append(a))
    return calls


def test_daily_report_is_stored_for_the_caller(monkeypatch):
    """A dashboard run has to be written down, not just returned.

    The Reports page reads `manager_reports`; when this store is missing the
    report exists only in the tab that asked for it and the page stays empty
    with nothing to explain why.
    """
    calls = _capture_store(monkeypatch)
    r = client.post("/daily-report", json={"date": "2026-07-23", "rows": ROWS})
    assert r.status_code == 200
    assert calls == [(1, "2026-07-23", CONTENT.objet, CONTENT.corps, "Test", "daily")]


def test_weekly_label_is_stored_as_weekly(monkeypatch):
    """The range label is what separates a week from a day — same endpoint."""
    calls = _capture_store(monkeypatch)
    r = client.post(
        "/daily-report", json={"date": "2026-08-03 → 2026-08-09", "rows": ROWS}
    )
    assert r.status_code == 200
    assert calls[0][1] == "2026-08-03 → 2026-08-09"
    assert calls[0][5] == "weekly"


def test_daily_report_engine_failure_is_502(monkeypatch):
    def boom(d, r, a=None):
        raise DailyReportError("both engines down")

    monkeypatch.setattr(main.daily_report, "generate_daily_report", boom)
    r = client.post("/daily-report", json={"date": "2026-07-23", "rows": ROWS})
    assert r.status_code == 502
    assert "both engines down" in r.json()["detail"]
