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

from app import daily_report, journal, logs, mailer, memory, sheets
from app.config import settings

# How often the loop wakes to look for due work. Well under the tightest
# interval (5 min) so the drain never drifts by a meaningful amount.
TICK_SECONDS = 30

RETENTION_DAYS = 30
DRAIN_INTERVAL_MINUTES = 5
DRAIN_BATCH = 50
NIGHTLY_HOUR = 3  # log prune + profile rebuild, while nobody is sending
REMINDER_INTERVAL_SECONDS = 60  # task reminders fire within a minute of due

# Ceiling per job, generous but bounded: a hung Google/SMTP call must cost the
# operator a visible failed run, not a frozen scheduler. Jobs not listed here
# run inline (they are DB-only and fast).
_TIMEOUT_SECONDS = {
    "sheet_queue": 120,
    # Sheet read + SMTP + one LLM call for the company digest *and one more per
    # site manager* (reports went per-manager on this branch): 180 s was sized
    # for the single-digest era and would kill the job — and every chef's stored
    # report with it — as soon as the org chart has a few chefs.
    "daily_report": 600,
    "weekly_report": 600,
    "profiles": 300,       # one Sheet read + one LLM call per technician
    "prune_logs": 120,
    "reminders": 60,
}

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
        try:
            # Through `journal.file_report`, not a raw append: a parked row
            # whose day already has a row on the sheet must merge into it, or
            # the retry would create the duplicate the live path avoided.
            appended_row = journal.file_report(payload).get("row")
        except sheets.SheetsError as exc:
            # Left in the queue with the attempt counted, not dropped.
            logs.resolve_write(item["id"], False, str(exc))
            failed.append({"id": item["id"], "error": str(exc)})
            continue
        except Exception as exc:  # noqa: BLE001
            # A payload the schema cannot parse will never parse: retrying it
            # forever blocks the batch behind it, so it is resolved as failed
            # and stays visible in the dashboard instead of stalling the drain.
            logs.resolve_write(item["id"], False, f"unprocessable: {exc}")
            failed.append({"id": item["id"], "error": f"unprocessable: {exc}"})
            continue
        logs.resolve_write(item["id"], True)
        # Link the parked message to the row it landed on, so a /modify reply
        # can find it even when the happy path's append is the one that failed.
        message_id = payload.get("message_id")
        if message_id and appended_row:
            try:
                logs.link_message_row(message_id, appended_row)
            except logs.LogStoreError:
                pass  # best-effort like the append itself
        written += 1
    return {"pending": len(pending), "written": written, "failed": failed}


