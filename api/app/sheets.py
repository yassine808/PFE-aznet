"""Google Sheets read/write for the manager dashboard.

Sheets stays the single source of truth (PLAN.md assumption 3): the dashboard
reads rows through here and manual corrections write back to the same cells.
Google client is lazy-imported so tests run without credentials.

Two caches live here, both with the same rule: only successful results are
cached, and every write path invalidates the read cache, so a correction is
visible to the next poll instead of 30 seconds later.

- `_service`: the googleapiclient service is expensive to build (credentials
  + discovery document, downloaded on every call when cache_discovery=False,
  which is the default here). One per process, like the prompt loader.
- `read_reports`: the dashboard polls /reports on an interval and n8n reads
  it on every message; a 30 s TTL turns ~1 s Google round trips into
  in-memory reads without ever serving stale edits.
"""
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from app.config import settings

RAPPORTS_TAB = "Rapports"

# Google's free tier throttles transiently; the client's own exponential
# backoff (num_retries) absorbs that without a row lost to a 429.
_RETRIES = 3

REPORTS_TTL_SECONDS = 30.0
_reports_cache: Optional[List[dict]] = None
_reports_cached_at: float = 0.0

# The header row, cached separately. Every write path resolves its columns by
# name, which cost a second Google call per write — and one per parked row on
# the retry drain. The header changes about as often as the schema does, and
# invalidate_reports() clears it, so a column rename still lands immediately.
HEADERS_TTL_SECONDS = 300.0
_headers_cache: Optional[List[str]] = None
_headers_cached_at: float = 0.0


class SheetsError(RuntimeError):
    pass


def _build_service():
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


@lru_cache(maxsize=1)
def _cached_service():
    """One service per process: building it re-downloads the discovery
    document, which costs ~hundreds of ms on every call otherwise. Exceptions
    are never cached, so a transient Google failure retries on the next call."""
    return _build_service()


def _service():
    return _cached_service()


def read_reports() -> List[dict]:
    """All rows of the Rapports tab as dicts, plus their 1-based sheet row number.

    TTL-cached: this is the dashboard's poll endpoint and n8n's per-message
    /rapport, so the same ~1 s Google call must not be repeated on every poll.
    Write paths call invalidate_reports(), so the cache can never outlive an
    edit.
    """
    now = time.monotonic()
    if _reports_cache is not None and now - _reports_cached_at < REPORTS_TTL_SECONDS:
        # A copy of the list, not the list: callers filter and sort these rows
        # (jobs.send_daily_report, memory.collect), and one in-place reverse
        # would corrupt what every other caller reads for the next 30 seconds.
        # The row dicts themselves are still shared — copying a few hundred
        # references is cheap, deep-copying every cell would not be.
        return list(_reports_cache)
    try:
        resp = (
            _service()
            .spreadsheets()
            .values()
            .get(spreadsheetId=settings.sheet_id, range=_a1(RAPPORTS_TAB))
            .execute(num_retries=_RETRIES)
        )
    except SheetsError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SheetsError(f"sheets read failed: {exc}") from exc
    values = resp.get("values", [])
    if not values:
        rows: List[dict] = []
    else:
        headers = values[0]
        rows = []
        for i, raw in enumerate(values[1:], start=2):  # row 1 = headers
            row = {h: (raw[j] if j < len(raw) else "") for j, h in enumerate(headers)}
            row["_row"] = i
            rows.append(row)
    _set_reports_cache(rows)
    return rows


def _set_reports_cache(rows: List[dict]) -> None:
    global _reports_cache, _reports_cached_at
    _reports_cache = rows
    _reports_cached_at = time.monotonic()


def invalidate_reports() -> None:
    """Drop both caches. Every write path calls this, or the dashboard would
    keep rendering the pre-edit state until the TTL expired."""
    global _reports_cache, _reports_cached_at, _headers_cache, _headers_cached_at
    _reports_cache = None
    _reports_cached_at = 0.0
    _headers_cache = None
    _headers_cached_at = 0.0


