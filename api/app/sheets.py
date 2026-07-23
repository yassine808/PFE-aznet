"""Google Sheets read/write for the manager dashboard.

Sheets stays the single source of truth (PLAN.md assumption 3): the dashboard
reads rows through here and manual corrections write back to the same cells.
Google client is lazy-imported so tests run without credentials.
"""
from pathlib import Path
from typing import List, Optional

from app.config import settings

RAPPORTS_TAB = "Rapports"


class SheetsError(RuntimeError):
    pass


def _service():
    if not settings.sheet_id:
        raise SheetsError("SHEET_ID not configured")
    key_path = Path(settings.google_service_account_json)
    if not key_path.is_absolute():
        # relative paths anchor to the repo root (same convention as .env resolution)
        key_path = Path(__file__).resolve().parents[2] / key_path
    if not key_path.exists():
        raise SheetsError(f"service account key not found: {key_path}")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        str(key_path), scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def read_reports() -> List[dict]:
    """All rows of the Rapports tab as dicts, plus their 1-based sheet row number."""
    try:
        resp = (
            _service()
            .spreadsheets()
            .values()
            .get(spreadsheetId=settings.sheet_id, range=RAPPORTS_TAB)
            .execute()
        )
    except SheetsError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SheetsError(f"sheets read failed: {exc}") from exc
    values = resp.get("values", [])
    if not values:
        return []
    headers = values[0]
    rows = []
    for i, raw in enumerate(values[1:], start=2):  # row 1 = headers
        row = {h: (raw[j] if j < len(raw) else "") for j, h in enumerate(headers)}
        row["_row"] = i
        rows.append(row)
    return rows


def update_report_field(row: int, field: str, value: Optional[str]) -> None:
    """Write one cell back (manual correction). Column resolved from the header row."""
    svc = _service()
    try:
        header_resp = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=settings.sheet_id, range=f"{RAPPORTS_TAB}!1:1")
            .execute()
        )
        headers = header_resp.get("values", [[]])[0]
        if field not in headers:
            raise SheetsError(f"unknown column: {field}")
        col = _col_letter(headers.index(field) + 1)
        svc.spreadsheets().values().update(
            spreadsheetId=settings.sheet_id,
            range=f"{RAPPORTS_TAB}!{col}{row}",
            valueInputOption="USER_ENTERED",
            body={"values": [[value if value is not None else ""]]},
        ).execute()
    except SheetsError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SheetsError(f"sheets write failed: {exc}") from exc


def _col_letter(n: int) -> str:
    letters = ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters
