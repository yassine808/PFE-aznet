"""Reactions and multi-identity delivery (`app/reply.py`).

`test_reply_endpoint.py` covers the HTTP endpoint; this file covers the two
functions underneath it that the endpoint does not reach — `set_reaction`,
which is called from the scheduler rather than from a request, and
`reply_to_identities`, whose partial-success contract is what lets a chef reach
a technician on Telegram while the WhatsApp window is closed.

`requests.post` is replaced everywhere: nothing here touches the network.
"""
import pytest
import requests

from app import reply


class FakePost:
    """Records every outbound call; optionally fails or answers non-2xx."""

    def __init__(self, *, ok=True, status_code=200, text="", error=None):
        self.calls = []
        self.ok = ok
        self.status_code = status_code
        self.text = text
        self.error = error

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.error is not None:
            raise self.error
        return self

    @property
    def last(self):
        return self.calls[-1]


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setattr(reply.settings, "telegram_bot_token", "TG")
    monkeypatch.setattr(reply.settings, "whatsapp_access_token", "WA")
    monkeypatch.setattr(reply.settings, "whatsapp_phone_number_id", "1001")


# --- set_reaction ----------------------------------------------------------

def test_telegram_reactions_use_the_whitelisted_symbols():
    """Telegram rejects any emoji outside its own list, so the two tables are
    deliberately different. A shared table would silently stop reacting."""
    assert reply.REACTIONS["telegram"]["working"] == "\U0001f440"
    assert reply.REACTIONS["whatsapp"]["working"] == "⏳"
    assert set(reply.REACTIONS["telegram"]) == set(reply.REACTIONS["whatsapp"])


def test_set_reaction_posts_a_telegram_reaction(monkeypatch, keys):
    post = FakePost()
    monkeypatch.setattr(reply.requests, "post", post)
    reply.set_reaction("telegram", "555", "42", "done")
    assert post.last["url"].endswith("/setMessageReaction")
    body = post.last["json"]
    # message_id is an int on Telegram; a string is refused.
    assert body["message_id"] == 42
    assert body["reaction"] == [{"type": "emoji", "emoji": "\U0001f44d"}]


def test_set_reaction_posts_a_whatsapp_reaction(monkeypatch, keys):
    post = FakePost()
    monkeypatch.setattr(reply.requests, "post", post)
    reply.set_reaction("whatsapp", "+212 612-345678", "wamid.X", "queued")
    body = post.last["json"]
    assert body["type"] == "reaction"
    assert body["reaction"] == {"message_id": "wamid.X", "emoji": "\U0001f504"}
    # The number is normalized on the way out, not stored normalized.
    assert body["to"] == reply.logs.normalize_external_id("whatsapp", "+212 612-345678")


@pytest.mark.parametrize("args", [
    ("telegram", "555", "42", "invented-state"),  # unknown state
    ("signal", "555", "42", "done"),              # unknown channel
    ("telegram", "", "42", "done"),               # no chat
    ("telegram", "555", "", "done"),              # no message
])
def test_set_reaction_sends_nothing_when_it_cannot_address_the_message(
    monkeypatch, keys, args
):
    post = FakePost()
    monkeypatch.setattr(reply.requests, "post", post)
    reply.set_reaction(*args)
    assert post.calls == []


@pytest.mark.parametrize("channel", ["telegram", "whatsapp"])
def test_set_reaction_is_silent_when_the_channel_has_no_credentials(
    monkeypatch, channel
):
    monkeypatch.setattr(reply.settings, "telegram_bot_token", "")
    monkeypatch.setattr(reply.settings, "whatsapp_access_token", "")
    monkeypatch.setattr(reply.settings, "whatsapp_phone_number_id", "")
    post = FakePost()
    monkeypatch.setattr(reply.requests, "post", post)
    reply.set_reaction(channel, "555", "42", "done")
    assert post.calls == []


