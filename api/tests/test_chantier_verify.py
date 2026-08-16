"""Confirming a chantier the pipeline invented from a voice note.

`journal.resolve_site` creates an unknown spoken site with `verifie = false`
rather than dropping the row. Nothing confirmed it until this endpoint existed,
so mis-transcribed names accumulated as real tabs — the gap this covers.
"""
import pytest
from fastapi.testclient import TestClient

import app.main as main

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _director(monkeypatch):
    # Per-test: other modules override auth deps at import time and the last
    # import would otherwise win for the whole run.
    monkeypatch.setitem(
        main.app.dependency_overrides,
        main.auth.require_director,
        lambda: {"id": 1, "name": "Directeur", "role": "directeur"},
    )
    monkeypatch.setitem(
        main.app.dependency_overrides,
        main.auth.require_user,
        lambda: {"id": 1, "name": "Directeur", "role": "directeur"},
    )
    monkeypatch.setattr(main.auth, "record", lambda *a, **k: None)


def test_list_exposes_the_unverified_flag(monkeypatch):
    monkeypatch.setattr(
        main.logs, "list_chantiers",
        lambda active_only=False: [{"id": 3, "nom": "Novick", "verifie": False}],
    )
    r = client.get("/chantiers")
    assert r.status_code == 200
    assert r.json()["chantiers"][0]["verifie"] is False


def test_patch_marks_it_verified(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        main.logs, "verify_chantier", lambda cid: seen.update(id=cid) or True
    )
    r = client.patch("/chantiers/3")
    assert r.status_code == 200
    assert r.json() == {"id": 3, "verifie": True}
    assert seen == {"id": 3}


def test_patch_on_a_missing_site_is_404(monkeypatch):
    monkeypatch.setattr(main.logs, "verify_chantier", lambda cid: False)
    assert client.patch("/chantiers/99").status_code == 404


def test_patch_is_director_only(monkeypatch):
    """The gate is the API's, not the dashboard hiding a button."""
    monkeypatch.delitem(
        main.app.dependency_overrides, main.auth.require_director, raising=False
    )
    monkeypatch.setitem(
        main.app.dependency_overrides,
        main.auth.require_human,
        lambda: {"id": 8, "name": "Chef", "role": "chef"},
    )
    assert client.patch("/chantiers/3").status_code == 403
