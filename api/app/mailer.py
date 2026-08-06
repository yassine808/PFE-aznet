"""Outgoing mail — one SMTP path for the test probe and the scheduled reports.

Kept apart from main.py because the scheduler sends mail from a background
thread, and duplicating the SMTP block would mean fixing a Gmail quirk twice.
smtplib is lazy-imported for symmetry with the other providers; credentials are
checked at call time so an unconfigured install starts fine and fails loudly
only when someone actually tries to send.
"""
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from app.config import settings


class MailError(RuntimeError):
    pass


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


# The dashboard's own tokens, resolved to sRGB once (`Dashboard/src/index.css`,
# `:root`): canvas slate-50, surface white, line slate-200, ink slate-900,
# muted slate-600, faint slate-400, accent-600, and slate-950 for the masthead
# slab. Mail cannot read OKLCH and cannot read a CSS variable either, so the
# palette crosses over as hex, in one place, rather than as literals scattered
# through the markup.
# The masthead is navy rather than the dashboard's slate-950: this is the one
# artefact that leaves the building, and fr.aznet.ma is navy — a client or a
# chef who has seen the company site should recognise the sender before they
# read the subject. Everything below the slab stays on the dashboard ramp, so
# the body still reads as the same instrument panel.
SLAB = "#062a4f"
SLAB_LINE = "#12456f"  # hairline between the slab and the sheet, one tonal step up
CANVAS = "#f1f5f9"
SURFACE = "#ffffff"
LINE = "#e2e8f0"
INK = "#0f172a"
MUTED = "#475569"
FAINT = "#94a3b8"
LABEL = "#64748b"
# Sampled from the mark itself (`assets/AZ-bot.png`, the circle is rgb(1,119,227)),
# not picked to look nice beside it. One accent, and it is the brand's own.
ACCENT = "#0177e3"
ACCENT_SOFT = "#81c2fd"  # the mark's node colour, for text on the navy slab

# Geist Mono never loads in an inbox; this is the same instrument, borrowed
# from whatever the reader already has. Tabular by construction — every glyph
# in a monospace face is one advance wide, which is all the Aligned Column
# Rule actually asks for.
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

# A ceiling, not a width. The table is `width="100%"` and every horizontal
# value below is padding rather than a fixed column, so the message fills
# whatever pane it lands in and reflows down to a phone without a media query
# — which matters because Gmail's mobile app strips <style> blocks, so a media
# query is exactly the tool not available here.
#
# 940 rather than the 560–680 newsletter convention: this is a report read on a
# desktop, and at 680 Gmail's reading pane left ~400px of empty gutter on
# either side while the per-chantier bullets still wrapped. The prose bands
# below cap themselves at 78ch so the paragraphs stay readable even when the
# frame is wider than a comfortable measure.
WIDTH = 940
SANS = "-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif"

# Reading measure for prose. Independent of WIDTH on purpose: the frame should
# grow with the window, a paragraph should not — past ~78 characters the eye
# loses the line it is returning to. DESIGN.md caps body copy the same way.
MEASURE = "max-width:78ch"


LOGO_CID = "aznet-logo"
# 128px crop of `assets/AZ-bot.png`, kept inside `api/` because the Docker
# image only copies that directory — a path to the repo root resolves at
# development time and 404s in the container.
_LOGO_PATH = Path(__file__).resolve().parent / "assets" / "az-bot.png"


@lru_cache(maxsize=1)
def logo_png() -> Optional[bytes]:
    """The brand mark, read once and cached for the scheduler's send loop.

    Returns None rather than raising if the file is missing: a report that
    arrives with a broken image is still the report, one that never left
    because an icon could not be found is not. The `alt` text carries the
    company name either way, so the header still says who sent it.
    """
    try:
        return _LOGO_PATH.read_bytes()
    except OSError as exc:
        print(f"[mail] logo unavailable ({exc}) — sending without it")
        return None


def _is_figure(value: str) -> bool:
    """Does this value belong in the numeric ledger, or under its own heading?

    Shape, not type: a date and a count both fit a right-aligned mono column,
    a sentence does not. Four words is the cut because "3 jours avant
    l'échéance" is still a reading, while anything longer is prose that would
    wrap inside a column meant to stay one line.
    """
    text = value.strip()
    return len(text) <= 28 and len(text.split()) <= 4 and "\n" not in text


def _band(label: str, content: str) -> str:
    """DESIGN.md's grouping primitive: a label over a top rule, not a box.

    The old layout wrapped every group in a bordered, rounded card — the
    "endless identical rounded card grid" the design system bans by name. A
    band is cheaper in markup *and* the thing the dashboard actually draws.
    """
    return (
        f'<div style="margin:16px 0 0;border-top:1px solid {LINE};padding-top:8px">'
        f'<div style="color:{LABEL};font-size:11px;font-weight:600;letter-spacing:0.8px;'
        f'text-transform:uppercase">{_escape(label)}</div>{content}</div>'
    )


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
            # A `## Synthèse` is a band heading, same treatment as the ones
            # `render_document` draws — the model's structure and ours have to
            # look like one document, not two stacked ones.
            label = line.lstrip("#").strip()
            out.append(
                f'<p style="margin:16px 0 6px;border-top:1px solid {LINE};padding-top:8px;'
                f'color:{LABEL};font-size:11px;'
                'font-weight:600;letter-spacing:0.8px;text-transform:uppercase">'
                f"{_escape(label)}</p>"
            )
        elif line[:1] in {"-", "*", "•"}:
            out.append(
                '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">'
                f'<tr><td width="14" style="padding:3px 0 3px 0;color:{FAINT};'
                'font-size:14px;vertical-align:top">&bull;</td>'
                f'<td style="padding:2px 0;color:{INK};font-size:14px;line-height:1.55;{MEASURE}">'
                f"{_escape(line[1:].strip())}</td></tr></table>"
            )
        else:
            out.append(
                f'<p style="margin:0 0 8px;color:{MUTED};font-size:14px;line-height:1.6;{MEASURE}">'
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
    # One `rows` list carries two different things — `("Rapports", "12")` is a
    # figure, `("Notes", "Prévoir le matériel fibre…")` is prose — and the
    # ledger can only hold the first. Splitting here rather than at the call
    # sites keeps one signature and, more to the point, means a future caller
    # cannot put a sentence in the numbers column by forgetting a parameter.
    pairs = [(str(label), str(value)) for label, value in rows if value]
    figures_rows = [(k, v) for k, v in pairs if _is_figure(v)]
    prose_rows = [(k, v) for k, v in pairs if not _is_figure(v)]

    # The Ledger, not a tile strip: label left, value right in tabular mono,
    # one hairline per row. Same shape as the dashboard's report table, which
    # is the whole point — the reader should recognise it before reading it.
    ledger = "".join(
        f'<tr><td style="padding:5px 0;border-top:1px solid {LINE};color:{MUTED};'
        f'font-size:13px">{_escape(label)}</td>'
        f'<td align="right" style="padding:5px 0;border-top:1px solid {LINE};color:{INK};'
        f'font-family:{MONO};font-size:14px;white-space:nowrap">{_escape(value)}</td></tr>'
        for label, value in figures_rows
    )
    figures = (
        _band(
            "Chiffres",
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"'
            f' style="margin-top:4px">{ledger}</table>',
        )
        if ledger
        else ""
    )
    details = "".join(
        _band(
            label,
            f'<p style="margin:5px 0 0;color:{MUTED};font-size:14px;line-height:1.6;{MEASURE}">'
            f"{_escape(value)}</p>",
        )
        for label, value in prose_rows
    )
    # `rich` is opt-in: a reminder's lead is one sentence and would gain
    # nothing, while a report's is a structured document that the single-<p>
    # treatment flattened into a wall with visible `##` in it. The rich path
    # writes its own band headings, so it is not wrapped in one.
    body = (
        f'<div style="margin-top:4px">{render_rich_text(lead)}</div>'
        if rich
        else _band(
            "Objet",
            f'<p style="margin:5px 0 0;color:{MUTED};font-size:14px;line-height:1.6;{MEASURE}">'
            f"{_escape(lead)}</p>",
        )
    )
    foot = (
        f'<p style="margin:18px 0 0;border-top:1px solid {LINE};padding-top:10px;'
        f'color:{FAINT};font-size:12px;line-height:1.55;{MEASURE}">'
        f"{_escape(footer)}</p>"
        if footer
        else ""
    )
    # A bulletproof button: the padding lives on the <a>, not on a <td>. Square
    # corners, because this system is flat and hairline everywhere else and a
    # lone rounded pill would be the only soft thing on the page.
    button = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:16px 0 0">'
        f'<tr><td style="background:{ACCENT}">'
        f'<a href="{_escape(cta[1])}" style="display:inline-block;padding:11px 20px;'
        f'color:#ffffff;font-size:14px;font-weight:600;text-decoration:none">{_escape(cta[0])}</a>'
        f'</td></tr></table>'
        if cta
        else ""
    )
    # The Masthead, as real text rather than the drawn PNG this used to attach
    # by Content-ID. An image header is one blocked-images setting away from
    # arriving as a grey box, and it cost Pillow, a hex-in-Content-ID round
    # trip and a catch-all `except` that shipped headerless mail on failure.
    # `banner` now chooses how much the slab says, not whether there is one.
    # The mark travels with the message (Content-ID), because a remote src is
    # blocked by default in Gmail and a data: URI is stripped outright. It is
    # the company's real logo file, not something drawn at send time — and the
    # slab is navy precisely so its transparent edge has something to sit on.
    # `width`/`height` as attributes as well as CSS: Outlook ignores the CSS.
    logo = (
        f'<td width="40" style="padding:0 12px 0 0;vertical-align:middle">'
        f'<img src="cid:{LOGO_CID}" width="36" height="36" alt="AZ Net"'
        ' style="display:block;width:36px;height:36px;border:0"></td>'
    )
    # Name and positioning stacked beside the mark, the way the company sets it
    # on fr.aznet.ma — "AZ Net Security & Networking", trading since 2000. The
    # dashboard says "aznet" because it is internal furniture; a report leaving
    # for a client's inbox says the whole name.
    mark = (
        f'<td style="padding:0;vertical-align:middle">'
        f'<div style="color:#ffffff;font-size:17px;font-weight:600;letter-spacing:-0.2px;'
        'line-height:1.2">AZ Net<span style="color:'
        f'{ACCENT_SOFT};font-weight:400"> Security &amp; Networking</span></div>'
        f'<div style="margin-top:3px;color:#8fb4d4;font-size:10px;letter-spacing:1.4px">'
        "RÉSEAUX &middot; SÉCURITÉ &middot; CÂBLAGE</div></td>"
        if banner
        else '<td style="padding:0;vertical-align:middle"><span style="color:#ffffff;'
        'font-size:15px;font-weight:600">AZ Net</span></td>'
    )
    # The period sits under a hairline of its own so it reads as a stamp on the
    # slab rather than as a third piece of the wordmark.
    period = (
        f'<td align="right" valign="middle" style="padding:0;color:#ffffff;'
        f'font-family:{MONO};font-size:10px;letter-spacing:1.4px">'
        f'<span style="display:inline-block;border:1px solid {SLAB_LINE};'
        f'padding:5px 9px">{_escape(caption.upper())}</span></td>'
        if caption
        else ""
    )
    return f"""\
<div style="margin:0;padding:12px;background:{CANVAS};font-family:{SANS}">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="width:100%;max-width:{WIDTH}px;margin:0 auto">
    <tr><td bgcolor="{SLAB}" style="background:{SLAB};padding:14px 22px;border-bottom:3px solid {ACCENT}">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"><tr>{logo}{mark}{period}</tr></table>
    </td></tr>
    <tr><td style="background:{SURFACE};border:1px solid {LINE};border-top:0;padding:16px 22px 20px">
      <h1 style="margin:0;color:{INK};font-size:18px;font-weight:600;letter-spacing:-0.3px;line-height:1.3">{_escape(title)}</h1>
      {figures}
      {body}
      {details}
      {button}
      {foot}
    </td></tr>
    <tr><td style="padding:10px 22px 0;color:{FAINT};font-size:11px;line-height:1.5">
      AZ Net Security &amp; Networking &middot; réseaux, sécurité et câblage depuis 2000
    </td></tr>
  </table>
</div>"""


