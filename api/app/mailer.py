"""Outgoing mail — one SMTP path for the test probe and the scheduled reports.

Kept apart from main.py because the scheduler sends mail from a background
thread, and duplicating the SMTP block would mean fixing a Gmail quirk twice.
smtplib is lazy-imported for symmetry with the other providers; credentials are
checked at call time so an unconfigured install starts fine and fails loudly
only when someone actually tries to send.
"""
from typing import List, Sequence

from app.config import settings


class MailError(RuntimeError):
    pass


def send(to: Sequence[str], subject: str, body: str, html: bool = False) -> List[str]:
    """Send one message to every recipient. Returns the addresses served."""
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
    if html:
        msg.add_alternative(body.replace("\n", "<br>"), subtype="html")

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        raise MailError(f"envoi échoué: {exc}") from exc
    return recipients
