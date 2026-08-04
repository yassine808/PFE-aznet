"""GET /rapport — the technicians' command, answered from stored reports.

The endpoint is machine-called by n8n, so it sits behind require_user (the
X-API-Key path), not require_human. Everything downstream is mocked: the
tests must never need a database.
"""
from fastapi.testclient import TestClient

import app.main as main

client = TestClient(main.app)

main.app.dependency_overrides[main.auth.require_user] = lambda: {
    "id": 1, "name": "n8n", "role": "directeur"
}


def test_unknown_sender_gets_found_false(monkeypatch):
    monkeypatch.setattr(main.logs, "find_technician", lambda c, e: None)
    r = client.get("/rapport", params={"channel": "telegram", "external_id": "123"})
    assert r.status_code == 200
    assert r.json()["found"] is False
    assert r.json()["detail"] == "inconnu"


def test_sender_without_manager_gets_found_false(monkeypatch):
    monkeypatch.setattr(
        main.logs, "find_technician",
        lambda c, e: {"person_id": 3, "name": "Tech", "role": "tech", "manager_id": None},
    )
    r = client.get("/rapport", params={"channel": "telegram", "external_id": "123"})
    assert r.json()["found"] is False
    assert r.json()["detail"] == "pas de responsable"


def test_manager_without_report_gets_found_false(monkeypatch):
    monkeypatch.setattr(
        main.logs, "find_technician",
        lambda c, e: {"person_id": 3, "name": "Tech", "role": "tech", "manager_id": 2},
    )
    monkeypatch.setattr(main.logs, "person_by_id", lambda mid: {"id": 2, "name": "Chef A"})
    monkeypatch.setattr(main.logs, "latest_manager_report", lambda mid: None)
    r = client.get("/rapport", params={"channel": "whatsapp", "external_id": "2126"})
    assert r.json()["found"] is False
    assert r.json()["detail"] == "aucun rapport"


def test_manager_report_returned_with_identity(monkeypatch):
    monkeypatch.setattr(
        main.logs, "find_technician",
        lambda c, e: {"person_id": 3, "name": "Tech", "role": "tech", "manager_id": 2},
    )
    monkeypatch.setattr(main.logs, "person_by_id", lambda mid: {"id": 2, "name": "Chef A", "role": "chef"})
    monkeypatch.setattr(
        main.logs, "latest_manager_report",
        lambda mid: {
            "period": "2026-08-01",
            "objet": "Rapport du 2026-08-01",
            "corps": "Salle 1 terminée.",
            "generated_at": "2026-08-01T18:31:00+00:00",
            "generated_by": "automatique",
        },
    )
    r = client.get("/rapport", params={"channel": "telegram", "external_id": "123"})
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["manager_name"] == "Chef A"
    assert body["corps"] == "Salle 1 terminée."


def test_generated_reports_listed_newest_first(monkeypatch):
    """The dashboard's reports page reads daily + weekly versions from the
    same store the mail and /rapport use — a placeholder name when the
    manager's person row is gone, so no report disappears from the list."""
    monkeypatch.setattr(
        main.logs, "list_manager_reports",
        lambda: [
            {"manager_id": 2, "manager_name": "Chef A", "period": "2026-08-01",
             "period_type": "daily", "objet": "Rapport du 2026-08-01", "corps": "…",
             "generated_at": "2026-08-01T18:31:00+00:00", "generated_by": "automatique"},
            {"manager_id": 4, "manager_name": "—", "period": "2026-07-27 → 2026-08-01",
             "period_type": "weekly", "objet": "Hebdo", "corps": "…",
             "generated_at": "2026-08-01T09:00:00+00:00", "generated_by": "automatique"},
        ],
    )
    r = client.get("/reports/generated")
    assert r.status_code == 200
    reports = r.json()["reports"]
    assert [g["period_type"] for g in reports] == ["daily", "weekly"]
    assert reports[1]["manager_name"] == "—"


def test_generated_reports_surfaces_store_failure(monkeypatch):
    def boom():
        raise main.logs.LogStoreError("postgres down")

    monkeypatch.setattr(main.logs, "list_manager_reports", boom)
    r = client.get("/reports/generated")
    assert r.status_code == 502
