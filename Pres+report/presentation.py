"""Build Soutenance-PFE.pptx -- the defence deck.

    python presentation.py

This script is the source of truth, the .pptx is the output: a content change is
an edit here followed by a rebuild, never a hand-edit of the deck. Same rule as
build.ps1 for the report, and for the same reason -- a slide corrected only in
PowerPoint is a correction that disappears on the next build.

Sized for a 20-minute defence (21 slides, ~1 min each) plus backup slides that
are never shown unless the live demo fails.

The palette is not invented: the green and the blue are sampled from
assets/logo-emsi.png and assets/logo-aznet.png, so the deck agrees with the two
institutions printed on its own cover page.
"""

from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

HERE = Path(__file__).parent
DIAGRAMS = HERE / "diagrams"
SCREENS = HERE / "screens"
ASSETS = HERE / "assets"
OUT = HERE / "Soutenance-PFE.pptx"

# --- design tokens ---------------------------------------------------------

GREEN = RGBColor(0x0B, 0x8E, 0x36)   # EMSI
BLUE = RGBColor(0x02, 0x78, 0xE4)    # AZNET
INK = RGBColor(0x1C, 0x1F, 0x23)
GREY = RGBColor(0x57, 0x56, 0x56)
MUTE = RGBColor(0x8A, 0x8A, 0x8A)
PAPER = RGBColor(0xFF, 0xFF, 0xFF)
WASH = RGBColor(0xF4, 0xF5, 0xF3)    # card background
LINE = RGBColor(0xDF, 0xE1, 0xDE)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

# --- zellige ---------------------------------------------------------------
#
# A second palette, for ornament ONLY. It is built outward from the AZNET blue
# already sampled from the logo rather than beside it, so the tilework reads as
# Moroccan without arguing with the two institutions on the cover. Nothing that
# carries meaning uses these: headings stay INK, the accent rule stays EMSI
# green, data stays AZNET blue. Decoration is decorative.
Z_BLUE = BLUE                        # the anchor, straight off logo-aznet.png
Z_TURQUOISE = RGBColor(0x17, 0xA2, 0xA8)
Z_TERRA = RGBColor(0xC4, 0x54, 0x2B)
Z_SAFFRON = RGBColor(0xE3, 0xB2, 0x3C)
Z_SAND = RGBColor(0xF2, 0xEF, 0xE6)

# The rail lives left of the content column: MARGIN is 0.85, so 0.30 wide at
# x=0.28 never touches a word.
RAIL_X, RAIL_W = 0.28, 0.30

FONT = "Arial"  # one of the two fonts EMSI sanctions, and present on any machine

SLIDE_W, SLIDE_H = 13.333, 7.5
MARGIN = 0.85
CONTENT_W = SLIDE_W - 2 * MARGIN
BODY_TOP = 2.05
FOOTER_Y = 6.92

FOOTER_TEXT = "AZnet — Automatisation des rapports journaliers de chantier par IA"

# --- primitives ------------------------------------------------------------


def ar(s):
    """Isolate an Arabic fragment embedded in French text.

    Without this the bidirectional algorithm reorders the neighbouring French
    punctuation and swallows the spaces on either side -- '27 كابل, (vérifier)'
    renders as '27 كابل,(vérifier)' with the comma on the wrong side.

    LRM (U+200E) and not the isolate pair FSI/PDI (U+2068/U+2069): PowerPoint
    has no glyph for the isolates and draws them as visible dotted boxes reading
    "FSI" and "PDI". LRM is zero-width and renders as nothing.
    """
    return "‎" + s + "‎"


def _txbox(slide, x, y, w, h):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return tf


def _run(p, text, size: float = 16, bold=False, color=INK, italic=False):
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = color
    r.font.name = FONT
    return r


def _para(tf, first=False):
    return tf.paragraphs[0] if first else tf.add_paragraph()


def _rect(slide, x, y, w, h, fill=None, line=None, line_w=1.0):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.shadow.inherit = False
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(line_w)
    sh.text_frame.word_wrap = True
    return sh


# --- zellige geometry ------------------------------------------------------
#
# Everything here is a real PowerPoint shape, never a picture. Three reasons:
# nothing to license, it stays crisp at whatever resolution the amphitheatre
# projector runs, and morph interpolates shapes -- a rosette can travel and
# spin between slides, which a bitmap can only cross-fade.


def _alpha(shape, pct):
    """Translucency, which python-pptx does not expose.

    A solid fill's XML gains <a:alpha val="n"/>; 100000 is opaque. Ornament
    sits behind content, so it is almost always partly transparent -- at full
    strength a star competes with the sentence in front of it.
    """
    fill = shape.fill._xPr.find(qn("a:solidFill"))
    if fill is None:
        return
    clr = fill.find(qn("a:srgbClr"))
    if clr is None:
        return
    a = parse_xml('<a:alpha xmlns:a="http://schemas.openxmlformats.org/'
                  'drawingml/2006/main" val="%d"/>' % int(pct * 1000))
    clr.append(a)


def _tile(slide, shape_kind, x, y, size, fill, alpha=100, rot=0.0, name=None):
    """One tile: a star, a diamond, a square. The unit the whole grid is made of."""
    sh = slide.shapes.add_shape(shape_kind, Inches(x), Inches(y),
                                Inches(size), Inches(size))
    sh.shadow.inherit = False
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.fill.background()
    if rot:
        sh.rotation = rot
    if alpha < 100:
        _alpha(sh, alpha)
    if name:
        sh.name = name
    return sh


def khatam(slide, cx, cy, size, name=None, rot=0.0, alpha=100,
           star=Z_BLUE, inner=Z_TURQUOISE, ring=Z_SAFFRON):
    """The khatam -- the eight-pointed star that signs Moroccan tilework.

    Three concentric pieces: the star, a diamond turned 45 degrees inside it,
    and a small centre. Named parts, because morph matches shapes across slides
    BY NAME: give the same rosette the same name on two slides at different
    positions and PowerPoint moves it rather than cutting.
    """
    parts = []
    parts.append(_tile(slide, MSO_SHAPE.STAR_8_POINT, cx - size / 2, cy - size / 2,
                       size, star, alpha, rot, name and name + "-star"))
    d = size * 0.46
    parts.append(_tile(slide, MSO_SHAPE.DIAMOND, cx - d / 2, cy - d / 2,
                       d, inner, alpha, rot, name and name + "-in"))
    c = size * 0.16
    parts.append(_tile(slide, MSO_SHAPE.OVAL, cx - c / 2, cy - c / 2,
                       c, ring, alpha, 0, name and name + "-c"))
    return parts


def zellige_rail(slide, on_dark=False):
    """The signature strip down the left edge of every slide.

    One star per tile, not a full three-part khatam, and every one carries a
    stable name -- zRail-0, zRail-1... The names are what make this cheap:
    morph matches shapes across slides by name, so a rail whose tiles are named
    identically on both slides is recognised as unchanged and animates nothing.
    Drawn as unnamed decoration it was sixty-three shapes per slide that every
    transition had to cross-fade, and a transition that stutters on the
    amphitheatre projector is worse than no ornament at all.

    The field runs past the top and bottom edges rather than stopping politely
    inside them, the way a tiled wall runs past a doorway.
    """
    ground = Z_SAND if not on_dark else RGBColor(0x24, 0x27, 0x2C)
    _rect(slide, RAIL_X, 0, RAIL_W, SLIDE_H, fill=ground)
    colours = (Z_BLUE, Z_TURQUOISE, Z_TERRA, Z_SAFFRON)
    step = RAIL_W * 2.0
    n = int(SLIDE_H / step) + 2
    for i in range(n):
        y = -step * 0.4 + i * step
        _tile(slide, MSO_SHAPE.STAR_8_POINT, RAIL_X + RAIL_W * 0.04, y,
              RAIL_W * 0.92, colours[i % 4],
              alpha=55 if not on_dark else 45,
              rot=22.5 * (i % 2), name="zRail-%d" % i)


def zellige_band(slide, y, height, tiles=13, alpha=70, on_dark=False):
    """A horizontal course of tilework, for the hero slides.

    The reference the deck was asked to echo is a photographed mosaic band
    above plain text -- this is that band, drawn rather than photographed.
    """
    _rect(slide, 0, y, SLIDE_W, height,
          fill=Z_SAND if not on_dark else RGBColor(0x1F, 0x22, 0x27))
    step = SLIDE_W / float(tiles)
    colours = (Z_BLUE, Z_TURQUOISE, Z_TERRA, Z_SAFFRON)
    # Two shapes per tile, not three, and one course rather than two
    # interleaved: the band reads the same from four metres away and costs a
    # third of the shapes, which is what the transition into the next slide has
    # to cross-fade.
    for i in range(tiles + 1):
        _tile(slide, MSO_SHAPE.STAR_8_POINT, i * step - step / 2,
              y + height / 2 - step / 2, step, colours[i % 4],
              alpha=alpha, rot=22.5 * (i % 2), name="zBand-%d" % i)
        d = step * 0.42
        _tile(slide, MSO_SHAPE.DIAMOND, i * step - d / 2,
              y + height / 2 - d / 2, d, colours[(i + 2) % 4],
              alpha=alpha, rot=0, name="zBandIn-%d" % i)


# Where the travelling rosette sits on each slide, as a fraction of the slide:
# (x, y, size, rotation). It is the SAME named shape throughout, so morph
# carries it from one slide to the next -- small in a corner while a table is
# being read, large and turning on the slides that breathe.
HERO_STOPS = {
    "s01_cover": (0.86, 0.30, 3.6, 0),
    "s03_quote": (0.18, 0.72, 2.6, 22.5),
    "s19_demo": (0.88, 0.34, 4.4, 45),
    "s22_merci": (0.50, 0.42, 5.2, 22.5),
}
HERO_DEFAULT = (0.955, 0.115, 0.52, 0)   # the header corner, out of the way


def zellige_hero(slide, key, on_dark=False):
    """The one rosette that travels the whole deck.

    Named `zHero`, so PowerPoint's morph recognises it as the same object from
    slide to slide and animates the move instead of cutting. On content slides
    it is a small mark beside the header; on the four slides that can carry it,
    it grows, turns and bleeds off the edge.
    """
    fx, fy, size, rot = HERO_STOPS.get(key, HERO_DEFAULT)
    big = size > 1.5
    khatam(slide, SLIDE_W * fx, SLIDE_H * fy, size, name="zHero", rot=rot,
           alpha=26 if big else 85,
           star=Z_BLUE if not on_dark else Z_TURQUOISE,
           inner=Z_TURQUOISE if not on_dark else Z_BLUE,
           ring=Z_SAFFRON)


def _to_back(slide, first):
    """Push everything added since `first` behind the content.

    The ornament is drawn after the slide is built -- the builders know nothing
    about it -- so without this the cover's tile band lands on top of the two
    logos and every rosette sits over the sentence it was meant to sit behind.
    Inserted in reverse so the tiles keep their own order among themselves: a
    star must still be under its own centre dot.
    """
    tree = slide.shapes._spTree
    for shape in reversed(list(slide.shapes)[first:]):
        el = shape._element
        tree.remove(el)
        tree.insert(2, el)      # after nvGrpSpPr and grpSpPr


