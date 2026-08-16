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

Beyond the director's original columns, the row also carries the blocker block
(`Arrêt (min)` + `MOTIF D'ARRÊT`), material needs (`BESOINS / MATÉRIEL`) and
the next steps (`PROCHAINES ÉTAPES`) — the three things he re-keys from
remarks prose today.

Everything here is pure: `merge_rows` and `reconcile_stock` take dicts and
return dicts. The Sheets round trip lives in `sheets.py`.
"""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

from app import sheets
from app.config import settings
from app.schemas import ARTICLE_FIELDS, ExtractedReport

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
    "temps_arret_min": "Arrêt (min)",
}

# The bordereau articles, appended after the director's own columns so his part
# of the tab keeps the order he knows. They merge like every other numeric
# column — a second message the same day adds — which is what makes the
# bordereau's `qte_installee` sum correct without storing it anywhere.
ARTICLE_COLUMNS = {
    "cordons_brassage_1m_u": "Cordons brassage 1m",
    "cordons_liaison_3m_u": "Cordons liaison 3m",
    "flexible_arme_d16_m": "Flexible armé D16 (ml)",
    "guide_cable_u": "Guide de câble",
    "tiroir_optique_24_u": "Tiroir optique 24",
    "tiroir_optique_12_u": "Tiroir optique 12",
    "pigtail_sc_u": "Pigtail SC",
    "jarretiere_om3_u": "Jarretière OM3",
    "jarretiere_sc_lc_u": "Jarretière SC/LC",
    "jarretiere_lc_lc_u": "Jarretière LC/LC",
    "switch_federateur_u": "Switch fédérateur",
    "switch_acces_u": "Switch d'accès",
    "point_acces_ap_u": "Point d'accès (AP)",
    "module_sfp_plus_u": "Module SFP+",
    "module_sfp_u": "Module SFP",
    "module_sfp_rj45_u": "Module SFP-RJ45",
    "cable_dac_u": "Câble DAC",
    "coffret_12u_u": "Coffret 12U",
    "onduleur_u": "Onduleur",
    "cable_elec_3x2_5_m": "Câble élec 3x2,5 (ml)",
    "fiche_2p_t_u": "Fiche F 2P+T",
    "disjoncteur_2x16a_u": "Disjoncteur 2x16A",
    "bandeau_elec_12p_u": "Bandeau élec 12P",
    "passe_cable_u": "Passe-câble",
    "borne_2_5_u": "Borne 2,5",
}
NUMERIC_COLUMNS.update(ARTICLE_COLUMNS)

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

TEXT_COLUMNS = {
    "remarques": "Remarques",
    "motif_arret": "MOTIF D'ARRÊT",
    "besoins": "BESOINS / MATÉRIEL",
    "prochaines_etapes": "PROCHAINES ÉTAPES",
}

# Column order inside a merge must stay the director's order, so the new
# blocker columns sit at the end of their blocks: quantity totals first, then
# the prose columns — the additions are the ones nothing depends on the
# position of.

# How a column merges, resolved once here rather than on every merged row.
_NUMERIC_COLS = set(NUMERIC_COLUMNS.values())
_LIST_COLS = set(LIST_COLUMNS.values())
_STOCK_COLS = {col for col, _ in STOCK_COLUMNS.values()}

# Pipeline metadata, kept to the right of the director's columns so his part of
# the sheet reads exactly like the file he already knows.
COL_RAPPORT = "Rapport complet"
COL_RESUME = "Résumé"
COL_CANAL = "Canal"
COL_LIEN_AUDIO = "Lien audio"
COL_FLAG = "Flag review"
# Why the flag is set. A bare TRUE told a reader that something was wrong and
# not what, so the cheapest thing to do with a flagged row was believe it.
COL_MOTIF_FLAG = "Motif du flag"
COL_CORRELATION = "Correlation id"
# Which STT engine actually heard this voice note. The chain falls through on
# failure, so the configured order does NOT tell you what ran: a row served by
# `local` means both free tiers were unavailable at that moment. Empty for text
# and photo reports, which never touch STT — blank, never "n/a", because the
# column is a fact about audio and there was none.
COL_STT = "Moteur STT"

HEADERS: Tuple[str, ...] = (
    (COL_DATE, COL_TECHNICIEN, COL_CHANTIER)
    + CHEF_COLUMNS
    + tuple(NUMERIC_COLUMNS.values())
    + tuple(LIST_COLUMNS.values())
    + tuple(col for col, _ in STOCK_COLUMNS.values())
    + tuple(TEXT_COLUMNS.values())
    + (COL_RESUME, COL_RAPPORT, COL_CANAL, COL_STT, COL_LIEN_AUDIO,
       COL_FLAG, COL_MOTIF_FLAG, COL_CORRELATION)
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
    for column, value in incoming.items():
        if column in CHEF_COLUMNS:
            continue
        merged[column] = _merge_cell(column, merged.get(column, ""), value)
    return merged


def _truthy(value) -> bool:
    """Whether a flag cell reads as set, in any of the shapes it arrives in.

    A fresh write hands us a Python bool; the sheet hands the same cell back as
    the string `TRUE`. Both have to mean the same thing or a re-read would
    clear a flag that was set an hour earlier.
    """
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "vrai", "1", "oui", "yes"}


def _union_csv(old, value) -> str:
    """The two comma-separated lists, first-seen order kept, no duplicates."""
    seen = [p.strip() for p in str(old).split(",") if p.strip()]
    for part in (p.strip() for p in str(value).split(",")):
        if part and part not in seen:
            seen.append(part)
    return ", ".join(seen)


def _merge_cell(column: str, old, value) -> str:
    """One cell's new content, by what the column measures."""
    if column == COL_FLAG:
        # A flag is a state, not prose: once any message of the day needs
        # checking the row needs checking. Merging it through the text branch
        # wrote `FALSE\nTrue` into the one column the director filters on —
        # unreadable for exactly the rows that matter. Sheets' own literals,
        # so the cell stays a boolean rather than becoming a string.
        return "TRUE" if (_truthy(old) or _truthy(value)) else "FALSE"
    if column == COL_STT:
        # Which engine answered last, not a transcript of the chain's history.
        return str(value).strip() or str(old)
    if not str(old).strip():
        return value
    if column in _NUMERIC_COLS:
        return _fmt((_num(old) or 0) + (_num(value) or 0))
    if column in _LIST_COLS:
        return _union_csv(old, value)
    if column in _STOCK_COLS:
        return value  # a level: the latest reading is the truth
    if str(value).strip() and str(value).strip() != str(old).strip():
        return "%s\n%s" % (str(old).rstrip(), str(value).strip())
    return old


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


