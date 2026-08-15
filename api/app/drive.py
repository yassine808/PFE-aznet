"""Google Drive upload — durable audio links for the Sheet.

Telegram file_ids and WhatsApp media ids are tickets, not URLs: Meta's media
URLs expire within minutes, so a `lien_audio` holding the id dies with the
chat. This module uploads the voice note to the service account's Drive and
publishes it with an anyone-with-link reader permission, so the Sheet row
keeps a URL that outlives the message.

Same service account as the Sheets reads (GOOGLE_SERVICE_ACCOUNT_JSON), so
there is no second credential to mint or rotate; the Drive API has to be
enabled on the Google Cloud project. Uploads are best-effort on the /process
path: a Drive outage must never cost a technician their summary, so callers
catch DriveError and fall back to the channel's own file id.

The `drive.file` scope is enough: files this account creates belong to it,
and the reader permission is granted on its own file.
"""
import io
import re
from functools import lru_cache
from typing import Any, Dict, Optional

from app.config import settings


class DriveError(RuntimeError):
    pass


# Same transient-throttle backoff as sheets.py: this runs on the /process path
# and a 429 must not silently lose the durable audio link.
_RETRIES = 3


def _build_service():
    if not settings.google_service_account_json:
        raise DriveError("GOOGLE_SERVICE_ACCOUNT_JSON not configured")
    from pathlib import Path

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    key_path = Path(settings.google_service_account_json)
    if not key_path.is_absolute():
        # relative paths anchor to the repo root (same convention as .env)
        key_path = Path(__file__).resolve().parents[2] / key_path
    if not key_path.exists():
        raise DriveError(f"service account key not found: {key_path}")
    creds = service_account.Credentials.from_service_account_file(
        str(key_path), scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


@lru_cache(maxsize=1)
def _cached_service():
    """One service per process — building re-downloads the discovery document.
    Same pattern as sheets._cached_service; exceptions are never cached, so a
    transient Google failure simply retries on the next call."""
    return _build_service()


def _service():
    return _cached_service()


def file_id_of(link: str) -> Optional[str]:
    """The file id inside a Drive URL, in either shape Drive hands out.

    Kept here rather than at the two call sites so the API and the dashboard's
    `audioSrc` cannot drift into disagreeing about what a Drive link looks like.
    """
    m = re.search(r"[?&]id=([\w-]+)", link) or re.search(r"/file/d/([\w-]+)", link)
    return m.group(1) if m else None


def download(file_id: str) -> tuple[bytes, str]:
    """One file's bytes and its MIME type, fetched with the service account.

    Exists because a Drive share link is not a media source. `/uc?export=
    download&id=…` answers with a redirect chain to `drive.usercontent…`,
    serves `Content-Disposition: attachment`, throws an HTML interstitial at
    anything it considers large, and does not honour Range — so an `<audio>`
    element pointed at one silently plays nothing, which is exactly what the
    Inbox did. The API streams the bytes itself instead, with a real audio
    content type.

    A side effect worth keeping: reading through the service account means the
    file no longer has to be world-readable for the dashboard to play it.

    ponytail: whole file into memory. A voice note is seconds long — a
    handful of MB at worst. Switch to `MediaIoBaseDownload` chunking if
    something big ever lands in the same folder.
    """
    svc = _service()
    try:
        meta = (
            svc.files()
            .get(fileId=file_id, fields="mimeType")
            .execute(num_retries=_RETRIES)
        )
        data = svc.files().get_media(fileId=file_id).execute(num_retries=_RETRIES)
    except Exception as exc:  # noqa: BLE001 - one error type for callers
        raise DriveError(f"drive download failed: {exc}") from exc
    return data, meta.get("mimeType") or "application/octet-stream"


def upload_audio(filename: str, mime_type: str, data: bytes) -> str:
    """Upload one voice note, publish it by link, return the download URL.

    The direct-download form (`/uc?export=download&id=`) rather than the
    viewer page: the Sheet links should download, not open an editor.
    """
    from googleapiclient.http import MediaIoBaseUpload

    svc = _service()
    try:
        # Annotated because `parents` is a list beside a str value: inferred from
        # the literal alone the dict is Dict[str, str] and the next line is a
        # type error.
        body: Dict[str, Any] = {"name": filename}
        folder_id = settings.google_drive_folder_id
        if folder_id:
            body["parents"] = [folder_id]
        file = (
            svc.files()
            .create(
                body=body,
                media_body=MediaIoBaseUpload(
                    io.BytesIO(data), mimetype=mime_type, resumable=False
                ),
                fields="id",
            )
            .execute(num_retries=_RETRIES)
        )
        svc.permissions().create(
            fileId=file["id"], body={"type": "anyone", "role": "reader"}
        ).execute(num_retries=_RETRIES)
    except Exception as exc:  # noqa: BLE001 - one error type for callers
        raise DriveError(f"drive upload failed: {exc}") from exc
    return f"https://drive.google.com/uc?export=download&id={file['id']}"