def zellige(slide, key, on_dark=False, band=None):
    """Dress one slide. Called once per slide, from main().

    """
    first = len(list(slide.shapes))
    zellige_rail(slide, on_dark)
    if band is not None:
        zellige_band(slide, band[0], band[1], on_dark=on_dark)
    zellige_hero(slide, key, on_dark)
    _to_back(slide, first)


def new_slide(prs, bg=PAPER):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = bg
    return slide


def header(slide, kicker, title, accent=BLUE, on_dark=False):
    """Kicker, title, and the short rule under it. Every content slide opens here."""
    ink = WHITE if on_dark else INK
    tf = _txbox(slide, MARGIN, 0.60, CONTENT_W, 0.34)
    _run(_para(tf, first=True), kicker.upper(), size=11.5, bold=True, color=accent)

    tf = _txbox(slide, MARGIN, 0.98, CONTENT_W, 0.75)
    _run(_para(tf, first=True), title, size=27, bold=True, color=ink)

    _rect(slide, MARGIN, 1.80, 1.15, 0.035, fill=accent)


# --- transitions, notes, progress ------------------------------------------

# How many numbered slides the parcours has, so the progress rule knows how far
# through the defence a slide sits. Backup slides are past the end and simply
# fill it.
DECK_LENGTH = 24


def morph(slide, seconds=0.7):
    """Morph this slide from the previous one.

    PowerPoint interpolates shapes that appear on both slides -- a title that
    moves, a card that grows -- instead of cutting. The deck reuses the same
    header block and the same card geometry throughout, so most transitions
    become a glide rather than a jump.

    python-pptx has no transition API, so this writes the XML directly. Morph
    is a 2016+ feature guarded by mc:AlternateContent: PowerPoint 2016 and
    newer read the mc:Choice and morph, everything older reads the mc:Fallback
    and fades. A deck that silently does nothing on the examiner's machine is
    worse than one that fades, which is why the fallback is not omitted.
    """
    xml = (
        '<mc:AlternateContent '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<mc:Choice '
        'xmlns:p159="http://schemas.microsoft.com/office/powerpoint/2015/09/main" '
        'Requires="p159">'
        '<p:transition '
        'xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main" '
        'spd="slow" p14:dur="%d">'
        '<p159:morph option="byObject"/>'
        '</p:transition>'
        '</mc:Choice>'
        '<mc:Fallback>'
        '<p:transition '
        'xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main" '
        'spd="slow" p14:dur="%d"><p:fade/></p:transition>'
        '</mc:Fallback>'
        '</mc:AlternateContent>'
    ) % (int(seconds * 1000), int(seconds * 1000))
    slide.element.append(parse_xml(xml))


def speaker_notes(slide, text):
    """What to say, visible only in Presenter View -- never on the projector."""
    slide.notes_slide.notes_text_frame.text = text.strip()


def progress(slide, n, on_dark=False):
    """A hairline showing how far through the defence this slide sits.

    Twenty minutes in front of a jury is easier to pace when the deck says
    where it is without anyone having to count slides. Thin and grey enough to
    ignore, which is the point: it informs the speaker, not the audience.
    """
    if not n:
        return
    done = max(0.0, min(1.0, n / float(DECK_LENGTH)))
    track = LINE if not on_dark else RGBColor(0x33, 0x36, 0x3B)
    _rect(slide, MARGIN, FOOTER_Y + 0.30, CONTENT_W, 0.015, fill=track)
    if done:
        _rect(slide, MARGIN, FOOTER_Y + 0.30, CONTENT_W * done, 0.015,
              fill=BLUE if not on_dark else RGBColor(0x4F, 0xA9, 0xF5))


def footer(slide, n, on_dark=False):
    if n is None:
        return
    c = MUTE if not on_dark else RGBColor(0x9A, 0x9A, 0x9A)
    tf = _txbox(slide, MARGIN, FOOTER_Y, CONTENT_W - 0.6, 0.22)
    _run(_para(tf, first=True), FOOTER_TEXT, size=8.5, color=c)
    tf = _txbox(slide, SLIDE_W - MARGIN - 0.6, FOOTER_Y, 0.6, 0.22)
    p = _para(tf, first=True)
    p.alignment = PP_ALIGN.RIGHT
    _run(p, str(n), size=8.5, bold=True, color=c)
    progress(slide, n, on_dark)


def bullets(slide, items, x=MARGIN, y=BODY_TOP, w=CONTENT_W, size=16.5,
            gap=13, accent=BLUE, on_dark=False):
    """items: str, or (lead, rest) where lead is emphasised."""
    ink = WHITE if on_dark else INK
    body = RGBColor(0xD8, 0xD8, 0xD8) if on_dark else GREY
    tf = _txbox(slide, x, y, w, SLIDE_H - y - 0.9)
    for i, item in enumerate(items):
        p = _para(tf, first=(i == 0))
        p.space_after = Pt(gap)
        p.line_spacing = 1.22
        _run(p, "▪  ", size=size, bold=True, color=accent)
        if isinstance(item, tuple):
            lead, rest = item
            _run(p, lead, size=size, bold=True, color=ink)
            if rest:
                _run(p, rest, size=size, color=body)
        else:
            _run(p, item, size=size, color=body)
    return tf


def image_fit(slide, path, x, y, w, h, frame=False):
    """Place an image contained in the box, centred, aspect preserved."""
    iw, ih = Image.open(path).size
    scale = min(w / iw, h / ih)
    dw, dh = iw * scale, ih * scale
    px, py = x + (w - dw) / 2, y + (h - dh) / 2
    if frame:
        pad = 0.055
        _rect(slide, px - pad, py - pad, dw + 2 * pad, dh + 2 * pad, fill=WHITE, line=LINE, line_w=0.9)
    slide.shapes.add_picture(str(path), Inches(px), Inches(py), Inches(dw), Inches(dh))
    return py + dh  # bottom edge, so a caption can sit right under the image


def caption(slide, text, x, y, w, align=PP_ALIGN.CENTER):
    tf = _txbox(slide, x, y, w, 0.28)
    p = _para(tf, first=True)
    p.alignment = align
    _run(p, text, size=10, color=MUTE, italic=True)


_NO_STYLE = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"


def table(slide, headers, rows, x, y, w, col_w=None, size=12.5,
          head_bg=INK, row_h=0.34, head_h=0.38, emphasis=()):
    """A table that does not look like PowerPoint's default banded blue."""
    n_r, n_c = len(rows) + 1, len(headers)
    gfx = slide.shapes.add_table(n_r, n_c, Inches(x), Inches(y), Inches(w),
                                 Inches(head_h + row_h * len(rows)))
    tbl = gfx.table

    # drop the inherited style so our own fills are the only ones showing
    tblPr = tbl._tbl.tblPr
    for e in tblPr.findall(qn("a:tableStyleId")):
        tblPr.remove(e)
    el = tblPr.makeelement(qn("a:tableStyleId"), {})
    el.text = _NO_STYLE
    tblPr.append(el)
    tbl.first_row = False
    tbl.horz_banding = False

    if col_w:
        total = sum(col_w)
        for i, cw in enumerate(col_w):
            tbl.columns[i].width = Emu(int(Inches(w) * cw / total))

    tbl.rows[0].height = Inches(head_h)
    for i in range(len(rows)):
        tbl.rows[i + 1].height = Inches(row_h)

    def fill(cell, text, bold, color, bg, align):
        cell.fill.solid()
        cell.fill.fore_color.rgb = bg
        cell.margin_left = cell.margin_right = Inches(0.10)
        cell.margin_top = cell.margin_bottom = Inches(0.03)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf = cell.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = align
        _run(p, text, size=size, bold=bold, color=color)

    for c, htxt in enumerate(headers):
        fill(tbl.cell(0, c), htxt, True, WHITE, head_bg,
             PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER)

    for r, row in enumerate(rows):
        hot = r in emphasis
        bg = RGBColor(0xE8, 0xF3, 0xFD) if hot else (WASH if r % 2 else WHITE)
        for c, val in enumerate(row):
            fill(tbl.cell(r + 1, c), str(val), hot, INK if hot else GREY, bg,
                 PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER)
    return tbl


def stats(slide, items, y=BODY_TOP, x=MARGIN, w=CONTENT_W, h=1.55,
          value_size=34, label_size=11, accent=BLUE):
    """A row of big numbers. items: (value, label)."""
    n = len(items)
    gap = 0.22
    cw = (w - gap * (n - 1)) / n
    for i, (val, lab) in enumerate(items):
        cx = x + i * (cw + gap)
        _rect(slide, cx, y, cw, h, fill=WASH)
        _rect(slide, cx, y, cw, 0.045, fill=accent)
        tf = _txbox(slide, cx + 0.20, y + 0.30, cw - 0.40, 0.62)
        _run(_para(tf, first=True), val, size=value_size, bold=True, color=INK)
        tf = _txbox(slide, cx + 0.20, y + 0.98, cw - 0.40, 0.48)
        p = _para(tf, first=True)
        p.line_spacing = 1.12
        _run(p, lab, size=label_size, color=GREY)


def note(slide, text, y, accent=GREEN, x=MARGIN, w=CONTENT_W, size=13.5, h=0.52):
    """A single emphasised takeaway, left-ruled. One per slide, at most."""
    _rect(slide, x, y, 0.035, h, fill=accent)
    tf = _txbox(slide, x + 0.24, y + 0.03, w - 0.24, h - 0.02)
    p = _para(tf, first=True)
    p.line_spacing = 1.18
    _run(p, text, size=size, color=INK)


def box(slide, x, y, w, h, title, sub=None, accent=BLUE, fill=WASH,
        title_size=12.5, sub_size=9.5):
    """A labelled card, the unit the native diagrams are built from."""
    _rect(slide, x, y, w, h, fill=fill)
    _rect(slide, x, y, w, 0.04, fill=accent)
    tf = _txbox(slide, x + 0.14, y + 0.20, w - 0.28, 0.34)
    p = _para(tf, first=True)
    p.alignment = PP_ALIGN.CENTER
    p.line_spacing = 1.06
    _run(p, title, size=title_size, bold=True, color=INK)
    if sub:
        tf = _txbox(slide, x + 0.12, y + 0.20 + 0.30 * (1 + title.count("\n")), w - 0.24, h - 0.6)
        p = _para(tf, first=True)
        p.alignment = PP_ALIGN.CENTER
        p.line_spacing = 1.12
        _run(p, sub, size=sub_size, color=GREY)


def arrow(slide, x, y, w, h, right=True, color=None):
    shape = MSO_SHAPE.RIGHT_ARROW if right else MSO_SHAPE.DOWN_ARROW
    sh = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.shadow.inherit = False
    sh.fill.solid()
    sh.fill.fore_color.rgb = color or RGBColor(0xC3, 0xC7, 0xC9)
    sh.line.fill.background()
    return sh


# --- slides ----------------------------------------------------------------


