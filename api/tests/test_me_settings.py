"""Per-account settings: stored per person in Postgres, confidence gated.

The confidence threshold left the browser the day these settings became
server-side, so the API refuses it for anyone but the directeur — the dashboard
hiding the slider is not a rule.
"""
import pytest
from fastapi.testclient import TestClient

import app.main as main

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _director(monkeypatch):
    # Per-test rather than module-level: other test modules also override this
    # dependency at import time, and the last import wins for the whole run.
    monkeypatch.setitem(
        main.app.dependency_overrides,
        main.auth.require_human,
        lambda: {"id": 7, "name": "Test", "role": "directeur"},
    )


def test_get_returns_stored_blob(monkeypatch):
    monkeypatch.setattr(
        main.logs, "get_person_settings", lambda pid: {"timeFormat": "12h"}
    )
    r = client.get("/me/settings")
    assert r.status_code == 200
    assert r.json() == {"settings": {"timeFormat": "12h"}}


def test_put_merges_into_caller_row(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        main.logs, "put_person_settings",
        lambda pid, values: calls.update(pid=pid, values=values) or {"timeFormat": "12h"},
    )
    r = client.put("/me/settings", json={"values": {"timeFormat": "12h"}})
    assert r.status_code == 200
    assert calls == {"pid": 7, "values": {"timeFormat": "12h"}}


def test_put_confidence_as_chef_is_403(monkeypatch):
    monkeypatch.setitem(
        main.app.dependency_overrides,
        main.auth.require_human,
        lambda: {"id": 8, "name": "Chef", "role": "chef"},
    )
    r = client.put("/me/settings", json={"values": {"confidence": 0.5}})
    assert r.status_code == 403


def test_put_confidence_as_directeur_ok(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        main.logs, "put_person_settings",
        lambda pid, values: calls.update(pid=pid, values=values) or {"confidence": 0.5},
    )
    r = client.put("/me/settings", json={"values": {"confidence": 0.5}})
    assert r.status_code == 200
    assert calls["values"] == {"confidence": 0.5}


def test_store_failure_is_502(monkeypatch):
    def boom(pid):
        raise main.logs.LogStoreError("db down")

    monkeypatch.setattr(main.logs, "get_person_settings", boom)
    assert client.get("/me/settings").status_code == 502
