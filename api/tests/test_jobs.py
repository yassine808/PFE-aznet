"""The scheduled jobs, without a database, a Sheet or an SMTP relay.

What matters here is the part that cost a bug in the n8n version: a parked row
must only leave the queue once the Sheet actually accepted it, and a failing job
must come back as a result rather than as an exception in the scheduler thread.
"""
from datetime import datetime

import pytest
import time
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
        "report": {"goulotte_m": 150, "resume": "Pose de 150 m de goulotte."},
    },
}


def test_drain_files_through_the_journal_and_resolves(monkeypatch):
    """The drain must merge like the live path, not append blindly — a parked
    row whose day already has a row would otherwise become a duplicate."""
    filed, resolved = [], []
    monkeypatch.setattr(jobs.logs, "pending_writes", lambda n: [QUEUED])
    monkeypatch.setattr(jobs.journal, "file_report",
                        lambda payload: filed.append(payload) or {"row": 12})
    monkeypatch.setattr(jobs.logs, "resolve_write", lambda i, ok, err=None: resolved.append((i, ok)))

    out = jobs.drain_sheet_queue()

    assert out == {"pending": 1, "written": 1, "failed": []}
    assert resolved == [(7, True)]
    assert filed[0]["technicien"] == "Yassine"
    assert filed[0]["warnings"] == ["short_transcription"]


def test_drain_keeps_row_when_sheet_refuses(monkeypatch):
    resolved = []

    def boom(payload):
        raise SheetsError("quota")

    monkeypatch.setattr(jobs.logs, "pending_writes", lambda n: [QUEUED])
    monkeypatch.setattr(jobs.journal, "file_report", boom)
    monkeypatch.setattr(jobs.logs, "resolve_write", lambda i, ok, err=None: resolved.append((i, ok, err)))

    out = jobs.drain_sheet_queue()

    assert out["written"] == 0
    assert out["failed"][0]["id"] == 7
    assert resolved == [(7, False, "quota")]  # attempt counted, row still pending


def test_drain_does_not_stall_on_an_unprocessable_payload(monkeypatch):
    """A payload the schema cannot parse never will — it must not block the
    batch behind it, and it must not vanish either."""
    resolved = []

    def boom(payload):
        raise ValueError("resume missing")

    monkeypatch.setattr(jobs.logs, "pending_writes", lambda n: [QUEUED])
    monkeypatch.setattr(jobs.journal, "file_report", boom)
    monkeypatch.setattr(jobs.logs, "resolve_write", lambda i, ok, err=None: resolved.append((i, ok, err)))

    out = jobs.drain_sheet_queue()

    assert out["written"] == 0
    assert "unprocessable" in out["failed"][0]["error"]
    assert resolved[0][1] is False


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


def test_run_times_out_a_hung_job(monkeypatch):
    """A job that hangs on a slow upstream must not freeze the scheduler: the
    overrun is recorded as a failed run the operator can see and re-trigger."""
    monkeypatch.setattr(jobs.logs, "write_safe", lambda *a, **k: None)
    monkeypatch.setitem(jobs.JOBS, "hang", lambda: time.sleep(5))
    monkeypatch.setitem(jobs._TIMEOUT_SECONDS, "hang", 0.2)

    status = jobs.run("hang")

    assert status["ok"] is False
    assert "timed out" in status["error"]
    assert jobs.status()  # the panel still has something to show


def test_run_fast_job_with_timeout_config_keeps_result(monkeypatch):
    """The timed path must not interfere with a job that finishes in time."""
    monkeypatch.setattr(jobs.logs, "write_safe", lambda *a, **k: None)
    monkeypatch.setitem(jobs.JOBS, "quick", lambda: {"done": 1})
    monkeypatch.setitem(jobs._TIMEOUT_SECONDS, "quick", 5)

    status = jobs.run("quick")

    assert status["ok"] is True
    assert status["result"] == {"done": 1}


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