def s01_cover(prs):
    slide = new_slide(prs)
    _rect(slide, 0, 0, SLIDE_W, 0.10, fill=GREEN)
    _rect(slide, 0, SLIDE_H - 0.10, SLIDE_W, 0.10, fill=BLUE)

    slide.shapes.add_picture(str(ASSETS / "logo-emsi.png"), Inches(MARGIN), Inches(0.62), height=Inches(0.72))
    ai = Image.open(ASSETS / "logo-aznet.png")
    ah = 0.78
    aw = ah * ai.size[0] / ai.size[1]
    slide.shapes.add_picture(str(ASSETS / "logo-aznet.png"),
                             Inches(SLIDE_W - MARGIN - aw), Inches(0.59), height=Inches(ah))

    tf = _txbox(slide, MARGIN, 1.78, CONTENT_W, 0.6)
    p = _para(tf, first=True)
    p.line_spacing = 1.3
    _run(p, "ÉCOLE MAROCAINE DES SCIENCES DE L'INGÉNIEUR — RABAT", size=11.5, bold=True, color=GREY)
    p = _para(tf)
    _run(p, "Rapport de Projet de Fin d'Études — diplôme d'Ingénieur d'État", size=11.5, color=MUTE)

    _rect(slide, MARGIN, 2.62, 1.6, 0.05, fill=GREEN)

    tf = _txbox(slide, MARGIN, 2.92, CONTENT_W - 0.5, 1.5)
    p = _para(tf, first=True)
    p.line_spacing = 1.14
    _run(p, "Automatisation des rapports journaliers\nde chantier par intelligence artificielle", size=33, bold=True, color=INK)

    tf = _txbox(slide, MARGIN, 4.44, CONTENT_W - 0.5, 0.4)
    _run(_para(tf, first=True), "Transcription de notes vocales en darija et extraction structurée",
         size=16, color=BLUE)

    tf = _txbox(slide, MARGIN, 5.30, 6.4, 1.3)
    for i, (k, v) in enumerate([
        ("Réalisé par", "Yassine [À COMPLÉTER — NOM]"),
        ("Encadrant académique", "[À COMPLÉTER]"),
        ("Encadrant industriel", "[À COMPLÉTER]"),
    ]):
        p = _para(tf, first=(i == 0))
        p.space_after = Pt(5)
        _run(p, f"{k} : ", size=12.5, bold=True, color=INK)
        _run(p, v, size=12.5, color=GREY)

    tf = _txbox(slide, SLIDE_W - MARGIN - 4.2, 5.30, 4.2, 1.3)
    for i, (k, v) in enumerate([
        ("Entreprise d'accueil", "AZNET — Rabat"),
        ("Soutenu le", "[À COMPLÉTER]"),
        ("Année universitaire", "2025 / 2026"),
    ]):
        p = _para(tf, first=(i == 0))
        p.space_after = Pt(5)
        p.alignment = PP_ALIGN.RIGHT
        _run(p, f"{k} : ", size=12.5, bold=True, color=INK)
        _run(p, v, size=12.5, color=GREY)


def s02_plan(prs, n):
    slide = new_slide(prs)
    header(slide, "Sommaire", "Plan de la présentation")
    items = [
        ("1", "Contexte et problématique", "Le terrain, les trois verrous techniques, les besoins"),
        ("2", "État de l'art", "Le darija comme langue peu dotée, extraction par LLM"),
        ("3", "Conception", "Architecture hybride, flux nominal, journal de chantier"),
        ("4", "Banc d'essai des moteurs de transcription", "Treize moteurs, une hypothèse renversée"),
        ("5", "Réalisation et qualité", "Périmètre livré, tableau de bord, chaîne DevOps"),
        ("6", "Démonstration, bilan et perspectives", ""),
    ]
    y = BODY_TOP - 0.05
    for num, title, sub in items:
        _rect(slide, MARGIN, y, 0.42, 0.42, fill=BLUE)
        tf = _txbox(slide, MARGIN, y + 0.085, 0.42, 0.3)
        p = _para(tf, first=True)
        p.alignment = PP_ALIGN.CENTER
        _run(p, num, size=14, bold=True, color=WHITE)

        tf = _txbox(slide, MARGIN + 0.66, y + 0.01, CONTENT_W - 0.7, 0.5)
        p = _para(tf, first=True)
        _run(p, title, size=17, bold=True, color=INK)
        if sub:
            p = _para(tf)
            _run(p, sub, size=12.5, color=MUTE)
        y += 0.78
    footer(slide, n)


def s03_quote(prs, _n):
    """Placed before any architecture: the jury meets the human stake first.

    The quote is the thesis of the whole project in one sentence -- the system
    exists so a technician reports in the language he actually thinks in,
    instead of translating himself into a form.
    """
    slide = new_slide(prs)
    # Full bleed, no footer and no rule: the artwork already carries the quote
    # and its attribution, and a page number laid over it would read as an
    # accident. The tie back to the project is spoken, not printed -- a caption
    # explaining the slide would compete with the one line it exists to show.
    img = ASSETS / "quote-wittgenstein.png"
    iw, ih = Image.open(img).size
    assert abs(iw / ih - SLIDE_W / SLIDE_H) < 0.02, (
        f"{img.name} is {iw}x{ih} ({iw / ih:.2f}); a full-bleed slide needs 16:9"
    )
    slide.shapes.add_picture(str(img), 0, 0, Inches(SLIDE_W), Inches(SLIDE_H))


def s03_contexte(prs, n):
    slide = new_slide(prs)
    header(slide, "1 — Contexte", "AZNET et la remontée d'information du terrain")
    bullets(slide, [
        ("Le métier. ", "Infrastructures réseau et câblage informatique : goulottes, tirage et raccordement cuivre et fibre, équipement de bureaux, de panneaux de brassage et de locaux techniques."),
        ("Le terrain. ", "Les équipes passent la journée sur les chantiers, loin de tout outil bureautique."),
        ("Le maillon faible. ", "Les comptes rendus remontent oralement, par messages dispersés ou sur papier — quand ils ne sont pas omis."),
        ("La langue de travail. ", "L'arabe marocain (darija), mêlé de vocabulaire technique français."),
    ], w=CONTENT_W, size=16)
    note(slide, "Le directeur tient déjà un fichier de suivi. Le problème n'est pas l'absence d'outil, c'est le coût de la saisie pour celui qui détient l'information.", y=5.55)
    footer(slide, n)


def s04_problematique(prs, n):
    slide = new_slide(prs)
    header(slide, "1 — Problématique", "Trois verrous techniques")

    tf = _txbox(slide, MARGIN, BODY_TOP - 0.02, CONTENT_W, 0.9)
    p = _para(tf, first=True)
    p.line_spacing = 1.22
    _run(p, "Comment transformer automatiquement une note vocale spontanée en darija en un rapport journalier structuré, fiable et exploitable, ", size=17, color=INK)
    _run(p, "en moins de deux minutes d'effort pour le technicien et sans budget logiciel", size=17, bold=True, color=BLUE)
    _run(p, " ?", size=17, color=INK)

    cards = [
        ("Transcription", "Les moteurs de reconnaissance vocale sont entraînés sur l'arabe standard moderne. Le darija est une langue peu dotée, au code-switching arabe / français fréquent."),
        ("Structuration", "Le texte transcrit est du langage libre. Il faut en extraire des champs normalisés — quantités, localisations, observations — sans jamais inventer une donnée absente."),
        ("Intégration", "La chaîne complète — messagerie, téléchargement, traitement IA, journal, notifications — doit fonctionner de bout en bout, de manière fiable et gratuite."),
    ]
    y = 3.30
    gap = 0.28
    cw = (CONTENT_W - 2 * gap) / 3
    for i, (t, d) in enumerate(cards):
        cx = MARGIN + i * (cw + gap)
        _rect(slide, cx, y, cw, 2.45, fill=WASH)
        _rect(slide, cx, y, cw, 0.05, fill=BLUE)
        tf = _txbox(slide, cx + 0.24, y + 0.30, cw - 0.48, 0.34)
        _run(_para(tf, first=True), f"0{i + 1}", size=13, bold=True, color=BLUE)
        tf = _txbox(slide, cx + 0.24, y + 0.62, cw - 0.48, 0.34)
        _run(_para(tf, first=True), t, size=17, bold=True, color=INK)
        tf = _txbox(slide, cx + 0.24, y + 1.05, cw - 0.48, 1.2)
        p = _para(tf, first=True)
        p.line_spacing = 1.2
        _run(p, d, size=12, color=GREY)
    footer(slide, n)


def s05_besoins(prs, n):
    slide = new_slide(prs)
    header(slide, "1 — Besoins", "Ce que le cahier des charges exige")
    left = [
        ("BF1 ", "Saisie vocale en darija via une messagerie — aucune autre action demandée au technicien"),
        ("BF2 ", "Un second canal alimente le même traitement"),
        ("BF3 ", "Transcription automatique, darija et mélange arabe / français"),
        ("BF4 ", "Extraction des travaux réalisés et des quantités"),
    ]
    right = [
        ("BF5 ", "Reformulation en français professionnel"),
        ("BF6 ", "Enregistrement dans le tableau de suivi Google Sheets"),
        ("BF7 ", "Notification du chef de chantier et du responsable"),
        ("BF8 ", "Confirmation au technicien que son rapport est traité"),
    ]
    half = (CONTENT_W - 0.6) / 2
    bullets(slide, left, x=MARGIN, w=half, size=14, gap=11)
    bullets(slide, right, x=MARGIN + half + 0.6, w=half, size=14, gap=11)

    y = 4.55
    _rect(slide, MARGIN, y, CONTENT_W, 1.45, fill=WASH)
    _rect(slide, MARGIN, y, 0.05, 1.45, fill=GREEN)
    tf = _txbox(slide, MARGIN + 0.32, y + 0.24, CONTENT_W - 0.64, 0.35)
    _run(_para(tf, first=True), "La contrainte structurante : budget zéro", size=17, bold=True, color=INK)
    tf = _txbox(slide, MARGIN + 0.32, y + 0.66, CONTENT_W - 0.64, 0.65)
    p = _para(tf, first=True)
    p.line_spacing = 1.2
    _run(p, "Aucune dépense logicielle autorisée. Toute la solution repose sur des paliers gratuits — Groq, Gemini AI Studio, Telegram Bot API, WhatsApp Cloud API, Google Sheets, Gmail SMTP — et sur du matériel déjà disponible. Cette contrainte n'est pas un détail d'intendance : elle dicte l'architecture, impose des chaînes de repli entre fournisseurs, et interdit la solution évidente à chaque étape.", size=12.5, color=GREY)
    footer(slide, n)


def s06_etat_art_stt(prs, n):
    slide = new_slide(prs)
    header(slide, "2 — État de l'art", "Reconnaissance vocale de l'arabe dialectal")
    bullets(slide, [
        ("Une langue peu dotée. ", "Le darija n'a ni orthographe normalisée, ni corpus annoté de grande taille. Il emprunte massivement au français pour le vocabulaire technique — précisément celui que le rapport doit conserver."),
        ("Deux architectures concurrentes. ", "Whisper, transformeur encodeur-décodeur de bout en bout, entraîné en multitâche sur 680 000 h ; wav2vec2 pré-entraîné de manière auto-supervisée puis affiné par classification temporelle connexionniste (CTC)."),
        ("Les affinages darija. ", "Plusieurs modèles publics existent sur Hugging Face, de quelques dizaines de millions à deux milliards de paramètres. Leur qualité réelle sur un usage métier n'est documentée nulle part."),
    ], size=15)

    _rect(slide, MARGIN, 5.28, CONTENT_W, 1.28, fill=WASH)
    _rect(slide, MARGIN, 5.28, 0.05, 1.28, fill=GREEN)
    tf = _txbox(slide, MARGIN + 0.32, 5.50, CONTENT_W - 0.64, 0.9)
    p = _para(tf, first=True)
    p.line_spacing = 1.2
    _run(p, "Les métriques standard. ", size=13.5, bold=True, color=INK)
    _run(p, "WER et CER comparent la transcription à une vérité terrain, mot à mot ou caractère à caractère. Pour une langue sans orthographe normalisée, deux transcriptions également correctes divergent sur l'écriture — et le WER punit cette divergence exactement comme une erreur de sens. Ce constat commande la méthode du banc d'essai (section 4).", size=13.5, color=GREY)
    footer(slide, n)


