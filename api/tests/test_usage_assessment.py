"""Reading a quota out loud (`app/usage.py`).

`test_usage.py` covers the recording side — what each vendor hands back and
what gets stored. This file covers the other half: turning those numbers into
the state and the French sentence the Consommation page prints, plus the two
outbound lookups (`_whatsapp`, `bot_links`) which must never cost the page.

The rule the assertions hold everywhere: a figure whose provenance is not
printed cannot be argued with, and a missing reading is `inconnu`, never zero.
"""
import io
import json
import urllib.request

import pytest

from app import usage


# --- _pos and _ratio_state -------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("42", 42), (42, 42), (None, None), ("", None), ("abc", None),
])
def test_a_header_that_is_not_a_number_records_none_never_zero(raw, expected):
    """Zero would read as "the vendor says nothing is left" — the one
    conclusion a missing header does not support."""
    assert usage._pos(raw) == expected


@pytest.mark.parametrize("remaining,limit,state", [
    (None, 100, None),      # nothing measured
    (50, None, None),       # no ceiling to divide by
    (50, 0, None),          # ditto
    (0, 100, "epuise"),
    (-5, 100, "epuise"),
    (10, 100, "bas"),       # exactly at the threshold
    (11, 100, "ok"),
])
def test_a_state_is_only_stated_when_there_is_something_to_divide(
    remaining, limit, state
):
    assert usage._ratio_state(remaining, limit) == state


@pytest.mark.parametrize("states,worst", [
    (["ok", "epuise", "bas"], "epuise"),
    (["ok", "bas"], "bas"),
    (["ok", "ok"], "ok"),
    ([], "inconnu"),
    (["inconnu", "ok"], "ok"),
])
def test_the_worst_state_travels_to_the_top(states, worst):
    assert usage._worst(states) == worst


# --- note_quota_refusal ----------------------------------------------------

REFUSAL = ("Rate limit reached for model `llama-3.3-70b`: Limit 100000, "
           "tokens per day (TPD): Limit 100000, Used 99997. "
           "Please try again in 2h31m12s.")


def test_a_daily_ceiling_is_recorded_only_a_refusal_ever_states_it(monkeypatch):
    """The headers carry the per-minute window and nothing else, so the page
    reported a comfortable minute while the day was already spent."""
    seen = {}
    monkeypatch.setattr(usage, "record", lambda p, m, k, **f: seen.update(
        provider=p, model=m, kind=k, **f))

    assert usage.note_quota_refusal("groq", "llama", "extraction",
                                    RuntimeError(REFUSAL)) is True
    assert seen["limit_tokens"] == 100000
    # What the vendor says is left, not what we wish were left.
    assert seen["remaining_tokens"] == 3
    assert seen["reset_tokens"] == "2h31m12s"


def test_a_refusal_that_names_no_daily_ceiling_records_nothing(monkeypatch):
    monkeypatch.setattr(usage, "record",
                        lambda *a, **k: pytest.fail("nothing to record"))
    assert usage.note_quota_refusal("groq", "m", "extraction",
                                    RuntimeError("429 too many requests")) is False


def test_a_refusal_without_a_retry_delay_still_records_the_ceiling(monkeypatch):
    seen = {}
    monkeypatch.setattr(usage, "record", lambda p, m, k, **f: seen.update(f))
    text = "tokens per day (TPD): Limit 100000, Used 100000."
    assert usage.note_quota_refusal("groq", "m", "extraction", text) is True
    assert seen["remaining_tokens"] == 0
    assert seen["reset_tokens"] is None


def test_noting_a_refusal_never_replaces_the_error_being_handled(monkeypatch):
    """It runs inside an except block on the extraction path."""
    def boom(*_a, **_k):
        raise RuntimeError("postgres down")

    monkeypatch.setattr(usage, "record", boom)
    assert usage.note_quota_refusal("groq", "m", "extraction", REFUSAL) is False


# --- _assess ---------------------------------------------------------------

def _entry(**kw):
    base = {"provider": "groq", "calls_24h": 12, "limit_source": "live"}
    return {**base, **kw}


def test_an_exhausted_quota_says_so_and_names_its_source():
    out = usage._assess(_entry(remaining_requests=0, limit_requests=1000,
                               reset_requests="1m30s"))
    assert out["state"] == "epuise"
    assert "Quota Groq épuisé" in out["message"]
    assert "compteur du fournisseur" in out["message"]
    assert out["message"].endswith("Réinitialisation dans 1m30s.")


def test_a_low_quota_prints_the_percentage_left():
    out = usage._assess(_entry(remaining_tokens=500, limit_tokens=10_000))
    assert out["state"] == "bas"
    assert "500 jetons restants sur 10000 (5 %" in out["message"]


def test_a_healthy_quota_agrees_with_its_unit():
    out = usage._assess(_entry(remaining_requests=900, limit_requests=1000))
    assert out["state"] == "ok"
    assert "900 requêtes restantes sur 1000" in out["message"]


def test_a_documented_ceiling_is_never_presented_as_a_live_reading():
    out = usage._assess(_entry(provider="gemini", limit_source="documented",
                               remaining_requests=900, limit_requests=1000))
    assert "non confirmé par le fournisseur" in out["message"]


def test_nothing_measurable_is_inconnu_rather_than_a_guess():
    out = usage._assess(_entry(limit_source="unknown", calls_24h=7))
    assert out["state"] == "inconnu"
    assert "7 appel(s) en 24 h, plafond inconnu" in out["message"]