def test_report_recipients_prefer_account_emails(monkeypatch):
    """Account emails are the source of truth once accounts exist; the manual
    list is only the fallback for installs without any."""
    monkeypatch.setattr(jobs.logs, "account_emails", lambda: ["directeur@aznet.ma"])
    monkeypatch.setattr(jobs.logs, "get_settings", lambda: {"emails": ["chef@aznet.ma"]})
    assert jobs._report_recipients() == ["directeur@aznet.ma"]

    monkeypatch.setattr(jobs.logs, "account_emails", lambda: [])
    assert jobs._report_recipients() == ["chef@aznet.ma"]


def test_weekly_report_covers_the_whole_week(monkeypatch):
    seen = {}
    rows = [
        {"date": "2026-07-27", "resume": "lundi"},   # Monday of that week
        {"date": "2026-07-31", "resume": "vendredi"},
        {"date": "2026-07-26", "resume": "dimanche d'avant"},  # previous week
    ]
    monkeypatch.setattr(jobs.sheets, "read_reports", lambda: rows)
    # No org chart rows in a DB-free test → the director's digest falls back to
    # the manual recipient list, and nobody's team buckets exist.
    monkeypatch.setattr(jobs.logs, "list_persons", lambda: [])
    monkeypatch.setattr(jobs.logs, "account_emails", lambda: [])
    monkeypatch.setattr(jobs.logs, "get_settings", lambda: {"emails": ["chef@aznet.ma"]})
    monkeypatch.setattr(
        jobs.daily_report, "generate_daily_report",
        lambda label, r: seen.update(label=label, n=len(r))
        or jobs.daily_report.DailyReportContent(objet="Hebdo", corps="…"),
    )
    monkeypatch.setattr(jobs.mailer, "send", lambda to, s, b, **k: list(to))

    out = jobs.send_weekly_report("2026-07-31")  # a Friday

    assert seen == {"label": "2026-07-27 → 2026-07-31", "n": 2}
    assert out["rows"] == 2
    assert out["sent_to"] == ["chef@aznet.ma"]
    assert out["managers"] == 0


def test_daily_report_is_per_manager(monkeypatch):
    """The director gets the company digest; each chef gets their team's rows,
    and every generated version is stored for the /rapport command."""
    persons = [
        {"id": 1, "name": "Directeur", "role": "directeur", "has_login": True, "email": "d@aznet.ma"},
        {"id": 2, "name": "Chef A", "role": "chef", "has_login": True, "email": "a@aznet.ma"},
        {"id": 3, "name": "Tech 1", "role": "tech", "has_login": False, "email": None, "manager_id": 2},
        {"id": 4, "name": "Tech 2", "role": "tech", "has_login": False, "email": None, "manager_id": 2},
    ]
    rows = [
        {"date": "2026-08-01", "technicien": "Tech 1", "resume": "salle 1"},
        {"date": "2026-08-01", "technicien": "Tech 2", "resume": "salle 2"},
        {"date": "2026-08-01", "technicien": "Inconnu", "resume": "libre"},
    ]
    generated, sent, stored = [], [], []

    def fake_gen(label, r):
        generated.append((label, sorted(row["resume"] for row in r)))
        return jobs.daily_report.DailyReportContent(objet=f"Rapport {label}", corps="corps")

    monkeypatch.setattr(jobs.sheets, "read_reports", lambda: rows)
    monkeypatch.setattr(jobs.logs, "list_persons", lambda: persons)
    monkeypatch.setattr(jobs.logs, "account_emails", lambda: [])
    monkeypatch.setattr(jobs.logs, "get_settings", lambda: {"emails": []})
    monkeypatch.setattr(jobs.daily_report, "generate_daily_report", fake_gen)
    monkeypatch.setattr(jobs.mailer, "send", lambda to, s, b, **k: sent.append(to) or to)
    monkeypatch.setattr(
        jobs.logs, "save_manager_report",
        lambda mid, period, o, c, g="automatique", pt="daily": stored.append((mid, period, pt)),
    )

    out = jobs.send_daily_report("2026-08-01")

    # Company digest sees everything; Chef A's sees only their two techs.
    assert ("2026-08-01", ["libre", "salle 1", "salle 2"]) in generated
    assert ("2026-08-01", ["salle 1", "salle 2"]) in generated
    assert out["managers"] == 1
    assert out["reports"][0]["manager"] == "Chef A"
    assert stored == [(2, "2026-08-01", "daily")]
    assert sorted(out["sent_to"]) == ["a@aznet.ma", "d@aznet.ma"]


