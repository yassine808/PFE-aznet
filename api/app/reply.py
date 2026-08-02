"""Outbound technician replies (POST /reply).

n8n owns the credentials for *reception*; the API sends replies itself so the
dashboard's inbox composer works even while n8n is down. Keys are optional —
unset ones make the endpoint answer 501 with a precise message, the same
fail-loudly policy as every other key in this service.

The message is sent on every active identity the person has (Telegram chat id,
WhatsApp number), so a chef replying from the dashboard reaches the technician
wherever they last wrote from. One channel refusing does not fail the others;
only zero deliveries raises.
"""
from typing import Dict, List

import requests

from app import logs
from app.config import settings


class ReplyError(Exception):
    """Raised when no channel took the message; carries a human-readable detail."""


def _telegram(external_id: str, text: str) -> None:
    token = settings.telegram_bot_token
    if not token:
        raise ReplyError("Réponse Telegram non configurée (TELEGRAM_BOT_TOKEN manquant)")
    res = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": external_id, "text": text},
        timeout=15,
    )
    if not res.ok:
        raise ReplyError(f"Telegram a refusé ({res.status_code}): {res.text[:200]}")


def _whatsapp(external_id: str, text: str) -> None:
    token = settings.whatsapp_access_token
    number_id = settings.whatsapp_phone_number_id
    if not token or not number_id:
        raise ReplyError(
            "Réponse WhatsApp non configurée "
            "(WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID manquants)"
        )
    res = requests.post(
        f"https://graph.facebook.com/v23.0/{number_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messaging_product": "whatsapp",
            "to": logs.normalize_external_id("whatsapp", external_id),
            "type": "text",
            "text": {"body": text},
        },
        timeout=15,
    )
    if not res.ok:
        raise ReplyError(f"WhatsApp a refusé ({res.status_code}): {res.text[:200]}")


def reply_to_identities(identities: List[dict], text: str) -> Dict[str, list]:
    """Send `text` to every identity given. Returns the channels that took it.

    Raises ReplyError only when *no* channel delivered, so a partial success
    (Telegram on, WhatsApp's 24h window closed) still reports what went out.
    """
    delivered: List[dict] = []
    failures: List[str] = []
    for identity in identities:
        channel = (identity.get("channel") or "").strip().lower()
        external_id = (identity.get("external_id") or "").strip()
        if not channel or not external_id:
            continue
        try:
            if channel == "telegram":
                _telegram(external_id, text)
            elif channel == "whatsapp":
                _whatsapp(external_id, text)
            else:
                failures.append(f"{channel}: canal inconnu")
                continue
            delivered.append({"channel": channel})
        except ReplyError as exc:
            failures.append(f"{channel}: {exc}")
    if not delivered:
        raise ReplyError("; ".join(failures) if failures else "aucune identité active")
    return {"delivered": delivered}
