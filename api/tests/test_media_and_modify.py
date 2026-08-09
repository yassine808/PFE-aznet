"""TO-DO #9 / #10 / #13 — media + chat archive, Drive links, /modify backend.

Same discipline as the rest of the suite: no API keys, no database. The log
store functions are monkeypatched at `main.logs.*`; the Sheets service is
faked through `main.sheets._service` so `append_report`, `clear_row` and
`update_report_fields` run their real column-mapping logic against a canned
header row.
"""
from fastapi.testclient import TestClient

import pytest

import app.main as main
from app.providers.base import TranscriptionInfo, TranscriptionProvider
from app.schemas import ExtractedReport

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _silence_bell(monkeypatch):
    """The bell is exercised in test_tasks_notifications.py. These tests are
    about archiving and Drive — the real notification store would hit the dev
    DB (or, worse, an unreachable one) for no assertion here."""
    monkeypatch.setattr(main.logs, "notify_technician_manager", lambda *a, **k: None)
    monkeypatch.setattr(main.logs, "notify_managers", lambda *a, **k: 0)

# /modify-command and /messages/link are machine-called by n8n, so they sit
# behind require_user (the X-API-Key path), not require_human — same shape as
# test_rapport_endpoint.py. Overriding require_user covers them and anything
# human-gated further up the chain.
main.app.dependency_overrides[main.auth.require_user] = lambda: {
    "id": 1, "name": "Test", "role": "directeur"
}

REPORT = ExtractedReport(
    etages=["E2"],
    goulotte_m=150,
    cables_installes_m=800,
    resume="Installation de 150 m de goulotte et pose de 800 m de câble réseau.",
)


class FakeProvider(TranscriptionProvider):
    name = "fake"

    def transcribe(self, audio, mime_type):
        return TranscriptionInfo(
            text="نصبنا goulotte 150 متر وجرّينا 800 متر ديال الكابل",
            provider="fake", latency_s=0.1,
        )


# ── /process archive hooks (TO-DO #10) ─────────────────────────────────────

