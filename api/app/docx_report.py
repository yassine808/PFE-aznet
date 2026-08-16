"""The report as a Word document, built server-side.

Why here and not in the browser: the scheduled mail is sent by `jobs.py` from a
thread inside the container, where there is no DOM, no `Blob` and no way to call
`Dashboard/src/lib/report-export.ts`. So the document only ever existed if a
human clicked Export — which is the opposite of what a *scheduled* report is
for. The owner's decision (2026-08-16) is that the backend renders it, the mail
attaches it, and the dashboard button downloads these same bytes rather than
building its own. One renderer, or the two drift the way the n8n Sheet mapping
did before it moved into `journal.py`.

The figures are recomputed here from the Sheet rows rather than posted by the
caller: the browser already derives them for the screen, and a second
transmitted copy is a second thing that can be stale or forged. The parsing
rules are `Dashboard/src/lib/metrics.ts` (`num`, `isFlagged`) exactly, so a cell
reads the same on the page and in the document.

*Which* columns are read is not decided here (2026-08-16). It comes from
`journal.quantity_columns()`, the same catalogue the journal tab and the
bordereau are built from. Before that this file named four Sheet columns in
Python literals, and the Rapports tab had grown to thirty-five quantity
columns — so the report was structurally incapable of mentioning fibre, tested
sockets or any of the twenty-five bordereau articles, however much of them the
crew installed. A hardcoded table cannot be kept in sync; a derived one has
nothing to keep in sync.

`python-docx` builds it — a .docx is a ZIP of several XML parts and genuinely
cannot be hand-rolled — and is imported inside the function so the test suite
and a plain API start stay free of it.
"""
from __future__ import annotations

import io
import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from app import journal

# Same four colours as the TypeScript renderer it replaces, so a document
# produced by the scheduler is indistinguishable from one exported by hand.
INK = "0F172A"
MUTED = "64748B"
BODY = "334155"
ACCENT = "2563EB"
RULE = "E2E8F0"
# Anything needing a human eye. One colour, used nowhere else in the document,
# so a reader scanning for problems finds them without reading a word.
ALERT = "DC2626"

FONT = "Calibri"

# A red triangle, as the owner asked for. `▲` rather than `⚠`: U+25B2 is in
# Calibri's own Geometric Shapes range, so it draws everywhere, while U+26A0
# is not and depends on Word finding a fallback font — a warning marker that
# renders as an empty box is worse than no marker.
ALERT_MARK = "▲"


def _is_flagged(value: Any) -> bool:
    """`metrics.ts:isFlagged` — the Sheet holds whatever the writer typed."""
    return str(value or "").strip().lower() in {"true", "vrai", "oui", "yes", "1"}


def _int(value: float) -> str:
    """Metres are read as whole numbers; a trailing `.0` is noise on a report."""
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def slug(title: str) -> str:
    """`Rapport journalier — 2026-07-25` -> `rapport-journalier-2026-07-25`."""
    plain = unicodedata.normalize("NFD", title)
    plain = "".join(c for c in plain if unicodedata.category(c) != "Mn")
    plain = re.sub(r"[^a-zA-Z0-9]+", "-", plain).strip("-").lower()
    return (plain[:60] or "rapport")


def compute_figures(rows: Sequence[dict]) -> Dict[str, str]:
    """The headline tiles: what was reported, by whom, where, and what to check.

    Deliberately no quantities. There are thirty-five quantity columns and this
    grid held four of them, named in Python literals — so every column added
    after 2026-07 was invisible in the report no matter what the crew installed.
    The quantities now have their own table below, with the director's own
    labels and no ceiling on how many there can be.
    """
    techs = {(r.get("technicien") or "").strip() for r in rows}
    sites = {(r.get("chantier") or "").strip() for r in rows}
    return {
        "Rapports": str(len(rows)),
        "Techniciens": str(len(techs - {""})),
        "Chantiers": str(len(sites - {""})),
        "À vérifier": str(sum(1 for r in rows if _is_flagged(r.get("flag_review")))),
    }


