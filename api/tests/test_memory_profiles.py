"""Technician profiles (`app/memory.py`).

Everything here runs offline: the two SDK callers are faked at the module
boundary the same way `test_extraction_profile.py` fakes them, and the cached
clients are cleared on both sides so a fake client cannot outlive its test.
"""
import sys
import types

import pytest

from app import memory


# --- collect ---------------------------------------------------------------

def test_collect_matches_on_the_person_name_case_insensitively():
    rows = [
        {"technicien": "yassine", "date": "2026-08-01", "chantier": "DGH",
         "rapport_complet": "pose de goulottes"},
        {"technicien": "Sara", "date": "2026-08-01", "rapport_complet": "autre"},
    ]
    out = memory.collect(rows, "  Yassine ")
    assert "pose de goulottes" in out
    assert "autre" not in out


def test_collect_is_newest_first_and_windowed():
    rows = [{"technicien": "Y", "date": f"d{i}", "rapport_complet": f"r{i}"}
            for i in range(memory.PROFILE_WINDOW_REPORTS + 5)]
    lines = memory.collect(rows, "Y").splitlines()
    assert len(lines) == memory.PROFILE_WINDOW_REPORTS
    # The last row written is the first line read.
    assert lines[0].endswith(f"r{memory.PROFILE_WINDOW_REPORTS + 4}")


def test_collect_falls_back_to_resume_skips_empty_and_truncates():
    long_text = "x" * (memory.MAX_CHARS_PER_REPORT + 50)
    rows = [
        {"technicien": "Y", "resume": "resume only"},
        {"technicien": "Y", "rapport_complet": "   "},
        {"technicien": "Y", "rapport_complet": long_text},
    ]
    lines = memory.collect(rows, "Y").splitlines()
    assert len(lines) == 2
    assert len(lines[0].split("| ")[-1]) == memory.MAX_CHARS_PER_REPORT
    # Missing date and chantier print as "?" rather than "None".
    assert lines[1] == "- ? | ? | resume only"


def test_collect_returns_empty_for_an_unknown_person():
    assert memory.collect([{"technicien": "Y", "resume": "r"}], "Sara") == ""


# --- _parse_chain ----------------------------------------------------------

def test_parse_chain_reads_provider_model_pairs_and_ignores_blanks():
    assert memory._parse_chain("gemini:a, groq:b ,") == [("gemini", "a"), ("groq", "b")]


@pytest.mark.parametrize("raw", ["gemini", ":model", "gemini:"])
def test_a_malformed_chain_entry_raises(raw):
    with pytest.raises(memory.ProfileError, match="malformed"):
        memory._parse_chain(raw)


def test_an_empty_chain_raises():
    with pytest.raises(memory.ProfileError, match="empty profile chain"):
        memory._parse_chain("  ,  ")


# --- build -----------------------------------------------------------------

def test_build_refuses_to_summarise_nothing():
    with pytest.raises(memory.ProfileError, match="no reports"):
        memory.build("Yassine", "tech", "   ")


def test_build_returns_the_first_model_that_answers(monkeypatch):
    seen = {}

    def ok(model, prompt):
        seen["prompt"] = prompt
        # The callers strip; `build` passes the text through as given.
        return "Intervient surtout sur des chantiers de cablage."

    def never(model, prompt):
        raise AssertionError("the second model must not be called")

    monkeypatch.setattr(memory.settings, "profile_chain", "gemini:m1,groq:m2")
    monkeypatch.setattr(memory, "_CALLERS", {"gemini": ok, "groq": never})

    profile, model = memory.build("Yassine", "tech", "- rapport")
    assert model == "gemini/m1"
    assert profile.startswith("Intervient")
    # Name, role and the reports all reach the model.
    assert "Yassine (tech)" in seen["prompt"]
    assert "- rapport" in seen["prompt"]


def test_build_omits_the_role_when_there_is_none(monkeypatch):
    seen = {}

    def ok(model, prompt):
        seen["prompt"] = prompt
        return "profil"

    monkeypatch.setattr(memory.settings, "profile_chain", "gemini:m1")
    monkeypatch.setattr(memory, "_CALLERS", {"gemini": ok})
    memory.build("Yassine", None, "- rapport")
    assert "## Technicien\nYassine\n" in seen["prompt"]


def test_build_falls_through_an_empty_answer_an_error_and_an_unknown_provider(monkeypatch):
    def boom(*_a):
        raise RuntimeError("429 rate limited")

    monkeypatch.setattr(memory.settings, "profile_chain", "nope:x,gemini:m1,groq:m2")
    monkeypatch.setattr(memory, "_CALLERS", {"gemini": lambda *_a: "", "groq": boom})
    with pytest.raises(memory.ProfileError) as err:
        memory.build("Yassine", "tech", "- rapport")
    msg = str(err.value)
    assert "nope: unknown provider" in msg
    assert "gemini/m1: empty response" in msg
    assert "groq/m2: 429 rate limited" in msg


