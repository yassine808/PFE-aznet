"""The conversation log: exchanges that never became Sheet rows.

Decided 2026-08-15: n8n records a message + the reply the technician got on
the no_report_content branch, so the dashboard inbox can show a complete
conversation instead of silence. `save_exchange` / `list_exchanges` are
covered on the SQL (recording cursor, no database), the endpoints through the
same dependency-override pattern as test_process_endpoint.py.
"""
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi.testclient import TestClient

import pytest

import app.main as main
from app import logs

client = TestClient(main.app)

main.app.dependency_overrides[main.auth.require_user] = lambda: {
    "id": 1, "name": "Test", "role": "directeur"
}


class _RecordingCursor:
    def __init__(self):
        self.statements = []
        self.rowcount = 0
        self._rows = []

    def execute(self, sql, args=None):
        self.statements.append((sql, args))

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


@contextmanager
def _fake_cursor(cur):
    yield cur


def _statement(cursor, needle):
    for sql, args in cursor.statements:
        if needle in sql:
            return sql, args
    raise AssertionError(f"no statement containing {needle!r}")


def _last_statement(cursor, needle):
    for sql, args in reversed(cursor.statements):
        if needle in sql:
            return sql, args
    raise AssertionError(f"no statement containing {needle!r}")


def test_save_exchange_inserts_all_columns(monkeypatch):
    cur = _RecordingCursor()
    cur._rows = [{"id": 7}]
    monkeypatch.setattr(logs, "_cursor", lambda: _fake_cursor(cur))

    returned = logs.save_exchange(
        date="2026-08-15", heure="10:30", channel="telegram",
        external_id="123", message_id="tg:123:456", technicien="Karim",
        kind="text", text="ok", reply="ℹ️ aucun rapport", correlation_id="corr-1",
    )

    assert returned == 7
    sql, args = _statement(cur, "INSERT INTO exchanges")
    assert all(needle in sql for needle in ("date", "heure", "channel", "external_id",
                                            "message_id", "technicien", "kind", "text",
                                            "reply", "correlation_id", "stt_engine"))
    # A typed message never touched STT, so the engine is NULL rather than a
    # placeholder: the inbox shows the chip only when one actually ran.
    assert args == ("2026-08-15", "10:30", "telegram", "123", "tg:123:456",
                    "Karim", "text", "ok", "ℹ️ aucun rapport", "corr-1", None)


def test_save_exchange_records_the_engine_for_audio(monkeypatch):
    """An exchange never becomes a Rapports row, so this column is the only
    place the engine that heard a no-report voice note is written down."""
    cur = _RecordingCursor()
    cur._rows = [{"id": 8}]
    monkeypatch.setattr(logs, "_cursor", lambda: _fake_cursor(cur))

    logs.save_exchange(
        date="2026-08-16", heure="11:00", channel="whatsapp",
        external_id="212600000000", message_id="wamid.x", technicien="Karim",
        kind="audio", text="salam", reply="ℹ️ aucun rapport",
        correlation_id="corr-2", stt_engine="local",
    )

    _, args = _statement(cur, "INSERT INTO exchanges")
    assert args[-1] == "local"


def test_list_exchanges_returns_iso_ts_and_media_id(monkeypatch):
    cur = _RecordingCursor()
    cur._rows = [
        {
            "id": 7, "ts": datetime(2026, 8, 15, 8, 30, tzinfo=timezone.utc),
            "date": "2026-08-15", "heure": "09:30", "channel": "telegram",
            "external_id": "123", "message_id": "tg:123:456", "technicien": "Karim",
            "kind": "audio", "text": "salam", "reply": "ℹ️ aucun rapport",
            "correlation_id": "corr-1", "media_id": 42,
        },
    ]
    monkeypatch.setattr(logs, "_cursor", lambda: _fake_cursor(cur))

    rows = logs.list_exchanges()

    assert len(rows) == 1
    assert rows[0]["ts"] == "2026-08-15T08:30:00+00:00"
    assert rows[0]["media_id"] == 42
    assert rows[0]["kind"] == "audio"
    sql, args = _statement(cur, "FROM exchanges")
    assert "ORDER BY e.ts DESC" in sql
    assert args == (200,)


def test_list_exchanges_clamps_limit(monkeypatch):
    cur = _RecordingCursor()
    cur._rows = []
    monkeypatch.setattr(logs, "_cursor", lambda: _fake_cursor(cur))

    logs.list_exchanges(limit=9999)
    _, args = _last_statement(cur, "FROM exchanges")
    assert args == (500,)

    logs.list_exchanges(limit=0)
    _, args = _last_statement(cur, "FROM exchanges")
    assert args == (1,)


