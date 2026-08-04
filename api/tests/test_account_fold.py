"""The gate after `users` folded into `persons`.

Both tables used to answer "is this row an account?" by existing. Now one table
holds accounts *and* technicians, so the answer is `password_hash IS NOT NULL`
and every path that used to rely on table membership has to say so explicitly.
These are the two places where getting it wrong is not a cosmetic bug:

- a technician's row must never authenticate, however the caller reaches it;
- their row must never carry the hash out to the browser.
"""
from contextlib import contextmanager

import pytest

from app import auth, logs


@contextmanager
def _fake_cursor(row):
    """A cursor that answers one SELECT with `row` and swallows writes."""

    class Cur:
        def execute(self, *_a, **_k):
            pass

        def fetchone(self):
            return row

        def fetchall(self):
            return [row] if row else []

    yield Cur()


def _with_row(monkeypatch, row):
    monkeypatch.setattr(logs, "_cursor", lambda: _fake_cursor(row))


TECH = {"id": 3, "name": "Youssef", "role": "tech", "active": True, "password_hash": None}
CHEF = {"id": 4, "name": "Karim", "role": "chef", "active": True,
        "password_hash": auth.hash_password("correct-horse")}


def test_technician_row_never_authenticates(monkeypatch):
    # The row exists and is active — only the missing hash stands between a
    # technician's e-mail address and a dashboard session.
    _with_row(monkeypatch, TECH)
    assert auth.login("youssef@aznet.ma", "anything") is None


def test_missing_hash_does_not_raise(monkeypatch):
    # Regression: verify_password(pw, None) reaches None.encode() and raises
    # AttributeError, which its `except (ValueError, TypeError)` misses. That
    # turns a wrong login into a 500 whose very existence confirms the account.
    _with_row(monkeypatch, TECH)
    # An AttributeError here is the bug: it escapes and fails this test loudly.
    assert auth.login("youssef@aznet.ma", "anything") is None


def test_wrong_password_still_fails_for_a_real_account(monkeypatch):
    _with_row(monkeypatch, CHEF)
    assert auth.login("karim@aznet.ma", "wrong") is None


def test_public_never_carries_the_hash():
    assert "password_hash" not in auth._public(dict(CHEF))


def test_list_persons_query_does_not_select_star():
    # `SELECT *` on persons now includes password_hash. Asserting on the source
    # rather than on a result because the leak is in the statement itself, and a
    # mocked cursor would happily return whatever it was handed.
    import inspect

    sql = inspect.getsource(logs.list_persons)
    assert "SELECT * FROM persons" not in sql
    assert "has_login" in sql


def test_person_cannot_manage_themselves(monkeypatch):
    _with_row(monkeypatch, None)
    with pytest.raises(logs.LogStoreError):
        logs.set_manager(7, 7)
