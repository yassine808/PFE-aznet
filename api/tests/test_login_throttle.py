"""Login throttle identity — which address the limit is keyed on.

Behind nginx every visitor arrives as the proxy's container IP, so keying on
`request.client.host` turns a per-visitor limit into a global one: eight bad
logins by anyone would lock out everyone. And keying on the *first*
X-Forwarded-For hop is worse than useless, because that entry is supplied by
the caller and a script could rotate it to bypass the limit outright.
"""
from types import SimpleNamespace

import app.main as main


def _req(xff=None, peer="10.0.0.9"):
    headers = {"x-forwarded-for": xff} if xff else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=peer))


def test_nginx_alone_takes_the_last_hop(monkeypatch):
    # nginx sets "$proxy_add_x_forwarded_for" = "<caller's value>, <real peer>",
    # so a caller claiming 1.2.3.4 must not shift its own key.
    monkeypatch.setattr(main.settings, "trusted_proxy_hops", 1)
    assert main._client_ip(_req("1.2.3.4, 203.0.113.7")) == "203.0.113.7"


def test_funnel_behind_nginx_takes_the_entry_tailscale_wrote(monkeypatch):
    # tailscaled replaces any caller-supplied header, then nginx appends the
    # docker gateway — which is the same for everyone, so it must be discarded.
    monkeypatch.setattr(main.settings, "trusted_proxy_hops", 2)
    assert main._client_ip(_req("100.112.203.0, 172.18.0.1")) == "100.112.203.0"


def test_more_hops_configured_than_present_never_indexes_out_of_range(monkeypatch):
    monkeypatch.setattr(main.settings, "trusted_proxy_hops", 5)
    assert main._client_ip(_req("203.0.113.7")) == "203.0.113.7"


def test_falls_back_to_the_socket_peer():
    assert main._client_ip(_req()) == "10.0.0.9"


def test_missing_client_is_named_not_crashing():
    assert main._client_ip(SimpleNamespace(headers={}, client=None)) == "unknown"


def test_throttle_is_per_address():
    main._login_failures.clear()
    for _ in range(main.LOGIN_MAX_FAILURES):
        main._login_failures.setdefault("a", []).append(__import__("time").time())
    assert main._login_allowed("a") is False
    # A second address must still get in — that is the whole point of the key.
    assert main._login_allowed("b") is True
    main._login_failures.clear()