def prune_logs() -> dict:
    """Retention sweep on the time-series tables *and* the never-pruned ones:
    expired sessions, idempotency claims, the audit trail and page visits."""
    return {
        "logs_deleted": logs.prune(RETENTION_DAYS),
        "samples_deleted": logs.prune_samples(RETENTION_DAYS),
        **logs.prune_meta(RETENTION_DAYS),
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
    """Generate one digest and mail it. Returns what the jobs report back.

    The mail is best-effort *per report*: the reports loop below is per manager,
    and a chef with no account email (`mailer.send([])` raises) or one bounced
    address must not abort the whole job — the remaining chefs would lose their
    mail and, worse, their stored report, which is what /rapport answers with.
    The failure travels in `mail_error` so the operator still sees it in the
    Automation panel instead of it disappearing.
    """
    if not rows:
        return {"rows": 0, "sent_to": [], "reason": "aucun rapport"}
    content = daily_report.generate_daily_report(period, rows)
    sent: List[str] = []
    mail_error = None
    try:
        sent = mailer.send(
            recipients,
            content.objet,
            content.corps,
            html_body=_report_html(period, content, len(rows)),
        )
    except mailer.MailError as exc:
        mail_error = str(exc)
    return {
        "rows": len(rows), "sent_to": sent, "subject": content.objet,
        "generated_by": "automatique", "objet": content.objet, "corps": content.corps,
        "mail_error": mail_error,
    }


def _report_link(period: str) -> str:
    """Deep link that opens this exact report in the dashboard.

    A weekly period is a range label (`2026-08-03 → 2026-08-09`); the weekly
    panel selects a week by its Monday, so the link carries that. A daily
    period is already the day. Both land on the panel with the period selected
    rather than on a list the reader then has to search — the mail says "voici
    le rapport", so the button has to open *that* one.
    """
    base = settings.dashboard_url.rstrip("/")
    if "→" in period:
        monday = period.split("→")[0].strip()
        return f"{base}/#/weekly?week={monday}"
    return f"{base}/#/daily?date={period}"


def _report_html(period: str, content, rows: int) -> str:
    """The report mail: banner, the model's own text, and a way back in."""
    weekly = "→" in period
    return mailer.render_document(
        title=content.objet,
        lead=content.corps,
        rows=[
            ("Rapports", str(rows)),
            ("Période", period),
        ],
        cta=("Ouvrir le rapport", _report_link(period)),
        footer="Envoi automatique du tableau de bord aznet.",
        # The header picture says which report this is, so the message is
        # identifiable before a single line of it is read — which matters most
        # in the one place it is read, a list of unopened mail.
        caption="Rapport hebdomadaire" if weekly else "Rapport du jour",
        # The model writes headings and bullets; render them as headings and
        # bullets rather than shipping the reader the raw `##`.
        rich=True,
    )


def _period_report(label: str, rows: List[dict], kind: str) -> dict:
    """One company digest to the director(s) + one team digest per chef.

    The daily and weekly jobs differed only in how they picked their rows and
    what they called the period — everything below was duplicated line for
    line, which meant every fix had to be made twice or silently applied to
    half the feature.
    """
    persons = logs.list_persons()
    buckets = _manager_buckets(persons, rows)
    by_id = {p["id"]: p for p in persons}

    # The company digest goes to the director(s); without a director row the
    # manual recipient list takes over, so an install without an org chart
    # behaves exactly as before reports went per-manager.
    directors = [
        p for p in persons
        if p.get("role") == "directeur" and p.get("has_login") and p.get("email")
    ]
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
                {"manager": chef["name"], "rows": result["rows"], "sent_to": result["sent_to"],
                 "mail_error": result.get("mail_error")}
            )
            # Stored even when the chef has no email: the /rapport command
            # answers from here, and a report a technician can read is worth
            # generating even if no account row is set up yet.
            logs.save_manager_report(
                manager_id, label, result["objet"], result["corps"], result["generated_by"], kind
            )

    return {
        "rows": len(rows),
        "sent_to": sorted(sent_all),
        "subject": company["subject"],
        "managers": len(manager_reports),
        "reports": manager_reports,
        "generated_by": "automatique",
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
    return {"date": day, **_period_report(day, rows, "daily")}


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
    return {"period": label, **_period_report(label, rows, "weekly")}


def _next_occurrence(due: Optional[datetime], repeat: str,
                     repeat_every: Optional[int] = None,
                     repeat_unit: Optional[str] = None) -> Optional[datetime]:
    """The next due_at after a reminder fires, per the repeat rule.

    `repeat_unit` carries a custom interval (every N days/weeks/months) and
    beats the presets; monthly math clamps to the month's real length (Jan 31 →
    Feb 28), so a task scheduled for the 31st never silently skips a short
    month. Custom + preset both land here through the same `shift_months`, so
    the clamping can only drift in one place.
    """
    if due is None or (repeat == "none" and repeat_unit is None):
        return None
    if repeat_unit:
        n = repeat_every or 1
        if repeat_unit == "day":
            return due + timedelta(days=n)
        if repeat_unit == "week":
            return due + timedelta(weeks=n)
        return logs.shift_months(due, n)
    if repeat == "daily":
        return due + timedelta(days=1)
    if repeat == "weekly":
        return due + timedelta(days=7)
    return logs.shift_months(due, 1)


def _reminder_body(task: dict) -> str:
    """The French body shared by the bell row and the reminder mail.

    Lifted out of `send_reminders` so the loop reads as notify → mail → stamp:
    the pluralisation and the two optional blocks were most of its branching.
    """
    body = f"Tâche à faire : {task['title']}"
    if task.get("notes"):
        body += f"\n{task['notes']}"
    if task.get("due_at"):
        body += f"\nÉchéance : {task['due_at'].strftime('%d/%m/%Y %H:%M')}"
    lead = _lead_label(task)
    if lead:
        body += f"\nRappel : {lead}"
    return body


def _lead_label(task: dict) -> str:
    """"3 jours avant l'échéance", or "" when the task has no lead time."""
    value = task.get("remind_before_value")
    unit = task.get("remind_before_unit")
    if not value or not unit:
        return ""
    label = {"day": "jour", "week": "semaine", "month": "mois"}.get(unit) or str(unit)
    if value > 1 and unit != "month":
        label += "s"
    return f"{value} {label} avant l'échéance"


def _reminder_html(task: dict) -> str:
    """The same reminder as `_reminder_body`, laid out for an inbox.

    Kept beside the plain-text version rather than derived from it: the two say
    the same thing but are not the same artefact — one is a fallback that must
    stay readable as raw text, the other is a table. Deriving the second from
    the first is what produces mail that looks like a log file with `<br>`
    between the lines, which is exactly what this replaced.
    """
    due = task.get("due_at")
    return mailer.render_document(
        title=task["title"],
        lead="Une tâche de l'équipe arrive à échéance.",
        rows=[
            ("Échéance", due.strftime("%d/%m/%Y à %H:%M") if due else ""),
            ("Rappel", _lead_label(task)),
            ("Notes", task.get("notes") or ""),
        ],
        cta=("Ouvrir la tâche", f"{settings.dashboard_url.rstrip('/')}/#/tasks"),
        footer="Rappel automatique du tableau de bord aznet.",
    )


def send_reminders() -> dict:
    """Fire every due task reminder: bell + mail, then advance the schedule.

    One shot per occurrence — the `last_notified_at` guard in `logs.due_tasks`
    makes this safe to run as often as the scheduler wakes, and a restart can
    never re-send what already fired. The bell row goes to every account and
    the mail to every account email, because the task list is shared.
    """
    now = datetime.now()
    due = logs.due_tasks(now)
    if not due:
        return {"due": 0, "notified": 0, "emailed": 0, "failed": []}
    # Two audiences for one reminder, because they are reached differently: the
    # bell needs an account to read it, mail only needs an address. A chef in
    # the org chart with an email and no password still gets told.
    emails = logs.manager_emails()
    notified, emailed, failed = [], [], []
    for task in due:
        title = task["title"]
        body = _reminder_body(task)
        try:
            logs.notify_managers("reminder", title, body, "#/tasks", str(task["id"]))
            notified.append(task["id"])
        except logs.LogStoreError as exc:
            failed.append({"id": task["id"], "error": str(exc)})
            continue
        if emails:
            try:
                mailer.send(
                    emails,
                    f"Rappel — {title}",
                    body,
                    html_body=_reminder_html(task),
                )
                emailed.append(task["id"])
            except mailer.MailError as exc:
                # The bell already fired; a dead SMTP must not re-fire it next tick.
                failed.append({"id": task["id"], "error": f"mail: {exc}"})
        try:
            logs.stamp_task_notified(
                task["id"],
                _next_occurrence(
                    task.get("due_at"),
                    task.get("repeat") or "none",
                    task.get("repeat_every"),
                    task.get("repeat_unit"),
                ),
            )
        except logs.LogStoreError as exc:
            failed.append({"id": task["id"], "error": str(exc)})
    return {
        "due": len(due),
        "notified": len(notified),
        "emailed": len(emailed),
        "failed": failed,
    }


JOBS: Dict[str, Callable[[], dict]] = {
    "sheet_queue": drain_sheet_queue,
    "prune_logs": prune_logs,
    "profiles": refresh_profiles,
    "reminders": send_reminders,
    "daily_report": send_daily_report,
    "weekly_report": send_weekly_report,
}


# ── Running and remembering ────────────────────────────────────────────────


def run(name: str) -> dict:
    """Run one job, record the outcome, never raise.

    The same path serves the scheduler and the dashboard's "Run now" button, so
    a manual run is visible in the panel exactly like an automatic one.

    Jobs with a timeout run in a daemon worker thread: the scheduler must keep
    ticking even when one job hangs on a slow upstream (a stuck Google call
    must not freeze the 03:00 nightly band, nor delay every drain), and the
    overrun is recorded as a failed run the operator can see and re-trigger.
    """
    job = JOBS.get(name)
    if job is None:
        raise KeyError(name)
    started = time.time()
    timeout = _TIMEOUT_SECONDS.get(name)
    if timeout is None:
        return _execute(job, name, started)
    result: Dict[str, dict] = {}
    worker = threading.Thread(
        target=_execute, args=(job, name, started, result), name=f"job-{name}", daemon=True
    )
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        # The thread is a daemon: once it finishes (or the process exits) it
        # dies, so an overrun cannot accumulate. Its status would have arrived
        # too late to matter; the timeout record is the one the operator sees.
        return _record(name, {"ok": False, "error": f"timed out after {timeout}s"}, started)
    # .get, not [...]: a worker that died before writing its status would make
    # this raise KeyError straight into _loop, and the rule this module opens
    # with is that a job never raises into the scheduler.
    status = result.get("status")
    if status is None:
        return _record(name, {"ok": False, "error": "worker produced no status"}, started)
    return status


def _execute(job, name: str, started: float, result: Optional[Dict[str, dict]] = None) -> dict:
    """Body shared by the direct and the timed path. Never raises."""
    try:
        payload: dict = job()
        status = {"job": name, "ok": True, "result": payload}
    except Exception as exc:  # any failure is data, not a crash  # noqa: BLE001
        status = {"job": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if result is not None:
        result["status"] = status
    return _record(name, status, started)


def _record(name: str, status: dict, started: float) -> dict:
    status["at"] = datetime.now().isoformat(timespec="seconds")
    status["seconds"] = round(time.time() - started, 2)
    with _LOCK:
        _STATUS[name] = status
    logs.write_safe(
        f"job:{name}",
        "info" if status["ok"] else "error",
        message=status.get("error") or "ok",
        payload=status.get("result"),
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
    if name == "reminders":
        return "chaque minute"
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
    if name == "reminders":
        return last is None or now - last >= timedelta(seconds=REMINDER_INTERVAL_SECONDS)
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


def _seed_last_run() -> Dict[str, Optional[datetime]]:
    """What each job's `last_run` starts at in a fresh process.

    Neither obvious answer is right on its own. Seeding `None` makes a restart
    at 19:00 re-send the 18:30 report; seeding process start makes a restart at
    08:00 cancel that day's report entirely, because `_due` gates the daily and
    weekly bands on `last.date() < now.date()`. The only correct value is when
    the job *actually* last ran, which `pipeline_logs` has been recording all
    along (`_record` -> `logs.write_safe("job:<name>")`).

    A log store outage falls back to the old process-start seed: skipping a
    report is a better failure than mailing every manager twice.
    """
    started = datetime.now()
    try:
        recorded = logs.last_job_runs()
    except Exception as exc:  # noqa: BLE001 — the loop must start regardless
        print(f"[jobs] could not read job history ({exc}) — seeding from process start")
        recorded = {}
    # The drain is the exception: it is idempotent and runs every 5 minutes, so
    # "never run in this process" should fire it immediately.
    return {
        name: (None if name == "sheet_queue" else recorded.get(name, started))
        for name in JOBS
    }


def _loop() -> None:
    last_run = _seed_last_run()
    while True:
        now = datetime.now()
        for name in JOBS:
            if _due(now, last_run[name], name):
                last_run[name] = now
                try:
                    run(name)
                except Exception as exc:  # noqa: BLE001
                    # `run` is meant never to raise, but if it ever does, the
                    # scheduler thread dies and takes all six jobs with it —
                    # silently, until someone notices the Sheet stopped filling.
                    print(f"[jobs] {name} raised into the scheduler: {exc}")
        time.sleep(TICK_SECONDS)


def start() -> bool:
    """Start the scheduler once per process. Returns False if already running."""
    global _THREAD
    if _THREAD is not None and _THREAD.is_alive():
        return False
    _THREAD = threading.Thread(target=_loop, name="aznet-jobs", daemon=True)
    _THREAD.start()
    return True
