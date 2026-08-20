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
import json
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from app import daily_report, docx_report, journal, logs, mailer, memory, sheets, stock
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
    # One /process replay per technician, and a voice note can pay a cold
    # local-STT load: sized above local_darija COLD_START_BUDGET_S.
    "message_queue": 480,
    # One model call per report still missing its articles, capped at 25.
    "refill_articles": 600,
    # Sheet read + SMTP + one LLM call for the company digest *and one more per
    # site manager* (reports went per-manager on this branch): 180 s was sized
    # for the single-digest era and would kill the job — and every chef's stored
    # report with it — as soon as the org chart has a few chefs.
    "daily_report": 600,
    "weekly_report": 600,
    "profiles": 300,       # one Sheet read + one LLM call per technician
    "prune_logs": 120,
    "reminders": 60,
    # A full journal-tab read per site, same cost as GET /alerts uncached.
    "watch_alerts": 300,
}

# name -> last result, newest wins. Read by GET /jobs.
_STATUS: Dict[str, dict] = {}
_LOCK = threading.Lock()
_THREAD: Optional[threading.Thread] = None

# name -> the timed path's last worker, kept so a run that outlived its budget
# is visible to the next fire. The reminders job is due every 60 s with a 60 s
# budget, so without this an overrun (a few due tasks and a stalled SMTP) would
# spawn a second worker that re-sends what the first has not stamped yet.
_WORKERS: Dict[str, threading.Thread] = {}


# ── The jobs ───────────────────────────────────────────────────────────────


def refill_articles() -> dict:
    """Fill in reports whose articles were lost to a rate-limited model.

    Hourly rather than at a fixed time: a daily token ceiling comes back on the
    vendor's clock, not ours, and a report is worth completing the hour it
    becomes possible rather than the next morning. Cheap when there is nothing
    to do — one indexed query returning no rows.
    """
    return journal.refill_missing_articles()


# What a quota refusal looks like coming back from Google: a 429, a
# RESOURCE_EXHAUSTED, or one of the Sheets rate-limit reasons. Matched on the
# error text because `sheets.SheetsError` carries the vendor's message and
# nothing more structured.
_QUOTA_SIGNS = re.compile(
    r"429|quota|rate.?limit|RESOURCE_EXHAUSTED|userRateLimitExceeded",
    re.I,
)
# Google's Sheets quotas are per-minute windows and the error names no
# retry-after, so the pause is a flat two minutes.
# ponytail: one constant; read a retry-after if Google ever sends one.
QUOTA_PAUSE_SECONDS = 120
_paused_until = 0.0


def sheet_queue_pause() -> Optional[float]:
    """Unix time the drain is paused until, or None when it is running."""
    return _paused_until if _paused_until > time.time() else None


def drain_sheet_queue() -> dict:
    """Append every parked report the Sheet refused earlier.

    Reply-first ordering means a Sheets outage costs a row, never a technician's
    summary. This is the other half of that bargain: without it the rows sit in
    `failed_writes` forever.
    """
    global _paused_until
    if _paused_until > time.time():
        # A quota is not a per-row failure: retrying inside the window refuses
        # every row, spends an attempt on each, and can retire a payload that
        # was never malformed. Wait for the window instead.
        return {"pending": 0, "written": 0, "failed": [],
                "paused_until": _paused_until}
    pending = logs.pending_writes(DRAIN_BATCH)
    written, failed = 0, []
    paused = None
    for item in pending:
        outcome, info = _drain_one(item)
        if outcome == "written":
            written += 1
            continue
        failed.append(info)
        if outcome == "quota":
            # The whole batch is behind the same ceiling: stop here and let the
            # window pass.
            _paused_until = paused = time.time() + QUOTA_PAUSE_SECONDS
            break
    return {"pending": len(pending), "written": written, "failed": failed,
            **({"paused_until": paused} if paused else {})}


