"""The journal tab — one row per message, per chantier.

This is the shape of the director's own tracking file, so the column names are
his, in his order and his language. Two rules make it work:

**One row per message, appended, never rewritten.** Until 2026-08-18 a second
report on the same day was folded into the first: quantities added, prose
appended, the working window widened. It kept the tab looking like the
director's file and it destroyed data — a wrong figure in the afternoon note
overwrote a correct one from the morning, in place, leaving nothing to compare
against. A correction now lands on its own line, where deleting the wrong one
does not take the right one with it.

The totals stay correct because nothing reads a single row: `totals()` and the
bordereau's `qte_installee` sum every row on the tab, and `JH` is not among the
columns they sum. `JH` is derived per row from that row's own hours and crew
(`compute_jh`), so it says what that message accounted for rather than what the
day cost; a day is `max` over its rows, never the sum, because two notes
describing one 07:00-20:00 day describe the same thirteen hours twice.

**Stock is reconciled, never assumed.** What is left on site is a physical
count. The arithmetic (last known minus installed) is only a baseline: a
delivery arrives, a cable gets cut by mistake, someone miscounts. So a reported
figure always wins, and when it disagrees with the baseline the row carries a
`stock_ecart` warning with the delta instead of silently picking a number.

Beyond the director's original columns, the row also carries the blocker block
(`Arrêt (min)` + `MOTIF D'ARRÊT`), material needs (`BESOINS / MATÉRIEL`) and
the next steps (`PROCHAINES ÉTAPES`) — the three things he re-keys from
remarks prose today.

Everything here is pure: `reconcile_stock` and `report_cells` take dicts and
return dicts. The Sheets round trip lives in `sheets.py`.
"""
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote

from app import sheets
from app.config import settings
from app.schemas import DATA_FIELDS, ExtractedReport

# --- the director's columns, in his order --------------------------------
COL_DATE = "Date"
COL_TECHNICIEN = "Technicien"
COL_CHANTIER = "Chantier"

# What the voice note now fills that used to be typed by hand. EQUIPE and the
# two hours were `CHEF_COLUMNS` until 2026-08-18, on the premise that "a
# technician never dictates these". The premise was false: they say "entré à
# 7h, sorti à 8h" in the note, the schema had no field for it, and the columns
# stayed empty while the information sat in the transcript, unreachable.
COL_JH = "JH"

DAY_COLUMNS = {
    "heure_entree": "HEURE D'ENTREE",
    "heure_sortie": "HEURE DE SORTIE",
    "equipe": "EQUIPE",
}

# Column order only. Nothing is protected from extraction any more: the
# project's whole point is that the voice note fills the sheet, so a column
# nobody can dictate is a column nobody fills. JH is not dictated either — it
# is computed from the hours and the crew. What is left for a human is what no
# report can state: the ORDRE DU JOUR is planned before the day rather than
# reported after it, and the completion rate is a judgement against that plan.
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
# of the tab keeps the order he knows. They behave like every other numeric
# column: one row per message, and the bordereau's `qte_installee` sums them
# across rows without storing a total anywhere.
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