# --- the two SDK callers ---------------------------------------------------

@pytest.fixture
def _clear_clients():
    """A cached client outlives a monkeypatched `sys.modules` entry, so both
    caches are dropped on the way in and on the way out."""
    memory._gemini_client.cache_clear()
    memory._groq_client.cache_clear()
    yield
    memory._gemini_client.cache_clear()
    memory._groq_client.cache_clear()


def _fake_genai(monkeypatch, client_cls):
    genai = types.SimpleNamespace(Client=client_cls)
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(genai=genai))
    monkeypatch.setitem(sys.modules, "google.genai", genai)


def test_gemini_caller_needs_a_key(monkeypatch, _clear_clients):
    monkeypatch.setattr(memory.settings, "gemini_api_key", "")
    with pytest.raises(memory.ProfileError, match="GEMINI_API_KEY"):
        memory._call_gemini("m", "p")


def test_groq_caller_needs_a_key(monkeypatch, _clear_clients):
    monkeypatch.setattr(memory.settings, "groq_api_key", "")
    with pytest.raises(memory.ProfileError, match="GROQ_API_KEY"):
        memory._call_groq("m", "p")


def test_gemini_caller_returns_the_stripped_text(monkeypatch, _clear_clients):
    calls = {}

    class Client:
        def __init__(self, api_key):
            calls["key"] = api_key
            self.models = types.SimpleNamespace(generate_content=self._gen)

        @staticmethod
        def _gen(model, contents):
            calls["model"] = model
            return types.SimpleNamespace(text="  profil  ")

    _fake_genai(monkeypatch, Client)
    monkeypatch.setattr(memory.settings, "gemini_api_key", "k")

    assert memory._call_gemini("gemini-2.0-flash", "p") == "profil"
    assert calls == {"key": "k", "model": "gemini-2.0-flash"}


def test_gemini_caller_turns_a_null_body_into_an_empty_string(monkeypatch, _clear_clients):
    """`build` reads empty as a failure and tries the next model; a None here
    would raise AttributeError and skip that fallback."""
    class Client:
        def __init__(self, api_key):
            self.models = types.SimpleNamespace(
                generate_content=lambda model, contents: types.SimpleNamespace(text=None))

    _fake_genai(monkeypatch, Client)
    monkeypatch.setattr(memory.settings, "gemini_api_key", "k")
    assert memory._call_gemini("m", "p") == ""


def test_groq_caller_returns_the_stripped_text(monkeypatch, _clear_clients):
    class Groq:
        def __init__(self, api_key):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=self._create))

        @staticmethod
        def _create(model, messages):
            assert messages[0]["role"] == "user"
            choice = types.SimpleNamespace(
                message=types.SimpleNamespace(content="  profil  "))
            return types.SimpleNamespace(choices=[choice])

    monkeypatch.setitem(sys.modules, "groq", types.SimpleNamespace(Groq=Groq))
    monkeypatch.setattr(memory.settings, "groq_api_key", "k")
    assert memory._call_groq("llama", "p") == "profil"


# --- refresh_person --------------------------------------------------------

def test_refresh_person_saves_the_profile(monkeypatch):
    from app import logs

    saved = {}
    monkeypatch.setattr(logs, "save_profile",
                        lambda pid, text: saved.update(id=pid, text=text))
    monkeypatch.setattr(memory, "build", lambda *_a: ("un profil", "gemini/m1"))

    out = memory.refresh_person({"id": 7, "name": "Yassine", "role": "tech"},
                                [{"technicien": "Yassine", "resume": "r"}])
    assert out["updated"] is True
    assert out["model"] == "gemini/m1"
    assert saved == {"id": 7, "text": "un profil"}


def test_refresh_person_keeps_yesterdays_profile_when_the_models_fail(monkeypatch):
    from app import logs

    def never(*_a, **_k):
        raise AssertionError("must not write on a model failure")

    monkeypatch.setattr(logs, "save_profile", never)
    out = memory.refresh_person({"id": 7, "name": "Yassine", "role": "tech"}, [])
    assert out["updated"] is False
    assert "no reports" in out["reason"]


def test_refresh_person_reports_a_failed_write_without_raising(monkeypatch):
    from app import logs

    def boom(*_a, **_k):
        raise logs.LogStoreError("connection refused")

    monkeypatch.setattr(logs, "save_profile", boom)
    monkeypatch.setattr(memory, "build", lambda *_a: ("un profil", "gemini/m1"))
    out = memory.refresh_person({"id": 7, "name": "Yassine", "role": "tech"},
                                [{"technicien": "Yassine", "resume": "r"}])
    assert out["updated"] is False
    assert out["reason"] == "save: connection refused"
