"""Rows from the pool are dicts, so they are read by name — never by position.

`_get_pool` sets `cursor_factory=RealDictCursor`, which makes every row a dict
subclass. `row[0]` on one is a *key* lookup that raises `KeyError: 0`, and
`_cursor()` rewraps that as `LogStoreError` — so two plain coding errors spent
their life disguised as a database outage:

- `notify_technician_manager` raised before it could notify anyone, so /process
  logged "notification failed" and the manager's bell stayed silent for every
  report from a technician the org chart actually knew. The escalation path was
  unreachable for the same reason.
- `stt_usage` raised, so the STT panel rendered empty behind an error message
  that read as if Postgres were down.

Neither showed up in the suite: the notification store is monkeypatched out of
every test that would have reached it. These tests use dict rows, the shape the
real cursor returns, so a return to positional access fails here first.
"""
from contextlib import contextmanager

from app import logs


class _DictCursor:
    """A cursor whose rows are dicts, as RealDictCursor delivers them."""

    def __init__(self, fetchone_queue=None, fetchall_rows=None):
        self.statements = []
        self.fetchone_queue = list(fetchone_queue or [])
        self.fetchall_rows = list(fetchall_rows or [])

    def execute(self, sql, args=None):
        self.statements.append((sql, args))

    def executemany(self, sql, seq):
        self.statements.append((sql, list(seq)))

    def fetchone(self):
        return self.fetchone_queue.pop(0) if self.fetchone_queue else None

    def fetchall(self):
        return self.fetchall_rows


@contextmanager
def _fake_cursor(cur):
    yield cur


def _use(monkeypatch, cur):
    monkeypatch.setattr(logs, "_cursor", lambda: _fake_cursor(cur))
    return cur


def _inserts(cur):
    return [a for s, a in cur.statements if "INSERT INTO notifications" in s]


def test_known_sender_rings_only_their_managers_bell(monkeypatch):
    """The whole point of the function: one row, for the chef, by name."""
    cur = _use(monkeypatch, _DictCursor(
        fetchone_queue=[{"manager_id": 7}, {"?column?": 1}],
    ))

    written = logs.notify_technician_manager("NAROUZE", "report", "Nouveau rapport")

    assert written == 1
    args, = _inserts(cur)
    assert args[0] == 7  # the manager, not a broadcast


def test_sender_with_no_manager_escalates_to_every_manager_account(monkeypatch):
    """Documented fallback, and unreachable while the lookup above raised."""
    cur = _use(monkeypatch, _DictCursor(
        fetchone_queue=[None],
        fetchall_rows=[{"id": 1, "name": "A"}, {"id": 2, "name": "B"}],
    ))

    written = logs.notify_technician_manager("Inconnu", "report", "Nouveau rapport")

    assert written == 2
    rows, = _inserts(cur)  # one executemany carrying both people
    assert [r[0] for r in rows] == [1, 2]


def test_stt_usage_reads_the_selects_own_aliases(monkeypatch):
    """engine / today / period are the SELECT's aliases, so they are the keys."""
    _use(monkeypatch, _DictCursor(
        fetchall_rows=[
            {"engine": "gemini", "today": 3, "period": 9},
            {"engine": "local", "today": 0, "period": 2},
        ],
    ))

    usage = logs.stt_usage(7)

    assert usage["days"] == 7
    assert usage["engines"] == [
        {"engine": "gemini", "today": 3, "period": 9},
        {"engine": "local", "today": 0, "period": 2},
    ]