def test_a_failed_reaction_is_logged_and_never_raised(monkeypatch, keys):
    """The retry job reacts after it has already filed the report. A raise here
    would re-park a row that Google accepted."""
    written = []
    monkeypatch.setattr(reply.requests, "post",
                        FakePost(error=requests.RequestException("timeout")))
    monkeypatch.setattr(reply.logs, "write_safe",
                        lambda *a, **k: written.append((a, k)))
    reply.set_reaction("whatsapp", "212612345678", "wamid.X", "done")
    assert "reaction done failed on whatsapp" in written[0][1]["message"]


def test_a_wamid_sent_to_telegram_is_caught_rather_than_crashing(monkeypatch, keys):
    """`int(message_id)` raises ValueError on a WhatsApp id. A channel mix-up
    must not take down the job that called this."""
    written = []
    monkeypatch.setattr(reply.requests, "post", FakePost())
    monkeypatch.setattr(reply.logs, "write_safe",
                        lambda *a, **k: written.append(k))
    reply.set_reaction("telegram", "555", "wamid.X", "done")
    assert "failed on telegram" in written[0]["message"]


# --- reply_to_identities ---------------------------------------------------

def test_a_message_goes_out_on_every_active_identity(monkeypatch, keys):
    post = FakePost()
    monkeypatch.setattr(reply.requests, "post", post)
    out = reply.reply_to_identities(
        [{"channel": "Telegram", "external_id": "555"},
         {"channel": "whatsapp", "external_id": "212612345678"}],
        "Bonjour",
    )
    assert out == {"delivered": [{"channel": "telegram"}, {"channel": "whatsapp"}]}
    assert len(post.calls) == 2


def test_incomplete_identities_are_skipped_not_reported_as_failures(monkeypatch, keys):
    post = FakePost()
    monkeypatch.setattr(reply.requests, "post", post)
    out = reply.reply_to_identities(
        [{"channel": "", "external_id": "555"},
         {"channel": "telegram", "external_id": "  "},
         {"channel": "telegram", "external_id": "555"}],
        "Bonjour",
    )
    assert out == {"delivered": [{"channel": "telegram"}]}
    assert len(post.calls) == 1


def test_one_channel_refusing_does_not_cost_the_other_its_delivery(monkeypatch, keys):
    def post(url, **kwargs):
        if "graph.facebook.com" in url:
            raise requests.RequestException("24h window closed")
        return FakePost()(url, **kwargs)

    monkeypatch.setattr(reply.requests, "post", post)
    out = reply.reply_to_identities(
        [{"channel": "telegram", "external_id": "555"},
         {"channel": "whatsapp", "external_id": "212612345678"}],
        "Bonjour",
    )
    assert out == {"delivered": [{"channel": "telegram"}]}


def test_an_unknown_channel_is_named_in_the_failure(monkeypatch, keys):
    monkeypatch.setattr(reply.requests, "post", FakePost())
    with pytest.raises(reply.ReplyError, match="signal: canal inconnu"):
        reply.reply_to_identities([{"channel": "signal", "external_id": "x"}], "hi")


def test_no_identity_at_all_is_its_own_message(monkeypatch, keys):
    monkeypatch.setattr(reply.requests, "post", FakePost())
    with pytest.raises(reply.ReplyError, match="aucune identité active"):
        reply.reply_to_identities([], "Bonjour")


def test_every_channel_failing_raises_with_all_the_reasons(monkeypatch, keys):
    monkeypatch.setattr(reply.requests, "post",
                        FakePost(ok=False, status_code=403, text="forbidden"))
    with pytest.raises(reply.ReplyError) as err:
        reply.reply_to_identities(
            [{"channel": "telegram", "external_id": "555"},
             {"channel": "whatsapp", "external_id": "212612345678"}],
            "Bonjour",
        )
    assert "Telegram a refusé (403)" in str(err.value)
    assert "WhatsApp a refusé (403)" in str(err.value)