# The same normalizer, under a public name: `/reports/export` has to match a
# period against the Sheet's own date spellings, and reaching into a private
# helper from another module is how a rename becomes an outage somewhere else.
norm_date = _norm_date


def _same_day(cell, when) -> bool:
    left, right = _norm_date(cell), _norm_date(when)
    return left is not None and left == right


def find_row(
    tab: str, date: str, technicien: str, rows: Optional[List[Dict[str, str]]] = None
) -> Tuple[Optional[int], Dict[str, str]]:
    """Today's row for this technician on this chantier, if it exists.

    `rows` lets a caller that already read the tab pass those rows in rather
    than pay a second full-tab round trip for the same data. The match is
    copied before `_row` is stripped, so a shared list is never mutated.
    """
    for row in (sheets.read_tab(tab) if rows is None else rows):
        if _same_day(row.get(COL_DATE, ""), date) and \
                str(row.get(COL_TECHNICIEN, "")).strip().lower() == technicien.strip().lower():
            cells = dict(row)
            return cells.pop("_row"), cells
    return None, {}


def write_report(
    tab: str,
    date: str,
    technicien: str,
    chantier: str,
    report: ExtractedReport,
    metadata: Optional[Dict[str, str]] = None,
    known: Optional[Tuple[Optional[int], Dict[str, str]]] = None,
    rows: Optional[List[Dict[str, str]]] = None,
) -> Tuple[Optional[int], List[str]]:
    """Put one report on the journal tab, merging if the day already has a row.

    Returns the row number and any warnings raised while reconciling stock.
    The tab is created on demand, so a chantier added in the dashboard works on
    its first message rather than after someone opens Google Sheets.
    `known` is find_row's (row, cells) and `rows` the tab it came from, when the
    caller already read it — the retry idempotency check in file_report needs
    the same row, so it ensures, reads once, and hands both down. Supplying
    `rows` therefore also means "the tab is already ensured".
    """
    if rows is None:
        sheets.ensure_tab(tab, list(HEADERS))
        rows = sheets.read_tab(tab)
    if known is None:
        existing_row, existing = find_row(tab, date, technicien, rows)
    else:
        existing_row, existing = known

    # Stock draws down from the last known level on this chantier: the last
    # reading anyone wrote, whoever it was. Stock is site-wide — two
    # technicians cut from the same reel — and the whole-tab scan is at least
    # as fresh as this technician's own row (which is itself part of `rows`),
    # so merging must not resurrect a staler reading when a colleague has
    # written a newer one behind it.
    baseline = _last_stock(tab, rows)
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


