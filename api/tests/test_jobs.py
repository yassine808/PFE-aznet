"""The scheduled jobs, without a database, a Sheet or an SMTP relay.

What matters here is the part that cost a bug in the n8n version: a parked row
must only leave the queue once the Sheet actually accepted it, and a failing job
must come back as a result rather than as an exception in the scheduler thread.
"""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import jobs
from app.sheets import SheetsError

client = TestClient(main.app)

main.app.dependency_overrides[main.auth.require_human] = lambda: {
    "id": 1, "name": "Test", "role": "directeur"
}

QUEUED = {
    "id": 7,
    "correlation_id": "abc",
    "payload": {
        "date": "2026-07-29",
        "heure": "09:15",
        "canal": "telegram",
        "technicien": "Yassine",
        "rapport_complet": "…",
        "warnings": ["short_transcription"],
        "report": {"chantier": "Atlas", "goulottes_m": 150},
    },
}


def test_drain_appends_and_resolves(monkeypatch):
    appended, resolved = [], []
    monkeypatch.setattr(jobs.logs, "pending_writes", lambda n: [QUEUED])
    monkeypatch.setattr(jobs.sheets, "append_report", lambda row: appended.append(row))
    monkeypatch.setattr(jobs.logs, "resolve_write", lambda i, ok, err=None: resolved.append((i, ok)))

    out = jobs.drain_sheet_queue()

    assert out == {"pending": 1, "written": 1, "failed": []}
    assert resolved == [(7, True)]
    # Flattened report fields and metadata land in one row; the warning flags it.
    assert appended[0]["chantier"] == "Atlas"
    assert appended[0]["technicien"] == "Yassine"
    assert appended[0]["flag_review"] is True


def test_drain_keeps_row_when_sheet_refuses(monkeypatch):
    resolved = []

    def boom(row):
        raise SheetsError("quota")

    monkeypatch.setattr(jobs.logs, "pending_writes", lambda n: [QUEUED])
    monkeypatch.setattr(jobs.sheets, "append_report", boom)
    monkeypatch.setattr(jobs.logs, "resolve_write", lambda i, ok, err=None: resolved.append((i, ok, err)))

    out = jobs.drain_sheet_queue()

    assert out["written"] == 0
    assert out["failed"][0]["id"] == 7
    assert resolved == [(7, False, "quota")]  # attempt counted, row still pending


def test_daily_report_without_rows_sends_nothing(monkeypatch):
    monkeypatch.setattr(jobs.sheets, "read_reports", lambda: [])
    monkeypatch.setattr(jobs.mailer, "send", lambda *a, **k: pytest.fail("should not mail"))

    out = jobs.send_daily_report("2026-07-29")

    assert out["rows"] == 0
    assert out["sent_to"] == []


def test_run_records_failure_instead_of_raising(monkeypatch):
    monkeypatch.setattr(jobs.logs, "write_safe", lambda *a, **k: None)
    monkeypatch.setitem(jobs.JOBS, "boom", lambda: (_ for _ in ()).throw(RuntimeError("nope")))

    status = jobs.run("boom")

    assert status["ok"] is False
    assert "nope" in status["error"]
    assert jobs.status()  # the panel still has something to show


def test_due_skips_sunday_for_daily_report(monkeypatch):
    monkeypatch.setattr(jobs, "_settings_safe", lambda: {"daily_time": "18:30"})
    sunday = datetime(2026, 8, 2, 19, 0)   # 2026-08-02 is a Sunday
    saturday = datetime(2026, 8, 1, 19, 0)

    assert jobs._due(sunday, None, "daily_report") is False
    assert jobs._due(saturday, None, "daily_report") is True
    # Same evening, already sent: not due twice.
    assert jobs._due(saturday, saturday.replace(hour=18, minute=31), "daily_report") is False


def test_jobs_endpoints(monkeypatch):
    monkeypatch.setattr(jobs.logs, "write_safe", lambda *a, **k: None)
    monkeypatch.setattr(jobs.logs, "get_settings", lambda: {"daily_time": "18:30"})
    monkeypatch.setattr(main.auth, "record", lambda *a, **k: None)
    monkeypatch.setitem(jobs.JOBS, "prune_logs", lambda: {"logs_deleted": 3})

    listed = client.get("/jobs")
    assert listed.status_code == 200
    assert {j["name"] for j in listed.json()["jobs"]} >= set(jobs.JOBS)

    ran = client.post("/jobs/prune_logs/run")
    assert ran.status_code == 200
    assert ran.json()["result"] == {"logs_deleted": 3}
    assert client.post("/jobs/nope/run").status_code == 404


def test_weekly_report_covers_the_whole_week(monkeypatch):
    seen = {}
    rows = [
        {"date": "2026-07-27", "resume": "lundi"},   # Monday of that week
        {"date": "2026-07-31", "resume": "vendredi"},
        {"date": "2026-07-26", "resume": "dimanche d'avant"},  # previous week
    ]
    monkeypatch.setattr(jobs.sheets, "read_reports", lambda: rows)
    monkeypatch.setattr(jobs.logs, "get_settings", lambda: {"emails": ["chef@aznet.ma"]})
    monkeypatch.setattr(
        jobs.daily_report, "generate_daily_report",
        lambda label, r: seen.update(label=label, n=len(r))
        or jobs.daily_report.DailyReportContent(objet="Hebdo", corps="…"),
    )
    monkeypatch.setattr(jobs.mailer, "send", lambda to, s, b, html=False: list(to))

    out = jobs.send_weekly_report("2026-07-31")  # a Friday

    assert seen == {"label": "2026-07-27 → 2026-07-31", "n": 2}
    assert out["rows"] == 2
    assert out["sent_to"] == ["chef@aznet.ma"]


def test_weekly_due_only_on_the_configured_day(monkeypatch):
    monkeypatch.setattr(jobs, "_settings_safe", lambda: {"weekly_day": 4, "weekly_time": "17:00"})
    friday_evening = datetime(2026, 7, 31, 17, 30)
    friday_morning = datetime(2026, 7, 31, 9, 0)
    thursday = datetime(2026, 7, 30, 17, 30)

    assert jobs._due(friday_evening, None, "weekly_report") is True
    assert jobs._due(friday_morning, None, "weekly_report") is False
    assert jobs._due(thursday, None, "weekly_report") is False
    assert jobs._due(friday_evening, friday_evening, "weekly_report") is False