def test_weekly_report_stores_period_type(monkeypatch):
    """The weekly run tags its stored rows 'weekly' so the dashboard's
    generated-reports list can separate the two cadences."""
    persons = [
        {"id": 1, "name": "Directeur", "role": "directeur", "has_login": True, "email": "d@aznet.ma"},
        {"id": 2, "name": "Chef B", "role": "chef", "has_login": True, "email": "b@aznet.ma"},
        {"id": 3, "name": "Tech 1", "role": "tech", "has_login": False, "email": None, "manager_id": 2},
    ]
    rows = [
        {"date": "2026-07-27", "technicien": "Tech 1", "resume": "lundi"},
        {"date": "2026-07-31", "technicien": "Tech 1", "resume": "vendredi"},
    ]
    stored = []

    def fake_gen(label, r):
        return jobs.daily_report.DailyReportContent(objet="Hebdo", corps="…")

    monkeypatch.setattr(jobs.sheets, "read_reports", lambda: rows)
    monkeypatch.setattr(jobs.logs, "list_persons", lambda: persons)
    monkeypatch.setattr(jobs.logs, "account_emails", lambda: [])
    monkeypatch.setattr(jobs.logs, "get_settings", lambda: {"emails": []})
    monkeypatch.setattr(jobs.daily_report, "generate_daily_report", fake_gen)
    monkeypatch.setattr(jobs.mailer, "send", lambda to, s, b, **k: to)
    monkeypatch.setattr(
        jobs.logs, "save_manager_report",
        lambda mid, period, o, c, g="automatique", pt="daily": stored.append((mid, pt)),
    )

    out = jobs.send_weekly_report("2026-07-31")

    assert out["managers"] == 1
    assert stored == [(2, "weekly")]


def test_manager_buckets_ignore_unassigned_rows(monkeypatch):
    """Rows from unknown senders or technicians without a chef never vanish:
    they stay in the director's digest, they just have no team bucket."""
    persons = [
        {"id": 1, "name": "Directeur", "role": "directeur", "has_login": True, "email": "d@aznet.ma"},
        {"id": 2, "name": "Chef B", "role": "chef", "has_login": True, "email": "b@aznet.ma"},
        {"id": 3, "name": "Tech 1", "role": "tech", "has_login": False, "email": None, "manager_id": 2},
        {"id": 4, "name": "Solo", "role": "tech", "has_login": False, "email": None, "manager_id": None},
    ]
    rows = [
        {"technicien": "Tech 1", "resume": "sous Chef B"},
        {"technicien": "Solo", "resume": "sans chef"},
        {"technicien": "Inconnu", "resume": "inconnu"},
    ]

    buckets = jobs._manager_buckets(persons, rows)

    assert set(buckets) == {2}
    assert [r["resume"] for r in buckets[2]] == ["sous Chef B"]


def test_weekly_due_only_on_the_configured_day(monkeypatch):
    monkeypatch.setattr(jobs, "_settings_safe", lambda: {"weekly_day": 4, "weekly_time": "17:00"})
    friday_evening = datetime(2026, 7, 31, 17, 30)
    friday_morning = datetime(2026, 7, 31, 9, 0)
    thursday = datetime(2026, 7, 30, 17, 30)

    assert jobs._due(friday_evening, None, "weekly_report") is True
    assert jobs._due(friday_morning, None, "weekly_report") is False
    assert jobs._due(thursday, None, "weekly_report") is False
    assert jobs._due(friday_evening, friday_evening, "weekly_report") is False


