"""The journal tab — one row per (date, technicien), per chantier.

This is the shape of the director's own tracking file, so the column names are
his, in his order and his language. Two rules make it work:

**Accumulation.** A technician reports twice in a day (morning, then afternoon)
more often than not. The second message must land on the same row: quantities
add, prose appends, the working window widens. A second row would double-count
JH and make the totals line at the bottom of his sheet wrong — the one number
he actually reads.

**Stock is reconciled, never assumed.** What is left on site is a physical
count. The arithmetic (last known minus installed) is only a baseline: a
delivery arrives, a cable gets cut by mistake, someone miscounts. So a reported
figure always wins, and when it disagrees with the baseline the row carries a
`stock_ecart` warning with the delta instead of silently picking a number.

Everything here is pure: `merge_rows` and `reconcile_stock` take dicts and
return dicts. The Sheets round trip lives in `sheets.py`.
"""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from app import sheets
from app.schemas import ExtractedReport

# --- the director's columns, in his order --------------------------------
COL_DATE = "Date"
COL_TECHNICIEN = "Technicien"
COL_CHANTIER = "Chantier"

# Filled by the chef in the dashboard: planned before the day, or judged after
# it. A technician never dictates these, so extraction never touches them and
# a merge must never clobber them.
CHEF_COLUMNS = (
    "EQUIPE",
    "HEURE D'ENTREE",
    "HEURE DE SORTIE",
    "JH",
    "ORDRE DU JOUR [Pose de câble cuivre]",
    "ORDRE DU JOUR [Connectiques cuivre]",
    "ORDRE DU JOUR [Test et etiquetage cuivre]",
    "ORDRE DU JOUR [Pose de goulotte]",
    "Taux de réalisation",
)

# Extracted field -> the column it feeds in the sheet.
NUMERIC_COLUMNS = {
    "cables_prepares_m": "Câbles préparés",
    "cables_installes_m": "Câble installé",
    "goulotte_m": "Goulotte installée",
    "prises_connectees": "Connexion des prises informatiques",
    "panneaux_prises_brassees": "Connexion des panneaux de brassage",
    "prises_testees": "Test et étiquetage",
    "fibre_m": "Fibre installée",
    "interconnexions": "Interconnexion installée",
    "connexions_optiques_brins": "Connexion optique",
}

LIST_COLUMNS = {
    "etages": "ETAGE",
    "ailes": "AILE",
    "locaux_techniques": "LOCAL TECHNIQUE",
}

# Stock columns and the installed quantity that draws them down.
STOCK_COLUMNS = {
    "stock_cable_m": ("Reste du câble (Stock)", "cables_installes_m"),
    "stock_goulotte_m": ("Reste de la goulotte (Stock)", "goulotte_m"),
    "stock_fibre_m": ("Reste du Fibre optique (Stock)", "fibre_m"),
}

TEXT_COLUMNS = {"remarques": "Remarques"}

# Pipeline metadata, kept to the right of the director's columns so his part of
# the sheet reads exactly like the file he already knows.
COL_RAPPORT = "Rapport complet"
COL_RESUME = "Résumé"
COL_CANAL = "Canal"
COL_LIEN_AUDIO = "Lien audio"
COL_FLAG = "Flag review"
COL_CORRELATION = "Correlation id"

HEADERS: Tuple[str, ...] = (
    (COL_DATE, COL_TECHNICIEN, COL_CHANTIER)
    + CHEF_COLUMNS
    + tuple(NUMERIC_COLUMNS.values())
    + tuple(LIST_COLUMNS.values())
    + tuple(col for col, _ in STOCK_COLUMNS.values())
    + tuple(TEXT_COLUMNS.values())
    + (COL_RESUME, COL_RAPPORT, COL_CANAL, COL_LIEN_AUDIO, COL_FLAG, COL_CORRELATION)
)