def _drain_one(item: dict) -> tuple:
    """File one parked row. Returns ("written"|"failed"|"quota", failure info)."""
    payload = item.get("payload") or {}
    try:
        # Through `journal.file_report`, not a raw append: a parked row
        # whose day already has a row on the sheet must merge into it, or
        # the retry would create the duplicate the live path avoided.
        filed = journal.file_report(payload)
    except sheets.SheetsError as exc:
        if _QUOTA_SIGNS.search(str(exc)):
            # Recorded without spending an attempt: nothing about this row failed.
            logs.resolve_write(item["id"], False, str(exc), count_attempt=False)
            logs.write_safe(
                "sheet", "warn",
                message=f"drain paused {QUOTA_PAUSE_SECONDS}s on quota: {exc}"[:400],
                correlation_id=item.get("correlation_id"),
            )
            return "quota", {"id": item["id"], "error": str(exc), "quota": True}
        # Left in the queue with the attempt counted, not dropped.
        logs.resolve_write(item["id"], False, str(exc))
        return "failed", {"id": item["id"], "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        # A payload the schema cannot parse will never parse: retrying it
        # forever blocks the batch behind it, so it is resolved as failed
        # and stays visible in the dashboard instead of stalling the drain.
        logs.resolve_write(item["id"], False, f"unprocessable: {exc}", retry=False)
        return "failed", {"id": item["id"], "error": f"unprocessable: {exc}"}
    logs.resolve_write(item["id"], True)
    # Link the parked message to the Rapports row it mirrored to, so the
    # dashboard can still play its voice note even when the happy path's
    # write is the one that failed.
    message_id = payload.get("message_id")
    appended_mirror = filed.get("rapports_row")
    if message_id and appended_mirror:
        try:
            logs.link_message_row(message_id, appended_mirror)
        except logs.LogStoreError:
            pass  # best-effort like the append itself
    return "written", None


# -- Message retry queue ----------------------------------------------------
# Runs on the scheduler tick (30 s) because a technician is waiting: the first
# backoff step is 30 s, and a five-minute cadence like the Sheet drain would
# make the fastest possible recovery five minutes.
MESSAGE_RETRY_SECONDS = 30
DEFAULT_QUEUE_MIME = "audio/ogg"
#: Set while the whole text chain refuses on quota. Not a per-message failure:
#: every message would fail identically, so we stop calling the model at all
#: until the window passes. Reception keeps running -- Telegram is polled and
#: Meta's webhooks are accepted -- because pausing intake loses updates
#: (Telegram retains them ~24h) while pausing *processing* loses nothing.
_quota_until = 0.0
QUOTA_WINDOW_SECONDS = 300


def message_quota_pause():
    """Unix time the retry loop is quota-paused until, or None if running."""
    return _quota_until if _quota_until > time.time() else None


def _is_quota_text(detail: str) -> bool:
    return bool(_QUOTA_SIGNS.search(detail or ""))


def _chat_of(item: dict) -> str:
    """The technician's address on the channel the message came in on."""
    try:
        person = logs.person_by_name(item.get("technicien") or "")
    except Exception:  # noqa: BLE001  # a reaction never breaks the job
        return ""
    for ident in (person or {}).get("identities", []):
        if ident.get("channel") == item.get("channel") and ident.get("active", True):
            return str(ident.get("external_id") or "")
    return ""


def _replay(item: dict):
    """Re-send one queued message through /process. (ok, detail, was_quota).

    Over local HTTP rather than by calling the endpoint's internals: the retry
    replays exactly what n8n sent, through the same validation, the same
    extraction chain and the same journal write. A second code path that files
    reports is a second place for them to be filed differently.
    """
    import requests

    base = (settings.api_self_url or "http://127.0.0.1:8000").rstrip("/")
    data = {k: v for k, v in (
        ("correlation_id", item.get("correlation_id")),
        ("channel", item.get("channel")),
        ("technicien", item.get("technicien")),
        ("message_id", item.get("message_id")),
        ("caption", item.get("caption")),
    ) if v}
    files = None
    if item.get("kind") == "text":
        data["text"] = item.get("text_input") or ""
    else:
        files = _replay_media(item)
        if files is None:
            # Nothing left to replay, and no later attempt can change that.
            return False, "media absent - rien a rejouer", False
    try:
        res = requests.post(
            base + "/process", data=data, files=files,
            headers={"X-API-Key": settings.internal_api_key or "",
                     "X-Queue-Retry": "1"},
            timeout=_TIMEOUT_SECONDS.get("message_queue", 480) - 20,
        )
    except requests.RequestException as exc:
        return False, "API injoignable: %s" % exc, False
    return _replay_outcome(res)


def _replay_media(item: dict):
    """The archived blob as a `requests` files mapping, or None if it is gone."""
    blob = logs.get_media(item["media_id"]) if item.get("media_id") else None
    if not blob or not blob.get("data"):
        return None
    return {"audio": ("queued-%s.ogg" % item["id"], bytes(blob["data"]),
                      item.get("mime") or DEFAULT_QUEUE_MIME)}


def _replay_outcome(res):
    """Read one /process answer as (ok, detail, was_quota)."""
    if res.status_code == 202:
        # Parked again -- by the gate, or by another failure. A failed try.
        try:
            body = res.json()
        except ValueError:
            body = {}
        detail = str(body.get("detail") or "toujours en attente")
        return False, detail, _is_quota_text(detail)
    if res.ok:
        return True, "", False
    return False, "%s: %s" % (res.status_code, res.text[:300]), _is_quota_text(res.text)


def _notify_quota(item: dict) -> None:
    """Tell this technician ONCE per outage that the service is saturated.

    Once per outage, not once per message: the point of the queue is that they
    need do nothing, and six identical notices would undo that. The bookmark
    doubles as the throttle, reusing the cursor store rather than adding state.
    """
    key = "quota-notice:%s" % (item.get("technicien") or "?")
    try:
        last = logs.get_cursor(key)
        if last and float(last) > time.time() - QUOTA_WINDOW_SECONDS:
            return
        logs.set_cursor(key, time.time())
    except Exception:  # noqa: BLE001
        return
    chat = _chat_of(item)
    if not chat:
        return
    try:
        from app import reply

        reply.set_reaction(item.get("channel") or "", chat,
                           item.get("message_id") or "", "quota")
        reply.reply_to_identities(
            [{"channel": item.get("channel"), "external_id": chat}],
            reply.QUOTA_MESSAGE,
        )
    except Exception:  # noqa: BLE001  # best effort, never costs the job
        pass


def retry_messages() -> dict:
    """Replay every queued message whose backoff has elapsed, oldest first.

    One message per technician per pass (`due_messages` enforces it): running
    two of one person's messages concurrently is the exact race the queue
    exists to prevent.
    """
    global _quota_until
    from app import reply

    if _quota_until > time.time():
        return {"paused_until": _quota_until, "retried": 0, "filed": 0, "abandoned": 0}
    due = logs.due_messages(DRAIN_BATCH)
    filed = abandoned = 0
    for item in due:
        ok, detail, was_quota = _replay(item)
        if was_quota:
            # Every message would fail the same way. Stop the pass, and do not
            # spend this one's attempt on someone else's rate limit.
            _quota_until = time.time() + QUOTA_WINDOW_SECONDS
            logs.resolve_message(item["id"], False, detail, count_attempt=False)
            logs.write_safe(
                "queued", "warn",
                message=("file en pause %ss (quota): %s" % (QUOTA_WINDOW_SECONDS, detail))[:400],
                correlation_id=item.get("correlation_id"))
            _notify_quota(item)
            break
        status = logs.resolve_message(item["id"], ok, detail)
        chat = _chat_of(item)
        if ok:
            filed += 1
            reply.set_reaction(item.get("channel") or "", chat,
                               item.get("message_id") or "", "done")
        elif status == "abandoned":
            abandoned += 1
            reply.set_reaction(item.get("channel") or "", chat,
                               item.get("message_id") or "", "failed")
            logs.write_safe(
                "queued", "error",
                message=("abandonne apres %s essais: %s" % (logs.MAX_MESSAGE_ATTEMPTS, detail))[:400],
                correlation_id=item.get("correlation_id"))
    out = {"retried": len(due), "filed": filed, "abandoned": abandoned}
    if _quota_until > time.time():
        out["paused_until"] = _quota_until
    return out


#: One row in the cursor store, holding {chantier|champ: signature} for every
#: finding the bell has already announced. A dict rather than a key per alert
#: so a finding that has gone away is pruned by the same write that records the
#: others — a per-key store would leave a bookmark behind that silently
#: suppressed the alert if it ever came back unchanged.
ALERT_NOTICE_CURSOR = "alert-notices"


def watch_alerts() -> dict:
    """Ring the bell for material findings nobody has been told about yet.

    The Sites page shows these permanently; this is for the person who is not
    on it. Announced once per *state*, not once per run: the signature carries
    the level and the remainder, so an unchanged shortage stays quiet and a
    `bas` that became `critique` — or that lost another 200 m — rings again.
    That is the same rule the mute follows, deliberately: a finding worth
    hiding again is a finding worth announcing again.

    Muted findings are skipped. Somebody said they had dealt with it, and a
    bell that fires anyway makes the ignore button a lie.
    """
    found = stock.apply_mutes(stock.assess())
    live = {
        f"{a['chantier']}|{a['champ']}": _alert_signature(a)
        for a in found
        if not a.get("ignored")
    }
    try:
        seen = json.loads(logs.get_cursor(ALERT_NOTICE_CURSOR) or "{}")
        if not isinstance(seen, dict):
            seen = {}
    except (TypeError, ValueError):
        seen = {}

    fresh = [a for a in found
             if not a.get("ignored")
             and seen.get(f"{a['chantier']}|{a['champ']}") != _alert_signature(a)]
    for a in fresh:
        try:
            logs.notify_accounts(
                "review",
                f"{a['article']} — {a['chantier']}",
                stock.line(a),
                "#/chantiers",
                f"{a['chantier']}|{a['champ']}",
            )
        except Exception as exc:  # noqa: BLE001 — one bell is not worth the job
            print(f"[jobs] alert notify failed: {exc}"[:200], flush=True)

    # Written even when nothing was fresh: this is also how a finding that has
    # been resolved drops out of the record.
    logs.set_cursor(ALERT_NOTICE_CURSOR, json.dumps(live, ensure_ascii=False))
    return {"alerts": len(found), "notified": len(fresh), "muted": len(found) - len(live)}


def _alert_signature(alert: dict) -> str:
    """Level plus remainder, rounded. Two readings of the same shortage that
    differ by a decimal are the same fact and must not ring twice."""
    reste = alert.get("reste")
    return f"{alert['niveau']}:{'' if reste is None else round(float(reste))}"


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
    # Computed once per report and passed to both consumers: the model that
    # writes the mail body and the table in the attached document. Two
    # assessments of the same day could disagree, and the reader would have
    # no way to tell which one to act on.
    alerts = stock.alerts_for_rows(rows)
    content = daily_report.generate_daily_report(period, rows, alerts)
    sent: List[str] = []
    mail_error = None
    kind = "Rapport hebdomadaire" if "→" in period else "Rapport journalier"
    # Best-effort, and deliberately not fatal: a document that fails to render
    # must not cost the chef the report itself, which is readable in the mail
    # body and stored either way. The failure is printed rather than swallowed
    # so it is visible in the container log.
    attachments: List[tuple] = []
    try:
        blob = docx_report.build(
            content.objet, content.corps, kind, period, rows,
            author="automatique", alerts=alerts
        )
        attachments.append((
            docx_report.filename(content.objet), blob,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ))
    except Exception as exc:  # noqa: BLE001
        print(f"[report] .docx non joint ({exc}) — le corps du mail reste complet")
    try:
        sent = mailer.send(
            recipients,
            content.objet,
            content.corps,
            html_body=_report_html(period, content, len(rows)),
            attachments=attachments,
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
    # From Postgres, not the Sheet: the quantities left the Rapports tab on
    # 2026-08-19, and a report that reads its own figures out of a spreadsheet
    # pays a Google call for every one of them.
    rows = logs.list_report_rows(dates=[day])
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
    rows = logs.list_report_rows(dates=sorted(span))
    label = f"{first_day.strftime('%Y-%m-%d')} → {last_day.strftime('%Y-%m-%d')}"
    if not rows:
        return {"period": label, "rows": 0, "sent_to": [], "reason": "aucun rapport sur la période"}
    return {"period": label, **_period_report(label, rows, "weekly")}


def _next_occurrence(due: Optional[datetime], repeat: str,
                     repeat_every: Optional[int] = None,
                     repeat_unit: Optional[str] = None,
                     anchor_day: Optional[int] = None) -> Optional[datetime]:
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
        return logs.shift_months(due, n, anchor_day)
    if repeat == "daily":
        return due + timedelta(days=1)
    if repeat == "weekly":
        return due + timedelta(days=7)
    return logs.shift_months(due, 1, anchor_day)


def _catch_up(due: Optional[datetime], repeat: str,
              repeat_every: Optional[int] = None,
              repeat_unit: Optional[str] = None,
              anchor_day: Optional[int] = None) -> Optional[datetime]:
    """The next occurrence that is actually still ahead of us.

    Stamping one period forward re-stamped a missed task to a date still in the
    past, and `due_tasks` matched it again on the very next tick: a daily
    reminder missed over a two-week outage sent fourteen bells and fourteen
    mails in fourteen minutes rather than one. Repeated stepping, because the
    rule is not always a fixed length — monthly clamps to the month, so the
    only way to land on a real occurrence is to walk them.

    Every step moves strictly forward, so this terminates; the cap is there
    only so a corrupt row cannot spin the scheduler thread.
    """
    nxt = _next_occurrence(due, repeat, repeat_every, repeat_unit, anchor_day)
    if nxt is None:
        return None
    now = datetime.now(nxt.tzinfo)
    for _ in range(1000):
        if nxt > now:
            break
        # The anchor travels through every catch-up step too. Stepping a
        # missed monthly task over a February without it re-introduced exactly
        # the drift this parameter exists to prevent, one skipped month at a
        # time.
        stepped = _next_occurrence(nxt, repeat, repeat_every, repeat_unit, anchor_day)
        if stepped is None or stepped <= nxt:
            break
        nxt = stepped
    return nxt


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
                _catch_up(
                    task.get("due_at"),
                    task.get("repeat") or "none",
                    task.get("repeat_every"),
                    task.get("repeat_unit"),
                    task.get("repeat_anchor_day"),
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
    "message_queue": retry_messages,
    "refill_articles": refill_articles,
    "prune_logs": prune_logs,
    "watch_alerts": watch_alerts,
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
    # last_run is stamped at schedule time, not completion: a run that outlives
    # its interval would otherwise be re-fired by the next tick while the first
    # worker is still sending. That is exactly the reminders shape (60 s due,
    # 60 s budget), and a duplicate fire would re-send bells and mails for
    # tasks the first worker has not stamped yet. Recorded as a failed run so
    # the panel shows the job is wedged instead of silently overlapping it.
    prev = _WORKERS.get(name)
    if prev is not None and prev.is_alive():
        return _record(
            name, {"ok": False, "error": "previous run still in progress, skipped"}, started
        )
    result: Dict[str, dict] = {}
    claim = _make_claim()
    worker = threading.Thread(
        target=_execute, args=(job, name, started, result, claim), name=f"job-{name}", daemon=True
    )
    _WORKERS[name] = worker
    worker.start()
    worker.join(timeout)
    if worker.is_alive() and claim():
        # The thread is a daemon: once it finishes (or the process exits) it
        # dies, so an overrun cannot accumulate. Its status would have arrived
        # too late to matter; the timeout record is the one the operator sees.
        #
        # `claim()` — not a plain Event — because `worker.is_alive()` and the
        # worker's own check are two unsynchronised reads. A job finishing in
        # the window between them used to record its success and then have this
        # line record a timeout over it: one run, two contradictory entries in
        # the panel and in pipeline_logs, which is exactly the kind of lie this
        # module exists to prevent. Whoever claims first writes; the loser
        # stays silent.
        return _record(name, {"ok": False, "error": f"timed out after {timeout}s"}, started)
    # .get, not [...]: a worker that died before writing its status would make
    # this raise KeyError straight into _loop, and the rule this module opens
    # with is that a job never raises into the scheduler.
    status = result.get("status")
    if status is None:
        return _record(name, {"ok": False, "error": "worker produced no status"}, started)
    return status


def _make_claim():
    """Hand out a one-shot right to record this run's outcome.

    Returns a callable that answers True to exactly one caller, ever. The timed
    path has two writers racing for one slot — the worker that finished and the
    caller whose join() timed out — and `threading.Event` cannot express
    "test and set as one step". A lock can, in four lines.
    """
    lock = threading.Lock()
    taken = False

    def claim() -> bool:
        nonlocal taken
        with lock:
            if taken:
                return False
            taken = True
            return True

    return claim


def _execute(
    job, name: str, started: float,
    result: Optional[Dict[str, dict]] = None,
    claim=None,
) -> dict:
    """Body shared by the direct and the timed path. Never raises."""
    try:
        payload: dict = job()
        status = {"job": name, "ok": True, "result": payload}
    except Exception as exc:  # any failure is data, not a crash  # noqa: BLE001
        status = {"job": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if result is not None:
        result["status"] = status
    if claim is not None and not claim():
        # The caller already recorded a timeout for this run; a result arriving
        # after the deadline is not a run the panel should show as a success.
        return status
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
    if name == "message_queue":
        return "toutes les %s s" % MESSAGE_RETRY_SECONDS
    if name == "sheet_queue":
        return f"toutes les {DRAIN_INTERVAL_MINUTES} min"
    if name in ("refill_articles", "watch_alerts"):
        return "toutes les heures"
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
    except Exception:  # noqa: BLE001  # DB down must not blank the panel
        return {}


# ── The loop ───────────────────────────────────────────────────────────────


#: Jobs that simply run every so often, and how often.
_INTERVALS = {
    "message_queue": timedelta(seconds=MESSAGE_RETRY_SECONDS),
    "sheet_queue": timedelta(minutes=DRAIN_INTERVAL_MINUTES),
    "refill_articles": timedelta(hours=1),
    # Hourly: a stock level moves at the speed of a working day, and the
    # assessment costs a Sheets read per site on a free quota.
    "watch_alerts": timedelta(hours=1),
    "reminders": timedelta(seconds=REMINDER_INTERVAL_SECONDS),
}


def _due(now: datetime, last: Optional[datetime], name: str) -> bool:
    every = _INTERVALS.get(name)
    if every is not None:
        return last is None or now - last >= every
    if name in ("prune_logs", "profiles"):
        return now.hour == NIGHTLY_HOUR and (last is None or last.date() < now.date())

    at = _report_time(now, name)
    if at is None or (now.hour, now.minute) < at:
        return False
    return last is None or last.date() < now.date()


def _report_time(now: datetime, name: str) -> Optional[tuple]:
    """(hour, minute) the report band is due at today, or None if not today."""
    row = _settings_safe()
    if name == "weekly_report":
        # Once on the chosen weekday. `last.date() < now.date()` alone would fire
        # again next week's same day, which is exactly what we want.
        if now.weekday() != _weekly_day(row):
            return None
        return _hhmm(row.get("weekly_time"), (17, 0))
    # daily_report: Monday–Saturday, once per day
    if now.weekday() == 6:  # Sunday: no site work, no report
        return None
    return _hhmm(row.get("daily_time"), (18, 30))


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
    except Exception as exc:  # noqa: BLE001  # the loop must start regardless
        print(f"[jobs] could not read job history ({exc}) — seeding from process start")
        recorded = {}
    # The drain is the exception: it is idempotent and runs every 5 minutes, so
    # "never run in this process" should fire it immediately.
    return {
        name: (None if name in ("sheet_queue", "message_queue") else recorded.get(name, started))
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
