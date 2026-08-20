"""How much of each free tier is left — and the honesty of each number.

The point of this module is not the arithmetic, it is the provenance. Three
vendors answer the same question with three different degrees of certainty:

- Groq returns real quota headers on every response;
- Gemini returns none at all, so its ceiling is a documented constant;
- Meta gives a live ceiling but not our consumption against it.

Presenting those identically would imply a precision two of them do not have, so
`limit_source` is what these tests pin hardest. No Postgres, no network.
"""
import types

from app import usage


def _raw(headers=None, prompt=11, completion=7):
    """A stand-in for Groq's raw response wrapper."""
    completion_obj = types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="{}"))],
        usage=types.SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
    )
    return types.SimpleNamespace(headers=headers or {}, parse=lambda: completion_obj)


def test_from_groq_reads_the_quota_headers_and_returns_the_parsed_body(monkeypatch):
    seen = {}
    monkeypatch.setattr(usage, "record", lambda *a, **k: seen.update(args=a, kw=k))

    parsed = usage.from_groq(
        _raw({
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-requests": "999",
            "x-ratelimit-limit-tokens": "12000",
            "x-ratelimit-remaining-tokens": "11963",
            "x-ratelimit-reset-requests": "1m26.4s",
        }),
        "llama-3.3-70b-versatile", "extraction",
    )
    # It hands back the completion, not the wrapper: a caller that got the
    # wrapper would fail deep in the happy path with an AttributeError.
    assert parsed.choices[0].message.content == "{}"
    assert seen["args"] == ("groq", "llama-3.3-70b-versatile", "extraction")
    assert seen["kw"]["remaining_requests"] == 999
    assert seen["kw"]["limit_tokens"] == 12000
    assert seen["kw"]["tokens_in"] == 11
    assert seen["kw"]["tokens_out"] == 7
    assert seen["kw"]["reset_requests"] == "1m26.4s"


def test_missing_headers_record_none_not_zero(monkeypatch):
    """A vendor that sends no header must leave the column NULL.

    Zero would be read as "the vendor says nothing is left", which is the one
    conclusion the data does not support.
    """
    seen = {}
    monkeypatch.setattr(usage, "record", lambda *a, **k: seen.update(k))
    usage.from_groq(_raw({}), "m", "stt")
    assert seen["limit_requests"] is None
    assert seen["remaining_requests"] is None


def test_recording_never_raises(monkeypatch):
    """Instrumentation is never worth a failed report."""
    import app.logs as logs

    monkeypatch.setattr(logs, "record_usage", _boom)
    usage.record("groq", "m", "extraction")  # must not raise


def test_from_gemini_records_tokens_and_no_quota(monkeypatch):
    seen = {}
    monkeypatch.setattr(usage, "record", lambda *a, **k: seen.update(args=a, kw=k))
    resp = types.SimpleNamespace(
        usage_metadata=types.SimpleNamespace(prompt_token_count=2, candidates_token_count=7)
    )
    usage.from_gemini(resp, "gemini-flash-lite-latest", "report")
    assert seen["kw"] == {"tokens_in": 2, "tokens_out": 7}
    # Verified against the live API: Gemini returns an empty header dict, so
    # there is no quota to record and none is invented.
    assert "limit_requests" not in seen["kw"]


def test_snapshot_labels_each_ceiling_by_where_it_came_from(monkeypatch):
    import app.logs as logs

    monkeypatch.setattr(logs, "usage_since", lambda since: [
        {"provider": "groq", "model": "llama", "calls": 12, "tokens": 900},
        {"provider": "gemini", "model": "gemini-flash-lite-latest", "calls": 30, "tokens": 400},
    ])
    monkeypatch.setattr(logs, "latest_usage_quota", lambda: {
        "groq": {"limit_requests": 1000, "remaining_requests": 988,
                 "limit_tokens": 12000, "remaining_tokens": 11000,
                 "reset_requests": "1m", "reset_tokens": "2s", "ts": "2026-08-16T22:00:00"},
    })
    monkeypatch.setattr(logs, "whatsapp_sent_since", lambda since: 4)
    monkeypatch.setattr(usage, "_whatsapp", lambda: {
        "provider": "whatsapp", "limit_source": "live", "tier": "TIER_250",
        "quality": "GREEN", "throughput": "STANDARD", "error": None,
    })

    out = usage.snapshot()
    by = {p["provider"]: p for p in out["providers"]}

    # Groq: straight from the headers, on the window Groq itself enforces.
    assert by["groq"]["limit_source"] == "live"
    assert by["groq"]["remaining_requests"] == 988
    assert by["groq"]["calls_24h"] == 12

    # Gemini: usage is measured, the ceiling is a published constant, and the
    # payload says which model that constant was read for.
    assert by["gemini"]["limit_source"] == "documented"
    assert by["gemini"]["documented_for"] == "gemini-flash-lite-latest"
    assert by["gemini"]["remaining_requests"] == 1000 - 30
    # No token ceiling is claimed: Gemini's is per-minute, and a per-minute
    # ceiling next to a 24-hour count would compare two different things.
    assert by["gemini"]["limit_tokens"] is None

    # WhatsApp: Meta's ceiling, our count, and the payload keeps them apart.
    assert by["whatsapp"]["tier"] == "TIER_250"
    assert by["whatsapp"]["sent_24h"] == 4


def test_snapshot_survives_an_unreachable_store(monkeypatch):
    """A usage page that vanishes when Postgres blinks is a page nobody trusts."""
    import app.logs as logs

    monkeypatch.setattr(logs, "usage_since", _boom)
    out = usage.snapshot()
    assert out["providers"] == []
    assert out["error"]


def _boom(*a, **k):
    raise RuntimeError("nope")