def s07_etat_art_llm(prs, n):
    slide = new_slide(prs)
    header(slide, "2 — État de l'art", "Extraction par LLM et plateformes d'orchestration")

    tf = _txbox(slide, MARGIN, BODY_TOP - 0.05, CONTENT_W, 0.3)
    _run(_para(tf, first=True), "Extraction d'information structurée", size=15, bold=True, color=BLUE)
    bullets(slide, [
        "Les approches classiques — règles, expressions régulières, modèles de reconnaissance d'entités — supposent une langue régulière et un vocabulaire fermé : ni l'un ni l'autre ici.",
        "Les LLM à sortie contrainte produisent directement un objet conforme à un schéma. Le risque se déplace : ce n'est plus l'échec de l'extraction, c'est l'invention plausible d'une valeur absente.",
    ], y=2.42, size=13.5, gap=9)

    tf = _txbox(slide, MARGIN, 3.62, CONTENT_W, 0.3)
    _run(_para(tf, first=True), "Plateformes d'orchestration", size=15, bold=True, color=BLUE)
    table(slide,
          ["Critère", "n8n", "Make", "Zapier"],
          [["Auto-hébergement", "Oui", "Non", "Non"],
           ["Coût à ce volume", "Gratuit", "Palier limité", "Palier limité"],
           ["Appels HTTP libres", "Oui", "Oui", "Restreint"],
           ["Contrôle des données", "Total", "Hébergé", "Hébergé"]],
          x=MARGIN, y=3.98, w=CONTENT_W, col_w=[3.4, 1.5, 1.5, 1.5], size=12, row_h=0.33)
    note(slide, "n8n est retenu pour une raison unique et vérifiable : c'est le seul auto-hébergeable, donc le seul compatible avec la contrainte de budget zéro à volume non plafonné.", y=5.98)
    footer(slide, n)


def s08_architecture(prs, n):
    """Drawn natively rather than reusing the report figure.

    diagrams/01-architecture.png is 1249x1698 -- portrait, laid out for an A4
    page. Dropped on a 16:9 slide its height is the binding constraint, the
    labels end up around 6 pt, and nothing is readable from the back of a room.
    """
    slide = new_slide(prs)
    header(slide, "3 — Conception", "Architecture générale : une répartition par valeur ajoutée")

    y = 2.22
    h = 1.62

    aw = 0.34
    n_box = 5
    w = (CONTENT_W - (n_box - 1) * (aw + 0.20)) / n_box

    chain = [
        ("Terrain", "Technicien\nnote vocale en darija,\nphoto ou texte", GREY),
        ("Réception", "Telegram Bot API\nWhatsApp Cloud API", GREEN),
        ("Orchestration", "n8n — 65 nœuds\nréception, déduplication,\nautorisation, réponses", GREEN),
        ("Service applicatif", "FastAPI — 66 routes\nSTT, extraction, journal,\nordonnanceur, comptes", BLUE),
        ("Persistance", "PostgreSQL — 11 tables\nGoogle Sheets\nun onglet par chantier", BLUE),
    ]
    x = MARGIN
    for i, (title, sub, accent) in enumerate(chain):
        box(slide, x, y, w, h, title, sub, accent=accent, title_size=13, sub_size=9.5)
        if i < len(chain) - 1:
            arrow(slide, x + w + 0.10, y + h / 2 - 0.11, aw, 0.22)
        x += w + aw + 0.20

    y2 = 4.42
    h2 = 1.05
    bw = (CONTENT_W - 0.5) / 2
    box(slide, MARGIN, y2, bw, h2, "Moteur local — sidecar GPU",
        "Morocco-Darija-STT-large sur RTX 3070, chargé à la première demande",
        accent=RGBColor(0x8E, 0x44, 0xAD), title_size=12, sub_size=9.5)
    box(slide, MARGIN + bw + 0.5, y2, bw, h2, "Consultation",
        "Tableau de bord React FR / EN / AR  ·  rapports quotidien et hebdomadaire par e-mail",
        accent=RGBColor(0x8E, 0x44, 0xAD), title_size=12, sub_size=9.5)

    note(slide, "Ce qui est intégration reste dans n8n ; ce qui est décision passe dans le service. La frontière est fonctionnelle, et elle a bougé une fois en cours de projet.",
         y=5.78, accent=BLUE, size=13)
    footer(slide, n)


def s09_frontiere(prs, n):
    slide = new_slide(prs)
    header(slide, "3 — Conception", "La frontière entre orchestration et code")

    half = (CONTENT_W - 0.55) / 2
    for i, (title, color, rows) in enumerate([
        ("n8n — orchestration", GREEN, [
            "Réception Telegram et WhatsApp",
            "Vérification du webhook Meta",
            "Déduplication des messages",
            "Téléchargement des médias",
            "Réponses au technicien",
            "Journalisation d'étape",
        ]),
        ("FastAPI — service métier", BLUE, [
            "Transcription et extraction",
            "Reformulation en français",
            "Tenue du journal de chantier",
            "Ordonnancement des tâches",
            "Authentification et comptes",
            "Service du tableau de bord",
        ]),
    ]):
        cx = MARGIN + i * (half + 0.55)
        _rect(slide, cx, BODY_TOP, half, 2.95, fill=WASH)
        _rect(slide, cx, BODY_TOP, half, 0.05, fill=color)
        tf = _txbox(slide, cx + 0.26, BODY_TOP + 0.26, half - 0.5, 0.32)
        _run(_para(tf, first=True), title, size=16.5, bold=True, color=INK)
        tf = _txbox(slide, cx + 0.26, BODY_TOP + 0.70, half - 0.5, 2.1)
        for j, r in enumerate(rows):
            p = _para(tf, first=(j == 0))
            p.space_after = Pt(6)
            _run(p, "–  ", size=12.5, color=color)
            _run(p, r, size=12.5, color=GREY)

    y = 5.28
    _rect(slide, MARGIN, y, CONTENT_W, 1.26, fill=INK)
    tf = _txbox(slide, MARGIN + 0.34, y + 0.22, CONTENT_W - 0.68, 0.9)
    p = _para(tf, first=True)
    p.line_spacing = 1.2
    _run(p, "La règle retenue : ", size=14.5, bold=True, color=WHITE)
    _run(p, "ce qui est ", size=14.5, color=RGBColor(0xDD, 0xDD, 0xDD))
    _run(p, "intégration", size=14.5, bold=True, color=WHITE)
    _run(p, " reste dans n8n ; ce qui est ", size=14.5, color=RGBColor(0xDD, 0xDD, 0xDD))
    _run(p, "décision", size=14.5, bold=True, color=WHITE)
    _run(p, " passe dans le service.", size=14.5, color=RGBColor(0xDD, 0xDD, 0xDD))
    p = _para(tf)
    p.line_spacing = 1.2
    _run(p, "La frontière a bougé une fois, le 5 août : l'écriture Google Sheets a migré de n8n vers Python, car tenir le journal exige un lire-modifier-écrire qu'un nœud conditionnel ne sait pas exprimer.",
         size=12, color=RGBColor(0xBB, 0xBB, 0xBB))
    footer(slide, n)


def s10_flux(prs, n):
    """The report's figure here is a sequence diagram -- inherently tall, and
    illegible once scaled to a slide. The seven steps are the message; they are
    drawn directly."""
    slide = new_slide(prs)
    header(slide, "3 — Conception", "Flux nominal : sept étapes, et un ordre qui n'est pas négociable")

    steps = [
        ("1", "Envoi", "Le technicien envoie une note vocale, une photo ou un texte sur Telegram ou WhatsApp.", GREY),
        ("2", "Réclamation", "n8n réclame l'identifiant du message au service — WhatsApp re-livre un webhook non acquitté.", GREY),
        ("3", "Identification", "L'expéditeur est retrouvé dans l'organigramme, son autorisation et son chantier vérifiés.", GREY),
        ("4", "Traitement", "POST /process : transcription, extraction contrainte, résumé français, avertissements.", GREY),
        ("5", "Réponse", "n8n répond au technicien avec son résumé.", GREEN),
        ("6", "Journal", "Ensuite seulement : POST /journal fusionne la ligne dans l'onglet du chantier.", GREEN),
        ("7", "Notification", "Les responsables sont notifiés.", GREY),
    ]

    y, h, gap = 2.20, 1.32, 0.22
    top, bottom = steps[:4], steps[4:]
    w4 = (CONTENT_W - 3 * gap) / 4
    for i, (num, title, desc, accent) in enumerate(top):
        x = MARGIN + i * (w4 + gap)
        _step_card(slide, x, y, w4, h, num, title, desc, accent)

    y2 = y + h + 0.30
    w3 = (CONTENT_W - 2 * gap) / 3
    for i, (num, title, desc, accent) in enumerate(bottom):
        x = MARGIN + i * (w3 + gap)
        _step_card(slide, x, y2, w3, h, num, title, desc, accent)

    note(slide, "L'ordre de 5 et 6 est un invariant, pas une préférence : une écriture Google Sheets qui échoue est garée dans une file de reprise et rejouée toutes les cinq minutes — elle ne coûte jamais au technicien son accusé de réception.",
         y=5.52, accent=BLUE, size=13, h=0.72)
    footer(slide, n)


def _step_card(slide, x, y, w, h, num, title, desc, accent):
    hot = accent is GREEN
    _rect(slide, x, y, w, h, fill=RGBColor(0xE9, 0xF5, 0xEC) if hot else WASH)
    _rect(slide, x, y, w, 0.04, fill=accent)
    _rect(slide, x + 0.16, y + 0.20, 0.34, 0.34, fill=accent)
    tf = _txbox(slide, x + 0.16, y + 0.255, 0.34, 0.26)
    p = _para(tf, first=True)
    p.alignment = PP_ALIGN.CENTER
    _run(p, num, size=12.5, bold=True, color=WHITE)
    tf = _txbox(slide, x + 0.60, y + 0.25, w - 0.75, 0.28)
    _run(_para(tf, first=True), title, size=13.5, bold=True, color=INK)
    tf = _txbox(slide, x + 0.16, y + 0.66, w - 0.32, h - 0.78)
    p = _para(tf, first=True)
    p.line_spacing = 1.14
    _run(p, desc, size=10.5, color=GREY)


