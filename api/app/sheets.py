"""Google Sheets read/write for the manager dashboard.

Sheets stays the single source of truth (PLAN.md assumption 3): the dashboard
reads rows through here and manual corrections write back to the same cells.
Google client is lazy-imported so tests run without credentials.
"""
import re
from pathlib import Path
from typing import List, Optional

from app.config import settings

RAPPORTS_TAB = "Rapports"

# Google's free tier throttles transiently; the client's own exponential
# backoff (num_retries) absorbs that without a row lost to a 429.
_RETRIES = 3


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
            .execute(num_retries=_RETRIES)
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
    update_report_fields(row, {field: value})


def update_report_fields(row: int, values: dict) -> None:
    """Write several cells of one row in one batch call (the /modify write-back).

    Column resolved from the header row like the single-cell variant, so a
    column reordered in the Sheet moves the value with it.
    """
    svc = _service()
    try:
        header_resp = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=settings.sheet_id, range=f"{RAPPORTS_TAB}!1:1")
            .execute(num_retries=_RETRIES)
        )
        headers = header_resp.get("values", [[]])[0]
        data = []
        for field, value in values.items():
            if field not in headers:
                raise SheetsError(f"unknown column: {field}")
            col = _col_letter(headers.index(field) + 1)
            data.append(
                {
                    "range": f"{RAPPORTS_TAB}!{col}{row}",
                    "values": [[value if value is not None else ""]],
                }
            )
        if not data:
            return
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=settings.sheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": data},
        ).execute(num_retries=_RETRIES)
    except SheetsError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SheetsError(f"sheets write failed: {exc}") from exc


def clear_row(row: int) -> None:
    """Empty every cell of a row (the /supprimer command).

    The row stays in place on purpose: Google has no cheap positional delete
    that would not shift every row number below it, which would invalidate
    every stored message→row link at once. An emptied row keeps its place and
    its row number; the reports the dashboard renders simply stop matching it.
    """
    svc = _service()
    try:
        header_resp = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=settings.sheet_id, range=f"{RAPPORTS_TAB}!1:1")
            .execute(num_retries=_RETRIES)
        )
        ncols = max(1, len(header_resp.get("values", [[]])[0]))
        svc.spreadsheets().values().clear(
            spreadsheetId=settings.sheet_id,
            range=f"{RAPPORTS_TAB}!A{row}:{_col_letter(ncols)}{row}",
            body={},
        ).execute(num_retries=_RETRIES)
    except SheetsError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SheetsError(f"sheets clear failed: {exc}") from exc


def append_report(values: dict) -> Optional[int]:
    """Append one report row to the Rapports tab, returning its row number.

    Used by the retry drain: the happy path still appends from n8n. Cells are
    placed by header name, so a column reordered in the Sheet moves the value
    with it instead of silently writing `chantier` into `client`. The returned
    row number is the same positional numbering read_reports uses, which is
    what lets the drain link the message to the row for /modify.
    """
    svc = _service()
    try:
        header_resp = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=settings.sheet_id, range=f"{RAPPORTS_TAB}!1:1")
            .execute(num_retries=_RETRIES)
        )
        headers = header_resp.get("values", [[]])[0]
        if not headers:
            raise SheetsError("Rapports tab has no header row")
        row = [_cell(values.get(h)) for h in headers]
        resp = (
            svc.spreadsheets()
            .values()
            .append(
                spreadsheetId=settings.sheet_id,
                range=RAPPORTS_TAB,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [row]},
            )
            .execute(num_retries=_RETRIES)
        )
        return _row_from_range(resp.get("updates", {}).get("updatedRange"))
    except SheetsError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SheetsError(f"sheets append failed: {exc}") from exc


def _row_from_range(updated_range: Optional[str]) -> Optional[int]:
    """'Rapports!A15:H15' → 15. Same positional numbering as read_reports."""
    if not updated_range:
        return None
    m = re.search(r"!([A-Z]+)(\d+)", updated_range)
    return int(m.group(2)) if m else None


def _cell(value) -> str:
    """Sheets takes strings. None becomes empty — absence is not zero."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)


def _col_letter(n: int) -> str:
    letters = ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters
