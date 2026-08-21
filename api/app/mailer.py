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
    """HTML-escape one caller-supplied string.

    The quote is escaped as well as the three angle characters, because this
    is interpolated into attribute values too — `render_document` builds the
    call-to-action as `href="{_escape(url)}"`, and a value carrying a double
    quote would close the attribute and open a new one. In a text node it
    renders as a plain quote either way, so nothing is lost by doing it
    unconditionally.
    """
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
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

    # SystemRandom rather than the Mersenne default: these figures are cosmetic,
    # but a CSPRNG costs nothing here and keeps the security scanners quiet.
    rng = random.SystemRandom()
    techs = rng.sample(
        ["Yassine", "Karim", "Rachid", "Mehdi", "Anas", "Hicham", "Youssef"], 3
    )
    # The real sites, so a test mail looks like the thing it is testing.
    sites = rng.sample(["DGH", "Extralait", "ACAPS"], 3)
    goulottes = rng.randrange(60, 260, 10)
    cables = rng.randrange(120, 700, 10)
    prises = rng.randrange(2, 20)
    reports = rng.randint(4, 12)
    corps = f"""## Synthèse
Journée de démonstration : {reports} interventions menées par {len(techs)} techniciens \
sur {len(sites)} chantiers, pour {goulottes} m de goulottes posées, {cables} m de \
câbles installés et {prises} prises testées. Les chiffres de ce message sont \
fictifs et tirés au hasard.

## Détail par chantier
- {sites[0]} — {techs[0]} : pose de {goulottes // 2} m de goulottes, \
raccordement de {rng.randint(2, 6)} panneaux, RDC et 1er étage.
- {sites[1]} — {techs[1]} : {cables // 3} m de câble tiré, \
{rng.randint(1, 4)} bureaux terminés, local technique SR{rng.randint(1, 9)}.
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


def _compose(recipients: Sequence[str], subject: str, body: str, html: bool,
             html_body: Optional[str],
             attachments: Sequence[Tuple[str, bytes, str]]):
    """Build the message. Split out of `send` so that function stays readable.

    `send`'s job is the conversation with the server: refuse what cannot be
    sent, hand the message over, report who actually took it. Assembling MIME
    parts is a different job that happens to need the same arguments, and
    keeping both in one function meant every part added over time — the HTML
    alternative, the inline mark, the attachments — made the send path itself
    harder to follow.
    """
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

    for name, blob, mime in attachments:
        maintype, _, subtype = mime.partition("/")
        msg.add_attachment(
            blob, maintype=maintype or "application",
            subtype=subtype or "octet-stream", filename=name,
        )

    return msg


def send(
    to: Sequence[str],
    subject: str,
    body: str,
    html: bool = False,
    html_body: Optional[str] = None,
    attachments: Sequence[Tuple[str, bytes, str]] = (),
) -> List[str]:
    """Send one message to every recipient. Returns the addresses **accepted**.

    The returned list is the server's answer, not the caller's request: an
    address the SMTP server refused is dropped from it, so a caller that
    records what it sent records what was actually taken.

    `body` is always the plain-text part — the fallback a text-only client and
    every spam filter reads. `html_body` is the rendered alternative when there
    is one; `html=True` without it keeps the old behaviour of showing the same
    text with its line breaks preserved.

    `attachments` are `(filename, blob, mime)`. They are added after the
    alternatives, so a client that shows only the plain part still gets the
    file — which is the point of attaching the .docx rather than trusting the
    reader to open the dashboard.
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

    msg = _compose(recipients, subject, body, html, html_body, attachments)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            # The return value is the point, not decoration. `send_message`
            # raises only when EVERY address is refused; when the server takes
            # the message for one recipient and rejects another, it returns
            # {address: (code, reason)} and raises nothing. Discarding it made
            # a bounced chef indistinguishable from a served one: the job
            # stored the full list as `sent_to`, the Automation panel showed
            # the report delivered, and that chef simply stopped receiving
            # anything until somebody asked them in person.
            refused = smtp.send_message(msg) or {}
    except Exception as exc:  # noqa: BLE001
        raise MailError(f"envoi échoué: {exc}") from exc

    if refused:
        # Printed AND removed from the answer. The caller records what it is
        # told was served, so the honest answer is the addresses the server
        # actually accepted — never the ones we hoped it would.
        detail = ", ".join(f"{addr} ({code})" for addr, (code, _r) in refused.items())
        print(f"[mail] refusé pour {detail}"[:300], flush=True)
    return [r for r in recipients if r not in refused]