def _num(value) -> Optional[float]:
    """A sheet cell back to a number, or None. Cells are strings and humans
    type '2274 m' — a value we cannot read is None, never 0: zero is a claim."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace(",", ".").replace(" ", " ").strip()
    kept = "".join(c for c in cleaned if c.isdigit() or c in ".-")
    try:
        return float(kept) if kept not in ("", "-", ".", "-.") else None
    except ValueError:
        return None


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return ""
    return str(int(value)) if float(value).is_integer() else str(value)


def reconcile_stock(
    report: ExtractedReport, previous: Optional[Dict[str, str]] = None
) -> Tuple[Dict[str, str], List[str]]:
    """Stock cells for this row, plus any discrepancy warnings.

    Baseline = last known stock on this chantier minus what was installed
    today. Reported value wins and becomes the new truth; a gap between the two
    is surfaced, not resolved — only a human knows whether it was a delivery or
    a loss. With no baseline and nothing reported, the cell stays empty rather
    than inventing a starting stock.
    """
    previous = previous or {}
    cells: Dict[str, str] = {}
    warnings: List[str] = []

    for field, (column, consumed_field) in STOCK_COLUMNS.items():
        reported = getattr(report, field)
        last = _num(previous.get(column))
        used = getattr(report, consumed_field)
        baseline = None
        if last is not None:
            baseline = max(0.0, last - float(used or 0))

        if reported is None:
            if baseline is not None:
                cells[column] = _fmt(baseline)
            continue

        cells[column] = _fmt(float(reported))
        if baseline is not None and abs(float(reported) - baseline) >= 1:
            warnings.append(
                "stock_ecart:%s:%s" % (column, _fmt(float(reported) - baseline))
            )
    return cells, warnings


def report_cells(report: ExtractedReport) -> Dict[str, str]:
    """The extracted part of a row — everything a voice note can fill.

    Stock is not here: it needs the previous row, so it comes from
    `reconcile_stock`.
    """
    cells: Dict[str, str] = {}
    for field, column in NUMERIC_COLUMNS.items():
        value = getattr(report, field)
        if value is not None:
            cells[column] = _fmt(float(value))
    for field, column in LIST_COLUMNS.items():
        values = getattr(report, field)
        if values:
            cells[column] = ", ".join(values)
    for field, column in TEXT_COLUMNS.items():
        value = getattr(report, field)
        if value:
            cells[column] = value.strip()
    return cells


def merge_rows(existing: Dict[str, str], incoming: Dict[str, str]) -> Dict[str, str]:
    """Fold a second report of the day into the row already on the sheet.

    Quantities add. Locations union (order kept: it reads as a route through
    the building). Prose appends. Stock is a level, not a flow, so the newer
    reading replaces the older one. Chef columns are never touched — the
    dashboard owns them, and a merge that overwrote EQUIPE would silently undo
    a human's edit.
    """
    merged = dict(existing)
    numeric_cols = set(NUMERIC_COLUMNS.values())
    list_cols = set(LIST_COLUMNS.values())
    stock_cols = {col for col, _ in STOCK_COLUMNS.values()}

    for column, value in incoming.items():
        if column in CHEF_COLUMNS:
            continue
        old = merged.get(column, "")
        if not str(old).strip():
            merged[column] = value
        elif column in numeric_cols:
            merged[column] = _fmt((_num(old) or 0) + (_num(value) or 0))
        elif column in list_cols:
            seen = [p.strip() for p in str(old).split(",") if p.strip()]
            for part in (p.strip() for p in str(value).split(",")):
                if part and part not in seen:
                    seen.append(part)
            merged[column] = ", ".join(seen)
        elif column in stock_cols:
            merged[column] = value  # a level: the latest reading is the truth
        elif str(value).strip() and str(value).strip() != str(old).strip():
            merged[column] = "%s\n%s" % (str(old).rstrip(), str(value).strip())
    return merged


# --- the Sheets round trip -----------------------------------------------


def _norm_date(value) -> Optional[str]:
    """Any of the forms a date takes on the way through, as `YYYY-MM-DD`.

    We write ISO; Google hands back `05/08/2026` once the column is formatted
    as a date, and the director's own file stores serials (`46174`). All three
    have to match the same day, or a second report would open a second row.
    Unrecognized input returns None rather than a guess — an unmatched row
    appends, which is visible; a wrongly matched row merges, which is not.
    """
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    if text.isdigit() and 20000 <= int(text) <= 90000:
        # Excel/Sheets serial: day 1 is 1899-12-31 under their 1900 leap bug.
        return (date(1899, 12, 30) + timedelta(days=int(text))).strftime("%Y-%m-%d")
    return None


def _same_day(cell, when) -> bool:
    left, right = _norm_date(cell), _norm_date(when)
    return left is not None and left == right


def find_row(tab: str, date: str, technicien: str) -> Tuple[Optional[int], Dict[str, str]]:
    """Today's row for this technician on this chantier, if it exists."""
    for row in sheets.read_tab(tab):
        if _same_day(row.get(COL_DATE, ""), date) and \
                str(row.get(COL_TECHNICIEN, "")).strip().lower() == technicien.strip().lower():
            number = row.pop("_row")
            return number, row
    return None, {}