def s11_journal(prs, n):
    slide = new_slide(prs)
    header(slide, "3 — Conception", "Le journal de chantier : deux règles qui le rendent juste")

    lw = CONTENT_W * 0.53
    tf = _txbox(slide, MARGIN, 2.02, lw, 0.28)
    _run(_para(tf, first=True), "Règle 1 — accumulation", size=14.5, bold=True, color=BLUE)

    mw = (lw - 0.28) / 2
    for i, (hdr, body) in enumerate([
        ("Message  08h12", "goulotte 120 m\nétage RDC"),
        ("Message  17h40", "goulotte 80 m\nétage E1"),
    ]):
        x = MARGIN + i * (mw + 0.28)
        _rect(slide, x, 2.38, mw, 0.98, fill=WASH)
        tf = _txbox(slide, x + 0.16, 2.50, mw - 0.32, 0.24)
        _run(_para(tf, first=True), hdr, size=10.5, bold=True, color=MUTE)
        tf = _txbox(slide, x + 0.16, 2.78, mw - 0.32, 0.5)
        p = _para(tf, first=True)
        p.line_spacing = 1.14
        _run(p, body, size=12, color=INK)

    arrow(slide, MARGIN + lw / 2 - 0.13, 3.48, 0.26, 0.34, right=False, color=BLUE)

    _rect(slide, MARGIN, 3.94, lw, 1.02, fill=RGBColor(0xE8, 0xF3, 0xFD))
    _rect(slide, MARGIN, 3.94, lw, 0.04, fill=BLUE)
    tf = _txbox(slide, MARGIN + 0.16, 4.10, lw - 0.32, 0.24)
    _run(_para(tf, first=True), "Une seule ligne  —  12/08, technicien X", size=10.5, bold=True, color=BLUE)
    tf = _txbox(slide, MARGIN + 0.16, 4.38, lw - 0.32, 0.5)
    p = _para(tf, first=True)
    p.line_spacing = 1.14
    _run(p, "goulotte 200 m", size=12.5, bold=True, color=INK)
    _run(p, "   ·   étages RDC + E1", size=12.5, color=INK)

    tf = _txbox(slide, MARGIN, 5.10, lw, 1.1)
    p = _para(tf, first=True)
    p.line_spacing = 1.18
    _run(p, "Les nombres s'ajoutent, les localisations s'unissent, la prose s'ajoute. ", size=11.5, color=GREY)
    _run(p, "Une seconde ligne doublerait les jours-hommes et fausserait la ligne de totaux — le seul chiffre que le directeur lit.", size=11.5, bold=True, color=INK)

    rx = MARGIN + lw + 0.55
    rw = CONTENT_W - lw - 0.55
    tf = _txbox(slide, rx, 2.02, rw, 0.28)
    _run(_para(tf, first=True), "Règle 2 — réconciliation de stock", size=14.5, bold=True, color=GREEN)

    tf = _txbox(slide, rx, 2.42, rw, 2.4)
    for i, (t, d) in enumerate([
        ("La référence", "dernier stock connu moins l'installé."),
        ("Un chiffre rapporté l'emporte toujours", "et devient la nouvelle référence."),
        ("Un écart émet un avertissement chiffré", "au lieu de choisir silencieusement."),
    ]):
        p = _para(tf, first=(i == 0))
        p.space_after = Pt(11)
        p.line_spacing = 1.18
        _run(p, "▪  ", size=12.5, bold=True, color=GREEN)
        _run(p, t + " ", size=12.5, bold=True, color=INK)
        _run(p, d, size=12.5, color=GREY)

    _rect(slide, rx, 4.42, rw, 1.78, fill=INK)
    tf = _txbox(slide, rx + 0.28, 4.62, rw - 0.56, 1.4)
    p = _para(tf, first=True)
    p.line_spacing = 1.22
    _run(p, "Une livraison et une perte sont identiques pour l'arithmétique. ", size=12.5, bold=True, color=WHITE)
    _run(p, "Le système ne peut pas trancher, donc il ne tranche pas : il écrit l'écart et son montant, et laisse un humain décider. C'est la même règle que partout ailleurs dans la chaîne — jamais d'échec silencieux, jamais de valeur devinée.", size=12.5, color=RGBColor(0xC0, 0xC0, 0xC0))
    footer(slide, n)


def s12_banc_protocole(prs, n):
    slide = new_slide(prs)
    header(slide, "4 — Banc d'essai", "Protocole, et une décision de méthode assumée")
    stats(slide, [("13", "moteurs de transcription\névalués"),
                  ("11", "clips réels de\ntechniciens"),
                  ("3 + 12", "par API\net en local sur GPU"),
                  ("RTX 3070", "8 Go, demi-précision")], y=BODY_TOP - 0.02, h=1.45)

    y = 3.72
    _rect(slide, MARGIN, y, CONTENT_W, 2.10, fill=WASH)
    _rect(slide, MARGIN, y, 0.05, 2.10, fill=GREEN)
    tf = _txbox(slide, MARGIN + 0.34, y + 0.24, CONTENT_W - 0.68, 0.34)
    _run(_para(tf, first=True), "Ni WER, ni CER — et pourquoi", size=17, bold=True, color=INK)
    tf = _txbox(slide, MARGIN + 0.34, y + 0.68, CONTENT_W - 0.68, 1.3)
    p = _para(tf, first=True)
    p.line_spacing = 1.22
    _run(p, "Établir une vérité terrain en darija suppose une orthographe de référence qui n'existe pas : deux transcriptions également justes divergent sur l'écriture, et le WER punit cette divergence comme une erreur de sens. Le critère retenu est donc ", size=13.5, color=GREY)
    _run(p, "applicatif", size=13.5, bold=True, color=INK)
    _run(p, " — la préservation des quantités numériques et des emprunts techniques français — jugé par un locuteur natif contre l'audio, parce que c'est exactement ce que le journal consomme. La limite est assumée : le classement est rigoureux mais non reproductible par un tiers sans le même locuteur.", size=13.5, color=GREY)
    footer(slide, n)


def s13_banc_api(prs, n):
    slide = new_slide(prs)
    header(slide, "4 — Banc d'essai", "Résultats — moteurs accessibles par API")
    table(slide,
          ["Moteur", "Clips", "Erreurs", "Latence moy.", "Confiance", "Caractères"],
          [["Groq (Whisper large-v3)", "11", "0", "1,53 s", "0,483", "613"],
           ["Gemini", "11", "0", "16,94 s", "non exposée", "20 651 *"],
           ["Hugging Face (affinage darija)", "11", "11", "—", "—", "jeton absent"]],
          x=MARGIN, y=BODY_TOP, w=CONTENT_W, col_w=[3.6, 1.0, 1.0, 1.5, 1.4, 1.4],
          size=13, row_h=0.42, head_h=0.44)
    caption(slide, "Tableau 4.2 — Comparaison des moteurs par API (7 août 2026). * chiffre faussé par une boucle de répétition du modèle.",
            MARGIN, 3.88, CONTENT_W, align=PP_ALIGN.LEFT)

    y = 4.28
    _rect(slide, MARGIN, y, CONTENT_W, 1.95, fill=WASH)
    _rect(slide, MARGIN, y, 0.05, 1.95, fill=BLUE)
    tf = _txbox(slide, MARGIN + 0.34, y + 0.20, CONTENT_W - 0.68, 0.34)
    _run(_para(tf, first=True), "Le constat majeur : le moteur le plus rapide déforme les quantités", size=16.5, bold=True, color=INK)
    tf = _txbox(slide, MARGIN + 0.34, y + 0.62, CONTENT_W - 0.68, 1.2)
    p = _para(tf, first=True)
    p.line_spacing = 1.25
    _run(p, "Sur un même clip — Gemini : ", size=13, color=GREY)
    _run(p, ar("40 كابل") + " · " + ar("12 پانُو") + " · 3ème étage", size=13, bold=True, color=INK)
    _run(p, "   contre Groq : ", size=13, color=GREY)
    _run(p, "mniya dyal panno, Pouzina ssimetro, 3O mietage", size=13, bold=True, color=RGBColor(0xC0, 0x39, 0x2B))
    p = _para(tf)
    p.line_spacing = 1.25
    _run(p, "Le schéma métier est intégralement composé de quantités et de localisations. Un moteur qui fusionne un chiffre dans le mot suivant ne donne rien à extraire — et le système conclut alors « aucune donnée » sur un rapport qui en contenait.", size=13, color=GREY)
    footer(slide, n)


def s14_banc_local(prs, n):
    slide = new_slide(prs)
    header(slide, "4 — Banc d'essai", "Résultats locaux : la confiance du modèle est un leurre")
    table(slide,
          ["Modèle", "Latence", "Confiance", "Caractères", "Chiffres"],
          [["boumehdi/wav2vec2-moroccan-darija", "0,7 s", "0,916", "501", "0"],
           ["amineouaki/xlsr-53-darija-combined", "6,3 s", "0,884", "493", "7"],
           ["amineouaki/wav2vec2-darija-combined", "4,0 s", "0,853", "439", "22"],
           ["ychafiqui/whisper-medium-darija", "3,7 s", "0,843", "184", "0"],
           ["BounharAbdelaziz/Morocco-Darija-STT-large", "7,7 s", "0,791", "249", "45"],
           ["openai/whisper-large-v3  (contrôle)", "5,7 s", "0,582", "214", "55"],
           ["C-Ilyas/whisper-base-darija", "5,0 s", "0,548", "0", "0"]],
          x=MARGIN, y=BODY_TOP - 0.05, w=CONTENT_W, col_w=[4.6, 1.3, 1.3, 1.4, 1.2],
          size=12, row_h=0.335, head_h=0.38, emphasis=(4,))
    caption(slide, "Tableau 4.3 — Extrait de la campagne locale (12 moteurs, 11 clips, RTX 3070). Tri par confiance décroissante.",
            MARGIN, 4.72, CONTENT_W, align=PP_ALIGN.LEFT)

    y = 5.14
    _rect(slide, MARGIN, y, CONTENT_W, 1.42, fill=INK)
    tf = _txbox(slide, MARGIN + 0.34, y + 0.24, CONTENT_W - 0.68, 1.0)
    p = _para(tf, first=True)
    p.line_spacing = 1.25
    _run(p, "Le tableau est trié par confiance précisément pour montrer qu'il ne faut pas s'y fier. ", size=13.5, bold=True, color=WHITE)
    _run(p, "boumehdi domine la colonne à 0,916 et perd purement et simplement le « 40 » ; le meilleur moteur n'arrive qu'en cinquième position. exp(mean logprob) mesure la certitude du décodeur, jamais son exactitude — et la colonne « chiffres » est elle-même un leurre, les affinages écrivant les nombres en toutes lettres arabes ("
         + ar("ربعين") + " pour 40), forme que la chaîne d'extraction lit sans difficulté.",
         size=13.5, color=RGBColor(0xC9, 0xC9, 0xC9))
    footer(slide, n)


