"""TO-DO #32 / #33 — the bell (per-account notifications) and the to-do panel.

Same discipline as the rest of the suite: no API keys, no database. Endpoint
tests stub the store at `main.logs.*`; the reminder job is tested against
monkeypatched `jobs.logs` / `jobs.mailer`. The notification functions
themselves are plain SQL and are covered through the wiring here — the store
behaviour against real Postgres belongs to the live stack, not the suite.
"""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

import pytest

import app.main as main
from app import jobs, logs, mailer
from app.providers.base import TranscriptionInfo, TranscriptionProvider
from app.schemas import ExtractedReport

client = TestClient(main.app)

# The override is also re-applied per-test below: module-level assignments in
# other test files overwrite this one when their import lands later, and the
# callers' ids must not silently depend on pytest's file ordering.
main.app.dependency_overrides[main.auth.require_human] = lambda: {
    "id": 7, "name": "Yassine", "role": "directeur"
}
main.app.dependency_overrides[main.auth.require_user] = lambda: {
    "id": 7, "name": "Yassine", "role": "directeur"
}


@pytest.fixture(autouse=True)
def _auth_as(monkeypatch):
    """Pin this module's caller identity, whatever the import order was."""
    monkeypatch.setitem(main.app.dependency_overrides, main.auth.require_human,
                        lambda: {"id": 7, "name": "Yassine", "role": "directeur"})
    monkeypatch.setitem(main.app.dependency_overrides, main.auth.require_user,
                        lambda: {"id": 7, "name": "Yassine", "role": "directeur"})


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    """Endpoint tests stub the store; audit writes and the /process noise
    (profile lookup, media archive) must never reach the real dev DB."""
    monkeypatch.setattr(main.auth, "record", lambda *a, **k: None)
    monkeypatch.setattr(main.logs, "notify_technician_manager", lambda *a, **k: None)
    monkeypatch.setattr(main.logs, "notify_managers", lambda *a, **k: 0)
    monkeypatch.setattr(main.logs, "profile_for", lambda name: None)
    monkeypatch.setattr(main.logs, "save_media", lambda *a, **k: None)
    monkeypatch.setattr(main.logs, "save_message", lambda *a, **k: None)


REPORT = ExtractedReport(
    chantier="Tour Atlas",
    goulottes_m=150,
    resume="Installation de 150 m de goulotte.",
)


class FakeProvider(TranscriptionProvider):
    name = "fake"

    def transcribe(self, audio, mime_type):
        return TranscriptionInfo(
            text="نصبنا 150 متر ديال الجولوط", provider="fake", latency_s=0.1,
        )


# ── /notifications endpoints ───────────────────────────────────────────────

def test_notifications_list_shape(monkeypatch):
    items = [{"id": 1, "kind": "report", "title": "Nouveau rapport",
              "read_at": None, "created_at": "2026-08-02T10:00:00"}]
    monkeypatch.setattr(main.logs, "list_notifications", lambda pid, limit: items)
    monkeypatch.setattr(main.logs, "unread_notifications", lambda pid: 3)
    r = client.get("/notifications")
    assert r.status_code == 200
    assert r.json() == {"items": items, "unread": 3}


def test_notifications_store_down_is_502(monkeypatch):
    def boom(*a, **k):
        raise logs.LogStoreError("down")
    monkeypatch.setattr(main.logs, "list_notifications", boom)
    assert client.get("/notifications").status_code == 502


def test_mark_read_accepts_ids_and_all(monkeypatch):
    calls = []

    def fake_mark(pid, ids):
        calls.append((pid, ids))
        return 2
    monkeypatch.setattr(main.logs, "mark_notifications_read", fake_mark)
    assert client.post("/notifications/read", json={"ids": [1, 2]}).json() == {"marked": 2}
    assert calls[-1] == (7, [1, 2])
    assert client.post("/notifications/read", json={}).json() == {"marked": 2}
    assert calls[-1] == (7, None)


# ── /tasks CRUD ────────────────────────────────────────────────────────────

