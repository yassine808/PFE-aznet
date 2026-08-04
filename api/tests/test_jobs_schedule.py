"""Scheduler seeding and supervisor robustness.

Two regressions:

- `_loop` seeded every job's `last_run` with process start, and `_due` gates the
  daily/weekly bands on `last.date() < now.date()`. A restart at 08:00 therefore
  cancelled that day's 18:30 report — silently, with nothing logged anywhere.
- `run()` ended with `result["status"]` and `_loop` called it unguarded, so a
  worker that died before writing that key would kill the scheduler thread and
  with it all six jobs.
"""
from datetime import datetime, timedelta

from app import jobs


# ── seeding: the restart that used to cost a day's report ──────────────────


def test_seed_uses_the_recorded_run_not_process_start(monkeypatch):
    yesterday = datetime.now() - timedelta(days=1)
    monkeypatch.setattr(jobs.logs, "last_job_runs", lambda: {"daily_report": yesterday})
    seeded = jobs._seed_last_run()
    assert seeded["daily_report"] == yesterday
    # …so the band is due today, which is exactly what the old seed prevented.
    now = datetime.now().replace(hour=19, minute=0)
    monkeypatch.setattr(jobs, "_settings_safe", lambda: {"daily_time": "18:30"})
    if now.weekday() != 6:  # Sunday has no report at all, by design
        assert jobs._due(now, seeded["daily_report"], "daily_report")


def test_seed_keeps_todays_run_so_a_restart_cannot_double_send(monkeypatch):
    """The other half of the bargain: a restart *after* the send must not resend."""
    today_1830 = datetime.now().replace(hour=18, minute=30, second=0, microsecond=0)
    monkeypatch.setattr(jobs.logs, "last_job_runs", lambda: {"daily_report": today_1830})
    monkeypatch.setattr(jobs, "_settings_safe", lambda: {"daily_time": "18:30"})
    seeded = jobs._seed_last_run()
    later = today_1830.replace(hour=19)
    assert not jobs._due(later, seeded["daily_report"], "daily_report")


def test_seed_falls_back_to_process_start_when_the_store_is_down(monkeypatch):
    def boom():
        raise jobs.logs.LogStoreError("down")

    monkeypatch.setattr(jobs.logs, "last_job_runs", boom)
    seeded = jobs._seed_last_run()
    # Skipping one report beats mailing every manager twice.
    assert seeded["daily_report"] is not None
    # The drain stays the exception: idempotent, so due immediately.
    assert seeded["sheet_queue"] is None


def test_unrecorded_job_falls_back_to_process_start(monkeypatch):
    monkeypatch.setattr(jobs.logs, "last_job_runs", lambda: {})
    seeded = jobs._seed_last_run()
    assert seeded["weekly_report"] is not None


# ── the supervisor must not be killable ────────────────────────────────────


def test_run_records_a_failure_when_the_worker_leaves_no_status(monkeypatch):
    """Regression: this used to raise KeyError straight into the loop."""
    monkeypatch.setitem(jobs.JOBS, "sheet_queue", lambda: {"ok": 1})
    monkeypatch.setattr(jobs, "_execute", lambda *a, **k: None)  # writes no status
    monkeypatch.setattr(jobs.logs, "write_safe", lambda *a, **k: None)
    status = jobs.run("sheet_queue")
    assert status["ok"] is False
    assert "no status" in status["error"]


def test_a_raising_job_is_recorded_not_propagated(monkeypatch):
    def boom():
        raise RuntimeError("google exploded")

    monkeypatch.setitem(jobs.JOBS, "prune_logs", boom)
    monkeypatch.setattr(jobs.logs, "write_safe", lambda *a, **k: None)
    status = jobs.run("prune_logs")
    assert status["ok"] is False
    assert "google exploded" in status["error"]
