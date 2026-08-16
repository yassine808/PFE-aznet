"""The technician profile must reach *every* text engine, not just Gemini.

Regression: `_call_groq` accepted `profile` and ignored it, and groq is the
primary entry of `extraction_text_chain` — so on the normal path the nightly
profile was built, stored, read and silently dropped. Nothing errored, which is
why it went unnoticed.
"""
import sys
import types

import pytest

from app import extraction


class _Recorder:
    """Stands in for the Groq SDK and keeps the messages it was handed."""

    def __init__(self):
        self.messages = None

    def _create(self, model, response_format, messages):
        """The *raw* response wrapper, because that is what the code now calls.

        `extraction` goes through `.with_raw_response` so `usage.py` can read
        Groq's rate-limit headers — they are the only live quota reading any
        vendor here gives us, and the parsed body drops them. A fake that only
        offers `.create` would pass while the real client raises.
        """
        self.messages = messages
        completion = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(
                content='{"resume": "Pose de goulottes.", "chantier": "Sidi Maarouf"}'
            ))],
            usage=types.SimpleNamespace(prompt_tokens=11, completion_tokens=7),
        )
        return types.SimpleNamespace(
            headers={"x-ratelimit-limit-requests": "1000",
                     "x-ratelimit-remaining-requests": "999"},
            parse=lambda: completion,
        )


@pytest.fixture
def groq_recorder(monkeypatch):
    """Install a fake `groq` module so no key and no network are needed."""
    rec = _Recorder()

    class FakeGroq:
        def __init__(self, api_key=None):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    with_raw_response=types.SimpleNamespace(create=rec._create)
                )
            )

    monkeypatch.setitem(sys.modules, "groq", types.SimpleNamespace(Groq=FakeGroq))
    monkeypatch.setattr(extraction.settings, "groq_api_key", "test-key")
    # `extraction._groq_client` is @lru_cache'd — one SDK client per process, so
    # that a report does not pay a fresh TLS handshake. That cache outlives a
    # monkeypatched `sys.modules["groq"]`: without clearing it, the second test
    # in this file would keep talking to the FIRST test's recorder and see
    # `rec.messages is None`. Cleared on the way in AND on the way out, so this
    # fixture neither inherits a stale client nor leaks its fake to other tests.
    extraction._groq_client.cache_clear()
    yield rec
    extraction._groq_client.cache_clear()


def _system_message(rec) -> str:
    return next(m["content"] for m in rec.messages if m["role"] == "system")


def test_groq_receives_the_profile(groq_recorder):
    extraction._call_groq(
        "openai/gpt-oss-120b",
        text="j'ai posé les goulottes",
        profile="Rachid intervient surtout sur des chantiers de bureaux.",
    )
    system = _system_message(groq_recorder)
    assert "Rachid intervient surtout" in system
    # …and framed as context, never as a source of values — the same guard
    # _profile_block puts around it for Gemini.
    assert "JAMAIS une source de valeurs" in system


def test_groq_without_a_profile_is_unchanged(groq_recorder):
    """No profile must not leave a dangling header in the prompt."""
    extraction._call_groq("openai/gpt-oss-120b", text="rien de spécial")
    system = _system_message(groq_recorder)
    assert "Contexte sur l'auteur" not in system


def test_groq_still_refuses_images():
    """The image guard sits before the key check, so it needs no fixture."""
    with pytest.raises(extraction.ExtractionError, match="no vision model"):
        extraction._call_groq("openai/gpt-oss-120b", image=b"\xff\xd8fake")
