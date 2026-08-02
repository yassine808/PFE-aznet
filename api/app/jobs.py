"""Scheduled maintenance — the three n8n cron bands, moved into the API.

They used to be extra bands in `n8n/aznet-complete.json`. They now live here so
the dashboard can show what ran, show what it produced, and re-run it by hand,
which a cron node inside n8n could never offer.

Two rules shape this file:

- **A job never raises into the scheduler.** Every run is wrapped and its
  failure recorded as a result, because a thread that dies at 03:00 takes the
  other three jobs with it and nobody finds out until the Sheet is empty.
- **Times come from `app_settings`, not from constants.** The dashboard already
  edits `daily_time`; a second copy of that hour in Python would drift the day
  someone changes it and wonders why the mail still arrives at 18:30.

Threading rather than APScheduler: one loop, a 30-second tick and four due
checks is the whole requirement, and a dependency would need pinning, mocking in
tests and explaining in the mémoire.
"""
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from app import daily_report, logs, mailer, memory, sheets

# How often the loop wakes to look for due work. Well under the tightest
# interval (5 min) so the drain never drifts by a meaningful amount.
TICK_SECONDS = 30

RETENTION_DAYS = 30
DRAIN_INTERVAL_MINUTES = 5
DRAIN_BATCH = 50
NIGHTLY_HOUR = 3  # log prune + profile rebuild, while nobody is sending

# name -> last result, newest wins. Read by GET /jobs.
_STATUS: Dict[str, dict] = {}
_LOCK = threading.Lock()
_THREAD: Optional[threading.Thread] = None


# ── The jobs ───────────────────────────────────────────────────────────────


def drain_sheet_queue() -> dict:
    """Append every parked report the Sheet refused earlier.

    Reply-first ordering means a Sheets outage costs a row, never a technician's
    summary. This is the other half of that bargain: without it the rows sit in
    `failed_writes` forever.
    """
    pending = logs.pending_writes(DRAIN_BATCH)
    written, failed = 0, []
    for item in pending:
        payload = item.get("payload") or {}
        report = payload.get("report") or {}
        warnings = payload.get("warnings") or []
        row = {
            "date": payload.get("date"),
            "heure": payload.get("heure"),
            "canal": payload.get("canal"),
            "technicien": payload.get("technicien"),
            "role": payload.get("role"),
            "rapport_complet": payload.get("rapport_complet"),
            "confidence": payload.get("confidence"),
            "lien_audio": payload.get("lien_audio"),
            # Same rule as the n8n node: anything the model was unsure about is
            # flagged for a human rather than trusted because it was retried.
            "flag_review": bool(
                {"low_confidence_transcription", "short_transcription", "image_input"}
                & set(warnings)
            ),
            **report,
        }
        try:
            sheets.append_report(row)
        except sheets.SheetsError as exc:
            # Left in the queue with the attempt counted, not dropped.
            logs.resolve_write(item["id"], False, str(exc))
            failed.append({"id": item["id"], "error": str(exc)})
            continue
        logs.resolve_write(item["id"], True)
        written += 1
    return {"pending": len(pending), "written": written, "failed": failed}


def prune_logs() -> dict:
    """Retention sweep on both time-series tables."""
    return {
        "logs_deleted": logs.prune(RETENTION_DAYS),
        "samples_deleted": logs.prune_samples(RETENTION_DAYS),
    }


def refresh_profiles() -> dict:
    """Rebuild every technician profile from the Sheet.

    The Sheet is read once for all of them: it is the slow part, and reading it
    per technician would turn a nightly job into a quota problem of its own.
    """
    persons = logs.list_persons()
    rows = sheets.read_reports()
    results = [memory.refresh_person(p, rows) for p in persons]
    return {
        "persons": len(persons),
        "refreshed": sum(1 for r in results if r["updated"]),
        "skipped": [r["name"] for r in results if not r["updated"]],
    }


def _report_recipients() -> List[str]:
    """Who the company report goes to: every account's email (admin + site managers).

    The `emails` app setting is the manual fallback, kept for installs where no
    account row carries an email yet — once the org chart has accounts, the list
    derives from the database and cannot drift from who can log in.
    """
    recipients = logs.account_emails()
    if not recipients:
        recipients = logs.get_settings().get("emails") or []
    return recipients


def _manager_buckets(persons: List[dict], rows: List[dict]) -> Dict[int, List[dict]]:
    """Bucket rows by the chef each sender reports to: manager person id → rows.

    A row is attributed through the sender's name (the Sheet has no channel
    ids), the same key the directory matches on. Rows whose sender resolves to
    no person, or to a person without a chef, belong to nobody's team — they
    only appear in the director's company-wide digest, so nothing a technician
    actually sent can be lost because the org chart is incomplete.
    """
    by_name = {p["name"].strip().lower(): p for p in persons}
    buckets: Dict[int, List[dict]] = {}
    for row in rows:
        person = by_name.get((row.get("technicien") or "").strip().lower())
        manager_id = None
        if person is not None:
            # A chef's own rows land in their own report; a tech's rows land in
            # their chef's. Unassigned or unknown senders stay with the director.
            manager_id = person.get("manager_id") or (
                person["id"] if person.get("role") == "chef" else None
            )
        if manager_id:
            buckets.setdefault(manager_id, []).append(row)
    return buckets


