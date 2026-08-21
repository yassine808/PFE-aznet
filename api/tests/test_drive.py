"""Google Drive upload and download (`app/drive.py`).

Offline by construction: `_service` is monkeypatched with a fake that records
the calls, and the one test that exercises `_build_service` stops at the
missing-key and missing-file guards, which is where every real failure this
module has had actually was. `_cached_service` is cleared around every test —
it is an `lru_cache` on a module-level function, so a fake service built in one
test would otherwise be handed to the next.
"""
import types

import pytest

from app import drive


@pytest.fixture(autouse=True)
def _clear_service_cache():
    drive._cached_service.cache_clear()
    yield
    drive._cached_service.cache_clear()


class _Exec:
    """A googleapiclient request stub: `.execute(num_retries=…)` or a raise."""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def execute(self, num_retries=0):
        if self.error is not None:
            raise self.error
        return self.result


class FakeDrive:
    def __init__(self, *, mime: str | None = "audio/ogg", data=b"bytes", error=None):
        self.mime = mime
        self.data = data
        self.error = error
        self.created = {}
        self.permission = {}

    # --- files() -----------------------------------------------------------
    def files(self):
        return self

    def get(self, fileId, fields):
        self.get_args = {"fileId": fileId, "fields": fields}
        return _Exec({"mimeType": self.mime}, self.error)

    def get_media(self, fileId):
        return _Exec(self.data, self.error)

    def create(self, body, media_body, fields):
        self.created = {"body": body, "fields": fields, "media": media_body}
        return _Exec({"id": "FILE1"}, self.error)

    # --- permissions() -----------------------------------------------------
    def permissions(self):
        return types.SimpleNamespace(create=self._permission_create)

    def _permission_create(self, fileId, body):
        self.permission = {"fileId": fileId, "body": body}
        return _Exec({}, self.error)


# --- file_id_of ------------------------------------------------------------

@pytest.mark.parametrize("link,expected", [
    ("https://drive.google.com/uc?export=download&id=AbC-123", "AbC-123"),
    ("https://drive.google.com/file/d/AbC-123/view?usp=sharing", "AbC-123"),
    ("https://drive.google.com/?id=AbC-123", "AbC-123"),
    ("https://example.com/audio.ogg", None),
    ("", None),
])
def test_file_id_of_reads_both_drive_url_shapes(link, expected):
    assert drive.file_id_of(link) == expected


# --- _build_service guards -------------------------------------------------

def test_build_service_needs_a_configured_key(monkeypatch):
    monkeypatch.setattr(drive.settings, "google_service_account_json", "")
    with pytest.raises(drive.DriveError, match="GOOGLE_SERVICE_ACCOUNT_JSON"):
        drive._build_service()


def test_build_service_reports_a_missing_key_file_by_path(monkeypatch, tmp_path):
    """No `sys.modules` fakes here on purpose: the Google client libraries are
    real dependencies of this service, so the imports at the top of
    `_build_service` succeed and the test reaches the file check. Faking them
    replaced the `googleapiclient` package object for the duration of the test,
    which left the later upload tests unable to import `googleapiclient.http`
    when the whole suite ran in one process."""
    missing = tmp_path / "no-such-key.json"
    monkeypatch.setattr(drive.settings, "google_service_account_json", str(missing))
    with pytest.raises(drive.DriveError, match="service account key not found"):
        drive._build_service()


def test_the_service_is_built_once_per_process(monkeypatch):
    built = []
    monkeypatch.setattr(drive, "_build_service", lambda: built.append(1) or "svc")
    assert drive._service() == "svc"
    assert drive._service() == "svc"
    assert built == [1]


# --- download --------------------------------------------------------------

def test_download_returns_the_bytes_and_the_mime_type(monkeypatch):
    fake = FakeDrive(mime="audio/ogg", data=b"opus")
    monkeypatch.setattr(drive, "_service", lambda: fake)
    assert drive.download("FILE1") == (b"opus", "audio/ogg")
    assert fake.get_args == {"fileId": "FILE1", "fields": "mimeType"}


def test_download_defaults_an_unknown_mime_type(monkeypatch):
    """An `<audio>` element needs a content type; a None would serialize into
    the response header as the string "None"."""
    monkeypatch.setattr(drive, "_service", lambda: FakeDrive(mime=None))
    assert drive.download("FILE1")[1] == "application/octet-stream"


def test_download_wraps_any_sdk_failure_in_one_error_type(monkeypatch):
    monkeypatch.setattr(drive, "_service",
                        lambda: FakeDrive(error=RuntimeError("403 forbidden")))
    with pytest.raises(drive.DriveError, match="drive download failed: 403 forbidden"):
        drive.download("FILE1")


# --- upload_audio ----------------------------------------------------------

def test_upload_returns_a_direct_download_url_and_publishes_by_link(monkeypatch):
    fake = FakeDrive()
    monkeypatch.setattr(drive, "_service", lambda: fake)
    monkeypatch.setattr(drive.settings, "google_drive_folder_id", "")

    url = drive.upload_audio("note.ogg", "audio/ogg", b"opus")

    assert url == "https://drive.google.com/uc?export=download&id=FILE1"
    # No folder configured: no `parents`, so the file lands in My Drive.
    assert fake.created["body"] == {"name": "note.ogg"}
    assert fake.permission == {"fileId": "FILE1",
                               "body": {"type": "anyone", "role": "reader"}}


def test_upload_files_into_the_configured_folder(monkeypatch):
    fake = FakeDrive()
    monkeypatch.setattr(drive, "_service", lambda: fake)
    monkeypatch.setattr(drive.settings, "google_drive_folder_id", "FOLDER9")
    drive.upload_audio("note.ogg", "audio/ogg", b"opus")
    assert fake.created["body"]["parents"] == ["FOLDER9"]


def test_upload_wraps_any_sdk_failure_in_one_error_type(monkeypatch):
    monkeypatch.setattr(drive, "_service",
                        lambda: FakeDrive(error=RuntimeError("quota exceeded")))
    with pytest.raises(drive.DriveError, match="drive upload failed: quota exceeded"):
        drive.upload_audio("note.ogg", "audio/ogg", b"opus")
