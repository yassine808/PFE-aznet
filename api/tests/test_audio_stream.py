"""Playing a voice note back from Drive.

The Inbox pointed `<audio src>` at the raw Drive share link and nothing ever
played: Drive answers that URL with a redirect chain, `Content-Disposition:
attachment` and no Range support, so the media element gets something it cannot
decode and fails without an error. `/audio/{id}` streams the bytes instead, and
answers Range — without it Chrome plays but will not seek, and Safari does not
play at all.
"""
import pytest
from fastapi.testclient import TestClient

import app.main as main

client = TestClient(main.app)

main.app.dependency_overrides[main.auth.require_user] = lambda: {
    "id": 1, "name": "Test", "role": "directeur"
}

BODY = b"OggS" + bytes(range(60))  # 64 bytes, Ogg magic in front


@pytest.fixture(autouse=True)
def fake_drive(monkeypatch):
    monkeypatch.setattr(
        main.drive, "download",
        lambda file_id: (BODY, "application/octet-stream"),
    )
    # No archived copy by default, so the tests above exercise the Drive path.
    monkeypatch.setattr(main.logs, "find_media_by_drive_id", lambda drive_id: None)


def test_full_request_returns_the_bytes_as_audio():
    r = client.get("/audio/abc")
    assert r.status_code == 200
    assert r.content == BODY
    # Drive labels Telegram voice notes octet-stream often enough that trusting
    # the stored type would leave the player with nothing to decode.
    assert r.headers["content-type"].startswith("audio/")
    assert r.headers["accept-ranges"] == "bytes"


def test_range_request_returns_206_and_the_slice():
    r = client.get("/audio/abc", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206
    assert r.content == BODY[10:20]
    assert r.headers["content-range"] == f"bytes 10-19/{len(BODY)}"


def test_open_ended_range_runs_to_the_end():
    r = client.get("/audio/abc", headers={"Range": "bytes=32-"})
    assert r.status_code == 206
    assert r.content == BODY[32:]
    assert r.headers["content-range"] == f"bytes 32-63/{len(BODY)}"


def test_suffix_range_is_the_last_n_bytes_not_an_offset():
    """`bytes=-8` means the final eight bytes. Read as an offset it would
    return the whole tail from byte 8 and the player would decode garbage."""
    r = client.get("/audio/abc", headers={"Range": "bytes=-8"})
    assert r.status_code == 206
    assert r.content == BODY[-8:]


def test_range_past_the_end_is_416_with_the_real_length():
    """A 416 that does not advertise the length makes players retry forever."""
    r = client.get("/audio/abc", headers={"Range": "bytes=500-"})
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{len(BODY)}"


def test_drive_failure_is_a_502(monkeypatch):
    def boom(file_id):
        raise main.drive.DriveError("no such file")

    monkeypatch.setattr(main.drive, "download", boom)
    assert client.get("/audio/abc").status_code == 502


def test_the_archived_copy_answers_before_drive(monkeypatch):
    """Postgres first: /process already stored the blob, so playing it back
    must not depend on Drive being reachable or the file still existing."""
    def exploding_drive(file_id):
        raise AssertionError("Drive must not be called when the blob is archived")

    monkeypatch.setattr(main.drive, "download", exploding_drive)
    monkeypatch.setattr(
        main.logs, "find_media_by_drive_id",
        lambda drive_id: {"data": BODY, "mime_type": "audio/ogg"},
    )
    r = client.get("/audio/abc")
    assert r.status_code == 200
    assert r.content == BODY


def test_a_log_store_outage_falls_back_to_drive(monkeypatch):
    """The lookup is an optimisation, not a dependency — losing Postgres must
    not also lose playback for rows that have a Drive copy."""
    def boom(drive_id):
        raise main.logs.LogStoreError("no db")

    monkeypatch.setattr(main.logs, "find_media_by_drive_id", boom)
    monkeypatch.setattr(main.logs, "write_safe", lambda *a, **k: None)
    r = client.get("/audio/abc")
    assert r.status_code == 200
    assert r.content == BODY


def test_media_file_route_sniffs_the_type_and_answers_range(monkeypatch):
    """The archive route had the same two silent killers: it handed back the
    stored octet-stream type and no Range header."""
    main.app.dependency_overrides[main.auth.require_human] = lambda: {
        "id": 1, "name": "Test", "role": "directeur"
    }
    monkeypatch.setattr(
        main.logs, "get_media",
        lambda media_id: {"id": media_id, "data": BODY, "mime_type": "application/octet-stream"},
    )
    r = client.get("/media/3/file")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/ogg")
    assert r.headers["accept-ranges"] == "bytes"

    ranged = client.get("/media/3/file", headers={"Range": "bytes=0-3"})
    assert ranged.status_code == 206
    assert ranged.content == b"OggS"
    main.app.dependency_overrides.pop(main.auth.require_human, None)