def report_cells(report: ExtractedReport,
                 limits: Optional[Dict[str, float]] = None) -> Dict[str, str]:
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
    for field, column in DAY_COLUMNS.items():
        value = getattr(report, field, None)
        if value:
            cells[column] = str(value).strip()
    # JH is derived, not dictated: nobody says "three point two five man-days".
    # Written only when both hours were given, so an unknown day stays empty
    # rather than claiming zero work.
    jh = compute_jh(report, limits)
    if jh is not None:
        cells[COL_JH] = _fmt(jh)
    return cells


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
# Public because `stock.py` reads the same cells and must read them the same
# way: "2274 m" is 2274 and an unparseable cell is None, never 0. Two parsers
# over one column is how a stock figure and the journal stop agreeing.
parse_number = _num


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
    rows: Optional[List[Dict[str, str]]] = None,
) -> Tuple[Optional[int], List[str]]:
    """Put one report on the journal tab, merging if the day already has a row.

    Returns the row number and any warnings raised while reconciling stock.
    The tab is created on demand, so a chantier added in the dashboard works on
    its first message rather than after someone opens Google Sheets.
    `rows` is the tab the caller already read — file_report's idempotency scan
    needs it too, so it ensures, reads once, and hands it down. Supplying
    `rows` therefore also means "the tab is already ensured".
    """
    if rows is None:
        sheets.ensure_tab(tab, list(HEADERS))
        rows = sheets.read_tab(tab)

    # Stock draws down from the last known level on this chantier: the last
    # reading anyone wrote, whoever it was. Stock is site-wide — two
    # technicians cut from the same reel — and the whole-tab scan is at least
    # as fresh as this technician's own row (which is itself part of `rows`),
    # so merging must not resurrect a staler reading when a colleague has
    # written a newer one behind it.
    baseline = _last_stock(tab, rows)
    stock_cells, warnings = reconcile_stock(report, baseline)

    cells = report_cells(report, jh_limits())
    cells.update(stock_cells)
    cells.update(metadata or {})
    cells[COL_DATE] = date
    cells[COL_TECHNICIEN] = technicien
    cells[COL_CHANTIER] = chantier

    # One row per message, always appended. Until 2026-08-18 a second report on
    # the same day was folded into the first: quantities added, prose appended.
    # It kept the tab shaped like the director's file, and it destroyed data —
    # a wrong figure in the second note overwrote a correct one in the first,
    # in place, with nothing left to compare against. Corrections now sit on
    # their own line, where a wrong one can be deleted without taking the right
    # one with it, and the totals stay correct because `totals()` and the
    # bordereau sum rows rather than reading one.
    #
    row = sheets.append_row(tab, cells, list(HEADERS))

    # If the day already had a row for this technician, this one adds to it, and
    # the sheet says so: the quantities are formatted +80 rather than 80. Only
    # the display changes -- the cell still holds a number, so the totals line
    # and the bordereau are untouched. The stock columns are deliberately left
    # alone: stock is a level, not a flow, and "+2095 m left" would be a lie.
    follow_up, _ = find_row(tab, date, technicien, rows)
    if row and follow_up is not None:
        first = HEADERS.index(next(iter(NUMERIC_COLUMNS.values())))
        sheets.mark_increment(tab, row, first, first + len(NUMERIC_COLUMNS) - 1)
    return row, warnings


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

# The only columns whose Rapports header predates the 2026-08-05 schema.
# Renaming one orphans every historical row in it, so the old spelling stays
# and the mapping records the difference.
_RAPPORTS_RENAMES = {
    "goulotte_m": "goulottes_m",
    "cables_installes_m": "cables_m",
    "prises_connectees": "bureaux_termines",
    "panneaux_prises_brassees": "panneaux_raccordes",
    "remarques": "observations",
    "temps_arret_min": "arrets_min",
}

# Derived from the schema, not hand-kept: as a hand-kept list this silently
# dropped eight fields for eleven days — `fibre_m`, `prises_testees`,
# `cables_prepares_m`, `interconnexions`, `connexions_optiques_brins`, the
# three location lists and the three stock columns never reached the flat tab,
# so nothing downstream of it (the dashboard, the daily report, the .docx)
# could show fibre or tested sockets at all. A field added to `DATA_FIELDS`
# now reaches the mirror by construction; `sheets.append_report` creates the
# column on first use, so no migration is needed either.
RAPPORTS_COLUMNS = {field: _RAPPORTS_RENAMES.get(field, field) for field in DATA_FIELDS}

# `_m` before `_min` would read "Arrêt (min)" as metres, so the suffixes are
# tried longest-first. A label that already carries its unit — "(ml)", "(min)"
# — gets none appended, or the cell would read "8 (ml) m".
_UNIT_SUFFIXES = (("_min", "min"), ("_m", "m"), ("_u", "u"))


def quantity_columns() -> List[Tuple[str, str, str]]:
    """Every quantity as (Rapports column, the director's label, unit).

    The one catalogue anything reporting on quantities reads, so a new article
    appears in the report the moment it appears in `NUMERIC_COLUMNS` — the
    .docx used to name four of the thirty-five columns in Python literals and
    was blind to the other thirty-one. Order is his: his own columns first,
    then the bordereau articles.
    """
    out: List[Tuple[str, str, str]] = []
    for field in NUMERIC_COLUMNS:
        column = RAPPORTS_COLUMNS.get(field)
        if column:
            out.append((column, *article_label(field)))
    return out


def rapports_totals(rows: Sequence[Dict]) -> List[Tuple[str, str, str, float]]:
    """(column, label, unit, total) for the quantities these flat rows carry.

    The one place a Rapports total is computed. Three things want them — the
    document's table, the per-group splits inside it, and the totals handed to
    the report model — and when each added up its own columns the mail body and
    the document attached to it could state different figures for the same day.
    A quantity nobody reported is left out entirely rather than printed as 0:
    absence is not zero here either.
    """
    out: List[Tuple[str, str, str, float]] = []
    for column, label, unit in quantity_columns():
        running = None
        for row in rows:
            value = _num(row.get(column))
            if value is not None:
                running = (running or 0.0) + value
        if running:
            out.append((column, label, unit, running))
    return out


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

    **The origin falls back to `dashboard_url`** (2026-08-16). It was
    `dashboard_base_url` alone, which is optional and was never set — so on the
    live install this branch never once ran and every cell took the fallback
    below. Two settings naming the same origin, one of them silently degrading
    the feature, is one setting too many: `dashboard_url` already has to be
    right for the report mail's "Ouvrir le rapport" button, so it is right here
    too, and `DASHBOARD_BASE_URL` remains available to point the Sheet somewhere
    else if that is ever wanted.

    The last resort is the Drive link **only if it is actually a link**. The
    payload's `lien_audio` is whatever n8n put there, and on the live install it
    was a bare message id — 22 cells in a column called "Lien audio" holding
    `1115179874166528`, which opens nothing. An empty cell says "no recording
    here"; an id says "here is your link" and lies. Absence over a false claim,
    the same rule the quantity columns follow.
    """
    base = (settings.dashboard_base_url or settings.dashboard_url or "").strip().rstrip("/")
    correlation = str(payload.get("correlation_id") or "").strip()
    if not base or not correlation:
        raw = str(payload.get("lien_audio") or "").strip()
        return raw if raw.startswith(("http://", "https://", "=")) else None
    url = f"{base}/#/inbox?msg={quote(correlation, safe='')}"
    # A HYPERLINK formula rather than the bare URL: the cell then reads
    # "▶ Écouter" instead of 120 characters of base64 wamid, and the column can
    # be narrow. Written with valueInputOption=USER_ENTERED everywhere in
    # sheets.py, which is what makes a leading `=` a formula and not text.
    # Quotes are doubled because a `"` inside a Sheets string literal escapes
    # that way; the id is percent-encoded above, so this is belt and braces.
    return f'=HYPERLINK("{url.replace(chr(34), chr(34) * 2)}"; "▶ Écouter")'


# --- jours-homme ----------------------------------------------------------
#
# A working day, in hours, and the unpaid break to subtract from a day's span.
# Both are overridable in `app_settings` (`jh_heures_jour`, `jh_pause_min`)
# without a restart, because they are a company's own convention rather than a
# fact about the domain, and getting them wrong scales every JH on the sheet.
#
# The break defaults to 0, which is the conservative choice and not the
# realistic one: a crew on site 07:00-20:00 almost certainly ate. Subtracting
# an hour nobody reported would be inventing data to make a figure prettier,
# which is the one thing this pipeline refuses to do everywhere else. Set
# `jh_pause_min` once the real convention is known.
JH_HEURES_JOUR = 8.0
JH_PAUSE_MIN = 0.0

_HHMM = re.compile(r"^\s*(\d{1,2})\s*[:hH]\s*(\d{1,2})?\s*$")


def jh_limits() -> Dict[str, float]:
    """The working-day convention, from `app_settings` or the defaults.

    Read per call rather than cached, like `stock._thresholds`: an edited
    convention has to take effect without a restart, and this runs once per
    report. An unreachable store falls back to the defaults instead of raising
    — a JH nobody can compute must not cost the technician their row.
    """
    from app import logs

    try:
        row = logs.get_settings()
    except Exception:  # noqa: BLE001 - an unreachable store must not cost the row
        row = {}

    def read(key: str, fallback: float) -> float:
        try:
            return float(row.get(key))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return fallback

    return {
        "heures_jour": read("jh_heures_jour", JH_HEURES_JOUR),
        "pause_min": read("jh_pause_min", JH_PAUSE_MIN),
    }


def _minutes(value) -> Optional[int]:
    """"07:00" -> 420. Tolerates "7h", "7h30", "07:00"; None on anything else."""
    m = _HHMM.match(str(value or ""))
    if not m:
        return None
    hours, minutes = int(m.group(1)), int(m.group(2) or 0)
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return None
    return hours * 60 + minutes


def crew_size(equipe) -> int:
    """How many people the row accounts for: the technician plus whoever they
    named. An empty EQUIPE is one person, never zero — somebody recorded it."""
    names = [n.strip() for n in str(equipe or "").split(",") if n.strip()]
    return 1 + len(names)


def compute_jh(report: ExtractedReport, limits: Optional[Dict[str, float]] = None
               ) -> Optional[float]:
    """Man-days for one report, or None when the hours were not given.

    `(sortie - entrée - pause) x people / hours-in-a-day`. Entered 07:00, left
    20:00, one colleague named: 13 h x 2 / 8 = 3.25.

    None rather than 0 when either hour is missing: a day whose span nobody
    stated is unknown, and 0 would read as "no work", which is a claim. A
    sortie before an entrée is a crossing of midnight -- an overnight shift is
    real on a cabling site -- so the span wraps rather than going negative.
    """
    limits = limits or {}
    start, end = _minutes(report.heure_entree), _minutes(report.heure_sortie)
    if start is None or end is None:
        return None
    span = end - start
    if span < 0:
        span += 24 * 60
    span -= float(limits.get("pause_min", JH_PAUSE_MIN))
    hours_per_day = float(limits.get("heures_jour", JH_HEURES_JOUR)) or JH_HEURES_JOUR
    jh = (max(span, 0) / 60.0) * crew_size(report.equipe) / hours_per_day
    return round(jh, 2)


def correlation_cell(correlation: Optional[str]) -> str:
    """What the "Correlation id" cell should hold.

    The id is the join key between n8n's logs, ours and the inbox, and until
    2026-08-18 the cell held it as 60-odd characters of raw text: readable by a
    machine, useless to the person reading the sheet, who had to copy it into
    the dashboard by hand to see the message it names. It now links straight to
    that message, keeping the id as the visible text so the cell still says
    what it is and still reads as the key it has always been.

    Falls back to the bare id when no dashboard origin is configured — a
    relative path in a spreadsheet cell opens nothing, the same rule
    `audio_link` follows.
    """
    correlation = str(correlation or "").strip()
    if not correlation:
        return ""
    base = (settings.dashboard_base_url or settings.dashboard_url or "").strip().rstrip("/")
    if not base:
        return correlation
    url = f"{base}/#/inbox?msg={quote(correlation, safe='')}"
    return (f'=HYPERLINK("{url.replace(chr(34), chr(34) * 2)}"; '
            f'"{correlation.replace(chr(34), chr(34) * 2)}")')


def correlation_of(cell) -> str:
    """The id inside a "Correlation id" cell, whether or not it is a link.

    The retry check compares this against the incoming message's id, so it has
    to read both shapes: the bare id written before 2026-08-18 (and whenever no
    dashboard origin is set) and the HYPERLINK formula written since. Reading
    only the raw form would make every retry look like a new message and file
    it twice — the one error that doubles a quantity without looking wrong.
    """
    text = str(cell or "").strip()
    if not text.startswith("="):
        return text
    shown = re.findall(r'"((?:[^"]|"")*)"', text)
    return shown[-1].replace('""', '"').strip() if shown else text


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
        # An empty list is absence, not a value: written through it would put a
        # literal `[]` in the cell, which reads as data to anyone scanning the
        # column and to every `num()` in the dashboard.
        if value is None or value == [] or value == "":
            continue
        # `etages` / `ailes` / `locaux_techniques` are lists; the flat tab is
        # one cell per column, joined the same way the journal tab joins them.
        cells[column] = ", ".join(value) if isinstance(value, list) else value
    return cells


def _mirror_rapports(payload: Dict, chantier: str, warnings: List[str],
                     increment: bool = False) -> Optional[int]:
    """Append the flat Rapports row for this message; never raises.

    The journal row is the record; the mirror is for the dashboard. When
    Google refuses it, the report itself is not lost — the journal write
    already succeeded — so this logs and moves on instead of failing the
    whole /journal call. Returns the appended row number, or None on
    failure, so /supprimer can clear the mirror row too.
    """
    try:
        row = sheets.append_report(_rapports_cells(payload, chantier, warnings))
        # The dashboard reads this tab, so a follow-up has to read as one here
        # too -- same number format, same reason as the journal row. It costs no
        # extra read: file_report already knows, from the tab it just scanned.
        if row and increment:
            cols = [RAPPORTS_COLUMNS[f] for f in NUMERIC_COLUMNS
                    if f in RAPPORTS_COLUMNS]
            if cols:
                headers = list(RAPPORTS_COLUMNS.values())
                idx = [headers.index(c) for c in cols]
                sheets.mark_increment("Rapports", row, min(idx), max(idx))
        return row
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


LIVRAISONS_TAB = "Livraisons"
LIVRAISONS_HEADERS: Tuple[str, ...] = (
    "Date", "Chantier", "Technicien", "Article", "Quantité", "Unité",
    "Canal", "Correlation id",
)


def article_label(field: str) -> Tuple[str, str]:
    """A quantity field as (the director's label, its unit)."""
    label = NUMERIC_COLUMNS.get(field, field)
    unit = next((u for suffix, u in _UNIT_SUFFIXES if field.endswith(suffix)), "")
    if re.search(r"\((?:ml|min)\)\s*$", label):
        unit = ""
    return label, unit


def file_livraison(payload: Dict, report: ExtractedReport) -> Dict:
    """A bon de livraison: ledger the quantities, write no journal row.

    A delivery is not a day's work. Merged into the journal it would add to the
    installed columns — the exact number the bordereau's `avancement` and every
    stock figure are computed from — so 500 m delivered would read as 500 m
    posed, and the site would look finished while the cable sat on a pallet.

    Postgres is the ledger and is written first; the `Livraisons` tab mirrors it
    best-effort, the same contract as the Rapports mirror. A tab that Google
    refuses must not cost the reception, because the balance is computed from
    the ledger and not from the sheet.
    """
    from app import logs

    technicien = str(payload.get("technicien") or "").strip()
    chantier, _tab, warnings, _source = resolve_site(
        technicien, payload.get("chantier") or report.chantier_mentionne
    )
    date = str(payload.get("date") or "")
    lignes = report.livraisons or {}
    recorded = logs.record_receptions(
        chantier, lignes, date,
        technicien=technicien,
        canal=payload.get("canal"),
        correlation_id=payload.get("correlation_id"),
    )
    try:
        sheets.ensure_tab(LIVRAISONS_TAB, list(LIVRAISONS_HEADERS))
        for field, qte in lignes.items():
            label, unit = article_label(field)
            sheets.append_row(LIVRAISONS_TAB, {
                "Date": date,
                "Chantier": chantier,
                "Technicien": technicien,
                "Article": label,
                "Quantité": _fmt(float(qte)),
                "Unité": unit,
                "Canal": payload.get("canal"),
                "Correlation id": payload.get("correlation_id"),
            }, list(LIVRAISONS_HEADERS))
    except Exception as exc:  # noqa: BLE001 - the ledger already holds it
        logs.write_safe(
            "sheet", "error",
            message=f"livraisons mirror failed: {exc}",
            correlation_id=payload.get("correlation_id"),
        )
    return {
        "chantier": chantier,
        "tab": LIVRAISONS_TAB,
        "lignes": len(lignes),
        "enregistrees": recorded,
        "warnings": warnings,
    }


def file_report(payload: Dict) -> Dict:
    """File one report into the right journal tab. Raises SheetsError on failure
    so the caller can park it in the retry queue — never a silent loss."""
    report = payload.get("report")
    if not isinstance(report, ExtractedReport):
        report = ExtractedReport(**(report or {}))
    # A delivery is ledgered whatever else the message carried: « on a reçu
    # 500 m et on a posé 80 » is two different facts and dropping either one
    # loses real work. Only `nature` decides whether a journal row follows.
    #
    # Both entrances — the live `/journal` call and the retry drain — come
    # through here, so a parked delivery can never be replayed as installed
    # quantities.
    livraison = file_livraison(payload, report) if report.livraisons else None
    if report.nature == "livraison":
        return {
            **(livraison or {"chantier": None, "lignes": 0, "warnings": []}),
            "livraison": True,
            "row": None,
            "rapports_row": None,
        }
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
    correlation = str(payload.get("correlation_id") or "").strip()
    if correlation:
        # Rows are appended one per message since 2026-08-18, so a message's
        # correlation id identifies exactly one row and the whole tab has to be
        # scanned for it. It used to be enough to look inside the day's single
        # merged row, whose Correlation cell accumulated every message that
        # touched it. Finding it means this exact message already landed — a
        # retry after a Sheets failure Google actually committed — and filing
        # again would double every quantity it carried.
        already = next(
            (i for i, row in enumerate(rows, start=2)
             if correlation_of(row.get(COL_CORRELATION)) == correlation),
            None,
        )
        if already is not None:
            existing_row = already
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
        COL_CORRELATION: correlation_cell(payload.get("correlation_id")),
        COL_FLAG: "TRUE" if REVIEW_WARNINGS & set(warnings) else "FALSE",
        COL_MOTIF_FLAG: flag_reason(warnings),
    }
    # Does this technician already have a row for this day on this tab? Both
    # writers need the answer and the tab has already been read, so it is
    # settled once here rather than scanned for twice.
    follow_up = find_row(tab, str(payload.get("date") or ""), technicien, rows)[0] is not None
    row, stock_warnings = write_report(
        tab, payload.get("date") or "", technicien, chantier, report,
        {k: v for k, v in metadata.items() if v not in (None, "")},
        rows,
    )
    warnings = warnings + stock_warnings
    # After the journal write succeeded, so a mirror failure cannot cost the
    # row — but before the reply, because the dashboard shows it.
    mirror_row = _mirror_rapports(payload, chantier, warnings, follow_up)
    return {
        "row": row,
        "tab": tab,
        "chantier": chantier,
        "warnings": warnings,
        "rapports_row": mirror_row,
        "duplicate": False,
        # Present only when the same message also declared a reception, so the
        # caller can say so without having to re-read the extraction.
        **({"livraison": livraison} if livraison else {}),
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