def _report_mail(
    recipients: List[str], period: str, rows: List[dict]
) -> dict:
    """Generate one digest and mail it. Returns what the jobs report back."""
    if not rows:
        return {"rows": 0, "sent_to": [], "reason": "aucun rapport"}
    content = daily_report.generate_daily_report(period, rows)
    sent = mailer.send(recipients, content.objet, content.corps, html=True)
    return {
        "rows": len(rows), "sent_to": sent, "subject": content.objet,
        "generated_by": "automatique", "objet": content.objet, "corps": content.corps,
    }


def send_daily_report(date: Optional[str] = None) -> dict:
    """Today's rows → one French summary per site manager, each to their inbox.

    Reports became per-manager: the director gets the company-wide digest, and
    every chef gets their team's. Each generated version is stored so the
    technicians' /rapport command answers with the *same* text the mail showed.
    """
    day = date or datetime.now().strftime("%Y-%m-%d")
    rows = [r for r in sheets.read_reports() if r.get("date") == day]
    if not rows:
        # Not an error: a Sunday with no reports is a normal outcome, and mailing
        # an empty report teaches the manager to ignore the mail.
        return {"date": day, "rows": 0, "sent_to": [], "reason": "aucun rapport pour cette date"}
    persons = logs.list_persons()
    buckets = _manager_buckets(persons, rows)
    by_id = {p["id"]: p for p in persons}

    # The company digest goes to the director(s); without a director row the
    # manual recipient list takes over, so an install without an org chart
    # behaves exactly as before this split.
    directors = [p for p in persons if p.get("role") == "directeur" and p.get("has_login") and p.get("email")]
    director_rcpts = [p["email"] for p in directors] or _report_recipients()
    company = _report_mail(director_rcpts, day, rows)

    sent_all = set(company["sent_to"])
    manager_reports = []
    for manager_id, team in sorted(buckets.items()):
        chef = by_id.get(manager_id)
        if chef is None:
            continue
        rcpts = [chef["email"]] if chef.get("has_login") and chef.get("email") else []
        result = _report_mail(rcpts, day, team)
        if result["rows"]:
            sent_all.update(result["sent_to"])
            manager_reports.append(
                {"manager": chef["name"], "rows": result["rows"], "sent_to": result["sent_to"]}
            )
            # Stored even when the chef has no email: the /rapport command
            # answers from here, and a report a technician can read is worth
            # generating even if no account row is set up yet.
            logs.save_manager_report(
                manager_id, day, result["objet"], result["corps"], result["generated_by"]
            )

    return {
        "date": day,
        "rows": len(rows),
        "sent_to": sorted(sent_all),
        "subject": company["subject"],
        "managers": len(manager_reports),
        "reports": manager_reports,
        "generated_by": "automatique",
    }