def test_audio_archived_and_drive_linked(monkeypatch):
    """The voice note lands in Postgres AND gets a durable Drive link that
    rides out in lien_audio."""
    saved = {}

    def fake_save(channel, external_id, message_id, kind, mime_type, data):
        saved.update(channel=channel, message_id=message_id, kind=kind,
                     mime_type=mime_type, data=data)

    monkeypatch.setattr(main.logs, "save_media", fake_save)
    monkeypatch.setattr(
        main.drive, "upload_audio",
        lambda filename, mime, data: "https://drive.google.com/uc?id=abc",
    )
    monkeypatch.setattr(main, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(
        main.extraction, "extract_report_with_model",
        lambda t, profile=None: (REPORT, "test/stub"),
    )
    r = client.post(
        "/process",
        data={"message_id": "tg:123:456", "channel": "telegram", "technicien": "Rachid"},
        files={"audio": ("note.ogg", b"fake-bytes", "audio/ogg")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["lien_audio"] == "https://drive.google.com/uc?id=abc"
    assert saved["channel"] == "telegram"
    assert saved["message_id"] == "tg:123:456"
    assert saved["kind"] == "audio"
    assert saved["data"] == b"fake-bytes"


def test_drive_failure_never_fails_process(monkeypatch):
    """A Drive outage degrades to the previous behavior: no lien_audio, but
    the report still comes back — the technician's reply must not depend on
    a file upload."""
    logged = []

    async def fake_log(stage, level="info", **kwargs):
        logged.append((stage, level, kwargs.get("message")))

    monkeypatch.setattr(main, "_log", fake_log)
    monkeypatch.setattr(main.logs, "save_media", lambda *a, **k: 1)
    monkeypatch.setattr(
        main.drive, "upload_audio", lambda *a, **k: (_ for _ in ()).throw(
            main.drive.DriveError("quota exceeded"))
    )
    monkeypatch.setattr(main, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(
        main.extraction, "extract_report_with_model",
        lambda t, profile=None: (REPORT, "test/stub"),
    )
    r = client.post(
        "/process",
        files={"audio": ("note.ogg", b"fake-bytes", "audio/ogg")},
    )
    assert r.status_code == 200
    assert r.json()["lien_audio"] is None
    assert any(stage == "api" and "drive upload failed" in msg for stage, _, msg in logged)


def test_media_archive_failure_never_fails_process(monkeypatch):
    """Same contract for the log store: DB down must not cost the reply."""
    logged = []

    async def fake_log(stage, level="info", **kwargs):
        logged.append((stage, level, kwargs.get("message")))

    def boom(*a, **k):
        raise main.logs.LogStoreError("db down")

    monkeypatch.setattr(main, "_log", fake_log)
    monkeypatch.setattr(main.logs, "save_media", boom)
    monkeypatch.setattr(main, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(
        main.extraction, "extract_report_with_model",
        lambda t, profile=None: (REPORT, "test/stub"),
    )
    r = client.post(
        "/process",
        files={"audio": ("note.ogg", b"fake-bytes", "audio/ogg")},
    )
    assert r.status_code == 200
    assert any(stage == "api" and "media archive failed" in msg for stage, _, msg in logged)


def test_text_archived_to_chat(monkeypatch):
    saved = {}

    def fake_save(channel, external_id, message_id, text):
        saved.update(channel=channel, message_id=message_id, text=text)

    monkeypatch.setattr(main.logs, "save_message", fake_save)
    monkeypatch.setattr(
        main.extraction, "extract_report_with_model",
        lambda t, profile=None: (REPORT, "test/stub"),
    )
    r = client.post(
        "/process",
        data={"text": "Installation de 150m de goulotte", "message_id": "wa:xyz"},
    )
    assert r.status_code == 200
    assert saved["message_id"] == "wa:xyz"
    assert "150m de goulotte" in saved["text"]


def test_image_archived(monkeypatch):
    saved = {}

    def fake_save(channel, external_id, message_id, kind, mime_type, data):
        saved.update(kind=kind, mime_type=mime_type, data=data, message_id=message_id)

    monkeypatch.setattr(main.logs, "save_media", fake_save)
    monkeypatch.setattr(
        main.extraction, "extract_report_from_image",
        lambda blob, mime, profile=None, caption=None: (REPORT, "gemini/test"),
    )
    r = client.post(
        "/process",
        data={"message_id": "tg:7:8"},
        files={"image": ("note.jpg", b"\xff\xd8fake", "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    assert saved["kind"] == "image"
    assert saved["mime_type"] == "image/jpeg"
    assert saved["message_id"] == "tg:7:8"


# ── archive read endpoints ─────────────────────────────────────────────────

def test_list_media(monkeypatch):
    monkeypatch.setattr(
        main.logs, "list_media",
        lambda limit: [{"id": 1, "kind": "audio", "mime_type": "audio/ogg", "size_bytes": 10}],
    )
    r = client.get("/media")
    assert r.status_code == 200
    assert r.json()["media"][0]["id"] == 1


def test_get_media_file(monkeypatch):
    monkeypatch.setattr(
        main.logs, "get_media",
        lambda mid: {"id": mid, "data": b"blob", "mime_type": "audio/ogg"},
    )
    r = client.get("/media/3/file")
    assert r.status_code == 200
    assert r.content == b"blob"
    assert r.headers["content-type"] == "audio/ogg"


def test_get_media_file_404(monkeypatch):
    monkeypatch.setattr(main.logs, "get_media", lambda mid: None)
    assert client.get("/media/99/file").status_code == 404


def test_list_messages(monkeypatch):
    monkeypatch.setattr(
        main.logs, "list_messages",
        lambda limit, channel=None, search=None: [{"id": 1, "text": "salam"}],
    )
    r = client.get("/messages?channel=telegram&search=sal")
    assert r.status_code == 200
    assert r.json()["messages"][0]["text"] == "salam"


# ── message → Sheet row link + /modify (TO-DO #13) ─────────────────────────

def test_link_message(monkeypatch):
    monkeypatch.setattr(main.logs, "link_message_row", lambda mid, row, tab=None: True)
    r = client.post("/messages/link", json={"message_id": "tg:1:2", "row": 42})
    assert r.status_code == 200
    assert r.json()["row"] == 42


def test_link_unknown_message_404(monkeypatch):
    monkeypatch.setattr(main.logs, "link_message_row", lambda mid, row, tab=None: False)
    r = client.post("/messages/link", json={"message_id": "tg:1:2", "row": 42})
    assert r.status_code == 404


def test_modify_command_updates_row(monkeypatch):
    monkeypatch.setattr(main.logs, "message_row", lambda mid: (None, 42))
    written = {}

    def fake_update(row, values, tab):
        written["row"] = row
        written["values"] = values
        written["tab"] = tab

    monkeypatch.setattr(main.sheets, "update_report_fields", fake_update)
    r = client.post(
        "/modify-command",
        json={"message_id": "tg:1:2", "action": "modify",
              "fields": {"chantier": "Tour Yasmine"}},
    )
    assert r.status_code == 200
    assert written["row"] == 42
    assert written["values"]["chantier"] == "Tour Yasmine"
    assert written["tab"] == "Rapports"  # legacy link without a tab


def test_modify_on_journal_tab_targets_that_tab(monkeypatch):
    """A /modify reply after a journal write must edit the journal row, not the
    flat Rapports feed — the tab from the link decides where the edit lands."""
    monkeypatch.setattr(main.logs, "message_row", lambda mid: ("Siège Casablanca", 5))
    written = {}

    def fake_update(row, values, tab):
        written["row"] = row
        written["tab"] = tab

    monkeypatch.setattr(main.sheets, "update_report_fields", fake_update)
    r = client.post(
        "/modify-command",
        json={"message_id": "tg:1:2", "action": "modify",
              "fields": {"remarques": "corrigé"}},
    )
    assert r.status_code == 200
    assert written["row"] == 5
    assert written["tab"] == "Siège Casablanca"


def test_supprimer_clears_row_and_unlinks(monkeypatch):
    monkeypatch.setattr(main.logs, "message_row", lambda mid: (None, 7))
    cleared = []
    unlinked = []

    def fake_clear(row, tab):
        cleared.append((row, tab))

    def fake_unlink(mid, row):
        unlinked.append((mid, row))

    monkeypatch.setattr(main.sheets, "clear_row", fake_clear)
    monkeypatch.setattr(main.logs, "link_message_row", fake_unlink)
    r = client.post(
        "/modify-command", json={"message_id": "tg:1:2", "action": "supprimer"}
    )
    assert r.status_code == 200
    assert cleared == [(7, "Rapports")]
    assert unlinked == [("tg:1:2", None)]


def test_modify_unknown_message_404(monkeypatch):
    monkeypatch.setattr(main.logs, "message_row", lambda mid: None)
    r = client.post(
        "/modify-command",
        json={"message_id": "tg:1:2", "action": "modify", "fields": {"chantier": "x"}},
    )
    assert r.status_code == 404


def test_modify_without_fields_422(monkeypatch):
    monkeypatch.setattr(main.logs, "message_row", lambda mid: (None, 1))
    r = client.post(
        "/modify-command", json={"message_id": "tg:1:2", "action": "modify"}
    )
    assert r.status_code == 422


# ── sheets.py row-number contract (used by drain + /modify) ────────────────

HEADERS = ["date", "heure", "canal", "technicien", "chantier", "goulottes_m", "lien_audio", "flag_review"]


def _fake_service(updated_range="Rapports!A17:Q17"):
    class _GetResp:
        def execute(self, **kwargs):
            return {"values": [HEADERS]}

    class Values:
        def __init__(self, svc):
            self._svc = svc
            self._get = _GetResp()

        def get(self, spreadsheetId=None, range=None):
            return self._get

        def append(self, spreadsheetId=None, range=None, valueInputOption=None,
                   insertDataOption=None, body=None):
            self._svc.appended = body
            return _Resp({"updates": {"updatedRange": updated_range}})

        def batchUpdate(self, spreadsheetId=None, body=None):
            self._svc.batched = body
            return _Resp({})

        def update(self, **kwargs):
            return _Resp({})

        def clear(self, spreadsheetId=None, range=None, body=None):
            self._svc.cleared = range
            return _Resp({})

    class Spreadsheets:
        def __init__(self, svc):
            self.values = lambda: Values(svc)

    class Svc:
        spreadsheets = lambda self: Spreadsheets(self)
        appended = batched = cleared = None

    class _Resp:
        def __init__(self, body):
            self._body = body

        def execute(self, **kwargs):
            return self._body

    return Svc()


def test_append_report_returns_row_number(monkeypatch):
    """The drain links a message to its Sheet row through this return value."""
    monkeypatch.setattr(main.sheets, "_service", _fake_service)
    row = main.sheets.append_report({"chantier": "Tour Atlas", "lien_audio": "x"})
    assert row == 17


def test_update_report_fields_places_cells_by_header(monkeypatch):
    """Batch write resolves columns from the header row, like the single-cell
    variant — a reordered Sheet column must move the value with it."""
    svc = _fake_service()
    monkeypatch.setattr(main.sheets, "_service", lambda: svc)
    main.sheets.update_report_fields(5, {"chantier": "Tour Yasmine", "goulottes_m": "200"})
    ranges = {d["range"] for d in svc.batched["data"]}
    assert "Rapports!E5" in ranges  # chantier is column E in HEADERS
    assert "Rapports!F5" in ranges


def test_clear_row_empties_header_width(monkeypatch):
    svc = _fake_service()
    monkeypatch.setattr(main.sheets, "_service", lambda: svc)
    main.sheets.clear_row(9)
    assert svc.cleared == "Rapports!A9:H9"  # 8 columns in HEADERS
