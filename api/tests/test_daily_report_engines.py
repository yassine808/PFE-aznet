"""The report engines and their payload (`app/daily_report.py`).

`test_daily_report_endpoint.py` covers the HTTP route; this file covers the two
model callers underneath it and `_payload`, whose whole reason for existing is
that the mail body and the attached .docx must not state different figures for
one day.

Both SDKs are faked at `sys.modules` and both cached clients are cleared around
every test — a cached client outlives a monkeypatched module, which is the trap
`test_extraction_profile.py` documents.
"""
import json
import sys
import types

import pytest

from app import daily_report


@pytest.fixture(autouse=True)
def _clear_clients():
    daily_report._gemini_client.cache_clear()
    daily_report._groq_client.cache_clear()
    yield
    daily_report._gemini_client.cache_clear()
    daily_report._groq_client.cache_clear()


@pytest.fixture(autouse=True)
def _no_usage_recording(monkeypatch):
    """Usage recording is instrumentation and has its own suite; here it would
    only drag Postgres into a test about prompts."""
    monkeypatch.setattr(daily_report.usage, "from_gemini", lambda *a, **k: None)
    monkeypatch.setattr(daily_report.usage, "from_groq", lambda resp, *a, **k: resp)


CONTENT = daily_report.DailyReportContent(objet="Rapport", corps="## Synthèse\nRAS.")


def _fake_gemini(monkeypatch, *, parsed: object = CONTENT, text="", error=None):
    calls = {}

    def generate_content(model, contents, config):
        calls.update(model=model, contents=contents, config=config)
        if error is not None:
            raise error
        return types.SimpleNamespace(parsed=parsed, text=text)

    class Client:
        def __init__(self, api_key):
            calls["key"] = api_key
            self.models = types.SimpleNamespace(generate_content=generate_content)

    genai = types.SimpleNamespace(Client=Client)
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(genai=genai))
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setattr(daily_report.settings, "gemini_api_key", "k")
    return calls


def _fake_groq(monkeypatch, *, content='{"objet":"O","corps":"C"}', error=None):
    calls = {}

    def create(**kwargs):
        calls.update(kwargs)
        if error is not None:
            raise error
        choice = types.SimpleNamespace(message=types.SimpleNamespace(content=content))
        return types.SimpleNamespace(choices=[choice])

    class Groq:
        def __init__(self, api_key):
            calls["key"] = api_key
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    with_raw_response=types.SimpleNamespace(create=create)))

    monkeypatch.setitem(sys.modules, "groq", types.SimpleNamespace(Groq=Groq))
    monkeypatch.setattr(daily_report.settings, "groq_api_key", "k")
    return calls


# --- _payload --------------------------------------------------------------

ROWS = [
    {"date": "2026-08-20", "technicien": "Yassine", "chantier": "DGH",
     "goulotte_m": 40, "observations": "RAS",
     # plumbing and blanks, neither of which should reach the model
     "correlation_id": "c-1", "STT_model": "gemini", "canal": "telegram",
     "confidence": 0.9, "lien_audio": "http://x", "role": "tech",
     "cables_m": "", "fibre_m": None},
]


def test_the_totals_are_computed_before_the_model_sees_the_rows():
    """The model used to add the rows up in prose, and the .docx table added
    them up again from the catalogue — two figures for one day."""
    out = daily_report._payload(ROWS)
    assert out.startswith("TOTAUX de la période (déjà calculés) :")
    totals = json.loads(out.splitlines()[1])
    assert any("40" in str(v) for v in totals.values())


def test_plumbing_and_empty_cells_never_reach_the_prompt():
    out = daily_report._payload(ROWS)
    trimmed = json.loads(out.rsplit("\n", 1)[-1])[0]
    assert set(trimmed) == {"date", "technicien", "chantier", "goulotte_m",
                            "observations"}


def test_a_day_with_no_quantities_says_so_rather_than_sending_an_empty_object():
    out = daily_report._payload([{"date": "2026-08-20", "technicien": "Y"}])
    assert "aucune quantité chiffrée" in out


def test_alerts_arrive_as_finished_sentences(monkeypatch):
    from app import stock

    monkeypatch.setattr(stock, "line", lambda a: f"{a['champ']} bas")
    out = daily_report._payload(ROWS, [{"champ": "cables_installes_m"}])
    assert "ALERTES (déjà calculées, ne pas recalculer) :" in out
    assert "- cables_installes_m bas" in out


def test_no_alerts_means_no_alerts_block():
    assert "ALERTES" not in daily_report._payload(ROWS)