def test_the_worse_of_the_two_windows_is_the_one_reported():
    out = usage._assess(_entry(remaining_requests=900, limit_requests=1000,
                               remaining_tokens=0, limit_tokens=10_000))
    assert out["state"] == "epuise"
    assert "jeton" in out["message"]


# --- _assess_whatsapp ------------------------------------------------------

def test_whatsapp_keeps_metas_ceiling_and_our_count_apart():
    out = usage._assess(_entry(provider="whatsapp", tier="TIER_1K",
                               quality="GREEN", sent_24h=12, error=None))
    assert out["state"] == "ok"
    assert "palier TIER_1K (plafond Meta)" in out["message"]
    assert "12 message(s) envoyés en 24 h d'après nos journaux" in out["message"]


def test_a_red_quality_rating_is_the_honest_warning_signal():
    """Meta gives a ceiling but not our consumption against it, so there is no
    ratio to state."""
    out = usage._assess(_entry(provider="whatsapp", tier="TIER_1K",
                               quality="red", sent_24h=3, error=None))
    assert out["state"] == "bas"
    assert "qualité du numéro dégradée (RED)" in out["message"]


def test_a_failed_whatsapp_lookup_is_inconnu_and_says_why():
    out = usage._assess(_entry(provider="whatsapp", error="401 unauthorized"))
    assert out["state"] == "inconnu"
    assert "quota inconnu — 401 unauthorized" in out["message"]


def test_a_whatsapp_entry_with_no_tier_still_prints_a_sentence():
    out = usage._assess(_entry(provider="whatsapp", quality="GREEN",
                               sent_24h=0, error=None))
    assert "palier inconnu" in out["message"]


# --- _whatsapp and bot_links ----------------------------------------------

class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _fake_urlopen(monkeypatch, payload=None, error=None, seen=None):
    def urlopen(req, timeout=0):
        if seen is not None:
            seen.append(getattr(req, "full_url", req))
        if error is not None:
            raise error
        return _Resp(json.dumps(payload).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


def test_whatsapp_reports_metas_live_ceiling(monkeypatch):
    monkeypatch.setattr(usage_settings(), "whatsapp_access_token", "T")
    monkeypatch.setattr(usage_settings(), "whatsapp_phone_number_id", "1001")
    _fake_urlopen(monkeypatch, {
        "messaging_limit_tier": "TIER_1K", "quality_rating": "GREEN",
        "throughput": {"level": "STANDARD"}, "display_phone_number": "+212 600-000000",
    })
    out = usage._whatsapp()
    assert out["limit_source"] == "live"
    assert (out["tier"], out["quality"], out["throughput"]) == (
        "TIER_1K", "GREEN", "STANDARD")
    assert out["error"] is None


def usage_settings():
    from app.config import settings

    return settings


def test_whatsapp_without_credentials_says_which_are_missing(monkeypatch):
    monkeypatch.setattr(usage_settings(), "whatsapp_access_token", "")
    monkeypatch.setattr(usage_settings(), "whatsapp_phone_number_id", "")
    assert "WHATSAPP_ACCESS_TOKEN" in usage._whatsapp()["error"]


def test_one_vendor_being_down_never_empties_the_panel(monkeypatch):
    monkeypatch.setattr(usage_settings(), "whatsapp_access_token", "T")
    monkeypatch.setattr(usage_settings(), "whatsapp_phone_number_id", "1001")
    _fake_urlopen(monkeypatch, error=OSError("connection reset"))
    out = usage._whatsapp()
    assert out["error"] == "connection reset"
    assert out["tier"] is None


def test_the_bot_links_are_the_two_addresses_that_open_its_own_thread(monkeypatch):
    usage.bot_links.cache_clear()
    monkeypatch.setattr(usage, "_whatsapp",
                        lambda: {"number": "+212 600-000000"})
    monkeypatch.setattr(usage_settings(), "telegram_bot_token", "T")
    _fake_urlopen(monkeypatch, {"result": {"username": "@aznet_bot"}})
    try:
        out = usage.bot_links()
        assert out["whatsapp"]["url"] == "https://wa.me/212600000000"
        assert out["telegram"] == {"username": "@aznet_bot",
                                   "url": "https://t.me/aznet_bot"}
    finally:
        usage.bot_links.cache_clear()


def test_a_link_is_never_worth_a_five_hundred(monkeypatch):
    usage.bot_links.cache_clear()
    monkeypatch.setattr(usage, "_whatsapp", lambda: {"number": None})
    monkeypatch.setattr(usage_settings(), "telegram_bot_token", "T")
    _fake_urlopen(monkeypatch, error=OSError("timeout"))
    try:
        out = usage.bot_links()
        assert out == {"telegram": None, "whatsapp": None,
                       "error_telegram": "timeout"}
    finally:
        usage.bot_links.cache_clear()


def test_no_telegram_token_means_no_telegram_link_and_no_error(monkeypatch):
    usage.bot_links.cache_clear()
    monkeypatch.setattr(usage, "_whatsapp", lambda: {"number": ""})
    monkeypatch.setattr(usage_settings(), "telegram_bot_token", "")
    try:
        assert usage.bot_links() == {"telegram": None, "whatsapp": None}
    finally:
        usage.bot_links.cache_clear()