def group_rows(rows: Sequence[dict], key: str, companion: str) -> List[dict]:
    """Rows bucketed by one column, busiest first.

    `companion` is the other axis printed on the line — the sites a technician
    worked, or the technicians who worked a site. Names, not a count: "2" tells
    the director nothing he can act on, "DGH, ACAPS" does.

    Each bucket's quantities come from `journal.rapports_totals` on its own
    rows, the same call the whole-period table uses, so a column total and the
    split under it can never be produced by two different sums.
    """
    buckets: Dict[str, List[dict]] = {}
    for row in rows:
        buckets.setdefault((row.get(key) or "").strip() or "—", []).append(row)
    groups = [
        {
            "name": name,
            "count": len(bucket),
            "others": {(r.get(companion) or "").strip() for r in bucket} - {""},
            "flagged": sum(1 for r in bucket if _is_flagged(r.get("flag_review"))),
            "totals": {c: total for c, _l, _u, total in journal.rapports_totals(bucket)},
        }
        for name, bucket in buckets.items()
    ]
    return sorted(groups, key=lambda e: (-e["count"], e["name"]))


def by_technician(rows: Sequence[dict]) -> List[dict]:
    return group_rows(rows, "technicien", "chantier")


def flagged(rows: Sequence[dict]) -> List[dict]:
    """The rows a human still has to look at, with the reason they were flagged.

    `motif_flag` has been written on every flagged row since 2026-08-09 and no
    report has ever shown it, so "À vérifier : 2" told the reader a number and
    nothing they could act on — and the cheapest thing to do with a flag you
    cannot explain is believe it. The reason is the whole point of the column.
    """
    return [
        {
            "heure": (r.get("heure") or "—").strip(),
            "technicien": (r.get("technicien") or "—").strip() or "—",
            "chantier": (r.get("chantier") or "—").strip() or "—",
            "motif": (r.get("motif_flag") or "non précisé").strip() or "non précisé",
        }
        for r in rows
        if _is_flagged(r.get("flag_review"))
    ]


def _count(n: int) -> str:
    """A flag count as a table cell: marked and red when there is one."""
    return f"{ALERT_MARK} {n}" if n else "—"


def _quantity(alert: dict) -> str:
    """The remaining quantity, marked when it is the critical kind.

    A dépassement carries a negative `reste` — it is how much the site is over
    the contract — so it prints with an explicit sign rather than as a quantity
    someone might read as stock on hand.
    """
    reste = alert.get("reste")
    if reste is None:
        return "—"
    unit = f" {alert['unite']}" if alert.get("unite") else ""
    if alert.get("niveau") == "depassement":
        return f"{ALERT_MARK} +{_int(abs(reste))}{unit}"
    marked = ALERT_MARK + " " if alert.get("niveau") == "critique" else ""
    return f"{marked}{_int(reste)}{unit}"


def _cover(alert: dict) -> str:
    """Days of cover, or why there are none to give."""
    if alert.get("niveau") == "depassement":
        return "dépassement"
    jours = alert.get("jours")
    if jours is None:
        # Fewer than two active days: an average over one day is that day, and
        # printing it as a rate would give a made-up number an air of trend.
        return "rythme inconnu"
    return f"{jours:.1f} j"


def _split(groups: Sequence[dict], column: str) -> str:
    """Who contributed to one quantity: `Yassine 40 · Ahmed 10`.

    This is the column that replaces a per-technician quantity table: the table
    would need one column per quantity and overflow the page at four of them,
    while a wrapping cell holds any number of contributors.
    """
    return " · ".join(
        f"{g['name']} {_int(g['totals'][column])}"
        for g in groups
        if g["totals"].get(column)
    )


def _run(paragraph, text: str, *, size: float = 10, bold: bool = False,
         color: str = BODY, caps: bool = False):
    """One styled run. `size` is in points here, not the half-points docx uses."""
    from docx.shared import Pt, RGBColor

    run = paragraph.add_run(text)
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)
    run.font.all_caps = caps
    return run


