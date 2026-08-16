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
transmitted copy is a second thing that can be stale or forged. The arithmetic
mirrors `Dashboard/src/lib/metrics.ts` (`num`, `isFlagged`) exactly, because the
table in the document and the tiles on the page have to agree.

`python-docx` builds it — a .docx is a ZIP of several XML parts and genuinely
cannot be hand-rolled — and is imported inside the function so the test suite
and a plain API start stay free of it.
"""
from __future__ import annotations

import io
import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence

# Same four colours as the TypeScript renderer it replaces, so a document
# produced by the scheduler is indistinguishable from one exported by hand.
INK = "0F172A"
MUTED = "64748B"
BODY = "334155"
ACCENT = "2563EB"
RULE = "E2E8F0"

FONT = "Calibri"


def _num(value: Any) -> float:
    """A Sheet cell as a number. `metrics.ts:num` — comma decimals included."""
    if value is None:
        return 0.0
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


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
    """The eight headline numbers, in the order the grid prints them.

    Reads the Sheet's own header names (`goulottes_m`, `cables_m`,
    `bureaux_termines`, `panneaux_raccordes`) — the four that kept their
    pre-2026-08-05 spelling, because renaming a column orphans every historical
    row in it. See `journal.RAPPORTS_COLUMNS`.
    """
    goulottes = sum(_num(r.get("goulottes_m")) for r in rows)
    cables = sum(_num(r.get("cables_m")) for r in rows)
    bureaux = sum(_num(r.get("bureaux_termines")) for r in rows)
    panneaux = sum(_num(r.get("panneaux_raccordes")) for r in rows)
    techs = {(r.get("technicien") or "").strip() for r in rows}
    sites = {(r.get("chantier") or "").strip() for r in rows}
    return {
        "Rapports": str(len(rows)),
        "Techniciens": str(len(techs - {""})),
        "Chantiers": str(len(sites - {""})),
        "À vérifier": str(sum(1 for r in rows if _is_flagged(r.get("flag_review")))),
        "Goulottes": f"{_int(goulottes)} m",
        "Câbles": f"{_int(cables)} m",
        "Bureaux": _int(bureaux),
        "Panneaux": _int(panneaux),
    }


def by_technician(rows: Sequence[dict]) -> List[dict]:
    """Per-sender activity, busiest first — the second table in the document."""
    acc: Dict[str, dict] = {}
    for row in rows:
        name = (row.get("technicien") or "").strip() or "—"
        entry = acc.setdefault(name, {"name": name, "count": 0, "goulottes": 0.0, "flagged": 0})
        entry["count"] += 1
        entry["goulottes"] += _num(row.get("goulottes_m"))
        entry["flagged"] += 1 if _is_flagged(row.get("flag_review")) else 0
    return sorted(acc.values(), key=lambda e: (-e["count"], e["name"]))


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


def build(
    title: str,
    body: str,
    kind: str,
    period: str,
    rows: Sequence[dict],
    author: Optional[str] = None,
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

    provenance = document.add_paragraph()
    provenance.paragraph_format.space_after = Pt(16)
    _run(
        provenance,
        f"{period} · établi par {author}"
        if author and author != "automatique"
        else f"{period} · rapport automatique",
        size=9,
        color=MUTED,
    )

    figures = compute_figures(rows)
    if rows:
        # Four per line rather than eight: at eight the labels wrap and the grid
        # stops being scannable, which is the only thing it is for.
        items = list(figures.items())
        grid = document.add_table(rows=2, cols=4)
        grid.alignment = WD_TABLE_ALIGNMENT.CENTER
        for index, (label, value) in enumerate(items):
            cell = grid.cell(index // 4, index % 4)
            cell.text = ""
            _borders(cell)
            top = cell.paragraphs[0]
            top.paragraph_format.space_after = Pt(2)
            _run(top, value, size=15, bold=True, color=ACCENT)
            _run(cell.add_paragraph(), label, size=8, color=MUTED, caps=True)
        document.add_paragraph().paragraph_format.space_after = Pt(12)

    _body_blocks(document, body)

    tech_rows = by_technician(rows)
    if tech_rows:
        title_paragraph = document.add_paragraph(style="Heading 2")
        title_paragraph.paragraph_format.space_before = Pt(16)
        title_paragraph.paragraph_format.space_after = Pt(6)
        _run(title_paragraph, "Activité par technicien", size=12, bold=True, color=INK)

        table = document.add_table(rows=1 + len(tech_rows), cols=4)
        headers = ("Technicien", "Rapports", "Goulottes (m)", "À vérifier")
        for column, label in enumerate(headers):
            cell = table.cell(0, column)
            cell.text = ""
            _borders(cell, sides=("bottom",))
            paragraph = cell.paragraphs[0]
            if column:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            _run(paragraph, label, size=9.5, bold=True, color=INK)
        for index, entry in enumerate(tech_rows, start=1):
            values = (
                entry["name"],
                str(entry["count"]),
                _int(entry["goulottes"]),
                str(entry["flagged"]) if entry["flagged"] else "—",
            )
            for column, value in enumerate(values):
                cell = table.cell(index, column)
                cell.text = ""
                _borders(cell, sides=("bottom",))
                paragraph = cell.paragraphs[0]
                if column:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                _run(paragraph, value, size=9.5)

    document.core_properties.author = "aznet"
    document.core_properties.title = title
    document.core_properties.comments = f"{kind} · {period}"

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def filename(title: str) -> str:
    return f"{slug(title)}.docx"