def _headers(svc, tab: str = RAPPORTS_TAB) -> List[str]:
    """A tab's header row; TTL-cached for Rapports only.

    Column names are resolved by name on every write so a reordered column
    moves its value with it — but that meant a second Google call per write,
    and the retry drain pays it once per parked row. The header is the one part
    of the sheet that does not change between two requests.

    Journal tabs are created by the API itself with a known header, so their
    row 1 is read live on the rare write that needs it (a /modify reply); the
    cache stays a single global slot for the tab the dashboard reads.
    """
    if tab != RAPPORTS_TAB:
        resp = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=settings.sheet_id, range=_a1(tab, "1:1"))
            .execute(num_retries=_RETRIES)
        )
        return resp.get("values", [[]])[0]
    global _headers_cache, _headers_cached_at
    now = time.monotonic()
    if _headers_cache is not None and now - _headers_cached_at < HEADERS_TTL_SECONDS:
        return list(_headers_cache)
    resp = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=settings.sheet_id, range=_a1(RAPPORTS_TAB, "1:1"))
        .execute(num_retries=_RETRIES)
    )
    headers = resp.get("values", [[]])[0]
    _headers_cache = headers
    _headers_cached_at = now
    return list(headers)


def _grow_columns(svc, tab: str, needed: int) -> None:
    """Widen a tab to at least `needed` columns. No-op when it already is.

    Uses appendDimension rather than an absolute resize, so it can only ever add
    columns — a resize computed from a stale grid size could shrink the tab and
    take real data with it.
    """
    meta = svc.spreadsheets().get(spreadsheetId=settings.sheet_id).execute(num_retries=_RETRIES)
    sheet = next((s for s in meta["sheets"] if s["properties"]["title"] == tab), None)
    if sheet is None:
        raise SheetsError(f"tab {tab!r} not found")
    current = sheet["properties"].get("gridProperties", {}).get("columnCount", 0)
    if current >= needed:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=settings.sheet_id,
        body={"requests": [{"appendDimension": {
            "sheetId": sheet["properties"]["sheetId"],
            "dimension": "COLUMNS",
            "length": needed - current,
        }}]},
    ).execute(num_retries=_RETRIES)


def _extend_headers(svc, names: List[str]) -> None:
    """Append columns to the Rapports header row.

    Called by `append_report` when a value has no column yet. Appends happen
    after the last existing header, never in the middle of the director's
    columns. The header cache dies with the `invalidate_reports()` the write
    already performs, so the next read sees the new layout.
    """
    existing = len(_headers(svc))
    # Grow the grid before writing into it. A tab has a fixed column count, and
    # writing past it is a 400 "exceeds grid limits", not an auto-extend. That
    # turns this function — whose whole job is to make sure a new schema field
    # can never be silently dropped — into the thing that raises: the append
    # fails, the row parks in `failed_writes`, and every retry fails the same
    # way forever. Hit for real on 2026-08-16 adding `motif_flag` to a Rapports
    # tab that was exactly 61 columns wide.
    _grow_columns(svc, RAPPORTS_TAB, existing + len(names))
    start = _col_letter(existing + 1)
    end = _col_letter(existing + len(names))
    svc.spreadsheets().values().update(
        spreadsheetId=settings.sheet_id,
        range=_a1(RAPPORTS_TAB, f"{start}1:{end}1"),
        valueInputOption="USER_ENTERED",
        body={"values": [names]},
    ).execute(num_retries=_RETRIES)


def update_report_field(row: int, field: str, value: Optional[str],
                        tab: str = RAPPORTS_TAB) -> None:
    """Write one cell back (manual correction). Column resolved from the header row."""
    update_report_fields(row, {field: value}, tab)