def _borders(cell, *, color: str = RULE, sides: Sequence[str] = ("top", "bottom", "left", "right")):
    """Hairlines on a table cell.

    python-docx exposes no border API, so this writes `w:tcBorders` directly —
    the one place raw XML is unavoidable. Every side not named is left absent,
    which Word renders as no line rather than as a default one.
    """
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    props = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for side in sides:
        element = OxmlElement(f"w:{side}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "6")  # eighths of a point
        element.set(qn("w:color"), color)
        borders.append(element)
    props.append(borders)


def _page_field(paragraph):
    """`PAGE / NUMPAGES` in the footer.

    A field, not a number: Word evaluates it at render time, so the footer is
    still right after the document is edited or printed to a different paper
    size. python-docx has no helper for fields either.
    """
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    for instruction, literal in (("PAGE", "1"), ("NUMPAGES", "1")):
        begin = OxmlElement("w:fldChar")
        begin.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = f" {instruction} "
        separate = OxmlElement("w:fldChar")
        separate.set(qn("w:fldCharType"), "separate")
        value = OxmlElement("w:t")
        value.text = literal
        end = OxmlElement("w:fldChar")
        end.set(qn("w:fldCharType"), "end")

        run = _run(paragraph, "", size=8, color=MUTED)._r
        for node in (begin, instr, separate, value, end):
            run.append(node)
        if instruction == "PAGE":
            _run(paragraph, " / ", size=8, color=MUTED)


def _body_blocks(document, body: str) -> None:
    """The model's text, turned into Word structure.

    `## ` becomes a real Heading 2 rather than bold text pretending to be one —
    bold text is invisible to Word's navigation pane and to a table of contents
    — and `- ` becomes a genuine list item. Anything else is a paragraph. The
    model is allowed exactly this much markup and no more; see `_INSTRUCTIONS`
    in `daily_report.py`.
    """
    from docx.shared import Pt

    for raw in body.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            paragraph = document.add_paragraph(style="Heading 2")
            paragraph.paragraph_format.space_before = Pt(16)
            paragraph.paragraph_format.space_after = Pt(6)
            _run(paragraph, line[3:], size=12, bold=True, color=INK)
        elif line.startswith("- "):
            paragraph = document.add_paragraph(style="List Bullet")
            paragraph.paragraph_format.space_after = Pt(4)
            _run(paragraph, line[2:], size=10.5)
        else:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(8)
            _run(paragraph, line, size=10.5)


def _heading(document, text: str, color: str = INK) -> None:
    from docx.shared import Pt

    paragraph = document.add_paragraph(style="Heading 2")
    paragraph.paragraph_format.space_before = Pt(16)
    paragraph.paragraph_format.space_after = Pt(6)
    _run(paragraph, text, size=12, bold=True, color=color)


def _table(document, headers: Sequence[str], body: Sequence[Sequence[str]],
           right: Sequence[int] = ()) -> None:
    """A hairline table. `right` is the indices of the numeric columns.

    Three tables share this now — quantities, technicians, sites — which is
    what earns the helper: the same fourteen lines written three times is
    three places to fix a border or a font size.
    """
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    table = document.add_table(rows=1 + len(body), cols=len(headers))
    for index, line in enumerate(((*headers,), *body)):
        for column, value in enumerate(line):
            cell = table.cell(index, column)
            cell.text = ""
            _borders(cell, sides=("bottom",))
            paragraph = cell.paragraphs[0]
            if column in right:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            # A cell the caller marked with the triangle is drawn in the alert
            # colour. Carried on the value rather than as a per-cell colour
            # argument because the callers build their rows as plain tuples,
            # and a parallel grid of colours is a second thing to keep aligned.
            alert = value.startswith(ALERT_MARK)
            _run(paragraph, value, size=9.5, bold=index == 0 or alert,
                 color=ALERT if alert else (INK if index == 0 else BODY))


def build(
    title: str,
    body: str,
    kind: str,
    period: str,
    rows: Sequence[dict],
    author: Optional[str] = None,
    alerts: Optional[Sequence[dict]] = None,
) -> bytes:
    """The whole document, as the bytes that get attached or downloaded.

    `rows` are the Sheet rows the report covers — the figures are derived, not
    passed. An empty `rows` simply prints no tables: a report generated for a
    day whose rows were deleted underneath it is still the report someone wrote.
    """
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    document = Document()

    normal = document.styles["Normal"].font  # type: ignore[attr-defined]
    normal.name = FONT
    normal.size = Pt(10.5)

    section = document.sections[0]
    for margin in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(section, margin, Cm(1.8))

    header = section.header.paragraphs[0]
    _run(header, "AZNET", size=9, bold=True, color=ACCENT)
    _run(header, "   ·   ", size=9, color=RULE)
    _run(header, kind, size=9, color=MUTED, caps=True)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _run(footer, f"{period}   ", size=8, color=MUTED)
    _page_field(footer)

    heading = document.add_paragraph(style="Title")
    heading.paragraph_format.space_after = Pt(3)
    _run(heading, title, size=20, bold=True, color=INK)

    # Two different facts, and a report that conflates them cannot be audited:
    # *who* the content came from (a person pressed Générer, or the 18:00 job
    # ran) and *when this file* was produced. The export button can render a
    # document days after the text was written, so one timestamp cannot honestly
    # stand for both.
    provenance = document.add_paragraph()
    provenance.paragraph_format.space_after = Pt(4)
    by_hand = bool(author) and author != "automatique"
    _run(provenance, period, size=9, bold=True, color=BODY)
    _run(provenance, "   ·   ", size=9, color=RULE)
    _run(
        provenance,
        f"établi par {author}" if by_hand else "rapport automatique",
        size=9,
        color=ACCENT if by_hand else MUTED,
    )
    _run(provenance, "   ·   ", size=9, color=RULE)
    _run(
        provenance,
        f"document généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
        size=9,
        color=MUTED,
    )

    figures = compute_figures(rows)
    if rows:
        # Four per line: past that the labels wrap and the grid stops being
        # scannable, which is the only thing it is for. The row count follows
        # the number of tiles rather than assuming eight, so the grid survives
        # a tile being added or dropped.
        items = list(figures.items())
        grid = document.add_table(rows=-(-len(items) // 4), cols=4)
        grid.alignment = WD_TABLE_ALIGNMENT.CENTER
        for index, (label, value) in enumerate(items):
            cell = grid.cell(index // 4, index % 4)
            cell.text = ""
            _borders(cell)
            top = cell.paragraphs[0]
            top.paragraph_format.space_after = Pt(2)
            # The one tile that means "someone has to do something" is drawn in
            # the alert colour, and only when it is not zero — a permanent red
            # tile reading 0 is exactly how a warning colour stops being read.
            alert = label == "À vérifier" and value != "0"
            _run(top, f"{ALERT_MARK} {value}" if alert else value,
                 size=15, bold=True, color=ALERT if alert else ACCENT)
            _run(cell.add_paragraph(), label, size=8,
                 color=ALERT if alert else MUTED, caps=True)
        document.add_paragraph().paragraph_format.space_after = Pt(12)

    _body_blocks(document, body)

    tech_rows = by_technician(rows)
    site_rows = group_rows(rows, "chantier", "technicien")

    # Every quantity the period actually carries, in the director's own column
    # order and with his own labels, plus who contributed to each. This is the
    # table that used to be four columns of Python literals.
    totals = journal.rapports_totals(rows)
    if totals:
        # "déclarées", not "réalisées": `temps_arret_min` belongs in this table —
        # a crew stopped 90 minutes is exactly what the director needs — and an
        # arrêt is the opposite of work realised.
        _heading(document, "Quantités déclarées")
        _table(
            document,
            ("Désignation", "Quantité", "Répartition par technicien"),
            [
                (label, f"{_int(total)} {unit}".strip(), _split(tech_rows, column) or "—")
                for column, label, unit, total in totals
            ],
            right=(1,),
        )

    if tech_rows:
        _heading(document, "Activité par technicien")
        _table(
            document,
            ("Technicien", "Rapports", "Chantiers", "À vérifier"),
            [
                (e["name"], str(e["count"]), ", ".join(sorted(e["others"])) or "—",
                 _count(e["flagged"]))
                for e in tech_rows
            ],
            right=(1, 3),
        )

    # Only when there is more than one: on a single-site day this table is one
    # row restating the tile above it, and a report earns nothing by repeating
    # itself in a different shape.
    if len(site_rows) > 1:
        _heading(document, "Activité par chantier")
        _table(
            document,
            ("Chantier", "Rapports", "Techniciens", "À vérifier"),
            [
                (e["name"], str(e["count"]), ", ".join(sorted(e["others"])) or "—",
                 _count(e["flagged"]))
                for e in site_rows
            ],
            right=(1, 3),
        )

    # Above the review section and below the work: what has to be ordered is
    # the one thing in this document with a deadline attached to it.
    if alerts:
        _heading(document, f"{ALERT_MARK} Alertes matériel", color=ALERT)
        _table(
            document,
            ("Chantier", "Article", "Reste", "Couverture", "Provenance du chiffre"),
            [
                (
                    a["chantier"],
                    a["article"],
                    _quantity(a),
                    _cover(a),
                    a.get("source") or "—",
                )
                for a in alerts
            ],
            right=(2, 3),
        )

    # Last, and only when there is something: the reader reaches it having
    # already seen what was done, so an empty section here reads as "nothing to
    # check" rather than as a heading with no content.
    review = flagged(rows)
    if review:
        _heading(document, f"{ALERT_MARK} Points à vérifier", color=ALERT)
        _table(
            document,
            ("Heure", "Technicien", "Chantier", "Motif du flag"),
            [(r["heure"], r["technicien"], r["chantier"], r["motif"]) for r in review],
        )

    document.core_properties.author = "aznet"
    document.core_properties.title = title
    document.core_properties.comments = f"{kind} · {period}"

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def filename(title: str) -> str:
    return f"{slug(title)}.docx"
