"""The message retry queue: backoff, the give-up cap, and the quota exemption.

The queue exists so a /process failure stops being the end of a report. Three
properties make it safe rather than merely persistent, and all three are the
kind that fail silently if they regress:

- the cap. Ordering is enforced per technician, so a message that can never
  succeed would block every later report from that person forever. Abandoning it
  is what releases them, and the release only happens if `attempts` actually
  reaches the cap.
- the quota exemption. A vendor refusing everyone is not this message's fault;
  spending six attempts on a five-minute rate-limit window abandons a report
  that would have succeeded. `count_attempt=False` must not advance the count
  and must never promote a row to `abandoned`.
- the backoff. Front-loaded then flat: most failures are a hiccup, and anything
  still failing at ten minutes is an outage that polling faster will not fix.

These run with no database — `_cursor` is faked — because the suite must stay
runnable without one, which is also why the SQL is asserted rather than the
resulting rows.
"""
from contextlib import contextmanager

import pytest

from app import logs


class _Cur:
    """A cursor that replays queued fetch results and records every statement."""

    def __init__(self, fetchone_queue=None):
        self.statements = []
        self.fetchone_queue = list(fetchone_queue or [])

    def execute(self, sql, args=None):
        self.statements.append((" ".join(sql.split()), args))

    def fetchone(self):
        return self.fetchone_queue.pop(0) if self.fetchone_queue else None

    def fetchall(self):
        return []


@pytest.fixture
def cur(monkeypatch):
    c = _Cur()

    @contextmanager
    def fake():
        yield c

    monkeypatch.setattr(logs, "_cursor", fake)
    return c


def _update(c):
    """The UPDATE statement resolve_message issued, with its arguments."""
    return next((s, a) for s, a in c.statements if s.startswith("UPDATE message_queue"))


# ── backoff ────────────────────────────────────────────────────────────────

def test_backoff_is_front_loaded_then_flat():
    steps = [logs.backoff_for(i) for i in range(len(logs.RETRY_BACKOFF_S))]
    assert steps == [30, 120, 300, 600, 600, 600]
    assert steps == sorted(steps), "a later attempt must never wait less than an earlier one"


def test_backoff_never_indexes_past_the_table():
    """Attempt counts above the cap still answer, rather than raising IndexError."""
    assert logs.backoff_for(99) == logs.RETRY_BACKOFF_S[-1]


# ── the give-up cap ────────────────────────────────────────────────────────

def test_attempt_below_the_cap_stays_retrying(cur):
    cur.fetchone_queue = [{"attempts": 0, "status": "queued"}]
    assert logs.resolve_message(1, False, "boom") == "retrying"
    _sql, args = _update(cur)
    assert args[0] == 1, "the attempt must actually be counted"


def test_last_attempt_abandons_and_releases_the_technician(cur):
    """At the cap the row stops being retried — that is what unblocks the queue."""
    cur.fetchone_queue = [{"attempts": logs.MAX_MESSAGE_ATTEMPTS - 1, "status": "retrying"}]
    assert logs.resolve_message(1, False, "boom") == "abandoned"
    _sql, args = _update(cur)
    assert args[0] == logs.MAX_MESSAGE_ATTEMPTS


def test_success_deletes_the_row(cur):
    assert logs.resolve_message(1, True) == "done"
    assert any(s.startswith("DELETE FROM message_queue") for s, _ in cur.statements)


def test_a_vanished_row_is_reported_not_crashed(cur):
    """The row can be gone: an operator dismissed it between the pass and now."""
    cur.fetchone_queue = [None]
    assert logs.resolve_message(1, False, "boom") == "gone"


# ── the quota exemption ────────────────────────────────────────────────────

def test_quota_refusal_spends_no_attempt(cur):
    cur.fetchone_queue = [{"attempts": 3, "status": "retrying"}]
    logs.resolve_message(1, False, "429 rate limit", count_attempt=False)
    _sql, args = _update(cur)
    assert args[0] == 3, "a vendor-wide refusal is not this message's fault"


def test_quota_refusal_never_abandons_even_at_the_cap(cur):
    """The dangerous case: at the cap, a quota must not tip the row over it."""
    cur.fetchone_queue = [{"attempts": logs.MAX_MESSAGE_ATTEMPTS, "status": "retrying"}]
    status = logs.resolve_message(1, False, "quota exhausted", count_attempt=False)
    assert status == "retrying"
    _sql, args = _update(cur)
    assert args[0] == logs.MAX_MESSAGE_ATTEMPTS
    assert args[2] == "retrying"


# ── the ordering gate ──────────────────────────────────────────────────────

def test_no_technician_is_never_blocked(monkeypatch):
    """An unknown sender has no queue to be ordered against — and must not
    inherit someone else's block by matching on an empty name."""
    called = []
    monkeypatch.setattr(logs, "_cursor", lambda: called.append(1))
    assert logs.blocked_technician(None) is None
    assert logs.blocked_technician("") is None
    assert not called, "the store should not even be asked"


def test_gate_asks_only_for_unresolved_rows(cur):
    cur.fetchone_queue = [None]
    logs.blocked_technician("Yassine")
    sql, args = cur.statements[0]
    assert "status IN ('queued','retrying')" in sql, "abandoned rows must not block anyone"
    assert "ORDER BY created_at ASC" in sql, "the oldest message is the head of the queue"
    assert args == ("Yassine",)


def test_enqueue_is_idempotent_on_correlation_id(cur):
    cur.fetchone_queue = [{"id": 7}]
    logs.enqueue_message({"correlation_id": "c-1", "technicien": "Y", "kind": "text"})
    sql, _args = cur.statements[0]
    assert "ON CONFLICT (correlation_id) DO NOTHING" in sql, (
        "n8n retries and the drain replays; a second row would block the "
        "technician twice and file the report twice"
    )


def test_due_takes_one_message_per_technician(cur):
    logs.due_messages(10)
    sql, _args = cur.statements[0]
    assert "DISTINCT ON (technicien)" in sql, (
        "two of one person's messages in one pass would race and file out of order"
    )