def _last_stock(tab: str, rows: Optional[List[Dict[str, str]]] = None) -> Dict[str, str]:
    """Last non-empty stock reading on the tab, whoever wrote it."""
    out: Dict[str, str] = {}
    for row in (sheets.read_tab(tab) if rows is None else rows):
        for column, _ in STOCK_COLUMNS.values():
            if str(row.get(column, "")).strip():
                out[column] = row[column]
    return out


# --- the one entry point both the endpoint and the retry drain use --------

UNROUTED_TAB = "Non affecté"

# Warnings that mean "a human should look at this row before it is believed".
REVIEW_WARNINGS = {
    "low_confidence_transcription", "short_transcription", "image_input",
    # A site nobody has confirmed yet: the row is filed on it, and the director
    # is told to look, because "Extralé" heard once is a new paper otherwise.
    "chantier_cree_non_verifie",
    # Locations read off a photo. See WARNING_LABELS for why this one exists.
    "photo_zones_partielles",
}

# What the flag actually means, in the secretary's language.
#
# The flag column was a bare TRUE, which tells a reader that something is wrong
# and not what — so the cheapest thing to do with a flagged row was believe it
# anyway. Each warning now writes its reason beside it.
#
# `photo_zones_partielles` is the one that came out of a measurement rather than
# a hunch. The 2026-08-16 vision benchmark showed attentional crowding under
# control: the same blue dots on the same corridor are found when they are the
# only marks on the plan and missed by 3 models out of 4 once louder marks are
# added elsewhere in the image. A dropped zone is invisible — it leaves no empty
# cell to notice, only a shorter list — so the row has to say so itself.
WARNING_LABELS = {
    "image_input": "Lu sur une photo",
    "photo_zones_partielles": "Zones lues sur une photo : la liste peut être incomplète",
    "low_confidence_transcription": "Transcription peu sûre",
    "short_transcription": "Transcription très courte",
    "chantier_cree_non_verifie": "Chantier non confirmé",
    "no_report_content": "Aucune donnée exploitable",
    "stock_ecart": "Écart de stock",
}


def flag_reason(warnings) -> str:
    """The flag column's reason, in the order the warnings arrived.

    An unknown warning falls through as its own name rather than being dropped:
    a reason nobody has written a label for is still more use than a blank cell,
    and a silent omission here would hide exactly what this column exists for.
    """
    seen, out = set(), []
    for w in warnings or ():
        key = str(w).split(":")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(WARNING_LABELS.get(key, key))
    return " · ".join(out)


def _sticky_chantier(technicien: str) -> Optional[str]:
    """The site on this technician's most recent report, or None.

    Derived from the Rapports mirror rather than stored on the person: the rows
    already are the record, and a `last_chantier_id` column would be a cache of
    them with nothing to keep it honest. No expiry — a technician silent for a
    month is still on the site they were on, and the reply says the site was
    inherited so a wrong one is visible on the first message.
    """
    name = technicien.strip().lower()
    found = None
    for row in sheets.read_reports():  # append order, so the last match wins
        if str(row.get("technicien", "")).strip().lower() != name:
            continue
        site = str(row.get("chantier", "")).strip()
        if site and site != UNROUTED_TAB:
            found = site
    return found