def s15_moteur_retenu(prs, n):
    slide = new_slide(prs)
    header(slide, "4 — Banc d'essai", "La référence d'exactitude, et sa place dans la chaîne")

    tf = _txbox(slide, MARGIN, BODY_TOP - 0.06, CONTENT_W, 0.32)
    p = _para(tf, first=True)
    _run(p, "Clip de référence : ", size=13, bold=True, color=INK)
    _run(p, "« hier 20/07/2026, arrivés à Essaouira à 1 h, vérifié le chemin de 27 câbles, pris le métrage, coupés, vérifié le chemin de la fibre, sortis à 7 h »", size=13, italic=True, color=GREY)

    # Arabic gets a column of its own: mixed inline with French, the bidi
    # algorithm reorders the surrounding punctuation and eats the spaces.
    table(slide,
          ["Modèle", "Transcription obtenue", "Conséquence sur les champs métier"],
          # No isolation needed: the column holds Arabic and nothing else.
          [["Morocco-Darija-STT-large", ar("27") + " كابل    فيريفينا    لافيبر", "Tous les champs survivent : quantité, verbe technique, matériel"],
           ["whisper-large-v3", "فرحنا", "« vérifier » devient « nous nous sommes réjouis »"],
           ["ychafiqui/medium-darija", "السبعة وعشر وعشر الين كابل", "« 27 câbles » : la quantité est détruite"]],
          x=MARGIN, y=2.52, w=CONTENT_W, col_w=[3.2, 3.6, 4.8], size=12, row_h=0.48, head_h=0.40,
          emphasis=(0,))
    caption(slide, "Tableau 4.4 — Comportement comparé sur les champs métier.", MARGIN, 4.42, CONTENT_W, align=PP_ALIGN.LEFT)

    y = 4.82
    half = (CONTENT_W - 0.4) / 2
    _rect(slide, MARGIN, y, half, 1.72, fill=WASH)
    _rect(slide, MARGIN, y, half, 0.05, fill=GREEN)
    tf = _txbox(slide, MARGIN + 0.26, y + 0.26, half - 0.52, 1.3)
    _run(_para(tf, first=True), "Ce qui est gagné", size=14.5, bold=True, color=INK)
    p = _para(tf)
    p.line_spacing = 1.2
    _run(p, "Seul moteur à préserver simultanément les quantités numériques et les emprunts techniques français. Conserve aussi les noms propres du domaine — Novec, Essaouira, Kenitra — sur l'ensemble des clips. Licence Apache 2.0.", size=12, color=GREY)

    _rect(slide, MARGIN + half + 0.4, y, half, 1.72, fill=WASH)
    _rect(slide, MARGIN + half + 0.4, y, half, 0.05, fill=RGBColor(0xC0, 0x39, 0x2B))
    tf = _txbox(slide, MARGIN + half + 0.66, y + 0.26, half - 0.52, 1.3)
    _run(_para(tf, first=True), "Ce qui est payé", size=14.5, bold=True, color=INK)
    p = _para(tf)
    p.line_spacing = 1.2
    _run(p, "7,7 s de latence moyenne, le plus lent des douze, contre 1,53 s pour l'API de Groq, et 4 Go de mémoire graphique immobilisés. C'est ce coût qui lui vaut, en production, la position de repli : la chaîne livrée est gemini, local, groq. Le banc d'essai désigne la référence d'exactitude ; l'ordre d'appel est une décision d'exploitation.", size=12, color=GREY)
    footer(slide, n)



def s05b_planning(prs, n):
    """Seven phases, March to August. Replaces the four-sprint story the report dropped."""
    slide = new_slide(prs)
    header(slide, "1 — Conduite du projet", "Six mois, sept phases")
    table(slide,
          ["Phase", "Période", "Objectif principal"],
          [["0 — Cadrage", "2 – 27 mars", "Immersion métier, cahier des charges"],
           ["1 — État de l'art", "30 mars – 30 avril", "Transcription du dialectal, extraction par LLM, jeu de test"],
           ["2 — Conception", "4 mai – 5 juin", "Architecture hybride, contrat de données, frontière n8n / code"],
           ["3 — Cœur IA", "8 juin – 17 juillet", "Service FastAPI, adaptateurs STT, chaînes de repli"],
           ["4 — Chaîne complète", "20 juillet – 1er août", "Workflow n8n, réception bicanale, tableau de bord"],
           ["5 — Bancs d'essai", "3 – 14 août", "Comparatifs STT et extraction, sécurité, intégration continue"],
           ["6 — Pilote et rapport", "17 – 28 août", "Déploiement pilote, livrables, soutenance"]],
          x=MARGIN, y=BODY_TOP, w=CONTENT_W, col_w=[2.5, 2.5, 6.6], size=12,
          row_h=0.44, head_h=0.40, emphasis=(0,))
    note(slide, "Le bout-en-bout réel a été atteint en phase 3, une phase avant le planning : le risque d'intégration a été neutralisé avant d'engager le reste.",
         y=6.16, accent=GREEN, size=12.5, h=0.58)
    footer(slide, n)


def s15b_extraction(prs, n):
    """The two extraction benchmarks: the report has them, the deck had only STT."""
    slide = new_slide(prs)
    header(slide, "4 — Banc d'essai", "Du texte au tableau : huit modèles, dix cas")
    table(slide,
          ["Modèle", "Cas répondus", "Exactitude", "Cas parfaits", "Valeurs inventées", "Latence"],
          [["openai/gpt-oss-120b", "10 / 10", "1,000", "10 / 10", "0", "1,72 s"],
           ["gemini-flash-lite-latest", "10 / 10", "0,980", "9 / 10", "1", "1,04 s"],
           ["gemini-3.6-flash", "4 / 10", "1,000", "4 / 4", "0", "4,98 s"],
           ["llama-3.3-70b-versatile", "10 / 10", "0,922", "7 / 10", "1", "0,69 s"],
           ["llama-3.1-8b-instant", "7 / 10", "0,876", "5 / 7", "5", "0,50 s"],
           ["qwen/qwen3.6-27b", "0 / 10", "—", "—", "—", "—"]],
          x=MARGIN, y=BODY_TOP, w=CONTENT_W, col_w=[3.4, 1.7, 1.5, 1.6, 2.1, 1.3],
          size=11.5, row_h=0.42, head_h=0.40, emphasis=(0,))

    y = 5.02
    half = (CONTENT_W - 0.4) / 2
    _rect(slide, MARGIN, y, half, 1.02, fill=WASH)
    _rect(slide, MARGIN, y, half, 0.05, fill=RGBColor(0xC0, 0x39, 0x2B))
    tf = _txbox(slide, MARGIN + 0.26, y + 0.20, half - 0.52, 0.76)
    _run(_para(tf, first=True), "La rapidité ne rachète rien", size=13.5, bold=True, color=INK)
    p = _para(tf)
    p.line_spacing = 1.15
    _run(p, "llama-3.1-8b-instant : le plus rapide du tableau, et cinq valeurs inventées — dont un client qu'aucun cas ne mentionne.", size=11.5, color=GREY)

    _rect(slide, MARGIN + half + 0.4, y, half, 1.02, fill=WASH)
    _rect(slide, MARGIN + half + 0.4, y, half, 0.05, fill=BLUE)
    tf = _txbox(slide, MARGIN + half + 0.66, y + 0.20, half - 0.52, 0.76)
    _run(_para(tf, first=True), "La disponibilité prime", size=13.5, bold=True, color=INK)
    p = _para(tf)
    p.line_spacing = 1.15
    _run(p, "gemini-3.6-flash obtient 1,000 — sur les quatre cas traités avant l'épuisement du quota gratuit. Parfait puis muet : c'est un repli, pas un primaire.", size=11.5, color=GREY)

    note(slide, "D'où la chaîne gpt-oss-120b → flash-lite → 3.6-flash : elle alterne les fournisseurs dès le second maillon, parce que Groq et Google comptent leurs quotas séparément. Sur l'image, quatre modèles de vision sur les mêmes dix cas : l'écart texte / image est quasi nul.",
         y=6.16, accent=BLUE, size=12, h=0.58)
    footer(slide, n)


def s18b_sonar(prs, n):
    """SonarCloud: the gate passes now, and the deck never said so."""
    slide = new_slide(prs)
    header(slide, "5 — Qualité", "L'analyse statique externe : SonarCloud")
    stats(slide, [("0", "bogue"),
                  ("0", "vulnérabilité"),
                  ("A / A / A", "fiabilité · sécurité\nmaintenabilité"),
                  ("60 %", "de couverture\nmesurée (service Python)")],
          y=BODY_TOP - 0.05, h=1.48)

    bullets(slide, [
        ("Le portail est passé de rouge à vert.", "Fiabilité E, sécurité C au départ : une image de conteneur qui s'exécutait en root et installait depuis des sources non épinglées, et une clé de projet qui ne désignait aucun projet existant."),
        ("Un signalement a été refusé, motif consigné.", "Verrouiller les empreintes des dépendances du service GPU tirerait la variante processeur de torch et casserait silencieusement l'inférence — la dépendance vient de l'image CUDA."),
        ("Un vrai bogue de test a été débusqué.", "Un test dépendait du fichier .env local : il passait sur la machine de développement et échouait en intégration continue. À lui seul, il maintenait la chaîne au rouge à chaque exécution."),
    ], y=3.72, size=13, gap=10)
    note(slide, "Une dette de 121 minutes et 15 mauvaises odeurs subsistent : maintenabilité déjà notée A, aucun correctif bloquant.",
         y=6.16, accent=MUTE, size=12.5, h=0.58)
    footer(slide, n)


def s16_perimetre(prs, n):
    slide = new_slide(prs)
    header(slide, "5 — Réalisation", "Périmètre livré et en production")
    col = [
        ["Réception Telegram", "Réception WhatsApp Cloud API",
         "Transcription — 3 moteurs, chaîne de repli", "Extraction structurée — 4 chaînes de repli",
         "Entrée par photo — modèle de vision", "Journal de chantier par site — fusion, stock",
         "Miroir plat pour le tableau de bord"],
        ["Observabilité PostgreSQL", "Tableau de bord trilingue FR / EN / AR",
         "Organigramme, comptes, chantiers, bordereau", "Ordonnanceur — 6 tâches, page Automatisation",
         "Rapports quotidien et hebdomadaire par e-mail", "Commandes /rapport, /modifier, /supprimer",
         "Moteur local sur GPU, conteneurisé"],
    ]
    half = (CONTENT_W - 0.5) / 2
    for i, items in enumerate(col):
        cx = MARGIN + i * (half + 0.5)
        tf = _txbox(slide, cx, BODY_TOP - 0.02, half, 3.4)
        for j, it in enumerate(items):
            p = _para(tf, first=(j == 0))
            p.space_after = Pt(10)
            _run(p, "✓  ", size=14, bold=True, color=GREEN)
            _run(p, it, size=13.5, color=INK)

    y = 5.06
    _rect(slide, MARGIN, y, CONTENT_W, 1.42, fill=WASH)
    _rect(slide, MARGIN, y, 0.05, 1.42, fill=BLUE)
    tf = _txbox(slide, MARGIN + 0.34, y + 0.22, CONTENT_W - 0.68, 1.05)
    p = _para(tf, first=True)
    p.line_spacing = 1.22
    _run(p, "Dès la phase 3", size=13.5, bold=True, color=INK)
    _run(p, " — le planning la prévoyait en phase 4 — la chaîne complète a été validée en conditions réelles : note vocale, détection, téléchargement, transcription, extraction, résumé français, réponse de confirmation. Le risque d'intégration majeur du projet a été neutralisé immédiatement. Lors de ces essais, ", size=13.5, color=GREY)
    _run(p, "le repli d'extraction s'est déclenché seul", size=13.5, bold=True, color=INK)
    _run(p, " sur indisponibilité du fournisseur principal, validant la conception sans intervention.", size=13.5, color=GREY)
    footer(slide, n)