def test_manager_without_email_does_not_abort_the_report_job(monkeypatch):
    """A chef with no account email must not take the whole daily job down.

    `mailer.send([])` raises, and it used to propagate: the company digest went
    out, then the first email-less chef aborted the loop — so the remaining
    chefs lost their mail *and* their stored report, which is exactly what the
    /rapport command answers with.
    """
    rows = [{"date": "2026-08-04", "technicien": "Ali", "resume": "x"}]
    persons = [
        {"id": 1, "name": "Dir", "role": "directeur", "has_login": True,
         "email": "d@x.ma", "manager_id": None},
        {"id": 2, "name": "Chef", "role": "chef", "has_login": False,
         "email": None, "manager_id": None},
        {"id": 3, "name": "Ali", "role": "tech", "has_login": False,
         "email": None, "manager_id": 2},
    ]
    stored = []
    monkeypatch.setattr(jobs.sheets, "read_reports", lambda: rows)
    monkeypatch.setattr(jobs.logs, "list_persons", lambda: persons)
    monkeypatch.setattr(jobs.logs, "save_manager_report",
                        lambda *a: stored.append(a))
    monkeypatch.setattr(jobs.daily_report, "generate_daily_report",
                        lambda period, r: jobs.daily_report.DailyReportContent(objet="o", corps="c"))

    def fake_send(to, subject, body, **kwargs):
        addresses = [a for a in to if a]
        if not addresses:
            raise jobs.mailer.MailError("aucun destinataire configuré")
        return addresses

    monkeypatch.setattr(jobs.mailer, "send", fake_send)

    result = jobs.send_daily_report("2026-08-04")
    assert result["sent_to"] == ["d@x.ma"]          # the director still got theirs
    assert result["managers"] == 1                   # the chef's report was still built
    assert stored                                    # …and stored for /rapport
    assert stored[0][0] == 2
    assert result["reports"][0]["mail_error"]        # the failure is visible, not swallowed


def test_report_link_targets_the_period_it_covers(monkeypatch):
    """The mail's button opens *that* report, not a list to search.

    A weekly period is a range label; the weekly panel selects a week by its
    Monday, so the link has to carry the left half of the range. Getting this
    wrong is invisible in a test that only checks the URL is non-empty — it
    lands the reader on the current week instead of the one they were mailed.

    `monkeypatch.setattr` rather than a plain assignment: `settings` is a
    process-wide singleton, and a test that leaves a fake hostname on it hands
    every later test in the session a URL nobody set.
    """
    monkeypatch.setattr(jobs.settings, "dashboard_url", "https://aznet.example/")
    assert (
        jobs._report_link("2026-08-05")
        == "https://aznet.example/#/daily?date=2026-08-05"
    )
    assert (
        jobs._report_link("2026-08-03 → 2026-08-09")
        == "https://aznet.example/#/weekly?week=2026-08-03"
    )


def test_report_mail_carries_banner_and_button():
    """Rendered document, not the plain body with <br> between the lines."""
    from app.daily_report import DailyReportContent

    html = jobs._report_html(
        "2026-08-05",
        DailyReportContent(objet="Rapport du 5", corps="Trois interventions."),
        3,
    )
    # The masthead is text plus the brand mark, and the mark travels *with* the
    # message: a remote src would be blocked by default in Gmail, so a header
    # referencing anything but a cid: would arrive as a grey box.
    assert "cid:aznet-logo" in html
    assert "AZ Net" in html
    assert "https://" not in html.split("<h1")[0]  # nothing remote above the fold
    assert "Ouvrir le rapport" in html
    assert "<table" in html