def resolve_site(
    technicien: str, spoken: Optional[str] = None, create: bool = True
) -> Tuple[str, str, List[str], str]:
    """Which chantier (and tab) this report belongs to, and where that came from.

    Order, decided with the owner 2026-08-15: **the voice wins** — the
    technician standing on the site knows it better than the org chart — then
    the site on their own most recent row, then the org chart, then
    `Non affecté`.

    Sticky deliberately outranks the org chart, which reads backwards until you
    know why: the org chart is only correct while a manager maintains it, and
    the owner's premise for this whole change is that managers will not open the
    dashboard. A stale assignment ahead of a live signal would silently misfile
    a crew that moved, and the "(repris du dernier rapport)" note would almost
    never appear. The org chart keeps the case sticky cannot answer — a
    technician's very first message, where there is no history to inherit.

    A spoken name is never trusted as a tab name. That was this function's
    first branch (`if chantier: return chantier, chantier, []`) and it was safe
    only because nothing ever reached it; the moment the voice fills it, "la
    DGH", "d.g.h" and "DGH" become three tabs, three split bordereaux and a
    totals line scattered across them. So a spoken name is normalized and
    matched against the `chantiers` table, and a genuine no-match creates the
    site marked **unverified** — a real new site works on its first message and
    the director confirms it afterwards.

    `create=False` is the read-only form used on the reply path: it answers the
    same question without writing a row for a name the journal call has not
    committed to yet.

    Returns (nom, tab, warnings, source) where source is one of
    `voix` / `nouveau` / `org` / `repris` / `aucun`.
    """
    try:
        from app import logs

        if spoken and spoken.strip():
            match = logs.find_chantier_by_name(spoken)
            if match:
                return match["nom"], match["sheet_tab"], [], "voix"
            nom = spoken.strip()
            if create:
                site = logs.create_chantier(nom, verifie=False)
                nom, tab = site["nom"], site["sheet_tab"]
            else:
                tab = nom
            return nom, tab, ["chantier_cree_non_verifie"], "nouveau"

        sticky = _sticky_chantier(technicien)
        if sticky:
            # The row carries the name; the tab it belongs to is still the
            # table's business, because nom and sheet_tab can differ.
            match = logs.find_chantier_by_name(sticky)
            nom = match["nom"] if match else sticky
            tab = match["sheet_tab"] if match else sticky
            return nom, tab, ["chantier_repris:%s" % nom], "repris"

        person = logs.person_by_name(technicien)
        if person:
            site = logs.resolve_chantier(person["id"])
            if site:
                return site["nom"], site["sheet_tab"], [], "org"
    except Exception:  # noqa: BLE001 - Postgres or Sheets down must not cost the row
        # Note this also swallows a spoken name: with the table unreachable we
        # cannot tell a known site from a mis-transcription, and writing an
        # unchecked tab is the exact failure this function exists to prevent.
        return UNROUTED_TAB, UNROUTED_TAB, ["chantier_non_resolu"], "aucun"
    return UNROUTED_TAB, UNROUTED_TAB, ["chantier_non_defini"], "aucun"


def resolve_tab(technicien: str, chantier: Optional[str] = None) -> Tuple[str, str, List[str]]:
    """`resolve_site` without the source — the shape the Sheet write needs."""
    nom, tab, warnings, _source = resolve_site(technicien, chantier)
    return nom, tab, warnings


# --- the Rapports mirror ---------------------------------------------------
#
# The dashboard reads the flat Rapports tab, whose columns are the schema the
# journal's tab is not. Every /journal call appends one flat row there — one
# row per message, like the old n8n append — so the two feeds stay in step and
# a drain-retried row gets mirrored too. The mapping is the one place the two
# schemas meet; the old n8n expressions (report.goulottes_m, ...) were that
# mapping and could not be tested, which is why this lives in Python now.

