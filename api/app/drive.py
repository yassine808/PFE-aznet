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
from typing import Optional

from app.config import settings


class DriveError(RuntimeError):
    pass


# Same transient-throttle backoff as sheets.py: this runs on the /process path
# and a 429 must not silently lose the durable audio link.
_RETRIES = 3


def _service():
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


def upload_audio(filename: str, mime_type: str, data: bytes) -> str:
    """Upload one voice note, publish it by link, return the download URL.

    The direct-download form (`/uc?export=download&id=`) rather than the
    viewer page: the Sheet links should download, not open an editor.
    """
    from googleapiclient.http import MediaIoBaseUpload

    svc = _service()
    try:
        body = {"name": filename}
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
