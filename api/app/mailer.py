"""Outgoing mail — one SMTP path for the test probe and the scheduled reports.

Kept apart from main.py because the scheduler sends mail from a background
thread, and duplicating the SMTP block would mean fixing a Gmail quirk twice.
smtplib is lazy-imported for symmetry with the other providers; credentials are
checked at call time so an unconfigured install starts fine and fails loudly
only when someone actually tries to send.
"""
import io
import re
from functools import lru_cache
from typing import List, Optional, Sequence, Tuple

from app.config import settings


class MailError(RuntimeError):
    pass


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


BANNER_CID = "aznet-banner"
_BANNER_SIZE = (1120, 300)


def _banner_cid(caption: str = "") -> str:
    """Content-ID for a banner, carrying its own caption.

    The header picture is per-message now — it prints the period the report
    covers — but `send()` only ever sees the finished HTML, so it has to be
    able to work out *which* banner to attach from the reference alone. Hex
    keeps the id to the characters a Content-ID may legally contain, and an
    empty caption keeps the plain id, so nothing that never sets one changes.
    """
    return f"{BANNER_CID}.{caption.encode('utf-8').hex()}" if caption else BANNER_CID


def _caption_of(cid: str) -> str:
    """Inverse of `_banner_cid`, used by `send()` when attaching the image."""
    _, _, token = cid.partition(".")
    try:
        return bytes.fromhex(token).decode("utf-8") if token else ""
    except ValueError:
        return ""

# The dashboard's own tokens, resolved to sRGB once (`Dashboard/src/index.css`:
# slate-950 / slate-900 / slate-400 / slate-50 and accent-500). Mail cannot read
# OKLCH, and it cannot read a CSS variable either — so the palette crosses over
# as numbers, in one place, rather than as magic triples scattered through the
# drawing code.
INK = (18, 24, 33)
INK_DEEP = (12, 16, 23)
ACCENT = (45, 128, 224)
PAPER = (248, 250, 252)
MUTED = (148, 163, 184)


