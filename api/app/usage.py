"""How much of each free tier is left.

The whole project runs on free tiers, and until now nothing said how close any
of them was to its ceiling. That matters here more than it would elsewhere: when
a quota runs out the symptom is not an error anyone sees, it is the extraction
chain quietly falling through to the next vendor, or WhatsApp going silent —
both of which look exactly like a working day.

**Every number here is measured, never estimated**, and each one says where it
came from, because the three vendors are not equally honest:

- **Groq** returns real quota on every response: `x-ratelimit-limit-requests`,
  `-remaining-requests`, `-limit-tokens`, `-remaining-tokens` and the two reset
  windows. Reading them costs nothing — the call already happened — but it does
  mean going through `.with_raw_response`, because the parsed object drops the
  headers. `limit_source: "live"`.
- **Gemini** returns `usage_metadata` (real token counts) and **no quota
  headers at all** — verified against the live API, the header dict comes back
  empty. So consumption is measured and the *ceiling* is a documented constant
  below. `limit_source: "documented"`, and the panel says so rather than
  implying Google told us.
- **WhatsApp** exposes its ceiling live (`messaging_limit_tier`,
  `quality_rating`, `throughput`) but not our consumption against it without a
  WABA id the System User token does not carry. So the ceiling is Meta's and
  the count is ours, from `pipeline_logs`. `limit_source: "live"` for the tier,
  and the count is labelled as our own.

Recording never raises and never blocks: a usage row that cannot be written must
not cost a technician their report. Every call site is wrapped accordingly.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# Documented free-tier ceilings for the Gemini models this project calls.
# **These are constants, not measurements** — Google publishes them and changes
# them, and the API returns nothing to check them against. Anything derived from
# them is reported with `limit_source: "documented"` so a reader never mistakes
# one for a live figure. Re-check when a model is added to a chain.
GEMINI_DOCUMENTED = {
    "gemini-flash-lite-latest": {"rpd": 1000, "tpm": 250_000},
    "gemini-flash-latest": {"rpd": 250, "tpm": 250_000},
}
GEMINI_DEFAULT = {"rpd": 250, "tpm": 250_000}


def _pos(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def record(provider: str, model: str, kind: str, **fields) -> None:
    """One API call, best-effort. Never raises: this is instrumentation."""
    try:
        from app import logs

        logs.record_usage(provider=provider, model=model, kind=kind, **fields)
    except Exception:  # noqa: BLE001 - a usage row is never worth a failed report
        pass


def from_groq(raw, model: str, kind: str):
    """Record a Groq call from its raw response, and hand back the parsed one.

    Returns the parsed body so the call site reads as one expression and cannot
    forget to unwrap it — the failure mode of `.with_raw_response` is a caller
    that treats the wrapper as the completion and gets an AttributeError deep in
    the happy path.
    """
    headers = {}
    try:
        headers = raw.headers
    except Exception:  # noqa: BLE001
        pass
    parsed = raw.parse()
    usage = getattr(parsed, "usage", None)
    record(
        "groq", model, kind,
        tokens_in=getattr(usage, "prompt_tokens", None),
        tokens_out=getattr(usage, "completion_tokens", None),
        limit_requests=_pos(headers.get("x-ratelimit-limit-requests")),
        remaining_requests=_pos(headers.get("x-ratelimit-remaining-requests")),
        limit_tokens=_pos(headers.get("x-ratelimit-limit-tokens")),
        remaining_tokens=_pos(headers.get("x-ratelimit-remaining-tokens")),
        reset_requests=headers.get("x-ratelimit-reset-requests"),
        reset_tokens=headers.get("x-ratelimit-reset-tokens"),
    )
    return parsed


def from_gemini(resp, model: str, kind: str) -> None:
    """Record a Gemini call. Tokens are real; there is no quota to read."""
    meta = getattr(resp, "usage_metadata", None)
    record(
        "gemini", model, kind,
        tokens_in=getattr(meta, "prompt_token_count", None),
        tokens_out=getattr(meta, "candidates_token_count", None),
    )


# ── The panel's payload ─────────────────────────────────────────────────────


def _whatsapp() -> Dict[str, Any]:
    """Meta's live ceiling for this number, plus our own count against it.

    The tier is what Meta will let this number send in 24 h; the count is what
    we actually sent, from our own logs. They come from different places and the
    payload says so — pretending the second is Meta's would be inventing a
    figure nobody measured.
    """
    import json
    import urllib.request

    from app.config import settings

    out: Dict[str, Any] = {
        "provider": "whatsapp", "limit_source": "live",
        "tier": None, "quality": None, "throughput": None, "error": None,
    }
    token = settings.whatsapp_access_token
    phone = settings.whatsapp_phone_number_id
    if not token or not phone:
        out["error"] = "WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID absent"
        return out
    url = (f"https://graph.facebook.com/v21.0/{phone}"
           "?fields=quality_rating,throughput,messaging_limit_tier,display_phone_number")
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - fixed host
            data = json.load(resp)
        out.update(
            tier=data.get("messaging_limit_tier"),
            quality=data.get("quality_rating"),
            throughput=(data.get("throughput") or {}).get("level"),
            number=data.get("display_phone_number"),
        )
    except Exception as exc:  # noqa: BLE001 - one vendor down must not empty the panel
        out["error"] = str(exc)[:200]
    return out


# ── Is a quota actually hit? ────────────────────────────────────────────────
#
# The numbers above are useless to a reader who has to divide them in their
# head, and the case that matters most — a tier that has actually run out — was
# the one nothing said out loud. So every provider carries a `state` a UI can
# colour on and a French `message` it can print as-is. The sentence always names
# its source, for the same reason `limit_source` exists: "il reste 0 requête"
# read from a Groq header and the same words derived from a documented ceiling
# are not the same claim.
#
# ponytail: one flat threshold (10 %) rather than stock.py's days-of-cover
# model — an API quota resets on a fixed window, so there is no consumption rate
# to project against, and % of the window is the honest unit here.
PCT_BAS = 10

STATES = ("epuise", "bas", "ok", "inconnu")


def _ratio_state(remaining: Optional[int], limit: Optional[int]) -> Optional[str]:
    """None when there is nothing to divide — never a zero, never a guess."""
    if remaining is None or not limit:
        return None
    if remaining <= 0:
        return "epuise"
    return "bas" if remaining * 100 <= limit * PCT_BAS else "ok"


def _worst(states: List[str]) -> str:
    for s in STATES:
        if s in states:
            return s
    return "inconnu"


def _assess(entry: Dict[str, Any]) -> Dict[str, Any]:
    """State + French sentence for one provider. Adds nothing it cannot measure."""
    label = {"groq": "Groq", "gemini": "Gemini", "whatsapp": "WhatsApp"}.get(
        entry["provider"], entry["provider"]
    )
    source = entry.get("limit_source")
    origin = {"live": "compteur du fournisseur",
              "documented": "plafond documenté, non confirmé par le fournisseur"}.get(source, "")

    if entry["provider"] == "whatsapp":
        # Meta gives a ceiling but not our consumption against it, so there is
        # no ratio to state — the honest signals are the quality rating and
        # whether the call answered at all.
        if entry.get("error"):
            return {"state": "inconnu",
                    "message": f"{label} : quota inconnu — {entry['error']}"}
        sent = entry.get("sent_24h")
        tier = entry.get("tier") or "inconnu"
        if str(entry.get("quality") or "").upper() == "RED":
            return {"state": "bas",
                    "message": (f"{label} : qualité du numéro dégradée (RED) — Meta réduit "
                                f"le palier {tier}. {sent} message(s) envoyés en 24 h.")}
        return {"state": "ok",
                "message": (f"{label} : palier {tier} (plafond Meta), "
                            f"{sent} message(s) envoyés en 24 h d'après nos journaux.")}

    req = _ratio_state(entry.get("remaining_requests"), entry.get("limit_requests"))
    tok = _ratio_state(entry.get("remaining_tokens"), entry.get("limit_tokens"))
    known = [s for s in (req, tok) if s]
    if not known:
        return {"state": "inconnu",
                "message": (f"{label} : {entry['calls_24h']} appel(s) en 24 h, "
                            f"plafond inconnu — rien à comparer.")}

    state = _worst(known)
    # "jetons restants" / "requêtes restantes" — the agreement is part of the
    # sentence, and this string is printed to the operator as it stands.
    unit, agreed = ("requêtes", "restantes") if req == state else ("jetons", "restants")
    left = entry.get("remaining_requests") if unit == "requêtes" else entry.get("remaining_tokens")
    ceiling = entry.get("limit_requests") if unit == "requêtes" else entry.get("limit_tokens")
    reset = entry.get("reset_requests") if unit == "requêtes" else entry.get("reset_tokens")
    tail = f" Réinitialisation dans {reset}." if reset else ""
    if state == "epuise":
        head = (f"Quota {label} épuisé : plus aucune {unit[:-1]} disponible "
                f"sur {ceiling} ({origin}).")
    elif state == "bas":
        head = (f"Quota {label} bas : {left} {unit} {agreed} sur {ceiling} "
                f"({left * 100 // ceiling} %, {origin}).")
    else:
        head = f"{label} : {left} {unit} {agreed} sur {ceiling} ({origin})."
    return {"state": state, "message": head + tail}


def snapshot() -> Dict[str, Any]:
    """Everything the usage panel draws. One database read, one Graph call."""
    from app import logs

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        rows = logs.usage_since(since)
        latest = logs.latest_usage_quota()
        wa_sent = logs.whatsapp_sent_since(since)
    except Exception as exc:  # noqa: BLE001
        return {"providers": [], "error": str(exc)[:200],
                "state": "inconnu", "hit": False}

    providers: List[Dict[str, Any]] = []
    for name in ("groq", "gemini"):
        mine = [r for r in rows if r["provider"] == name]
        calls = sum(int(r["calls"]) for r in mine)
        tokens = sum(int(r["tokens"] or 0) for r in mine)
        entry: Dict[str, Any] = {
            "provider": name,
            "calls_24h": calls,
            "tokens_24h": tokens,
            "by_model": [
                {"model": r["model"], "calls": int(r["calls"]), "tokens": int(r["tokens"] or 0)}
                for r in sorted(mine, key=lambda r: -int(r["calls"]))
            ],
        }
        quota = latest.get(name)
        if name == "groq" and quota:
            # Straight from the last response's headers: a real remaining count
            # against a real ceiling, on the window Groq itself is enforcing.
            entry.update(
                limit_source="live",
                limit_requests=quota.get("limit_requests"),
                remaining_requests=quota.get("remaining_requests"),
                limit_tokens=quota.get("limit_tokens"),
                remaining_tokens=quota.get("remaining_tokens"),
                reset_requests=quota.get("reset_requests"),
                reset_tokens=quota.get("reset_tokens"),
                measured_at=quota.get("ts"),
            )
        elif name == "gemini":
            # No quota header exists, so the ceiling is a documented constant
            # and the panel must say which model it was read for.
            model = entry["by_model"][0]["model"] if entry["by_model"] else None
            doc = GEMINI_DOCUMENTED.get(model or "", GEMINI_DEFAULT)
            entry.update(
                limit_source="documented",
                limit_requests=doc["rpd"],
                remaining_requests=max(0, doc["rpd"] - calls),
                limit_tokens=None,
                remaining_tokens=None,
                documented_for=model,
            )
        else:
            entry["limit_source"] = "unknown"
        providers.append(entry)

    wa = _whatsapp()
    wa["sent_24h"] = wa_sent
    providers.append(wa)
    for entry in providers:
        entry.update(_assess(entry))
    # The worst state travels to the top so a header badge does not have to
    # re-derive it, and `hit` is the one question the TO-DO asked: has any free
    # tier actually run out right now.
    states = [e["state"] for e in providers]
    return {"providers": providers, "window_hours": 24,
            "state": _worst(states), "hit": "epuise" in states}