def s17_dashboard(prs, n):
    slide = new_slide(prs)
    header(slide, "5 — Réalisation", "Le tableau de bord : consulter, corriger, administrer")
    image_fit(slide, SCREENS / "en-overview.jpg", MARGIN, 1.98, CONTENT_W * 0.62, 4.05, frame=True)
    tx = MARGIN + CONTENT_W * 0.65
    tw = CONTENT_W - CONTENT_W * 0.65
    tf = _txbox(slide, tx, 2.06, tw, 4.0)
    for i, (t, d) in enumerate([
        ("Trilingue", "Français, anglais, arabe. L'arabe impose le sens droite-à-gauche sur toute l'interface."),
        ("Sans dépendance d'UI", "React 19 et Tailwind v4, graphiques en SVG écrits à la main, aucune bibliothèque de composants."),
        ("Huit écrans", "Vue d'ensemble, boîte de réception, rapports, quotidien, hebdomadaire, automatisation, journaux, équipe."),
        ("Organigramme éditable", "Le rattachement d'un technicien à un chef détermine le chantier de ses rapports."),
    ]):
        p = _para(tf, first=(i == 0))
        p.space_after = Pt(3)
        _run(p, t, size=14, bold=True, color=BLUE)
        p = _para(tf)
        p.space_after = Pt(13)
        p.line_spacing = 1.18
        _run(p, d, size=12, color=GREY)
    caption(slide, "Figure 5.1 — Vue d'ensemble, thème sombre, connectée à la pile complète.", MARGIN, 6.16, CONTENT_W * 0.62)
    footer(slide, n)


def s18_devops(prs, n):
    slide = new_slide(prs)
    header(slide, "5 — Qualité", "La chaîne d'intégration continue")
    stats(slide, [("6 mois", "de développement\n(2 mars – 31 août 2026)"),
                  ("18", "contrôles automatiques\nà chaque push"),
                  ("288", "tests, sans aucune\nclé d'API ni base"),
                  ("38", "demandes Dependabot\nsur 5 écosystèmes")],
          y=BODY_TOP - 0.05, h=1.48)

    y = 3.70
    tf = _txbox(slide, MARGIN, y, CONTENT_W, 0.3)
    _run(_para(tf, first=True), "Les 18 contrôles, par famille", size=14.5, bold=True, color=BLUE)
    fams = [
        ("Correction", GREEN, "API — ruff, types, 288 tests  ·  Dashboard — tsc, oxlint, build  ·  workflow n8n  ·  Docker compose  ·  parité des locales"),
        ("Sécurité du code", BLUE, "CodeQL (python)  ·  CodeQL (javascript-typescript)  ·  Semgrep OWASP Top 10  ·  Bandit"),
        ("Dépendances et secrets", RGBColor(0x8E, 0x44, 0xAD), "Trivy filesystem  ·  Trivy config  ·  pip-audit  ·  npm audit  ·  gitleaks + check_secrets.py"),
        ("Conformité des fichiers", GREY, "Hadolint (api)  ·  Hadolint (Dashboard)  ·  actionlint"),
    ]
    yy = y + 0.38
    for name, color, detail in fams:
        _rect(slide, MARGIN, yy, 0.035, 0.44, fill=color)
        tf = _txbox(slide, MARGIN + 0.20, yy + 0.005, 2.55, 0.4)
        _run(_para(tf, first=True), name, size=12.5, bold=True, color=INK)
        tf = _txbox(slide, MARGIN + 2.85, yy + 0.02, CONTENT_W - 2.85, 0.42)
        p = _para(tf, first=True)
        p.line_spacing = 1.1
        _run(p, detail, size=11.5, color=GREY)
        yy += 0.50

    note(slide, "Dependabot ouvre ses demandes quotidiennement sur npm, pip, les deux images Docker et les actions GitHub — chacune doit franchir les 18 contrôles avant de pouvoir être fusionnée.",
         y=6.16, accent=BLUE, size=12.5, h=0.58)
    footer(slide, n)


def s19_demo(prs, n):
    slide = new_slide(prs, bg=INK)
    header(slide, "6 — Démonstration", "La chaîne complète, en direct", accent=RGBColor(0x4F, 0xA9, 0xF5), on_dark=True)
    bullets(slide, [
        ("Une note vocale en darija ", "est envoyée depuis Telegram."),
        ("Le bot répond ", "avec le résumé en français professionnel et les quantités extraites."),
        ("La ligne apparaît ", "dans l'onglet du chantier, fusionnée s'il en existe déjà une pour la journée."),
        ("Le tableau de bord ", "affiche le rapport, ses avertissements de qualité et la trace de traitement."),
    ], y=BODY_TOP + 0.15, size=16.5, gap=17, accent=RGBColor(0x4F, 0xA9, 0xF5), on_dark=True)

    _rect(slide, MARGIN, 5.68, CONTENT_W, 0.86, fill=RGBColor(0x2A, 0x2E, 0x34))
    tf = _txbox(slide, MARGIN + 0.34, 5.86, CONTENT_W - 0.68, 0.55)
    p = _para(tf, first=True)
    p.line_spacing = 1.2
    _run(p, "Si le réseau ou un palier gratuit fait défaut : ", size=12.5, bold=True, color=WHITE)
    _run(p, "les captures de secours suivent la dernière diapositive et couvrent le même parcours, écran par écran.", size=12.5, color=RGBColor(0xB4, 0xB4, 0xB4))
    footer(slide, n, on_dark=True)


def s20_bilan(prs, n):
    slide = new_slide(prs)
    header(slide, "6 — Bilan", "Contributions et limites")
    half = (CONTENT_W - 0.5) / 2

    tf = _txbox(slide, MARGIN, BODY_TOP - 0.05, half, 0.3)
    _run(_para(tf, first=True), "Contributions", size=15, bold=True, color=GREEN)
    tf = _txbox(slide, MARGIN, BODY_TOP + 0.32, half, 4.0)
    for i, t in enumerate([
        "Une architecture hybride dont la frontière a été fixée par une contrainte fonctionnelle identifiée en cours de projet, non par préférence.",
        "Un banc d'essai de treize moteurs de transcription du darija, avec une critique argumentée du WER et une métrique applicative de substitution.",
        "Un service d'extraction à sortie contrainte, quatre chaînes de repli alternant les fournisseurs, et une politique stricte d'absence de données inventées.",
        "Un modèle métier reconstruit sur le fichier réel du client, avec accumulation intra-journalière et réconciliation de stock.",
        "Une conception indépendante du canal, démontrée par la mise en service de deux messageries aux contraintes opposées.",
    ]):
        p = _para(tf, first=(i == 0))
        p.space_after = Pt(9)
        p.line_spacing = 1.18
        _run(p, "▪  ", size=12.5, bold=True, color=GREEN)
        _run(p, t, size=12.5, color=GREY)

    cx = MARGIN + half + 0.5
    tf = _txbox(slide, cx, BODY_TOP - 0.05, half, 0.3)
    _run(_para(tf, first=True), "Limites énoncées sans détour", size=15, bold=True, color=RGBColor(0xC0, 0x39, 0x2B))
    tf = _txbox(slide, cx, BODY_TOP + 0.32, half, 4.0)
    for i, t in enumerate([
        "Le WER et le CER n'ont pas été calculés. Le choix d'une métrique applicative est argumenté, mais il prive la comparaison d'un chiffre universellement reconnu : le classement repose sur un jugement humain, rigoureux mais non reproductible sans le même locuteur.",
        "La suite de tests ne parcourt jamais le réseau réel. Elle sécurise les régressions de logique, non les ruptures de contrat des fournisseurs — qui ont été la source de la majorité des défauts rencontrés.",
        "Le déploiement pilote auprès des techniciens constitue l'étape suivante ; les chiffres d'usage réel ne sont donc pas encore établis.",
    ]):
        p = _para(tf, first=(i == 0))
        p.space_after = Pt(11)
        p.line_spacing = 1.18
        _run(p, "▪  ", size=12.5, bold=True, color=RGBColor(0xC0, 0x39, 0x2B))
        _run(p, t, size=12.5, color=GREY)
    footer(slide, n)


def s21_perspectives(prs, n):
    slide = new_slide(prs)
    header(slide, "6 — Perspectives", "Ce que ce travail ouvre")
    bullets(slide, [
        ("Constituer la vérité terrain qui manque, ", "à partir des rapports réels accumulés, afin de publier un WER et un CER et de rendre le classement reproductible."),
        ("Affiner un modèle de transcription ", "sur ce corpus darija propre au câblage — l'apport de l'affinage étant désormais démontré pour un modèle assez grand."),
        ("Remplacer Google Sheets par une base de données ", "lorsque la volumétrie le justifiera : l'infrastructure PostgreSQL est déjà en place."),
        ("Étendre le tableau de bord vers l'analytique de chantier ", "— avancement par site, consommation de matériel, alertes de stock ; le bordereau en fournit la base."),
    ], size=14.5, gap=13)

    y = 4.72
    _rect(slide, MARGIN, y, CONTENT_W, 1.68, fill=INK)
    tf = _txbox(slide, MARGIN + 0.38, y + 0.28, CONTENT_W - 0.76, 1.2)
    p = _para(tf, first=True)
    p.line_spacing = 1.24
    _run(p, "Dans les applications des grands modèles de langage, la valeur ne réside pas dans le choix des modèles, mais dans l'architecture qui les entoure : ", size=14.5, color=RGBColor(0xDD, 0xDD, 0xDD))
    _run(p, "contrats de données stricts, chaînes de repli explicites, refus des échecs silencieux, et bancs d'essai assez sceptiques pour se surprendre eux-mêmes.", size=14.5, bold=True, color=WHITE)
    p = _para(tf)
    p.line_spacing = 1.2
    _run(p, "Ce banc d'essai a renversé son hypothèse de départ deux fois, et démasqué un bogue qui lui faisait couronner un vainqueur sur une transcription jamais générée.", size=12.5, color=RGBColor(0xA8, 0xA8, 0xA8))
    footer(slide, n)


def s22_merci(prs):
    slide = new_slide(prs)
    _rect(slide, 0, 0, SLIDE_W, 0.10, fill=GREEN)
    _rect(slide, 0, SLIDE_H - 0.10, SLIDE_W, 0.10, fill=BLUE)
    tf = _txbox(slide, MARGIN, 2.85, CONTENT_W, 1.0)
    p = _para(tf, first=True)
    p.alignment = PP_ALIGN.CENTER
    _run(p, "Merci de votre attention", size=40, bold=True, color=INK)
    tf = _txbox(slide, MARGIN, 3.95, CONTENT_W, 0.5)
    p = _para(tf, first=True)
    p.alignment = PP_ALIGN.CENTER
    _run(p, "Questions", size=18, color=BLUE)
    slide.shapes.add_picture(str(ASSETS / "logo-emsi.png"), Inches(MARGIN), Inches(6.30), height=Inches(0.55))
    ai = Image.open(ASSETS / "logo-aznet.png")
    ah = 0.60
    aw = ah * ai.size[0] / ai.size[1]
    slide.shapes.add_picture(str(ASSETS / "logo-aznet.png"),
                             Inches(SLIDE_W - MARGIN - aw), Inches(6.27), height=Inches(ah))


def backups(prs, start):
    """Never shown unless the live demo fails. Same parcours, screen by screen."""
    shots = [
        ("en-inbox.jpg", "Boîte de réception — les rapports arrivés, avec leurs avertissements de qualité"),
        ("en-reports.jpg", "Rapports — consultation et correction ligne à ligne"),
        ("en-equipe.jpg", "Équipe — l'organigramme : directeur, chefs de chantier, techniciens"),
        ("en-automation.jpg", "Automatisation — les six tâches planifiées et leurs dernières exécutions"),
        ("en-logs.jpg", "Journaux — la trace de traitement, n8n et service réunis par correlation_id"),
        ("mobile-overview.jpg", "Usage mobile — la même interface, consultée depuis un téléphone"),
    ]
    n = start
    for i, (f, cap) in enumerate(shots):
        p = SCREENS / f
        if not p.exists():
            continue
        slide = new_slide(prs)
        header(slide, f"Annexe — capture {i + 1}", cap, accent=MUTE)
        image_fit(slide, p, MARGIN, 2.02, CONTENT_W, 4.35, frame=True)
        footer(slide, n)
        n += 1
    return n


