"""The extraction chain and its two engines (`app/extraction.py`).

`test_extraction_profile.py` covers how a profile reaches the prompt; this file
covers the rest — the Gemini schema surgery, the two callers, and `_run_chain`'s
two hard-won rules: an engine that answers with no figures on a message full of
digits has not answered, and the first such answer is still kept if every engine
does it.

Both SDKs are faked at `sys.modules`. The cached clients are cleared around each
test: a cached client outlives a monkeypatched module and would be handed to the
next test.
"""
import sys
import types

import pytest

from app import extraction
from app.schemas import ExtractedReport


@pytest.fixture(autouse=True)
def _clear_clients():
    extraction._gemini_client.cache_clear()
    extraction._groq_client.cache_clear()
    yield
    extraction._gemini_client.cache_clear()
    extraction._groq_client.cache_clear()


@pytest.fixture(autouse=True)
def _no_usage_recording(monkeypatch):
    monkeypatch.setattr(extraction.usage, "from_gemini", lambda *a, **k: None)
    monkeypatch.setattr(extraction.usage, "from_groq", lambda resp, *a, **k: resp)
    monkeypatch.setattr(extraction.usage, "note_quota_refusal", lambda *a, **k: None)


FULL = '{"resume": "Pose de goulottes.", "goulotte_m": 40}'
EMPTY = '{"resume": "Rien de chiffré.", "etages": ["RDC"]}'


# --- _parse_chain ----------------------------------------------------------

def test_parse_chain_reads_pairs_and_trims():
    assert extraction._parse_chain(" gemini : a , groq:b ,") == [("gemini", "a"),
                                                                 ("groq", "b")]


def test_a_chain_entry_without_a_model_raises():
    with pytest.raises(extraction.ExtractionError, match="malformed"):
        extraction._parse_chain("gemini")


def test_an_empty_chain_raises():
    with pytest.raises(extraction.ExtractionError, match="empty extraction chain"):
        extraction._parse_chain(" , ")


# --- the two framing blocks ------------------------------------------------

@pytest.mark.parametrize("value", [None, "", "   "])
def test_an_absent_profile_or_caption_adds_nothing(value):
    assert extraction._profile_block(value) == ""
    assert extraction._caption_block(value) == ""


def test_a_profile_is_framed_as_context_and_forbidden_as_a_source():
    block = extraction._profile_block("  Intervient surtout sur Sidi Maarouf.  ")
    assert "Contexte sur l'auteur" in block
    assert "JAMAIS une source de valeurs" in block
    assert "Intervient surtout sur Sidi Maarouf." in block


def test_a_caption_is_framed_as_message_content_and_allowed_as_a_source():
    block = extraction._caption_block("40 m posés ce matin")
    assert "Légende envoyée avec la photo" in block
    assert "source de valeurs" in block


# --- the Gemini schema -----------------------------------------------------

def test_nested_models_are_inlined_before_defs_is_dropped():
    """Stripping `$defs` while leaving the `$ref` produced a schema pointing at
    nothing, and both Gemini engines died with a bare KeyError."""
    schema = extraction._gemini_schema()
    flat = repr(schema)
    assert "$defs" not in flat
    assert "$ref" not in flat
    # `additionalProperties` is what Gemini rejected outright on `livraisons`.
    assert "additionalProperties" not in flat
    assert schema["properties"]["resume"]["type"] in ("string", ["string", "null"])


def test_a_self_referencing_definition_degrades_to_a_plain_object():
    defs = {"Node": {"type": "object",
                     "properties": {"child": {"$ref": "#/$defs/Node"}}}}
    out: dict = extraction._inline_refs({"$ref": "#/$defs/Node"}, defs)
    assert out["properties"]["child"] == {"type": "object"}


def test_a_reference_to_a_missing_definition_degrades_too():
    assert extraction._inline_refs({"$ref": "#/$defs/Gone"}, {}) == {"type": "object"}


def test_lists_and_scalars_pass_through_both_walkers():
    node = {"anyOf": [{"type": "string"}, 3, None]}
    assert extraction._inline_refs(node, {}) == node
    assert extraction._strip_unsupported(node) == node


# --- fakes -----------------------------------------------------------------