RAPPORTS_COLUMNS = {
    "goulotte_m": "goulottes_m",
    "cables_installes_m": "cables_m",
    "prises_connectees": "bureaux_termines",
    "panneaux_prises_brassees": "panneaux_raccordes",
    "remarques": "observations",
    "temps_arret_min": "arrets_min",
    "motif_arret": "motif_arret",
    "besoins": "besoins",
    "prochaines_etapes": "prochaines_etapes",
    # The bordereau articles keep their schema name in the flat tab: this
    # mapping exists to rename the four columns whose Rapports header predates
    # the 2026-08-05 schema, not to invent a second vocabulary for 25 new
    # fields that never had an old name to preserve.
    **{field: field for field in ARTICLE_FIELDS},
}


def audio_link(payload: Dict) -> Optional[str]:
    """What the Sheet's "Lien audio" cell should hold for this message.

    A Drive URL opens a bare file: no transcript, no summary, no reply, and a
    dependency on a third party to play something we already host in
    `media_files`. So when the dashboard has a public origin the cell points at
    *this* application instead — the inbox, at the message it belongs to, where
    the player sits above the transcript that can be corrected.

    Keyed on `correlation_id`, not the Rapports row number: the row number only
    exists after the append, so using it would mean a second Sheets call to
    rewrite the cell we just wrote. The correlation id is carried end to end by
    the message, is already the join key between n8n's logs and ours, and also
    identifies a message that never became a row at all.

    Falls back to the Drive link when `DASHBOARD_BASE_URL` is unset or the
    message has no correlation id — a relative path in a spreadsheet cell opens
    nothing, and a dead link is worse than one that goes to Drive.
    """
    drive_link = payload.get("lien_audio")
    base = (settings.dashboard_base_url or "").strip().rstrip("/")
    correlation = str(payload.get("correlation_id") or "").strip()
    if not base or not correlation:
        return drive_link
    return f"{base}/#/inbox?msg={quote(correlation, safe='')}"


def _rapports_cells(payload: Dict, chantier: str, warnings: List[str]) -> Dict:
    """The flat Rapports row for one message, keyed by its header names."""
    report = payload.get("report")
    if not isinstance(report, ExtractedReport):
        report = ExtractedReport(**(report or {}))
    cells: Dict = {
        "date": payload.get("date"),
        "heure": payload.get("heure"),
        "canal": payload.get("canal"),
        "technicien": payload.get("technicien"),
        "role": payload.get("role"),
        "chantier": chantier,
        "resume": report.resume,
        "rapport_complet": payload.get("rapport_complet"),
        "confidence": payload.get("confidence"),
        "flag_review": bool(REVIEW_WARNINGS & set(warnings)),
        "motif_flag": flag_reason(warnings),
        "lien_audio": audio_link(payload),
        "STT_model": payload.get("stt_engine"),
        # The key the "Lien audio" address resolves against, and the join with
        # n8n's own logs. Mirrored so the inbox can find one message from a
        # click in the Sheet without a second lookup table.
        "correlation_id": payload.get("correlation_id"),
    }
    for field, column in RAPPORTS_COLUMNS.items():
        value = getattr(report, field)
        if value is not None:
            cells[column] = value
    return cells


def _mirror_rapports(payload: Dict, chantier: str, warnings: List[str]) -> Optional[int]:
    """Append the flat Rapports row for this message; never raises.

    The journal row is the record; the mirror is for the dashboard. When
    Google refuses it, the report itself is not lost — the journal write
    already succeeded — so this logs and moves on instead of failing the
    whole /journal call. Returns the appended row number, or None on
    failure, so /supprimer can clear the mirror row too.
    """
    try:
        return sheets.append_report(_rapports_cells(payload, chantier, warnings))
    except Exception as exc:  # noqa: BLE001 - best-effort by design
        try:
            from app import logs

            logs.write_safe(
                "sheet", "error",
                message=f"rapports mirror failed: {exc}",
                correlation_id=payload.get("correlation_id"),
            )
        except Exception:  # noqa: BLE001 - the mirror must never take the row down
            pass
        return None


