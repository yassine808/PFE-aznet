"""Outgoing mail — one SMTP path for the test probe and the scheduled reports.

Kept apart from main.py because the scheduler sends mail from a background
thread, and duplicating the SMTP block would mean fixing a Gmail quirk twice.
smtplib is lazy-imported for symmetry with the other providers; credentials are
checked at call time so an unconfigured install starts fine and fails loudly
only when someone actually tries to send.
"""
import io
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
_BANNER_SIZE = (1120, 280)


@lru_cache(maxsize=1)
def banner_png() -> bytes:
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
    canvas = Image.new("RGB", (w, h), (15, 23, 42))
    draw = ImageDraw.Draw(canvas)

    # A diagonal wash from slate to the accent blue, one column at a time.
    # Cheap enough at 1120px, and it saves pulling in numpy for a gradient.
    for x in range(w):
        t = x / w
        draw.line(
            [(x, 0), (x, h)],
            fill=(
                int(15 + t * 22),
                int(23 + t * 60),
                int(42 + t * 110),
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
    canvas = Image.blend(canvas, Image.blend(canvas, grid, 0.35), 0.30)
    draw = ImageDraw.Draw(canvas)

    # The rule sits *below* the wordmark, not through it: at 72px the glyphs
    # run to about y+92, so anything drawn at the old y=156 crossed the
    # baseline and read as a strikethrough.
    draw.text((64, 78), "aznet", font=_font(72, bold=True), fill=(248, 250, 252))
    draw.line([(64, 190), (188, 190)], fill=(59, 130, 246), width=5)
    draw.text((64, 212), "RAPPORTS DE CHANTIER", font=_font(24), fill=(148, 163, 184))

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_document(
    title: str,
    lead: str,
    rows: Sequence[tuple],
    footer: str = "",
    cta: Optional[Tuple[str, str]] = None,
    banner: bool = True,
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
    body_rows = "".join(
        f'<tr>'
        f'<td style="padding:6px 16px 6px 0;color:#64748b;font-size:13px;'
        f'white-space:nowrap;vertical-align:top">{_escape(str(label))}</td>'
        f'<td style="padding:6px 0;color:#0f172a;font-size:14px">{_escape(str(value))}</td>'
        f'</tr>'
        for label, value in rows
        if value
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
        f'<img src="cid:{BANNER_CID}" width="560" alt="aznet"'
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
      <h1 style="margin:0 0 8px;color:#0f172a;font-size:19px;font-weight:600;letter-spacing:-0.3px">{_escape(title)}</h1>
      <p style="margin:0 0 18px;color:#475569;font-size:14px;line-height:1.6">{_escape(lead)}</p>
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"
             style="border-top:1px solid #e2e8f0;padding-top:12px">{body_rows}</table>
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
        if f"cid:{BANNER_CID}" in html_body:
            try:
                msg.get_payload()[-1].add_related(
                    banner_png(), maintype="image", subtype="png", cid=f"<{BANNER_CID}>"
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