def sample_report(to: str = "") -> Tuple[str, str]:
    """A fake but complete daily report — subject and HTML — for the test probe.

    `POST /notify/test` used to send one plain sentence, which proves the
    address works and nothing else: the manager configuring their mailbox
    could not see what the thing they were subscribing to would look like, and
    the first real report at 19:00 was the first time anyone saw the layout.
    This sends the *shape* of a report instead, with the figures randomised so
    nobody mistakes it for a real day's numbers — a fixed set would be read as
    data, and today's real totals would be a lie.

    Kept here rather than in main.py because the preview script renders it too,
    and a second copy would drift from the first the day the layout changes.
    """
    import random
    from datetime import date

    techs = random.sample(
        ["Yassine", "Karim", "Rachid", "Mehdi", "Anas", "Hicham", "Youssef"], 3
    )
    sites = random.sample(["Sidi Maarouf", "Aïn Sebaâ", "Anfa", "Nouaceur"], 3)
    goulottes = random.randrange(60, 260, 10)
    cables = random.randrange(120, 700, 10)
    prises = random.randrange(2, 20)
    reports = random.randint(4, 12)
    corps = f"""## Synthèse
Journée de démonstration : {reports} interventions menées par {len(techs)} techniciens \
sur {len(sites)} chantiers, pour {goulottes} m de goulottes posées, {cables} m de \
câbles installés et {prises} prises testées. Les chiffres de ce message sont \
fictifs et tirés au hasard.

## Détail par chantier
- {sites[0]} — {techs[0]} : pose de {goulottes // 2} m de goulottes, \
raccordement de {random.randint(2, 6)} panneaux, RDC et 1er étage.
- {sites[1]} — {techs[1]} : {cables // 3} m de câble tiré, \
{random.randint(1, 4)} bureaux terminés, local technique SR{random.randint(1, 9)}.
- {sites[2]} — {techs[2]} : reprise de brassage, aucun métrage déclaré.

## Problèmes et besoins
- Message de test : aucun problème réel n'est signalé ici.
"""
    today = date.today().strftime("%d/%m/%Y")
    subject = f"aznet — test de notification (exemple de rapport du {today})"
    html = render_document(
        title=f"Rapport journalier — {today} — {reports} interventions",
        lead=corps,
        rows=[
            ("Rapports", str(reports)),
            ("Techniciens", str(len(techs))),
            ("Chantiers", str(len(sites))),
            ("Destinataire", to),
        ],
        footer=(
            "Message de test envoyé depuis les réglages du tableau de bord. "
            "Si vous le recevez, cette adresse recevra les rapports quotidiens "
            "et hebdomadaires — avec, à la place de ces chiffres tirés au "
            "hasard, les données réelles de la journée."
        ),
        cta=(
            "Ouvrir le rapport du jour",
            # The same deep link the real report mails carry, built here rather
            # than imported from `jobs` — jobs imports this module, so reaching
            # back for `_report_link` would be a cycle. One f-string is cheaper
            # than untangling that for a URL shape that has not changed.
            f"{settings.dashboard_url.rstrip('/')}/#/daily?date={date.today().isoformat()}",
        ),
        caption="Exemple",
        rich=True,  # `corps` carries `##` headings, same as a real report
    )
    return subject, html


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
        # The mark rides along as a related part rather than a URL: a remote
        # src is blocked by default in Gmail, Outlook and Apple Mail, and a
        # data: URI is stripped. Attached only when the HTML references it, so
        # a message built without the masthead carries no orphan attachment —
        # which some clients would still show as a paperclip.
        if f"cid:{LOGO_CID}" in html_body:
            blob = logo_png()
            if blob:
                msg.get_payload()[-1].add_related(  # type: ignore[union-attr]
                    blob, maintype="image", subtype="png", cid=f"<{LOGO_CID}>"
                )
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