def write_report(
    tab: str,
    date: str,
    technicien: str,
    chantier: str,
    report: ExtractedReport,
    metadata: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[int], List[str]]:
    """Put one report on the journal tab, merging if the day already has a row.

    Returns the row number and any warnings raised while reconciling stock.
    The tab is created on demand, so a chantier added in the dashboard works on
    its first message rather than after someone opens Google Sheets.
    """
    sheets.ensure_tab(tab, list(HEADERS))
    existing_row, existing = find_row(tab, date, technicien)

    # Stock draws down from the last known level on this chantier — the
    # technician's own previous row if there is one, else the last row anyone
    # wrote. Stock is site-wide: two technicians cut from the same reel.
    baseline = existing or _last_stock(tab)
    stock_cells, warnings = reconcile_stock(report, baseline)

    cells = report_cells(report)
    cells.update(stock_cells)
    cells.update(metadata or {})
    cells[COL_DATE] = date
    cells[COL_TECHNICIEN] = technicien
    cells[COL_CHANTIER] = chantier

    if existing_row is None:
        return sheets.append_row(tab, cells, list(HEADERS)), warnings
    merged = merge_rows(existing, cells)
    sheets.write_row(tab, existing_row, merged)
    return existing_row, warnings


def _last_stock(tab: str) -> Dict[str, str]:
    """Last non-empty stock reading on the tab, whoever wrote it."""
    out: Dict[str, str] = {}
    for row in sheets.read_tab(tab):
        for column, _ in STOCK_COLUMNS.values():
            if str(row.get(column, "")).strip():
                out[column] = row[column]
    return out


# --- the one entry point both the endpoint and the retry drain use --------

UNROUTED_TAB = "Non affecté"

# Warnings that mean "a human should look at this row before it is believed".
REVIEW_WARNINGS = {
    "low_confidence_transcription", "short_transcription", "image_input",
}


def resolve_tab(technicien: str, chantier: Optional[str] = None) -> Tuple[str, str, List[str]]:
    """Which tab this technician's report belongs to.

    Routing lives in the org chart: the chef carries the chantier and their
    technicians inherit it. A technician nobody has assigned lands in a tab
    named `Non affecté` with a warning — visible and fixable, where dropping
    the row or guessing a site would be neither.
    """
    if chantier:
        return chantier, chantier, []
    try:
        from app import logs

        person = logs.person_by_name(technicien)
        if person:
            site = logs.resolve_chantier(person["id"])
            if site:
                return site["nom"], site["sheet_tab"], []
    except Exception:  # noqa: BLE001 - Postgres down must not cost the row
        return UNROUTED_TAB, UNROUTED_TAB, ["chantier_non_resolu"]
    return UNROUTED_TAB, UNROUTED_TAB, ["chantier_non_defini"]


def file_report(payload: Dict) -> Dict:
    """File one report into the right journal tab. Raises SheetsError on failure
    so the caller can park it in the retry queue — never a silent loss."""
    report = payload.get("report")
    if not isinstance(report, ExtractedReport):
        report = ExtractedReport(**(report or {}))
    technicien = str(payload.get("technicien") or "").strip()
    warnings = list(payload.get("warnings") or [])

    chantier, tab, routing_warnings = resolve_tab(technicien, payload.get("chantier"))
    warnings.extend(routing_warnings)

    metadata = {
        COL_RESUME: report.resume,
        COL_RAPPORT: payload.get("rapport_complet"),
        COL_CANAL: payload.get("canal"),
        COL_LIEN_AUDIO: payload.get("lien_audio"),
        COL_CORRELATION: payload.get("correlation_id"),
        COL_FLAG: bool(REVIEW_WARNINGS & set(warnings)),
    }
    row, stock_warnings = write_report(
        tab, payload.get("date") or "", technicien, chantier, report,
        {k: v for k, v in metadata.items() if v not in (None, "")},
    )
    return {
        "row": row,
        "tab": tab,
        "chantier": chantier,
        "warnings": warnings + stock_warnings,
    }


def totals(rows: List[Dict[str, str]]) -> Dict[str, float]:
    """Sum every quantity column across a journal tab, keyed by schema field.

    This is the bordereau's `qte_installée` and nothing else computes it: the
    journal is where a quantity is entered, so a stored total could only drift
    from it. A cell that will not parse is skipped rather than counted as 0 —
    the same rule as everywhere else here, absence is not zero.
    """
    out: Dict[str, float] = {}
    for field, column in NUMERIC_COLUMNS.items():
        running = None
        for row in rows:
            value = _num(row.get(column))
            if value is not None:
                running = (running or 0.0) + value
        if running is not None:
            out[field] = running
    return out