# --- _generate_gemini ------------------------------------------------------

def test_gemini_needs_a_key(monkeypatch):
    monkeypatch.setattr(daily_report.settings, "gemini_api_key", "")
    with pytest.raises(daily_report.DailyReportError, match="GEMINI_API_KEY"):
        daily_report._generate_gemini("2026-08-20", "{}")


def test_gemini_asks_for_the_schema_and_returns_the_parsed_object(monkeypatch):
    calls = _fake_gemini(monkeypatch)
    out = daily_report._generate_gemini("2026-08-20", "ROWS", "## Alertes")
    assert out is CONTENT
    assert calls["config"]["response_schema"] is daily_report.DailyReportContent
    # Date, the alerts section and the rows all reach the prompt.
    assert "2026-08-20" in calls["contents"]
    assert "## Alertes" in calls["contents"]
    assert calls["contents"].endswith("ROWS")


def test_an_unparseable_gemini_answer_raises_rather_than_returning_a_blank(monkeypatch):
    _fake_gemini(monkeypatch, parsed=None, text="not json at all")
    with pytest.raises(daily_report.DailyReportError, match="unparseable"):
        daily_report._generate_gemini("2026-08-20", "{}")


def test_a_gemini_sdk_failure_is_named(monkeypatch):
    _fake_gemini(monkeypatch, error=RuntimeError("503 unavailable"))
    with pytest.raises(daily_report.DailyReportError, match="gemini: 503 unavailable"):
        daily_report._generate_gemini("2026-08-20", "{}")


# --- _generate_groq --------------------------------------------------------

def test_groq_needs_a_key(monkeypatch):
    monkeypatch.setattr(daily_report.settings, "groq_api_key", "")
    with pytest.raises(daily_report.DailyReportError, match="GROQ_API_KEY"):
        daily_report._generate_groq("2026-08-20", "{}")


def test_groq_asks_for_json_and_parses_the_completion(monkeypatch):
    calls = _fake_groq(monkeypatch)
    out = daily_report._generate_groq("2026-08-20", "ROWS")
    assert (out.objet, out.corps) == ("O", "C")
    assert calls["response_format"] == {"type": "json_object"}
    assert calls["messages"][1] == {"role": "user", "content": "ROWS"}


def test_an_empty_groq_completion_is_a_failure_not_an_empty_report(monkeypatch):
    _fake_groq(monkeypatch, content="")
    with pytest.raises(daily_report.DailyReportError, match="empty completion"):
        daily_report._generate_groq("2026-08-20", "{}")


def test_a_groq_sdk_failure_is_named(monkeypatch):
    _fake_groq(monkeypatch, error=RuntimeError("429 rate limited"))
    with pytest.raises(daily_report.DailyReportError, match="groq: 429 rate limited"):
        daily_report._generate_groq("2026-08-20", "{}")


# --- generate_daily_report -------------------------------------------------

def test_the_primary_engine_answers_and_groq_is_never_called(monkeypatch):
    _fake_gemini(monkeypatch)
    monkeypatch.setattr(daily_report, "_generate_groq",
                        lambda *a, **k: pytest.fail("fallback must not run"))
    assert daily_report.generate_daily_report("2026-08-20", ROWS) is CONTENT


def test_groq_takes_over_when_gemini_fails(monkeypatch):
    _fake_gemini(monkeypatch, error=RuntimeError("503"))
    _fake_groq(monkeypatch)
    out = daily_report.generate_daily_report("2026-08-20", ROWS)
    assert out.objet == "O"


def test_both_engines_failing_names_both(monkeypatch):
    _fake_gemini(monkeypatch, error=RuntimeError("503 unavailable"))
    _fake_groq(monkeypatch, error=RuntimeError("429 rate limited"))
    with pytest.raises(daily_report.DailyReportError) as err:
        daily_report.generate_daily_report("2026-08-20", ROWS)
    msg = str(err.value)
    assert "gemini: gemini: 503 unavailable" in msg
    assert "groq: groq: 429 rate limited" in msg


def test_the_alerts_section_is_only_added_when_there_are_alerts(monkeypatch):
    from app import stock

    monkeypatch.setattr(stock, "line", lambda a: "cable bas")
    calls = _fake_gemini(monkeypatch)

    daily_report.generate_daily_report("2026-08-20", ROWS)
    assert "## Alertes matériel" not in calls["contents"]

    daily_report.generate_daily_report("2026-08-20", ROWS, [{"champ": "x"}])
    assert "## Alertes matériel" in calls["contents"]
