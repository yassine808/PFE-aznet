"""The 2026-08-03 hardening: five endpoints used to answer anonymous requests
(POST /process, GET /logs, POST|GET /service-samples, PATCH /sheet-queue/{id}).
Each test strips the shared dependency overrides so the *real* gate runs, then
asserts 401. A bare POST /process must cost the caller nothing: no STT engine,
no Sheet write, no free-tier quota.

These tests exist because the suite used to mask the missing gates: modules
set module-level `dependency_overrides` on the shared app object, so the real
`require_user` never ran once any such module had been imported — the full
suite stayed green against an anonymous API.
"""
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.schemas import ExtractedReport

client = TestClient(main.app)

_AUTH_DEPS = (main.auth.current_user, main.auth.require_user, main.auth.require_human)


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    """Same guarantees as the other modules: nothing may reach the dev DB."""
    monkeypatch.setattr(main.logs, "notify_technician_manager", lambda *a, **k: None)
    monkeypatch.setattr(main.logs, "notify_managers", lambda *a, **k: 0)
    monkeypatch.setattr(main.logs, "profile_for", lambda name: None)


@pytest.fixture
def _real_gate(monkeypatch):
    """Remove every auth override so the actual gate runs for this test."""
    for dep in _AUTH_DEPS:
        monkeypatch.delitem(main.app.dependency_overrides, dep, raising=False)


def test_process_requires_auth(_real_gate):
    r = client.post("/process", data={"text": "installation goulotte"})
    assert r.status_code == 401
    assert "authentication required" in r.json()["detail"]


def test_get_logs_requires_auth(_real_gate):
    assert client.get("/logs").status_code == 401


def test_post_logs_requires_auth(_real_gate):
    r = client.post("/logs", json={"stage": "received", "level": "info", "message": "x"})
    assert r.status_code == 401


def test_service_samples_require_auth(_real_gate):
    assert client.post("/service-samples", json={"samples": []}).status_code == 401
    assert client.get("/service-samples").status_code == 401


def test_sheet_queue_resolve_requires_auth(_real_gate):
    r = client.patch("/sheet-queue/1", json={"ok": True})
    assert r.status_code == 401


def test_machine_key_opens_the_gate(_real_gate, monkeypatch):
    """n8n's way in: X-API-Key against a configured INTERNAL_API_KEY."""
    monkeypatch.setattr(main.settings, "internal_api_key", "test-key")
    monkeypatch.setattr(
        main.extraction, "extract_report_with_model",
        lambda t, profile=None: (ExtractedReport(resume="Le technicien salue."), "test/stub"),
    )
    r = client.post(
        "/process",
        data={"text": "salam"},
        headers={"X-API-Key": "test-key"},
    )
    assert r.status_code == 200, r.text


def test_wrong_key_still_rejected(_real_gate, monkeypatch):
    monkeypatch.setattr(main.settings, "internal_api_key", "test-key")
    r = client.post(
        "/process",
        data={"text": "salam"},
        headers={"X-API-Key": "not-the-key"},
    )
    assert r.status_code == 401


def test_unconfigured_key_disables_machine_access(_real_gate, monkeypatch):
    """Unset INTERNAL_API_KEY means machine access is *off*, never 'everyone
    is a machine' — the docstring promise in auth.py, pinned by a test."""
    monkeypatch.setattr(main.settings, "internal_api_key", None)
    r = client.post("/process", data={"text": "salam"}, headers={"X-API-Key": "anything"})
    assert r.status_code == 401