def send_weekly_report(end: Optional[str] = None) -> dict:
    """Monday→today of the current week, same generator as the daily mail.

    There is deliberately no weekly prompt: `/daily-report` already takes an
    arbitrary row set and a free-text label, and the dashboard's weekly panel
    has been calling it that way since it was built. A second prompt would be a
    second thing to keep true when the Sheet columns change.
    """
    last_day = datetime.strptime(end, "%Y-%m-%d") if end else datetime.now()
    first_day = last_day - timedelta(days=last_day.weekday())
    span = {(first_day + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}
    rows = [r for r in sheets.read_reports() if r.get("date") in span]
    label = f"{first_day.strftime('%Y-%m-%d')} → {last_day.strftime('%Y-%m-%d')}"
    if not rows:
        return {"period": label, "rows": 0, "sent_to": [], "reason": "aucun rapport sur la période"}
    persons = logs.list_persons()
    buckets = _manager_buckets(persons, rows)
    by_id = {p["id"]: p for p in persons}

    directors = [p for p in persons if p.get("role") == "directeur" and p.get("has_login") and p.get("email")]
    director_rcpts = [p["email"] for p in directors] or _report_recipients()
    company = _report_mail(director_rcpts, label, rows)

    sent_all = set(company["sent_to"])
    manager_reports = []
    for manager_id, team in sorted(buckets.items()):
        chef = by_id.get(manager_id)
        if chef is None:
            continue
        rcpts = [chef["email"]] if chef.get("has_login") and chef.get("email") else []
        result = _report_mail(rcpts, label, team)
        if result["rows"]:
            sent_all.update(result["sent_to"])
            manager_reports.append(
                {"manager": chef["name"], "rows": result["rows"], "sent_to": result["sent_to"]}
            )
            logs.save_manager_report(
                manager_id, label, result["objet"], result["corps"], result["generated_by"]
            )

    return {
        "period": label,
        "rows": len(rows),
        "sent_to": sorted(sent_all),
        "subject": company["subject"],
        "managers": len(manager_reports),
        "reports": manager_reports,
        "generated_by": "automatique",
    }


JOBS: Dict[str, Callable[[], dict]] = {
    "sheet_queue": drain_sheet_queue,
    "prune_logs": prune_logs,
    "profiles": refresh_profiles,
    "daily_report": send_daily_report,
    "weekly_report": send_weekly_report,
}


# ── Running and remembering ────────────────────────────────────────────────


def run(name: str) -> dict:
    """Run one job, record the outcome, never raise.

    The same path serves the scheduler and the dashboard's "Run now" button, so
    a manual run is visible in the panel exactly like an automatic one.
    """
    job = JOBS.get(name)
    if job is None:
        raise KeyError(name)
    started = time.time()
    try:
        result: dict = job()
        status = {"job": name, "ok": True, "result": result}
    except Exception as exc:  # any failure is data, not a crash  # noqa: BLE001
        status = {"job": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    status["at"] = datetime.now().isoformat(timespec="seconds")
    status["seconds"] = round(time.time() - started, 2)
    with _LOCK:
        _STATUS[name] = status
    logs.write_safe(
        f"job:{name}",
        "info" if status["ok"] else "error",
        message=status.get("error") or "ok",
        detail=status.get("result"),
    )
    return status


def status() -> List[dict]:
    """One entry per job, with its schedule and last outcome."""
    with _LOCK:
        last = dict(_STATUS)
    return [
        {"name": name, "schedule": _schedule_label(name), "last": last.get(name)}
        for name in JOBS
    ]


DAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _schedule_label(name: str) -> str:
    if name == "sheet_queue":
        return f"toutes les {DRAIN_INTERVAL_MINUTES} min"
    if name in ("prune_logs", "profiles"):
        return f"chaque nuit à {NIGHTLY_HOUR:02d}:00"
    row = _settings_safe()
    if name == "daily_report":
        return f"du lundi au samedi à {row.get('daily_time') or '18:30'}"
    day = DAYS_FR[_weekly_day(row)]
    return f"chaque {day} à {row.get('weekly_time') or '17:00'}"


def _weekly_day(row: dict) -> int:
    """0 = Monday, matching both `datetime.weekday()` and the dashboard's picker."""
    try:
        return max(0, min(6, int(row.get("weekly_day", 4))))
    except (TypeError, ValueError):
        return 4  # Friday


def _hhmm(raw: Optional[str], fallback: tuple) -> tuple:
    try:
        hour, minute = (int(x) for x in str(raw).split(":")[:2])
    except (AttributeError, ValueError):
        return fallback
    return hour, minute


def _settings_safe() -> dict:
    try:
        return logs.get_settings()
    except Exception:  # noqa: BLE001 — DB down must not blank the panel
        return {}


# ── The loop ───────────────────────────────────────────────────────────────


def _due(now: datetime, last: Optional[datetime], name: str) -> bool:
    if name == "sheet_queue":
        return last is None or now - last >= timedelta(minutes=DRAIN_INTERVAL_MINUTES)
    if name in ("prune_logs", "profiles"):
        return now.hour == NIGHTLY_HOUR and (last is None or last.date() < now.date())

    row = _settings_safe()
    if name == "weekly_report":
        # Once on the chosen weekday. `last.date() < now.date()` alone would fire
        # again next week's same day, which is exactly what we want.
        if now.weekday() != _weekly_day(row):
            return False
        hour, minute = _hhmm(row.get("weekly_time"), (17, 0))
    else:  # daily_report: Monday–Saturday, once per day
        if now.weekday() == 6:  # Sunday: no site work, no report
            return False
        hour, minute = _hhmm(row.get("daily_time"), (18, 30))

    if (now.hour, now.minute) < (hour, minute):
        return False
    return last is None or last.date() < now.date()


def _loop() -> None:
    # Nothing has run yet in this process; a restart at 03:05 must not replay the
    # nightly jobs, so "never run" counts as due only for the 5-minute drain.
    started = datetime.now()
    last_run: Dict[str, Optional[datetime]] = {
        name: (None if name == "sheet_queue" else started) for name in JOBS
    }
    while True:
        now = datetime.now()
        for name in JOBS:
            if _due(now, last_run[name], name):
                last_run[name] = now
                run(name)
        time.sleep(TICK_SECONDS)


def start() -> bool:
    """Start the scheduler once per process. Returns False if already running."""
    global _THREAD
    if _THREAD is not None and _THREAD.is_alive():
        return False
    _THREAD = threading.Thread(target=_loop, name="aznet-jobs", daemon=True)
    _THREAD.start()
    return True
