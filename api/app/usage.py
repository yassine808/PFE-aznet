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


def snapshot() -> Dict[str, Any]:
    """Everything the usage panel draws. One database read, one Graph call."""
    from app import logs

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        rows = logs.usage_since(since)
        latest = logs.latest_usage_quota()
        wa_sent = logs.whatsapp_sent_since(since)
    except Exception as exc:  # noqa: BLE001
        return {"providers": [], "error": str(exc)[:200]}

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
    return {"providers": providers, "window_hours": 24}