@lru_cache(maxsize=8)
def banner_png(caption: str = "") -> bytes:
    """The header picture, drawn rather than shipped.

    A remote `<img src="https://…">` is blocked by default in Gmail, Outlook
    and Apple Mail until the reader clicks "load images", so a banner served
    from a URL arrives as a grey box on a routine report. A `data:` URI is
    worse — Gmail strips it outright. What does work everywhere is an image
    *attached* to the message and referenced by Content-ID, which is what this
    feeds.

    Drawn with Pillow because the alternative is committing a binary asset that
    nobody can diff and everybody forgets to update: this way the wordmark and
    the palette come from the same constants as the rest of the project, and
    the render is deterministic. Cached: it is identical for every message and
    the scheduler sends in a loop.
    """
    from PIL import Image, ImageDraw

    from app.imagegen import _font  # same fallback chain: slim image, no system fonts

    w, h = _BANNER_SIZE
    canvas = Image.new("RGB", (w, h), INK)
    draw = ImageDraw.Draw(canvas)

    # A vertical settle from slate to a deeper slate — the tonal step DESIGN.md
    # asks for, not the violet-to-blue wash it names as the generic-SaaS tell.
    # The accent stays out of the background entirely so it can mean one thing
    # in the foreground.
    for y in range(h):
        t = y / h
        draw.line(
            [(0, y), (w, y)],
            fill=(
                int(INK[0] + (INK_DEEP[0] - INK[0]) * t),
                int(INK[1] + (INK_DEEP[1] - INK[1]) * t),
                int(INK[2] + (INK_DEEP[2] - INK[2]) * t),
            ),
        )

    # Faint grid, so the surface reads as a plan rather than a flat rectangle.
    # Drawn on its own layer and blended down: painting near-black lines
    # directly needs a fill per column to stay readable over the gradient,
    # whereas one blend fades the whole grid evenly.
    grid = Image.new("RGB", (w, h), (0, 0, 0))
    gdraw = ImageDraw.Draw(grid)
    for gx in range(0, w, 56):
        gdraw.line([(gx, 0), (gx, h)], fill=(255, 255, 255), width=1)
    for gy in range(0, h, 56):
        gdraw.line([(0, gy), (w, gy)], fill=(255, 255, 255), width=1)
    canvas = Image.blend(canvas, Image.blend(canvas, grid, 0.30), 0.22)
    draw = ImageDraw.Draw(canvas)

    # One accent mark, and it is structural: a rule down the inline-start edge
    # that the wordmark hangs off, so the whole header is read as one block
    # rather than as text floating on a texture.
    draw.rectangle([(0, 0), (6, h)], fill=ACCENT)

    # The rule sits *below* the wordmark, not through it: at 72px the glyphs
    # run to about y+92, so anything drawn at the old y=156 crossed the
    # baseline and read as a strikethrough.
    draw.text((64, 72), "aznet", font=_font(72, bold=True), fill=PAPER)
    draw.line([(64, 184), (188, 184)], fill=ACCENT, width=5)
    draw.text((64, 206), "RAPPORTS DE CHANTIER", font=_font(24), fill=MUTED)

    # What this particular message is about, set against the inline-end edge —
    # the header stops being a logo plate and starts carrying information the
    # reader needs before they have scrolled at all.
    if caption:
        text = caption.upper()
        font = _font(26)
        try:
            width = int(draw.textlength(text, font=font))
        except AttributeError:  # very old Pillow
            width = len(text) * 13
        x = max(64, w - 64 - width)
        draw.text((x, 206), text, font=font, fill=PAPER)
        draw.line([(x, 184), (x + width, 184)], fill=(70, 84, 104), width=2)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_rich_text(text: str) -> str:
    """The report's own structure, as inline-styled HTML.

    `daily_report` writes `## Synthèse` headings and `- ` bullets, and the mail
    used to drop that whole string into a single `<p>`: the hashes and dashes
    arrived literally and every paragraph break collapsed, so the one part of
    the message the reader actually came for was the least readable thing in
    it. The three shapes recognised here are exactly the three the dashboard's
    reading pane draws, so the same report looks like the same report in both
    places.

    Not a Markdown parser, and it must not grow into one — anything it does not
    recognise falls through as a paragraph, which is what the old code did to
    every line.
    """
    out: List[str] = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            label = line.lstrip("#").strip()
            out.append(
                '<p style="margin:22px 0 8px;color:#64748b;font-size:11px;'
                'font-weight:600;letter-spacing:0.8px;text-transform:uppercase">'
                f"{_escape(label)}</p>"
            )
        elif line[:1] in {"-", "*", "•"}:
            out.append(
                '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">'
                '<tr><td width="14" style="padding:3px 0 3px 0;color:#94a3b8;'
                'font-size:14px;vertical-align:top">&bull;</td>'
                '<td style="padding:3px 0;color:#0f172a;font-size:14px;line-height:1.6">'
                f"{_escape(line[1:].strip())}</td></tr></table>"
            )
        else:
            out.append(
                '<p style="margin:0 0 10px;color:#334155;font-size:14px;line-height:1.65">'
                f"{_escape(line)}</p>"
            )
    return "".join(out)