def update_report_fields(row: int, values: dict, tab: str = RAPPORTS_TAB) -> None:
    """Write several cells of one row in one batch call (the /modify write-back).

    Column resolved from the header row like the single-cell variant, so a
    column reordered in the Sheet moves the value with it. `tab` is where the
    row lives — Rapports for the dashboard editor, a journal tab for a /modify
    reply on a journal-linked message.
    """
    svc = _service()
    try:
        headers = _headers(svc, tab)
        data = []
        for field, value in values.items():
            if field not in headers:
                raise SheetsError(f"unknown column: {field}")
            col = _col_letter(headers.index(field) + 1)
            data.append(
                {
                    "range": _a1(tab, f"{col}{row}"),
                    "values": [[value if value is not None else ""]],
                }
            )
        if not data:
            return
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=settings.sheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": data},
        ).execute(num_retries=_RETRIES)
        invalidate_reports()
    except SheetsError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SheetsError(f"sheets write failed: {exc}") from exc


def clear_row(row: int, tab: str = RAPPORTS_TAB) -> None:
    """Empty every cell of a row (the /supprimer command).

    The row stays in place on purpose: Google has no cheap positional delete
    that would not shift every row number below it, which would invalidate
    every stored message→row link at once. An emptied row keeps its place and
    its row number; the reports the dashboard renders simply stop matching it.
    """
    svc = _service()
    try:
        ncols = max(1, len(_headers(svc, tab)))
        svc.spreadsheets().values().clear(
            spreadsheetId=settings.sheet_id,
            range=_a1(tab, f"A{row}:{_col_letter(ncols)}{row}"),
            body={},
        ).execute(num_retries=_RETRIES)
        invalidate_reports()
    except SheetsError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SheetsError(f"sheets clear failed: {exc}") from exc


def append_report(values: dict) -> Optional[int]:
    """Append one report row to the Rapports tab, returning its row number.

    The journal mirror (`_mirror_rapports`) and the retry drain both file
    through here. Columns not yet in the header row are appended to it first,
    so a new schema field can never be silently dropped. Cells are placed by
    header name, so a column reordered in the Sheet moves the value with it
    instead of silently writing `chantier` into `client`. The returned row
    number is the same positional numbering read_reports uses, which is what
    lets the drain link the message to the row for /modify.
    """
    svc = _service()
    try:
        headers = _headers(svc)
        if not headers:
            raise SheetsError("Rapports tab has no header row")
        missing = [h for h in values if h not in headers]
        if missing:
            # A new schema field arrives with no column to land in: extend the
            # header row first, then write the value. Without this, the mirror
            # would silently drop the first (and every) new field, and a column
            # that appears only after the feature shipped looks like the field
            # never worked.
            _extend_headers(svc, missing)
            headers = headers + missing
        row = [_cell(values.get(h)) for h in headers]
        resp = (
            svc.spreadsheets()
            .values()
            .append(
                spreadsheetId=settings.sheet_id,
                range=_a1(RAPPORTS_TAB),
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [row]},
            )
            .execute(num_retries=_RETRIES)
        )
        # The appended row changes what the dashboard renders, so the read
        # cache dies here. The drain itself re-reads through the TTL window —
        # which is fine, because this very row is what it just wrote.
        invalidate_reports()
        return _row_from_range(resp.get("updates", {}).get("updatedRange"))
    except SheetsError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SheetsError(f"sheets append failed: {exc}") from exc

# --- journal tabs, one per chantier --------------------------------------
#
# The director keeps one tab per site and reads them side by side, so the
# pipeline writes into that shape rather than a flat table with a filter
# column. Tabs are created on demand: adding a chantier in the dashboard must
# not require anyone to open Google Sheets first.


def read_tab(tab: str) -> List[dict]:
    """Rows of an arbitrary tab as dicts, with their 1-based row number.

    Uncached, unlike read_reports: journal reads happen once per incoming
    message (to find the row to merge into), not on a dashboard poll, and a
    stale hit here would merge into the wrong row.
    """
    try:
        resp = (
            _service()
            .spreadsheets()
            .values()
            .get(spreadsheetId=settings.sheet_id, range=_a1(tab))
            .execute(num_retries=_RETRIES)
        )
    except SheetsError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SheetsError(f"sheets read failed ({tab}): {exc}") from exc
    values = resp.get("values", [])
    if not values:
        return []
    headers = values[0]
    rows = []
    for i, raw in enumerate(values[1:], start=2):
        row = {h: (raw[j] if j < len(raw) else "") for j, h in enumerate(headers)}
        row["_row"] = i
        rows.append(row)
    return rows