# --- ce que je dis, pas ce qui est projeté ---------------------------------
#
# Visible uniquement dans le mode Présentateur. Une ligne par idée, la durée
# visée en tête : vingt minutes se tiennent si chaque diapositive sait combien
# elle coûte. Ce sont des repères, pas un texte à lire — lire ses notes devant
# un jury s'entend immédiatement.
NOTES = {
    "s01_cover": """
[30 s] Bonjour. Mohammed Yassine MAGRI, filière Ingénierie Informatique et
Réseaux. Sujet : automatiser les rapports journaliers de chantier chez AZNET,
à Rabat, à partir de notes vocales en darija.
Attendre que le jury soit installé avant de commencer.
""",
    "s02_plan": """
[30 s] Annoncer le parcours en une phrase : le problème, la conception, les
bancs d'essai, la démonstration. Ne pas lire les six points.
""",
    "s03_quote": """
[20 s] Laisser la citation à l'écran deux secondes avant de parler. C'est la
phrase du directeur : elle pose le problème mieux que je ne le ferais.
""",
    "s03_contexte": """
[1 min] AZNET pose des infrastructures réseau. Le suivi de chantier se fait
aujourd'hui à la main, le soir, de mémoire.
Chiffre à donner si la question vient : le directeur re-saisit les rapports
lui-même dans son fichier de suivi.
""",
    "s04_problematique": """
[1 min 30] Le cœur du problème : le technicien parle darija, mélange les
emprunts français techniques, et le journal attend des chiffres par colonne.
Insister sur l'écart entre « ce qui est dit » et « ce qui est compté » — c'est
ce que tout le reste de la présentation résout.
""",
    "s05_besoins": """
[1 min] Besoins fonctionnels puis non fonctionnels. Souligner la contrainte de
budget zéro : elle explique presque toutes les décisions techniques qui
suivent, y compris la chaîne de repli entre fournisseurs.
""",
    "s05b_planning": """
[45 s] Sept phases sur six mois. Le point à faire passer : le bout-en-bout
réel a été atteint en phase 3, une phase avant le planning — le risque
d'intégration a été neutralisé avant d'engager le reste.
Si on demande pourquoi : un défaut d'intégration ne se voit pas hors ligne.
""",
    "s06_etat_art_stt": """
[1 min] État de l'art de la transcription de l'arabe dialectal. Dire que la
littérature ne tranchait pas pour le darija : c'est ce qui a rendu le banc
d'essai nécessaire plutôt que confortable.
""",
    "s07_etat_art_llm": """
[1 min] Extraction structurée par LLM : sortie contrainte par schéma, et le
risque central — un modèle qui invente une valeur plausible. C'est le critère
qui décidera du choix au banc d'essai n°2.
""",
    "s08_architecture": """
[1 min 30] Architecture hybride : n8n orchestre, le service Python fait l'IA.
La frontière est le sujet de la diapositive suivante, ne pas l'anticiper ici.
Cinq services, une seule origine publique.
""",
    "s09_frontiere": """
[1 min] Pourquoi cette frontière : ce qui est testable va dans le code, ce qui
est du câblage reste dans n8n. Exemple concret si on demande — la fusion d'une
ligne de journal a quitté n8n parce qu'un nœud IF ne sait pas relire une ligne.
""",
    "s10_flux": """
[1 min 30] Dérouler le flux une fois, lentement. Le point non évident :
la réponse au technicien part AVANT l'écriture du Sheet. Une panne Google ne
doit jamais coûter son résumé au technicien ; la ligne est mise en file.
""",
    "s11_journal": """
[1 min 30] Le journal reproduit le fichier du directeur, colonne pour colonne.
Deux règles : une ligne par message (jamais de réécriture, une correction
fausse ne détruit pas un chiffre juste) et le stock réconcilié, jamais supposé.
""",
    "s12_banc_protocole": """
[1 min] Protocole. Assumer la décision de méthode : ni WER ni CER. Le journal
ne consomme que des chiffres et des emprunts techniques — c'est cela qu'on
mesure, jugé par un locuteur natif contre l'audio.
""",
    "s13_banc_api": """
[45 s] Trois moteurs par API. Groq est rapide, et c'est le plancher toujours
disponible de la chaîne — pas le meilleur.
""",
    "s14_banc_local": """
[1 min] Douze moteurs en local sur la 3070. Raconter l'hypothèse renversée
puis rétablie : les petits affinages darija perdaient, les grands gagnent.
C'est la diapositive où l'on montre que le résultat n'était pas acquis.
""",
    "s15_moteur_retenu": """
[1 min 30] La référence d'exactitude est le modèle darija open-source. Dire
tout de suite ce qui suit, avant qu'on le trouve dans la config : il est en
REPLI en production, pas en tête. 7,7 s et 4 Go de VRAM se paient sur chaque
note ; Gemini répond d'abord, le local prend le relais quand le quota tombe.
Le banc d'essai désigne une référence, l'ordre d'appel est une décision
d'exploitation.
""",
    "s15b_extraction": """
[1 min 30] Deuxième banc d'essai. Le chiffre qui frappe : llama-3.1-8b-instant
est le plus rapide du tableau ET invente cinq valeurs. La vitesse ne rachète
rien quand le modèle remplit des champs à partir de rien.
Assumer la limite si on la soulève : les dix cas ont été écrits par l'auteur du
système. C'est dit au §4.3.9 du rapport.
""",
    "s16_perimetre": """
[1 min] Périmètre livré. Rester factuel, ne pas survendre : ce qui tourne, ce
qui reste à faire.
""",
    "s17_dashboard": """
[1 min] Le tableau de bord. Trilingue, arabe en RTL, graphiques écrits à la
main — aucune bibliothèque de composants. Les vingt-deux captures sont en
annexe H du rapport.
""",
    "s18_devops": """
[1 min] Dix-huit contrôles à chaque push. Le point honnête : Dependabot ouvre
les demandes, aucune n'a encore été fusionnée — le dispositif rend l'écart
visible, il ne l'a pas encore résorbé.
""",
    "s18b_sonar": """
[45 s] SonarCloud : la porte qualité passe. Raconter le vrai bogue trouvé — un
test qui dépendait du .env local, vert sur ma machine, rouge en intégration
continue, et qui maintenait la chaîne au rouge à chaque exécution.
""",
    "s19_demo": """
[3 min] DÉMONSTRATION EN DIRECT.
Ordre : envoyer la note vocale → montrer le ⏳ → attendre le ✅ → ouvrir le
Sheet → ouvrir la boîte de réception du tableau de bord.
Si le réseau tombe : passer aux captures d'annexe, elles suivent le même
parcours. Ne pas déboguer devant le jury.
""",
    "s20_bilan": """
[1 min 30] Compétences techniques puis méthodologiques. La leçon à énoncer :
un résultat flatteur mérite plus de vérification qu'un résultat décevant — le
banc d'essai avait un bogue silencieux qui couronnait un modèle sur une
transcription qu'il n'avait jamais produite.
""",
    "s21_perspectives": """
[1 min] Perspectives, et les limites assumées. Mieux vaut nommer les limites
avant le jury : jeu de test écrit par l'auteur, pilote court, couverture qui
ne décrit que le service Python.
""",
    "s22_merci": """
[fin] Remercier, puis se taire. Laisser venir les questions.
Questions attendues : pourquoi pas Whisper seul / pourquoi n8n et pas tout en
code / que se passe-t-il si les quotas gratuits tombent / comment on empêche
le modèle d'inventer une valeur.
""",
}


# The design line appended to each slide's notes: enough to answer a question
# about the visual identity without turning the notes into a design brief.
DESIGN_NOTE = {
    "s01_cover": "Bandeau zellige plein : khatam (étoile à 8 branches), le motif "
                 "qui signe la mosaïque marocaine. La rosace repart vers la diapo "
                 "suivante — c'est un morph, pas une coupure.",
    "s03_quote": "La rosace a traversé depuis la couverture, agrandie et tournée.",
    "s19_demo": "Fond sombre : la rosace passe au turquoise pour rester lisible.",
    "s22_merci": "Rosace au centre, plein format — dernière image, on la laisse "
                 "respirer avant les questions.",
}
DESIGN_DEFAULT = ("Rail zellige à gauche + rosace khatam près du titre. Palette "
                  "d'ornement ancrée sur le bleu AZNET ; le texte et les chiffres "
                  "gardent les couleurs institutionnelles.")


# Slides whose background is INK, where the ornament has to invert.
DARK_SLIDES = {"s19_demo"}

# The two slides that carry a full course of tilework, and where it sits.
BANDS = {
    "s01_cover": (0.0, 1.15),
    "s22_merci": (SLIDE_H - 1.15, 1.15),
}


def _dress(prs, name):
    """Put the zellige on the slide that was just built."""
    zellige(prs.slides[-1], name,
            on_dark=name in DARK_SLIDES,
            band=BANDS.get(name))


def _annotate(prs, name):
    """Attach the speaker notes for the slide that was just built.

    The design line comes last and is deliberately short: the notes exist to
    pace a defence, not to explain a colour choice. It is there for the one
    question a jury sometimes asks about a deck that does not look like every
    other deck.
    """
    text = NOTES.get(name)
    if not text:
        return
    design = DESIGN_NOTE.get(name, DESIGN_DEFAULT)
    speaker_notes(prs.slides[-1], text.strip() + "\n\n— Design : " + design)


def main():
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)

    # Numbered in order of appearance, so inserting a slide never means
    # renumbering the ones after it by hand.
    s01_cover(prs)
    _dress(prs, "s01_cover")
    _annotate(prs, "s01_cover")
    n = 1
    for build in (s02_plan, s03_quote, s03_contexte, s04_problematique, s05_besoins,
                  s05b_planning, s06_etat_art_stt, s07_etat_art_llm, s08_architecture,
                  s09_frontiere, s10_flux, s11_journal, s12_banc_protocole, s13_banc_api,
                  s14_banc_local, s15_moteur_retenu, s15b_extraction, s16_perimetre,
                  s17_dashboard, s18_devops, s18b_sonar, s19_demo, s20_bilan,
                  s21_perspectives):
        n += 1
        build(prs, n)
        _dress(prs, build.__name__)
        _annotate(prs, build.__name__)
    s22_merci(prs)
    _dress(prs, "s22_merci")
    _annotate(prs, "s22_merci")
    first_backup = len(prs.slides._sldIdLst)
    backups(prs, n + 2)
    # The backups only ever appear if the live demo dies. They get the rail, so
    # they still belong to the deck, and nothing else: that is not a moment for
    # decoration.
    # The backups get the rail so they still belong to the deck, and nothing
    # else: they only appear if the live demo dies, which is not a moment for
    # decoration.
    for slide in list(prs.slides)[first_backup:]:
        zellige_rail(slide)

    # Morph on every slide, including the backups: a transition missing from
    # one slide is the one the audience notices.
    for slide in prs.slides:
        morph(slide)

    prs.save(str(OUT))
    print(f"slides : {len(prs.slides._sldIdLst)}")
    print(f"deck   : {OUT}")


if __name__ == "__main__":
    main()
