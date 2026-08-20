"""GET /n8n/* — the read-only orchestrator proxy.

These routes exist so the API, not the reverse proxy, holds X-N8N-API-KEY: a
proxy that injected it would expose an unauthenticated n8n admin API to anyone
who could reach the public URL. So the two things worth pinning are that the key
is actually sent, and that every n8n-side failure comes back as 502 rather than
a 500 the dashboard cannot render.
"""
import httpx
from fastapi.testclient import TestClient

import app.main as main

client = TestClient(main.app)

main.app.dependency_overrides[main.auth.require_human] = lambda: {
    "id": 1, "name": "Test", "role": "directeur"
}


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    """Stands in for httpx.AsyncClient; records the last request it was given."""

    last = {}

    def __init__(self, response=None, raises=None, **kwargs):
        self._response = response
        self._raises = raises

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        _FakeClient.last = {"url": url, "headers": headers or {}}
        if self._raises is not None:
            raise self._raises
        return self._response


def _patch(monkeypatch, response=None, raises=None, key="k-123"):
    monkeypatch.setattr(main.settings, "n8n_api_key", key)
    monkeypatch.setattr(main.settings, "n8n_url", "http://n8n:5678")
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeClient(response=response, raises=raises)
    )


def test_workflows_sends_the_key_and_returns_the_payload(monkeypatch):
    _patch(monkeypatch, _FakeResponse(200, {"data": [{"id": "1", "name": "réception"}]}))
    r = client.get("/n8n/workflows")
    assert r.status_code == 200
    assert r.json()["data"][0]["name"] == "réception"
    assert _FakeClient.last["url"] == "http://n8n:5678/api/v1/workflows"
    assert _FakeClient.last["headers"]["X-N8N-API-KEY"] == "k-123"


def test_executions_passes_the_limit(monkeypatch):
    _patch(monkeypatch, _FakeResponse(200, {"data": []}))
    assert client.get("/n8n/executions?limit=5").status_code == 200
    assert _FakeClient.last["url"].endswith("/api/v1/executions?limit=5")


def test_missing_key_is_502_not_a_silent_empty_list(monkeypatch):
    _patch(monkeypatch, _FakeResponse(200, {"data": []}), key=None)
    r = client.get("/n8n/workflows")
    assert r.status_code == 502
    assert "N8N_API_KEY" in r.json()["detail"]


def test_rejected_key_is_502_and_says_rejected(monkeypatch):
    # The dashboard distinguishes "n8n is down" from "n8n refused the key" on
    # this word (Dashboard/src/lib/api.ts, n8nStatus).
    _patch(monkeypatch, _FakeResponse(401))
    r = client.get("/n8n/workflows")
    assert r.status_code == 502
    assert "rejected" in r.json()["detail"]


def test_connection_error_is_502(monkeypatch):
    _patch(monkeypatch, raises=httpx.ConnectError("refused"))
    r = client.get("/n8n/workflows")
    assert r.status_code == 502
    assert "unreachable" in r.json()["detail"]


# ── GET /n8n/listening ─────────────────────────────────────────────────────
# 2026-08-19: n8n's crons were unregistered after a run of Telegram "Bad
# request". Polling and the WhatsApp webhook were dead for an hour while the
# process answered every health probe. Only finished work proves listening.

main.app.dependency_overrides[main.auth.require_user] = lambda: {
    "id": 1, "name": "Test", "role": "directeur"
}


def _ago(seconds: float) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def test_recent_execution_is_not_stale(monkeypatch):
    _patch(monkeypatch, _FakeResponse(200, {"data": [{"stoppedAt": _ago(60)}]}))
    body = client.get("/n8n/listening").json()
    assert body["stale"] is False
    assert body["age_seconds"] < 120


def test_old_execution_is_stale(monkeypatch):
    _patch(monkeypatch, _FakeResponse(200, {"data": [{"stoppedAt": _ago(7200)}]}))
    monkeypatch.setattr(main.settings, "n8n_stale_after_minutes", 30)
    body = client.get("/n8n/listening").json()
    assert body["stale"] is True
    assert body["threshold_seconds"] == 1800


def test_running_execution_falls_back_to_started_at(monkeypatch):
    _patch(monkeypatch, _FakeResponse(200, {"data": [{"stoppedAt": None, "startedAt": _ago(30)}]}))
    assert client.get("/n8n/listening").json()["stale"] is False


def test_no_executions_at_all_is_stale(monkeypatch):
    """Never having run is the worst version of not listening, not the best."""
    _patch(monkeypatch, _FakeResponse(200, {"data": []}))
    body = client.get("/n8n/listening").json()
    assert body["stale"] is True and body["age_seconds"] is None


def test_unreadable_timestamp_is_stale_not_healthy(monkeypatch):
    _patch(monkeypatch, _FakeResponse(200, {"data": [{"stoppedAt": "hier"}]}))
    assert client.get("/n8n/listening").json()["stale"] is True


def test_unreachable_n8n_is_502(monkeypatch):
    _patch(monkeypatch, raises=httpx.ConnectError("refused"))
    assert client.get("/n8n/listening").status_code == 502


def test_naive_timestamp_is_stale_not_a_500(monkeypatch):
    """n8n has answered without a timezone; naive minus aware is a TypeError,
    and a crash here would take the status line down with it."""
    _patch(monkeypatch, _FakeResponse(200, {"data": [{"stoppedAt": "2026-08-19T06:48:00"}]}))
    r = client.get("/n8n/listening")
    assert r.status_code == 200 and r.json()["stale"] is True
