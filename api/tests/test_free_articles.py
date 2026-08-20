"""Free articles: the figures must move with the name, and never twice.

`report_rows.data` is what every total is computed from, so a registry row and
a Sheet column are only two thirds of an article. These tests pin the third:
deleting drops the quantities, renaming carries them, and a rename that lands
on an article a row already carries **adds** rather than replacing or keeping
both — the two ways one day's work gets counted wrong.

They also pin the second half of the quota work: a payload that says in words
that a free tier is exhausted.
"""
from contextlib import contextmanager

from app import logs, usage


class _FakeRows:
    """Just enough cursor to hold one `report_rows` table in memory."""

    def __init__(self, rows):
        self.rows = rows
        self._out = []

    def execute(self, sql, args=None):
        if sql.startswith("SELECT id, data -> 'articles_libres'"):
            self._out = [{"id": i, "libres": r} for i, r in enumerate(self.rows)]
        elif sql.startswith("UPDATE report_rows"):
            import json
            payload, rid = args
            self.rows[rid] = json.loads(payload)

    def fetchall(self):
        return self._out


@contextmanager
def _fake_cursor(cur):
    yield cur


def _rekey(monkeypatch, rows, slug, designation):
    monkeypatch.setattr(logs.settings, "database_url", "postgres://test")
    cur = _FakeRows(rows)
    monkeypatch.setattr(logs, "_cursor", lambda: _fake_cursor(cur))
    return logs._rekey_free_article(slug, designation)


def test_delete_removes_the_quantity_from_every_row(monkeypatch):
    rows = [{"prise étanche": 4}, {"prise étanche": 9, "goulotte": 2}]
    assert _rekey(monkeypatch, rows, logs._slug_article("prises étanches"), None) == 2
    assert rows == [{}, {"goulotte": 2}]


def test_rename_carries_the_quantity_under_the_new_name(monkeypatch):
    rows = [{"prise étanche": 4}]
    _rekey(monkeypatch, rows, logs._slug_article("prise étanche"), "prise IP44")
    assert rows == [{"prise IP44": 4.0}]


def test_merge_adds_instead_of_overwriting(monkeypatch):
    # One message named the same socket twice; folding one into the other must
    # not lose 4 (overwrite) nor keep 4 counted apart (no re-key at all).
    rows = [{"prise 2P+T": 4, "prise industrielle 2P+T": 6}]
    _rekey(monkeypatch, rows, logs._slug_article("prise 2P+T"), "prise industrielle 2P+T")
    assert rows == [{"prise industrielle 2P+T": 10.0}]


def test_unconfigured_is_a_no_op(monkeypatch):
    monkeypatch.setattr(logs.settings, "database_url", "")
    assert logs._rekey_free_article("prise", None) == 0


def test_exhausted_quota_says_so_in_words():
    entry = {"provider": "groq", "calls_24h": 30, "limit_source": "live",
             "limit_requests": 1000, "remaining_requests": 0,
             "limit_tokens": None, "remaining_tokens": None,
             "reset_requests": "2m59s"}
    verdict = usage._assess(entry)
    assert verdict["state"] == "epuise"
    assert "épuisé" in verdict["message"]
    assert "2m59s" in verdict["message"]


def test_unknown_ceiling_is_not_a_full_tank():
    entry = {"provider": "gemini", "calls_24h": 12, "limit_source": "documented",
             "limit_requests": None, "remaining_requests": None,
             "limit_tokens": None, "remaining_tokens": None}
    assert usage._assess(entry)["state"] == "inconnu"


def test_low_is_a_share_of_the_ceiling_not_a_flat_count():
    entry = {"provider": "groq", "calls_24h": 1, "limit_source": "live",
             "limit_requests": 1000, "remaining_requests": 50,
             "limit_tokens": None, "remaining_tokens": None, "reset_requests": None}
    assert usage._assess(entry)["state"] == "bas"
    entry["remaining_requests"] = 500
    assert usage._assess(entry)["state"] == "ok"