def test_record_exchange_roundtrip(monkeypatch):
    captured = {}

    def fake_save(**kwargs):
        captured.update(kwargs)
        return 7

    monkeypatch.setattr(main.logs, "save_exchange", fake_save)

    response = client.post("/exchanges", json={
        "date": "2026-08-15", "heure": "10:30", "channel": "telegram",
        "external_id": "123", "message_id": "tg:123:456", "technicien": "Karim",
        "text": "ok", "reply": "ℹ️ aucun rapport", "correlation_id": "corr-1",
    })

    assert response.status_code == 200
    assert response.json() == {"ok": True, "id": 7}
    assert captured["kind"] == "text"  # default
    assert captured["message_id"] == "tg:123:456"


def test_record_exchange_502_when_store_unreachable(monkeypatch):
    def boom(**kwargs):
        raise logs.LogStoreError("postgres query failed: connection refused")

    monkeypatch.setattr(main.logs, "save_exchange", boom)

    response = client.post("/exchanges", json={"text": "ok"})
    assert response.status_code == 502


def test_list_exchanges_endpoint(monkeypatch):
    monkeypatch.setattr(
        main.logs, "list_exchanges",
        lambda limit: [{"id": 7, "date": "2026-08-15", "reply": "ℹ️ aucun rapport"}],
    )

    response = client.get("/exchanges")

    assert response.status_code == 200
    body = response.json()
    assert body["exchanges"][0]["id"] == 7
    assert body["exchanges"][0]["reply"] == "ℹ️ aucun rapport"


def test_list_exchanges_rejects_huge_limit(monkeypatch):
    monkeypatch.setattr(main.logs, "list_exchanges", lambda limit: [])

    response = client.get("/exchanges", params={"limit": 9999})
    assert response.status_code == 422


# ── Correcting a transcript ────────────────────────────────────────────────
# Added 2026-08-16 with the inbox's editable transcript. The behaviour that
# matters is not that the UPDATE runs — it is that the *previous* text reaches
# the audit trail, because that is the whole reason a transcript is allowed to
# be corrected at all.


def test_update_exchange_text_returns_the_previous_value(monkeypatch):
    cur = _RecordingCursor()
    cur._rows = [{"text": "chi 18 prises"}]
    monkeypatch.setattr(logs, "_cursor", lambda: _fake_cursor(cur))

    assert logs.update_exchange_text(7, "18 prises") == {"before": "chi 18 prises"}
    sql, args = _last_statement(cur, "UPDATE exchanges")
    assert args == ("18 prises", 7)


def test_update_exchange_text_none_when_the_row_is_gone(monkeypatch):
    cur = _RecordingCursor()
    cur._rows = []
    monkeypatch.setattr(logs, "_cursor", lambda: _fake_cursor(cur))

    assert logs.update_exchange_text(7, "18 prises") is None
    # Nothing is written for a row that does not exist — an UPDATE matching no
    # row would look identical from here and answer 200 to the browser.
    assert not any("UPDATE" in sql for sql, _ in cur.statements)


def test_patch_exchange_records_before_and_after(monkeypatch):
    main.app.dependency_overrides[main.auth.require_human] = lambda: {
        "id": 1, "name": "Test", "role": "directeur"
    }
    recorded = {}
    monkeypatch.setattr(
        main.logs, "update_exchange_text", lambda i, t: {"before": "chi 18 prises"}
    )
    monkeypatch.setattr(
        main.auth, "record",
        lambda caller, action, **kw: recorded.update({"action": action, **kw}),
    )

    response = client.patch("/exchanges/7", json={"text": "18 prises"})

    assert response.status_code == 200
    assert recorded["action"] == "transcript_edited"
    assert recorded["before"] == "chi 18 prises"
    assert recorded["after"] == "18 prises"
    main.app.dependency_overrides.pop(main.auth.require_human, None)


def test_patch_exchange_404_when_absent(monkeypatch):
    main.app.dependency_overrides[main.auth.require_human] = lambda: {
        "id": 1, "name": "Test", "role": "directeur"
    }
    monkeypatch.setattr(main.logs, "update_exchange_text", lambda i, t: None)
    monkeypatch.setattr(main.auth, "record", lambda *a, **k: None)

    assert client.patch("/exchanges/7", json={"text": "x"}).status_code == 404
    main.app.dependency_overrides.pop(main.auth.require_human, None)