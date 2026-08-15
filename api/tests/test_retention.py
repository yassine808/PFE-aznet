"""Retention sweep coverage: the archive tables age out on their own clocks.

`prune_meta` used to cover sessions / idempotency claims / audit / visits only,
so `media_files`, `chat_messages`, `exchanges` and `notifications` grew forever.
These tests pin the policy decided 2026-08-10 — blobs 30 days (the audio already
has a durable Drive link), chat and exchanges 90 days, read notifications 30
days (unread rows are never touched) — so a future edit that collapses the
clocks back onto the pipeline-logs `days` argument fails loudly.
"""
from contextlib import contextmanager

from app import logs

TABLES = (
    "sessions",
    "processed_messages",
    "user_actions",
    "page_visits",
    "media_files",
    "chat_messages",
    "exchanges",
    "notifications",
)


class _RecordingCursor:
    """Captures every statement so the policy is asserted on the SQL."""

    def __init__(self):
        self.statements = []
        self.rowcount = 0

    def execute(self, sql, args=None):
        self.statements.append((sql, args))

    def fetchone(self):
        return None

    def fetchall(self):
        return []


@contextmanager
def _fake_cursor(cur):
    yield cur


def _run(monkeypatch):
    cur = _RecordingCursor()
    monkeypatch.setattr(logs, "_cursor", lambda: _fake_cursor(cur))
    result = logs.prune_meta(30)
    return result, dict(cur.statements)


def test_archive_tables_prune_on_their_own_clocks(monkeypatch):
    _, by_sql = _run(monkeypatch)

    def args_for(table):
        (sql, args), = [(s, a) for s, a in by_sql.items() if f"DELETE FROM {table}" in s]
        return sql, args

    _, media = args_for("media_files")
    assert media == (logs.ARCHIVE_RETENTION_DAYS,)
    _, chat = args_for("chat_messages")
    assert chat == (logs.CHAT_RETENTION_DAYS,)
    _, exchanges = args_for("exchanges")
    assert exchanges == (logs.CHAT_RETENTION_DAYS,)
    _, notifs = args_for("notifications")
    assert notifs == (logs.NOTIF_RETENTION_DAYS,)

    # The time-series tables stay on the caller-supplied days.
    _, claims = args_for("processed_messages")
    assert claims == (30,)
    _, actions = args_for("user_actions")
    assert actions == (30,)
    _, visits = args_for("page_visits")
    assert visits == (30,)


def test_sessions_prune_on_expiry_not_age(monkeypatch):
    _, by_sql = _run(monkeypatch)
    (sql, _), = [(s, a) for s, a in by_sql.items() if "DELETE FROM sessions" in s]
    assert "expires_at < now()" in sql
    assert "created_at" not in sql


def test_only_read_notifications_prune(monkeypatch):
    _, by_sql = _run(monkeypatch)
    (sql, _), = [(s, a) for s, a in by_sql.items() if "DELETE FROM notifications" in s]
    assert "read_at IS NOT NULL" in sql
    assert "read_at < now()" in sql
    assert "created_at" not in sql


def test_archive_counts_reported_in_result(monkeypatch):
    result, _ = _run(monkeypatch)
    assert result["media_files_deleted"] == 0
    assert result["chat_messages_deleted"] == 0
    assert result["exchanges_deleted"] == 0
    assert result["notifications_deleted"] == 0
    assert result["sessions_deleted"] == 0