def file_report(payload: Dict) -> Dict:
    """File one report into the right journal tab. Raises SheetsError on failure
    so the caller can park it in the retry queue — never a silent loss."""
    report = payload.get("report")
    if not isinstance(report, ExtractedReport):
        report = ExtractedReport(**(report or {}))
    technicien = str(payload.get("technicien") or "").strip()
    warnings = list(payload.get("warnings") or [])

    # The voice wins: what the technician said beats the org chart. `chantier`
    # on the payload stays supported (the drain re-files an already-routed row)
    # and takes precedence over the extraction it was derived from.
    chantier, tab, routing_warnings = resolve_tab(
        technicien, payload.get("chantier") or report.chantier_mentionne
    )
    warnings.extend(routing_warnings)

    # Create the tab before reading it. `read_tab` on a tab Google has never
    # heard of is a 400 ("Unable to parse range"), not an empty list, so the
    # first message to a chantier added in the dashboard used to 502, park in
    # `failed_writes`, and fail identically on every drain thereafter.
    sheets.ensure_tab(tab, list(HEADERS))
    # One read serves all three: the retry idempotency test below, the merge
    # lookup and the stock baseline inside write_report.
    rows = sheets.read_tab(tab)
    known = find_row(tab, str(payload.get("date") or ""), technicien, rows)
    existing_row, existing = known
    correlation = str(payload.get("correlation_id") or "").strip()
    if existing_row is not None and correlation:
        # The row's Correlation cell accumulates every message that touched it
        # (the merge appends with a newline), so membership means "this exact
        # message already landed here" — a retry after a Sheets failure that
        # Google actually committed. Merging again would add the same numbers
        # twice to the totals line, the one number the director reads.
        filed = str(existing.get(COL_CORRELATION, "")).split("\n")
        if correlation in filed:
            # The mirror is the one thing the failed first write lost, so it
            # still runs: exactly one Rapports row per message.
            mirror_row = _mirror_rapports(payload, chantier, warnings)
            return {
                "row": existing_row,
                "tab": tab,
                "chantier": chantier,
                "warnings": warnings,
                "rapports_row": mirror_row,
                "duplicate": True,
            }

    metadata = {
        COL_RESUME: report.resume,
        COL_RAPPORT: payload.get("rapport_complet"),
        COL_CANAL: payload.get("canal"),
        COL_STT: payload.get("stt_engine"),
        COL_LIEN_AUDIO: payload.get("lien_audio"),
        COL_CORRELATION: payload.get("correlation_id"),
        COL_FLAG: "TRUE" if REVIEW_WARNINGS & set(warnings) else "FALSE",
        COL_MOTIF_FLAG: flag_reason(warnings),
    }
    row, stock_warnings = write_report(
        tab, payload.get("date") or "", technicien, chantier, report,
        {k: v for k, v in metadata.items() if v not in (None, "")},
        known, rows,
    )
    warnings = warnings + stock_warnings
    # After the journal write succeeded, so a mirror failure cannot cost the
    # row — but before the reply, because the dashboard shows it.
    mirror_row = _mirror_rapports(payload, chantier, warnings)
    return {
        "row": row,
        "tab": tab,
        "chantier": chantier,
        "warnings": warnings,
        "rapports_row": mirror_row,
        "duplicate": False,
    }


# Summed on a merge (two stops make 130 minutes) but never into the bordereau:
# `Arrêt (min)` is a loss, not an installed quantity, and the one number the
# bordereau answers is how much of the contract is in.
_TOTAL_EXCLUDED = frozenset({"temps_arret_min"})


def totals(rows: List[Dict[str, str]]) -> Dict[str, float]:
    """Sum every quantity column across a journal tab, keyed by schema field.

    This is the bordereau's `qte_installee` and nothing else computes it: the
    journal is where a quantity is entered, so a stored total could only drift
    from it. A cell that will not parse is skipped rather than counted as 0 —
    the same rule as everywhere else here, absence is not zero.
    """
    out: Dict[str, float] = {}
    for field, column in NUMERIC_COLUMNS.items():
        if field in _TOTAL_EXCLUDED:
            continue
        running = None
        for row in rows:
            value = _num(row.get(column))
            if value is not None:
                running = (running or 0.0) + value
        if running is not None:
            out[field] = running
    return out