def _fake_gemini(monkeypatch, *, text=FULL, error=None):
    calls = {}

    def generate_content(model, contents, config):
        calls.update(model=model, contents=contents, config=config)
        if error is not None:
            raise error
        return types.SimpleNamespace(text=text)

    class Client:
        def __init__(self, api_key):
            calls["key"] = api_key
            self.models = types.SimpleNamespace(generate_content=generate_content)

    class Part:
        @staticmethod
        def from_bytes(data, mime_type):
            calls["part"] = {"data": data, "mime_type": mime_type}
            return "PART"

    genai = types.SimpleNamespace(Client=Client, types=types.SimpleNamespace(Part=Part))
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(genai=genai))
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", genai.types)
    monkeypatch.setattr(extraction.settings, "gemini_api_key", "k")
    return calls


def _fake_groq(monkeypatch, *, content=FULL, error=None):
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
    monkeypatch.setattr(extraction.settings, "groq_api_key", "k")
    return calls


# --- _call_gemini ----------------------------------------------------------

def test_gemini_needs_a_key(monkeypatch):
    monkeypatch.setattr(extraction.settings, "gemini_api_key", "")
    with pytest.raises(extraction.ExtractionError, match="GEMINI_API_KEY"):
        extraction._call_gemini("m", text="salam")


def test_the_text_path_sends_instructions_then_the_message(monkeypatch):
    calls = _fake_gemini(monkeypatch)
    out = extraction._call_gemini("m", text="40 m de goulotte", profile="Contexte.")
    assert out.goulotte_m == 40
    assert calls["contents"].endswith("40 m de goulotte")
    assert "Contexte sur l'auteur" in calls["contents"]


def test_the_image_path_sends_the_bytes_as_a_part_with_the_caption(monkeypatch):
    calls = _fake_gemini(monkeypatch)
    extraction._call_gemini("m", image=b"JPEG", mime_type="image/jpeg",
                            caption="40 m posés")
    assert calls["part"] == {"data": b"JPEG", "mime_type": "image/jpeg"}
    assert "Légende envoyée avec la photo" in calls["contents"][1]


def test_a_gemini_sdk_failure_names_the_engine(monkeypatch):
    _fake_gemini(monkeypatch, error=RuntimeError("400 bad schema"))
    with pytest.raises(extraction.ExtractionError, match="gemini/m: 400 bad schema"):
        extraction._call_gemini("m", text="x")


def test_an_answer_that_does_not_fit_the_contract_fails_this_engine(monkeypatch):
    """It has to raise rather than return a blank, or the chain never reaches
    the engine that can read the message."""
    _fake_gemini(monkeypatch, text="not json")
    with pytest.raises(extraction.ExtractionError, match="unparseable"):
        extraction._call_gemini("m", text="x")


# --- _call_groq ------------------------------------------------------------

def test_groq_refuses_an_image_before_it_asks_for_a_key(monkeypatch):
    monkeypatch.setattr(extraction.settings, "groq_api_key", "")
    with pytest.raises(extraction.ExtractionError, match="no vision model"):
        extraction._call_groq("m", image=b"JPEG")


def test_groq_needs_a_key(monkeypatch):
    monkeypatch.setattr(extraction.settings, "groq_api_key", "")
    with pytest.raises(extraction.ExtractionError, match="GROQ_API_KEY"):
        extraction._call_groq("m", text="x")


def test_groq_carries_the_profile_too(monkeypatch):
    """Groq is the primary text engine: leaving the profile out meant the
    nightly rebuild was stored and then silently dropped on every request."""
    calls = _fake_groq(monkeypatch)
    out = extraction._call_groq("m", text="40 m", profile="Contexte.")
    assert out.goulotte_m == 40
    system = calls["messages"][0]["content"]
    assert "Contexte sur l'auteur" in system
    assert calls["messages"][1] == {"role": "user", "content": "40 m"}
    assert calls["response_format"] == {"type": "json_object"}


def test_an_empty_groq_completion_is_a_failure(monkeypatch):
    _fake_groq(monkeypatch, content="")
    with pytest.raises(extraction.ExtractionError, match="empty completion"):
        extraction._call_groq("m", text="x")


def test_a_groq_refusal_is_recorded_as_a_possible_daily_ceiling(monkeypatch):
    """The headers only carry the per-minute window; a refusal is the one place
    Groq states the daily one."""
    noted = []
    monkeypatch.setattr(extraction.usage, "note_quota_refusal",
                        lambda *a, **k: noted.append(a))
    _fake_groq(monkeypatch, error=RuntimeError("429 daily limit"))
    with pytest.raises(extraction.ExtractionError, match="groq/m: 429 daily limit"):
        extraction._call_groq("m", text="x")
    assert noted
    assert noted[0][:3] == ("groq", "m", "extraction")


# --- _carries_figures ------------------------------------------------------