def render_document(
    title: str,
    lead: str,
    rows: Sequence[tuple],
    footer: str = "",
    cta: Optional[Tuple[str, str]] = None,
    banner: bool = True,
    caption: str = "",
    rich: bool = False,
) -> str:
    """One branded HTML message: header, lead sentence, label/value rows, footer.

    Written as inline-styled tables on purpose. Mail clients strip `<style>`
    blocks, ignore flexbox and grid, and Outlook renders through Word — so the
    layout every other part of this project would express in Tailwind has to be
    spelled out attribute by attribute here. No external stylesheet, no web font
    and no remote image either: all three are blocked by default in most
    inboxes, and a message that needs them arrives unstyled or, worse, as a
    "load remote content?" prompt on a routine reminder.

    Callers pass plain text; escaping happens here so no call site can forget.
    """
    # Figures as a strip of tiles rather than a label/value table: the two or
    # three numbers a report carries are what the reader scans first, and a
    # table row put them at the same weight as their own labels. Tiles inside
    # one bordered box, not a grid of bordered cards — the box is the group.
    cells = [(str(label), str(value)) for label, value in rows if value]
    def _tile(index: int, label: str, value: str) -> str:
        # The separator is a border on every tile but the first, so the strip
        # reads as one object with divisions rather than as three boxes.
        rule = ";border-left:1px solid #e2e8f0" if index else ""
        return (
            f'<td style="padding:12px 16px;vertical-align:top{rule}">'
            f'<div style="color:#0f172a;font-size:17px;font-weight:600;line-height:1.2">'
            f"{_escape(value)}</div>"
            f'<div style="margin-top:4px;color:#94a3b8;font-size:11px;letter-spacing:0.6px;'
            f'text-transform:uppercase">{_escape(label)}</div></td>'
        )

    tiles = "".join(_tile(i, label, value) for i, (label, value) in enumerate(cells))
    figures = (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"'
        ' style="margin:18px 0 4px;border:1px solid #e2e8f0;border-radius:10px;'
        f'background:#f8fafc"><tr>{tiles}</tr></table>'
        if tiles
        else ""
    )
    # `rich` is opt-in: a reminder's lead is one sentence and would gain
    # nothing, while a report's is a structured document that the single-<p>
    # treatment flattened into a wall with visible `##` in it.
    body = (
        render_rich_text(lead)
        if rich
        else f'<p style="margin:0;color:#475569;font-size:14px;line-height:1.6">{_escape(lead)}</p>'
    )
    foot = (
        f'<p style="margin:24px 0 0;color:#94a3b8;font-size:12px;line-height:1.6">'
        f"{_escape(footer)}</p>"
        if footer
        else ""
    )
    # A bulletproof button: the padding lives on the <a>, not on a <td>, and
    # there is no border-radius fallback drama because a square-ish button that
    # renders everywhere beats a rounded one that collapses in Outlook.
    button = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:22px 0 4px">'
        f'<tr><td style="background:#2563eb;border-radius:8px">'
        f'<a href="{_escape(cta[1])}" style="display:inline-block;padding:12px 22px;'
        f'color:#ffffff;font-size:14px;font-weight:600;text-decoration:none">{_escape(cta[0])}</a>'
        f'</td></tr></table>'
        if cta
        else ""
    )
    head = (
        f'<tr><td style="padding:0;line-height:0">'
        f'<img src="cid:{_banner_cid(caption)}" width="560" alt="aznet"'
        f' style="display:block;width:100%;max-width:560px;height:auto;border:0;border-radius:12px 12px 0 0"></td></tr>'
        if banner
        else (
            '<tr><td style="background:#0f172a;border-radius:12px 12px 0 0;padding:18px 24px">'
            '<span style="color:#f8fafc;font-size:15px;font-weight:600">aznet</span></td></tr>'
        )
    )
    return f"""\
<div style="margin:0;padding:24px 12px;background:#f1f5f9;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:560px;margin:0 auto">
    {head}
    <tr><td style="background:#ffffff;border-radius:0 0 12px 12px;padding:24px">
      <h1 style="margin:0 0 14px;color:#0f172a;font-size:19px;font-weight:600;letter-spacing:-0.3px">{_escape(title)}</h1>
      {figures}
      <div style="margin-top:18px;border-top:1px solid #e2e8f0;padding-top:14px">{body}</div>
      {button}
      {foot}
    </td></tr>
  </table>
</div>"""


def send(
    to: Sequence[str],
    subject: str,
    body: str,
    html: bool = False,
    html_body: Optional[str] = None,
) -> List[str]:
    """Send one message to every recipient. Returns the addresses served.

    `body` is always the plain-text part — the fallback a text-only client and
    every spam filter reads. `html_body` is the rendered alternative when there
    is one; `html=True` without it keeps the old behaviour of showing the same
    text with its line breaks preserved.
    """
    recipients = [a for a in (x.strip() for x in to) if a]
    if not recipients:
        raise MailError("aucun destinataire configuré")
    if not settings.smtp_user or not settings.smtp_password:
        raise MailError(
            "SMTP is not configured — set SMTP_USER and SMTP_PASSWORD in .env "
            "(Gmail requires an app password, not the account password)"
        )

    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
        # The banner rides along as a related part, not a URL. Attached only
        # when the HTML actually references it, so a message built with
        # `banner=False` does not carry a picture nobody sees — which some
        # clients would still show as a paperclip.
        found = re.search(rf"cid:({re.escape(BANNER_CID)}[.\w]*)", html_body)
        if found:
            cid = found.group(1)
            try:
                msg.get_payload()[-1].add_related(
                    banner_png(_caption_of(cid)),
                    maintype="image",
                    subtype="png",
                    cid=f"<{cid}>",
                )
            except Exception as exc:  # noqa: BLE001 — Pillow missing, font gone, anything
                # A message with a broken header image is still the report; one
                # that never left because the banner failed to draw is not.
                print(f"[mail] banner skipped: {exc}")
    elif html:
        msg.add_alternative(body.replace("\n", "<br>"), subtype="html")

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        raise MailError(f"envoi échoué: {exc}") from exc
    return recipients
