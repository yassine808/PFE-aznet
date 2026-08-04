"""POST /reply — the inbox composer's outbound channel.

require_human (a logged-in browser), person resolution and channel sends all
mocked: the tests must never need a database or a bot token.
"""
from fastapi.testclient import TestClient

import app.main as main

client = TestClient(main.app)

main.app.dependency_overrides[main.auth.require_human] = lambda: {
    "id": 1, "name": "Directeur", "role": "directeur"
}

PERSON = {
    "id": 3,
    "name": "Tech 1",
    "role": "tech",
    "identities": [
        {"id": 1, "channel": "telegram", "external_id": "123", "active": True},
        {"id": 2, "channel": "whatsapp", "external_id": "21261234567", "active": True},
    ],
}


def test_reply_sends_to_every_active_channel(monkeypatch):
    monkeypatch.setattr(main.logs, "person_by_name", lambda name: PERSON)
    sent = []

    def fake_send(identities, text):
        assert text == "Merci, j'ai bien reçu."
        sent.extend(i["channel"] for i in identities)
        return {"delivered": [{"channel": i["channel"]} for i in identities]}

    monkeypatch.setattr(main.reply, "reply_to_identities", fake_send)
    r = client.post("/reply", json={"name": "Tech 1", "text": "Merci, j'ai bien reçu."})
    assert r.status_code == 200
    assert set(r.json()["delivered"][0]) == {"channel"}
    assert set(sent) == {"telegram", "whatsapp"}


def test_reply_ignores_inactive_identities(monkeypatch):
    person = {
        **PERSON,
        "identities": [
            {"id": 1, "channel": "telegram", "external_id": "123", "active": True},
            {"id": 2, "channel": "whatsapp", "external_id": "21261234567", "active": False},
        ],
    }
    monkeypatch.setattr(main.logs, "person_by_name", lambda name: person)
    sent = []
    monkeypatch.setattr(
        main.reply, "reply_to_identities",
        lambda identities, text: sent.extend(i["channel"] for i in identities) or {
            "delivered": [{"channel": "telegram"}]
        },
    )
    r = client.post("/reply", json={"name": "Tech 1", "text": "Bonjour"})
    assert r.status_code == 200
    assert sent == ["telegram"]


def test_reply_unknown_person_is_404(monkeypatch):
    monkeypatch.setattr(main.logs, "person_by_name", lambda name: None)
    r = client.post("/reply", json={"name": "Ghost", "text": "Bonjour"})
    assert r.status_code == 404
    assert "no technician named" in r.json()["detail"]


def test_reply_without_active_channel_is_404(monkeypatch):
    monkeypatch.setattr(
        main.logs, "person_by_name",
        lambda name: {**PERSON, "identities": [{"channel": "telegram", "external_id": "123", "active": False}]},
    )
    r = client.post("/reply", json={"name": "Tech 1", "text": "Bonjour"})
    assert r.status_code == 404
    assert "no active channel" in r.json()["detail"]


def test_reply_empty_text_is_422():
    r = client.post("/reply", json={"name": "Tech 1", "text": "   "})
    assert r.status_code == 422


def test_reply_all_channels_refused_is_502(monkeypatch):
    monkeypatch.setattr(main.logs, "person_by_name", lambda name: PERSON)
    monkeypatch.setattr(
        main.reply, "reply_to_identities",
        lambda identities, text: (_ for _ in ()).throw(
            main.reply.ReplyError("telegram: refusé; whatsapp: fenêtre fermée")
        ),
    )
    r = client.post("/reply", json={"name": "Tech 1", "text": "Bonjour"})
    assert r.status_code == 502
    assert "refusé" in r.json()["detail"]


def test_reply_missing_tokens_fails_loudly(monkeypatch):
    monkeypatch.setattr(main.logs, "person_by_name", lambda name: PERSON)
    monkeypatch.setattr(
        main.reply, "reply_to_identities",
        lambda identities, text: (_ for _ in ()).throw(
            main.reply.ReplyError("Réponse Telegram non configurée (TELEGRAM_BOT_TOKEN manquant)")
        ),
    )
    r = client.post("/reply", json={"name": "Tech 1", "text": "Bonjour"})
    assert r.status_code == 502
    assert "TELEGRAM_BOT_TOKEN" in r.json()["detail"]


def test_reply_log_store_down_is_502(monkeypatch):
    def boom(name):
        raise main.logs.LogStoreError("database not configured")

    monkeypatch.setattr(main.logs, "person_by_name", boom)
    r = client.post("/reply", json={"name": "Tech 1", "text": "Bonjour"})
    assert r.status_code == 502