def ensure_tab(tab: str, headers: List[str]) -> None:
    """Create the tab with its header row if it is not there yet.

    Idempotent, and it does not touch an existing header row: the director
    renaming a column of his own is a decision, not a drift to correct.
    """
    svc = _service()
    try:
        meta = svc.spreadsheets().get(spreadsheetId=settings.sheet_id).execute(
            num_retries=_RETRIES
        )
        titles = {s["properties"]["title"] for s in meta.get("sheets", [])}
        if tab not in titles:
            svc.spreadsheets().batchUpdate(
                spreadsheetId=settings.sheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
            ).execute(num_retries=_RETRIES)
        existing = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=settings.sheet_id, range=_a1(tab, "1:1"))
            .execute(num_retries=_RETRIES)
            .get("values", [[]])
        )
        if not existing or not existing[0]:
            svc.spreadsheets().values().update(
                spreadsheetId=settings.sheet_id,
                range=_a1(tab, "A1"),
                valueInputOption="RAW",
                body={"values": [list(headers)]},
            ).execute(num_retries=_RETRIES)
            # A tab is styled once, when it is born. Re-styling on every write
            # would spend a batchUpdate per message to change nothing, and
            # would undo a column width the director had widened himself.
            style_tab(tab, list(headers))
    except SheetsError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SheetsError(f"sheets tab setup failed ({tab}): {exc}") from exc


def write_row(tab: str, row: int, values: dict) -> None:
    """Overwrite named cells of an existing row. Columns resolved by name, so a
    reordered sheet moves the value with its header instead of shifting it."""
    svc = _service()
    try:
        headers = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=settings.sheet_id, range=_a1(tab, "1:1"))
            .execute(num_retries=_RETRIES)
            .get("values", [[]])
        )[0]
        data = []
        for field, value in values.items():
            if field not in headers:
                continue
            col = _col_letter(headers.index(field) + 1)
            data.append({"range": _a1(tab, f"{col}{row}"), "values": [[_cell(value)]]})
        if not data:
            return
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=settings.sheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": data},
        ).execute(num_retries=_RETRIES)
    except SheetsError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SheetsError(f"sheets row write failed ({tab}!{row}): {exc}") from exc