def test_task_crud(monkeypatch):
    monkeypatch.setattr(
        main.logs, "create_task",
        lambda title, notes=None, due_at=None, repeat="none",
        remind_before_value=None, remind_before_unit=None,
        repeat_every=None, repeat_unit=None: 9,
    )
    r = client.post("/tasks", json={"title": "Envoyer devis", "repeat": "weekly"})
    assert r.status_code == 200
    assert r.json()["id"] == 9 and r.json()["repeat"] == "weekly"

    task = {"id": 9, "title": "Envoyer devis", "notes": None, "due_at": None,
            "repeat": "weekly", "done": False}
    monkeypatch.setattr(main.logs, "list_tasks", lambda: [task])
    assert client.get("/tasks").json() == {"tasks": [task]}

    monkeypatch.setattr(main.logs, "update_task", lambda tid, fields: True)
    assert client.patch("/tasks/9", json={"done": True}).json() == {"ok": True, "id": 9}
    monkeypatch.setattr(main.logs, "update_task", lambda tid, fields: False)
    assert client.patch("/tasks/9", json={"done": True}).status_code == 404

    monkeypatch.setattr(main.logs, "delete_task", lambda tid: True)
    assert client.delete("/tasks/9").json() == {"ok": True}
    monkeypatch.setattr(main.logs, "delete_task", lambda tid: False)
    assert client.delete("/tasks/9").status_code == 404


def test_task_repeat_enum_enforced(monkeypatch):
    monkeypatch.setattr(
        main.logs, "create_task",
        lambda title, notes=None, due_at=None, repeat="none",
        remind_before_value=None, remind_before_unit=None,
        repeat_every=None, repeat_unit=None: 1,
    )
    assert client.post("/tasks", json={"title": "x", "repeat": "annually"}).status_code == 422
    assert client.post("/tasks", json={"title": "x", "repeat": "monthly"}).status_code == 200


def test_task_custom_interval_and_lead_accepted(monkeypatch):
    seen = {}

    def fake_create(title, notes=None, due_at=None, repeat="none",
                    remind_before_value=None, remind_before_unit=None,
                    repeat_every=None, repeat_unit=None):
        seen.update(title=title, repeat=repeat, remind_before_value=remind_before_value,
                    remind_before_unit=remind_before_unit, repeat_every=repeat_every,
                    repeat_unit=repeat_unit)
        return 10
    monkeypatch.setattr(main.logs, "create_task", fake_create)
    r = client.post("/tasks", json={
        "title": "Facture fournisseur", "repeat": "none",
        "remind_before_value": 3, "remind_before_unit": "day",
        "repeat_every": 2, "repeat_unit": "week",
    })
    assert r.status_code == 200
    assert seen == {"title": "Facture fournisseur", "repeat": "none",
                    "remind_before_value": 3, "remind_before_unit": "day",
                    "repeat_every": 2, "repeat_unit": "week"}


def test_task_pair_fields_are_rejected_alone():
    assert client.post("/tasks", json={"title": "x", "repeat_every": 3}).status_code == 422
    assert client.post("/tasks", json={"title": "x", "repeat_unit": "day"}).status_code == 422
    assert client.post("/tasks", json={"title": "x", "remind_before_value": 3}).status_code == 422
    assert client.post("/tasks", json={"title": "x", "remind_before_unit": "day"}).status_code == 422


def test_lead_must_be_shorter_than_repeat_period(monkeypatch):
    monkeypatch.setattr(
        main.logs, "create_task",
        lambda title, notes=None, due_at=None, repeat="none",
        remind_before_value=None, remind_before_unit=None,
        repeat_every=None, repeat_unit=None: 1,
    )
    assert client.post(
        "/tasks", json={"title": "x", "repeat": "daily", "remind_before_value": 1,
                        "remind_before_unit": "day"}
    ).status_code == 422  # lead == period: windows would overlap
    assert client.post(
        "/tasks", json={"title": "x", "repeat": "weekly", "remind_before_value": 7,
                        "remind_before_unit": "day"}
    ).status_code == 422
    assert client.post(
        "/tasks", json={"title": "x", "repeat": "weekly", "remind_before_value": 6,
                        "remind_before_unit": "day"}
    ).status_code == 200
    assert client.post(
        "/tasks", json={"title": "x", "repeat": "monthly", "remind_before_value": 2,
                        "remind_before_unit": "week"}
    ).status_code == 200
    assert client.post(
        "/tasks", json={"title": "x", "repeat": "none", "remind_before_value": 30,
                        "remind_before_unit": "day"}
    ).status_code == 200  # one-shot: a lead can be arbitrarily long


def test_lead_must_be_shorter_than_custom_interval(monkeypatch):
    """The period guard applies to custom cadences too (repeat='none' +
    repeat_unit), not just the presets — a long lead on a short custom
    interval would overlap windows and re-ring every tick."""
    monkeypatch.setattr(
        main.logs, "create_task",
        lambda title, notes=None, due_at=None, repeat="none",
        remind_before_value=None, remind_before_unit=None,
        repeat_every=None, repeat_unit=None: 1,
    )
    assert client.post(
        "/tasks", json={"title": "x", "repeat": "none", "repeat_every": 3,
                        "repeat_unit": "day", "remind_before_value": 30,
                        "remind_before_unit": "day"}
    ).status_code == 422  # lead >> custom period
    assert client.post(
        "/tasks", json={"title": "x", "repeat": "none", "repeat_every": 30,
                        "repeat_unit": "day", "remind_before_value": 30,
                        "remind_before_unit": "day"}
    ).status_code == 422  # lead == custom period
    assert client.post(
        "/tasks", json={"title": "x", "repeat": "none", "repeat_every": 30,
                        "repeat_unit": "day", "remind_before_value": 29,
                        "remind_before_unit": "day"}
    ).status_code == 200
    assert client.post(
        "/tasks", json={"title": "x", "repeat": "none", "repeat_every": 2,
                        "repeat_unit": "week", "remind_before_value": 13,
                        "remind_before_unit": "day"}
    ).status_code == 200  # 13 days < 14-day period
    assert client.post(
        "/tasks", json={"title": "x", "repeat": "none", "repeat_every": 2,
                        "repeat_unit": "week", "remind_before_value": 14,
                        "remind_before_unit": "day"}
    ).status_code == 422


def test_patch_checks_lead_against_known_period(monkeypatch):
    """PATCH validates the period when it carries the repeat (then the
    resulting task is fully known); a repeat-less patch is checked against
    the stored cadence; only pairs are enforced when there is no lead."""
    monkeypatch.setattr(main.logs, "update_task", lambda tid, fields: True)
    assert client.patch(
        "/tasks/9", json={"remind_before_value": 30, "remind_before_unit": "day",
                          "repeat": "daily"}
    ).status_code == 422
    assert client.patch(
        "/tasks/9", json={"remind_before_value": 30, "remind_before_unit": "day",
                          "repeat": "none"}
    ).status_code == 200  # one-shot lead stays unbounded
    # Repeat untouched: the stored task decides.
    monkeypatch.setattr(
        main.logs, "get_task",
        lambda tid: {"repeat": "weekly", "repeat_every": None, "repeat_unit": None},
    )
    assert client.patch(
        "/tasks/9", json={"remind_before_value": 30, "remind_before_unit": "day"}
    ).status_code == 422  # stored weekly period is 7 days
    assert client.patch(
        "/tasks/9", json={"remind_before_value": 6, "remind_before_unit": "day"}
    ).status_code == 200
    monkeypatch.setattr(
        main.logs, "get_task",
        lambda tid: {"repeat": "none", "repeat_every": None, "repeat_unit": None},
    )
    assert client.patch(
        "/tasks/9", json={"remind_before_value": 30, "remind_before_unit": "day"}
    ).status_code == 200  # stored one-shot: any lead
    # Clearing a lead clears both fields; the guard must not trip on None.
    assert client.patch(
        "/tasks/9", json={"remind_before_value": None, "remind_before_unit": None}
    ).status_code == 200


def test_patch_unknown_task_is_404_before_period_check(monkeypatch):
    monkeypatch.setattr(main.logs, "get_task", lambda tid: None)
    r = client.patch("/tasks/99", json={"remind_before_value": 3,
                                        "remind_before_unit": "day"})
    assert r.status_code == 404


def test_tasks_store_down_is_502(monkeypatch):
    def boom(*a, **k):
        raise logs.LogStoreError("down")
    monkeypatch.setattr(main.logs, "create_task", boom)
    assert client.post("/tasks", json={"title": "x"}).status_code == 502
    monkeypatch.setattr(main.logs, "list_tasks", boom)
    assert client.get("/tasks").status_code == 502


# ── /process and /sheet-queue wiring ───────────────────────────────────────

def test_process_report_rings_the_managers_bell(monkeypatch):
    calls = []
    monkeypatch.setattr(
        main.logs, "notify_technician_manager",
        lambda *a, **k: calls.append(a) or 1,
    )
    monkeypatch.setattr(main, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(
        main.extraction, "extract_report_with_model",
        lambda t, profile=None: (REPORT, "test/stub"),
    )
    monkeypatch.setattr(main.drive, "upload_audio",
                        lambda filename, mime, data: "https://drive.google.com/uc?id=abc")
    r = client.post(
        "/process",
        data={"message_id": "tg:1:2", "channel": "telegram", "technicien": "Rachid"},
        files={"audio": ("note.ogg", b"fake-bytes", "audio/ogg")},
    )
    assert r.status_code == 200
    assert calls
    technicien, kind, title = calls[0][0], calls[0][1], calls[0][2]
    assert technicien == "Rachid" and kind == "report" and "Nouveau rapport" in title
    assert calls[0][4] == "#/reports"


def test_process_short_voice_note_rings_review_bell(monkeypatch):
    """A too-short transcription is flagged for a human eye: the bell says
    'à vérifier', never 'nouveau rapport'."""
    calls = []

    class ShortProvider(TranscriptionProvider):
        name = "short"
        def transcribe(self, audio, mime_type):
            return TranscriptionInfo(text="سلام", provider="short", latency_s=0.1)

    monkeypatch.setattr(main, "get_provider", lambda name: ShortProvider())
    monkeypatch.setattr(
        main.logs, "notify_technician_manager",
        lambda *a, **k: calls.append(a) or 1,
    )
    monkeypatch.setattr(
        main.extraction, "extract_report_with_model",
        lambda t, profile=None: (REPORT, "test/stub"),
    )
    r = client.post(
        "/process", data={"technicien": "Rachid"},
        files={"audio": ("note.ogg", b"fake-bytes", "audio/ogg")},
    )
    assert r.status_code == 200
    assert calls and calls[0][1] == "review" and "à vérifier" in calls[0][2]


def test_process_greeting_does_not_ring_bell(monkeypatch):
    calls = []
    monkeypatch.setattr(
        main.logs, "notify_technician_manager",
        lambda *a, **k: calls.append(a) or 1,
    )
    monkeypatch.setattr(
        main.extraction, "extract_report_with_model",
        lambda t, profile=None: (ExtractedReport(resume="Salam, comment allez-vous ?"), "test/stub"),
    )
    r = client.post("/process", data={"text": "salam"})
    assert r.status_code == 200
    assert calls == []


def test_process_image_rings_review_bell(monkeypatch):
    calls = []
    monkeypatch.setattr(
        main.logs, "notify_technician_manager",
        lambda *a, **k: calls.append(a) or 1,
    )
    monkeypatch.setattr(
        main.extraction, "extract_report_from_image",
        lambda blob, mime, profile, caption: (REPORT, "test/vision"),
    )
    r = client.post(
        "/process", data={"technicien": "Rachid"},
        files={"image": ("note.jpg", b"\xff\xd8fake", "image/jpeg")},
    )
    assert r.status_code == 200
    assert calls and calls[0][1] == "review"


def test_sheet_queue_writes_and_rings_error_bell(monkeypatch):
    calls = []
    monkeypatch.setattr(main.logs, "queue_failed_write", lambda payload, error, cid: 42)
    monkeypatch.setattr(
        main.logs, "notify_managers",
        lambda *a, **k: calls.append(a) or 1,
    )
    r = client.post(
        "/sheet-queue",
        json={"payload": {"chantier": "x"}, "error": "boom", "correlation_id": "c1"},
    )
    assert r.status_code == 200
    assert r.json() == {"id": 42}
    assert calls and calls[0][0] == "error" and "Sheets" in calls[0][1]


def test_sheet_queue_store_down_is_502(monkeypatch):
    def boom(*a, **k):
        raise logs.LogStoreError("down")
    monkeypatch.setattr(main.logs, "queue_failed_write", boom)
    assert client.post(
        "/sheet-queue", json={"payload": {}, "error": "e"}
    ).status_code == 502


# ── the reminders job ──────────────────────────────────────────────────────

def test_send_reminders_fires_bell_and_mail(monkeypatch):
    due = [{"id": 1, "title": "Devis", "notes": "client Atlas",
            "due_at": datetime.now(), "repeat": "none"}]
    notified, stamped, sent = [], [], []
    monkeypatch.setattr(jobs.logs, "due_tasks", lambda now: due)
    monkeypatch.setattr(
        jobs.logs, "account_people",
        lambda: [{"id": 7, "name": "Y", "email": "y@aznet.ma"}],
    )
    monkeypatch.setattr(
        jobs.logs, "notify_accounts",
        lambda *a, **k: notified.append(a) or 1,
    )
    monkeypatch.setattr(
        jobs.logs, "stamp_task_notified",
        lambda tid, nxt: stamped.append((tid, nxt)),
    )
    monkeypatch.setattr(jobs.mailer, "send", lambda to, subj, body: sent.append((to, subj)) or to)
    out = jobs.send_reminders()
    assert out["due"] == 1 and out["notified"] == 1 and out["emailed"] == 1
    assert notified[0][0] == "reminder" and notified[0][1] == "Devis"
    assert notified[0][3] == "#/tasks"
    assert stamped == [(1, None)]  # one-shot: never fires again
    assert sent and sent[0][1] == "Rappel — Devis"


def test_send_reminders_advances_recurring_task(monkeypatch):
    due = [{"id": 2, "title": "Point hebdo", "notes": None,
            "due_at": datetime(2026, 8, 2, 9, 0), "repeat": "weekly"}]
    stamped = []
    monkeypatch.setattr(jobs.logs, "due_tasks", lambda now: due)
    monkeypatch.setattr(jobs.logs, "account_people", lambda: [])
    monkeypatch.setattr(jobs.logs, "notify_accounts", lambda *a, **k: 0)
    monkeypatch.setattr(
        jobs.logs, "stamp_task_notified",
        lambda tid, nxt: stamped.append((tid, nxt)),
    )
    out = jobs.send_reminders()
    assert out["emailed"] == 0  # no emails configured → nothing to send
    assert stamped == [(2, datetime(2026, 8, 9, 9, 0))]


def test_mail_failure_never_blocks_the_bell(monkeypatch):
    due = [{"id": 3, "title": "T", "notes": None,
            "due_at": datetime.now(), "repeat": "none"}]
    monkeypatch.setattr(jobs.logs, "due_tasks", lambda now: due)
    monkeypatch.setattr(
        jobs.logs, "account_people",
        lambda: [{"id": 7, "name": "Y", "email": "y@aznet.ma"}],
    )
    monkeypatch.setattr(jobs.logs, "notify_accounts", lambda *a, **k: 1)
    monkeypatch.setattr(jobs.logs, "stamp_task_notified", lambda *a, **k: None)
    def dead_smtp(*a, **k):
        raise mailer.MailError("smtp down")
    monkeypatch.setattr(jobs.mailer, "send", dead_smtp)
    out = jobs.send_reminders()
    assert out["notified"] == 1 and out["emailed"] == 0
    assert out["failed"] and "mail" in out["failed"][0]["error"]


def test_next_occurrence_rules():
    base = datetime(2026, 8, 2, 9, 0)
    assert jobs._next_occurrence(base, "daily") == base + timedelta(days=1)
    assert jobs._next_occurrence(base, "weekly") == base + timedelta(days=7)
    assert jobs._next_occurrence(base, "monthly") == datetime(2026, 9, 2, 9, 0)
    assert jobs._next_occurrence(base, "none") is None
    # Jan 31 → Feb 28: clamp to the month's real length, never skip February.
    jan31 = datetime(2026, 1, 31, 8, 0)
    assert jobs._next_occurrence(jan31, "monthly") == datetime(2026, 2, 28, 8, 0)
    dec31 = datetime(2026, 12, 31, 8, 0)
    assert jobs._next_occurrence(dec31, "monthly") == datetime(2027, 1, 31, 8, 0)


def test_next_occurrence_custom_intervals():
    base = datetime(2026, 8, 2, 9, 0)
    assert jobs._next_occurrence(base, "none", 3, "day") == base + timedelta(days=3)
    assert jobs._next_occurrence(base, "none", 2, "week") == base + timedelta(days=14)
    assert jobs._next_occurrence(base, "none", 2, "month") == datetime(2026, 10, 2, 9, 0)
    assert jobs._next_occurrence(base, "none", None, None) is None
    # The custom interval clamps monthly too: Jan 31 + 2 months → Mar 31.
    jan31 = datetime(2026, 1, 31, 8, 0)
    assert jobs._next_occurrence(jan31, "none", 2, "month") == datetime(2026, 3, 31, 8, 0)


def test_notify_time_opens_the_window_early():
    due = datetime(2026, 8, 10, 9, 0)
    assert logs.notify_time(due, None, None) == due
    assert logs.notify_time(due, 0, "day") == due
    assert logs.notify_time(due, 3, "day") == datetime(2026, 8, 7, 9, 0)
    assert logs.notify_time(due, 1, "week") == datetime(2026, 8, 3, 9, 0)
    # Calendar-aware months: Mar 31 minus one month clamps to Feb 28.
    assert logs.notify_time(datetime(2026, 3, 31, 9, 0), 1, "month") == datetime(2026, 2, 28, 9, 0)


def test_send_reminders_fires_early_for_lead_time(monkeypatch):
    due = [{"id": 4, "title": "Devis Atlas", "notes": None,
            "due_at": datetime.now() + timedelta(days=2), "repeat": "none",
            "remind_before_value": 3, "remind_before_unit": "day",
            "repeat_every": None, "repeat_unit": None}]
    bodies = []
    monkeypatch.setattr(jobs.logs, "due_tasks", lambda now: due)
    monkeypatch.setattr(jobs.logs, "account_people", lambda: [])
    monkeypatch.setattr(
        jobs.logs, "notify_accounts",
        lambda *a, **k: bodies.append(a) or 1,
    )
    monkeypatch.setattr(jobs.logs, "stamp_task_notified", lambda *a, **k: None)
    out = jobs.send_reminders()
    assert out["due"] == 1 and out["notified"] == 1
    assert "Rappel : 3 jours avant l'échéance" in bodies[0][2]
    assert "Échéance" in bodies[0][2]


def test_send_reminders_advances_custom_interval(monkeypatch):
    due = [{"id": 5, "title": "Contrôle stock", "notes": None,
            "due_at": datetime(2026, 8, 2, 9, 0), "repeat": "none",
            "remind_before_value": None, "remind_before_unit": None,
            "repeat_every": 3, "repeat_unit": "day"}]
    stamped = []
    monkeypatch.setattr(jobs.logs, "due_tasks", lambda now: due)
    monkeypatch.setattr(jobs.logs, "account_people", lambda: [])
    monkeypatch.setattr(jobs.logs, "notify_accounts", lambda *a, **k: 0)
    monkeypatch.setattr(
        jobs.logs, "stamp_task_notified",
        lambda tid, nxt: stamped.append((tid, nxt)),
    )
    jobs.send_reminders()
    assert stamped == [(5, datetime(2026, 8, 5, 9, 0))]