def test_names_and_floors_are_not_figures():
    report = ExtractedReport.model_validate_json(EMPTY)
    assert extraction._carries_figures(report) is False


def test_a_quantity_an_article_or_a_delivery_all_count():
    assert extraction._carries_figures(
        ExtractedReport.model_validate_json(FULL)) is True
    assert extraction._carries_figures(ExtractedReport(
        resume="x", articles_libres={"switch 24 ports": 2})) is True
    assert extraction._carries_figures(ExtractedReport(
        resume="x", nature="livraison", livraisons={"cables_installes_m": 500})) is True


# --- _run_chain ------------------------------------------------------------

def _chain(monkeypatch, engines):
    """Replace `_ENGINES` with callables keyed by provider name."""
    monkeypatch.setattr(extraction, "_ENGINES", engines)


def test_the_first_engine_that_answers_wins(monkeypatch):
    _chain(monkeypatch, {
        "a": lambda model, **kw: ExtractedReport.model_validate_json(FULL),
        "b": lambda model, **kw: pytest.fail("must not be reached"),
    })
    report, who = extraction._run_chain("a:m1,b:m2", text="40 m")
    assert (report.goulotte_m, who) == (40, "a/m1")


def test_an_unknown_provider_is_named_and_skipped(monkeypatch):
    _chain(monkeypatch, {"a": lambda model, **kw:
                         ExtractedReport.model_validate_json(FULL)})
    report, who = extraction._run_chain("nope:x,a:m1", text="40 m")
    assert who == "a/m1"


def test_an_engine_answering_with_no_figures_does_not_end_the_chain(monkeypatch):
    """A message listing forty items came back with every quantity null, and
    the one model that could read it was never asked."""
    seen = []

    def weak(model, **kw):
        seen.append(model)
        return ExtractedReport.model_validate_json(EMPTY)

    def strong(model, **kw):
        seen.append(model)
        return ExtractedReport.model_validate_json(FULL)

    _chain(monkeypatch, {"a": weak, "b": strong})
    report, who = extraction._run_chain("a:m1,b:m2", text="40 m de goulotte")
    assert (who, seen) == ("b/m2", ["m1", "m2"])
    assert report.goulotte_m == 40


def test_a_message_with_no_digits_is_never_judged_empty(monkeypatch):
    """"salam" extracts perfectly and carries no figures; that is `has_data`'s
    case, not this one."""
    _chain(monkeypatch, {"a": lambda model, **kw:
                         ExtractedReport.model_validate_json(EMPTY)})
    _report, who = extraction._run_chain("a:m1", text="salam khouya")
    assert who == "a/m1"


def test_when_every_engine_answers_empty_the_first_answer_still_stands(monkeypatch):
    """Losing a report to a heuristic would be worse than the emptiness it was
    written to catch."""
    _chain(monkeypatch, {
        "a": lambda model, **kw: ExtractedReport.model_validate_json(EMPTY),
        "b": lambda model, **kw: ExtractedReport.model_validate_json(EMPTY),
    })
    _report, who = extraction._run_chain("a:m1,b:m2", text="40 m de goulotte")
    assert who == "a/m1"


def test_every_engine_failing_raises_with_every_reason(monkeypatch):
    def boom(model, **kw):
        raise extraction.ExtractionError(f"{model}: 503")

    _chain(monkeypatch, {"a": boom, "b": boom})
    with pytest.raises(extraction.ExtractionError) as err:
        extraction._run_chain("a:m1,b:m2", text="40 m")
    assert "m1: 503" in str(err.value)
    assert "m2: 503" in str(err.value)


# --- the three public entry points -----------------------------------------

def test_the_public_helpers_read_their_chain_from_settings(monkeypatch):
    calls = []

    def engine(model, **kw):
        calls.append({"model": model, **kw})
        return ExtractedReport.model_validate_json(FULL)

    _chain(monkeypatch, {"a": engine})
    monkeypatch.setattr(extraction.settings, "extraction_text_chain", "a:text")
    monkeypatch.setattr(extraction.settings, "extraction_image_chain", "a:vision")

    assert extraction.extract_report("40 m").goulotte_m == 40
    assert extraction.extract_report_with_model("40 m", profile="P")[1] == "a/text"
    assert extraction.extract_report_from_image(b"JPEG", "image/png",
                                                caption="40 m")[1] == "a/vision"

    assert calls[0]["text"] == "40 m"
    assert calls[1]["profile"] == "P"
    assert calls[2]["image"] == b"JPEG"
    assert calls[2]["mime_type"] == "image/png"
    assert calls[2]["caption"] == "40 m"