def append_row(tab: str, values: dict, headers: List[str]) -> Optional[int]:
    """Append a row to any tab, placing cells by header name."""
    svc = _service()
    try:
        row = [_cell(values.get(h)) for h in headers]
        resp = (
            svc.spreadsheets()
            .values()
            .append(
                spreadsheetId=settings.sheet_id,
                range=_a1(tab),
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
        raise SheetsError(f"sheets append failed ({tab}): {exc}") from exc


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


def _a1(tab: str, ref: str = "") -> str:
    """An A1 range with the tab name quoted.

    Google rejects an unquoted tab name that contains a space — and the
    unrouted fallback tab is literally `Non affecté`, so every write for a
    technician with no chef used to 400 out, park in `failed_writes` and fail
    identically on every drain. Quoting is always valid, so it is applied
    unconditionally rather than only when a space is spotted; an apostrophe
    inside the name is escaped by doubling it, which is the A1 rule.
    """
    quoted = "'" + tab.replace("'", "''") + "'"
    return f"{quoted}!{ref}" if ref else quoted


def _col_letter(n: int) -> str:
    letters = ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


# ── presentation: what the director actually opens ─────────────────────────
#
# The sheet is the deliverable for the one person who never opens the
# dashboard, and unstyled it is 62 columns of identical grey text where the
# header scrolls out of sight on the first row you read. Everything below is
# formatting only — it never writes, moves or reinterprets a value.
#
# Kept deliberately narrow: no conditional formatting rules per column (they
# multiply on every re-run and Google gives no clean way to tell ours from a
# human's), no merged cells (they break every range write in this module).

# Long-form columns get room and wrapping; everything else stays narrow enough
# that a whole day fits on one screen. Matched on the header text, because
# both vocabularies (journal and Rapports) name the same things differently.
_WIDE_COLUMNS = (
    "résumé", "resume", "rapport", "remarques", "observations", "besoins",
    "prochaines étapes", "prochaines_etapes", "ordre du jour", "motif",
    "autres", "lien", "audio", "equipe", "équipe",
)
_NARROW_COLUMNS = ("date", "heure", "jh", "flag", "canal", "role", "taux")

_HEADER_BG = {"red": 0.12, "green": 0.16, "blue": 0.22}
_BAND_BG = {"red": 0.96, "green": 0.97, "blue": 0.98}


def _sheet_id(svc, tab: str) -> Optional[int]:
    meta = svc.spreadsheets().get(spreadsheetId=settings.sheet_id).execute(
        num_retries=_RETRIES
    )
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == tab:
            return s["properties"]["sheetId"]
    return None


def _width_for(header: str) -> int:
    h = (header or "").strip().lower()
    if any(k in h for k in _WIDE_COLUMNS):
        return 320
    if any(h.startswith(k) for k in _NARROW_COLUMNS):
        return 90
    return 150


def style_tab(tab: str, headers: Optional[List[str]] = None) -> None:
    """Make one tab readable: frozen bold header, column widths, banding.

    Idempotent by construction — every request here *sets* a property rather
    than adding one, except the banding, which is added only when the tab has
    none. Re-running it on a styled tab changes nothing.

    Never raises into a caller: this is presentation. A report that files
    correctly into an ugly sheet is a working pipeline; a report lost because
    the header could not be tinted is not.
    """
    try:
        svc = _service()
        sid = _sheet_id(svc, tab)
        if sid is None:
            return
        if headers is None:
            headers = _headers(svc, tab)
        cols = max(1, len(headers))

        requests: List[dict] = [
            # The header stays on screen. Without this, reading row 40 means
            # counting columns by hand to know what a number is.
            {"updateSheetProperties": {
                "properties": {"sheetId": sid,
                               "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 2}},
                "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}},
            {"repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": _HEADER_BG,
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "wrapStrategy": "WRAP",
                    "textFormat": {"bold": True, "fontSize": 10,
                                   "foregroundColor": {"red": 1, "green": 1, "blue": 1}}}},
                "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,"
                          "verticalAlignment,wrapStrategy,textFormat)"}},
            {"updateDimensionProperties": {
                "range": {"sheetId": sid, "dimension": "ROWS",
                          "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 46}, "fields": "pixelSize"}},
            # Body: wrapped and top-aligned. A 300-character transcript in a
            # clipped cell reads as an empty cell with a stray word in it.
            {"repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 1},
                "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP",
                                               "verticalAlignment": "TOP"}},
                "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"}},
        ]
        for i, name in enumerate(headers[:cols]):
            requests.append({"updateDimensionProperties": {
                "range": {"sheetId": sid, "dimension": "COLUMNS",
                          "startIndex": i, "endIndex": i + 1},
                "properties": {"pixelSize": _width_for(name)}, "fields": "pixelSize"}})

        meta = svc.spreadsheets().get(spreadsheetId=settings.sheet_id).execute(
            num_retries=_RETRIES
        )
        banded = any(
            b.get("range", {}).get("sheetId") == sid
            for s in meta.get("sheets", []) for b in s.get("bandedRanges", [])
        )
        if not banded:
            # Alternating rows, added once. Banding is the one request here
            # that appends rather than sets, so a second copy would stack.
            requests.append({"addBanding": {"bandedRange": {
                "range": {"sheetId": sid, "startRowIndex": 0},
                "rowProperties": {
                    "headerColor": _HEADER_BG,
                    "firstBandColor": {"red": 1, "green": 1, "blue": 1},
                    "secondBandColor": _BAND_BG}}}})

        svc.spreadsheets().batchUpdate(
            spreadsheetId=settings.sheet_id, body={"requests": requests},
        ).execute(num_retries=_RETRIES)
    except Exception as exc:  # noqa: BLE001 — presentation is never fatal
        print(f"[sheets] style_tab({tab}) skipped: {type(exc).__name__}: {exc}", flush=True)
