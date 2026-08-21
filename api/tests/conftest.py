"""Shared fixtures.

`chantier_table` exists because routing stopped being a string pass-through on
2026-08-15: `journal.resolve_site` now checks every name against the `chantiers`
table before it becomes a Google Sheet tab. Tests run with no database, so a
test that files a report needs this stand-in — without it Postgres is
unreachable and every row lands (correctly) in `Non affecté`.
"""
import os

import pytest


@pytest.fixture(autouse=True)
def _fresh_sheet_caches():
    """Empty every Sheets cache around each test.

    `sheets` keeps three process-wide caches — the Rapports rows, the header
    row and, since the Chantiers page became slow, one entry per journal tab.
    They exist to stop a dashboard poll paying for a Google round trip the last
    poll already paid for, and in production they are dropped by
    `invalidate_reports()` on every write.

    A test suite has no writes, so without this a cache entry outlives the test
    that created it: two tests that describe the SAME tab with different rows —
    which is most of `test_stock_alerts.py` — see whichever ran first. It fails
    as a wrong assertion in the second test, pointing at code that is correct,
    which is the most expensive kind of test failure to read.

    Autouse and both sides: `yield` guarantees a test cannot leak into the next
    one even if it fails part-way through.
    """
    from app import sheets

    sheets.invalidate_reports()
    yield
    sheets.invalidate_reports()


@pytest.fixture
def chantier_table(monkeypatch):
    """In-memory `chantiers` table.

    The matching itself is NOT faked: `find` runs the real
    `logs.normalize_site_name`, so a test about "la DGH" tests the shipped
    normalization rather than a copy of it.
    """
    from app import logs

    class Table:
        def __init__(self):
            self.rows = [
                {"id": 1, "nom": "DGH", "sheet_tab": "DGH", "verifie": True},
                {"id": 2, "nom": "ACAPS", "sheet_tab": "ACAPS", "verifie": True},
            ]
            self.created = []

        def find(self, nom):
            key = logs.normalize_site_name(nom)
            if not key:
                return None
            return next(
                (r for r in self.rows
                 if logs.normalize_site_name(r["nom"]) == key), None
            )

        def create(self, nom, sheet_tab=None, client=None, verifie=True):
            row = {
                "id": len(self.rows) + 1,
                "nom": nom.strip(),
                "sheet_tab": (sheet_tab or nom).strip(),
                "client": client,
                "verifie": verifie,
            }
            self.rows.append(row)
            self.created.append(row)
            return row

    table = Table()
    monkeypatch.setattr(logs, "find_chantier_by_name", table.find)
    monkeypatch.setattr(logs, "create_chantier", table.create)
    # No person_by_name / resolve_chantier fakes: routing no longer asks who the
    # technician reports to. Leaving them would let a test pass against a
    # resolver that had quietly regained an org-chart branch.
    return table


# --- Integration: the one fixture that talks to a real database ------------
#
# `logs.py` is 915 coverable lines that the offline suite cannot reach: with no
# DATABASE_URL every function raises before it touches SQL. Faking psycopg2
# would execute those lines without a database ever parsing the statements —
# coverage that proves nothing. So the DB tests use a real Postgres, and the
# rule that `pytest` needs no database survives by keying on a SEPARATE
# variable: TEST_DATABASE_URL. Unset (the default, and every developer box that
# has not opted in) skips them; the API's own `DATABASE_URL` is never read here,
# so a running production database cannot be truncated by a stray test run.
#
#   docker compose up -d postgres
#   TEST_DATABASE_URL=postgresql://pfe:pfe@localhost:5432/pfe_test pytest -m integration


def _test_database_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def db(monkeypatch):
    """A schema-fresh database, torn down by rebuild rather than by DELETE.

    DROP SCHEMA + init_schema() instead of truncating a list of tables: the list
    would be a second copy of the schema, and the day someone adds a table
    without adding it here, tests start leaking rows into each other and fail in
    whichever test happens to run second — the most expensive failure to read.

    The pool is reset on both sides. It is a module-level global built once per
    process, so a pool opened against the previous test's connection settings
    would outlive it and quietly serve the next one.
    """
    url = _test_database_url()
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")

    from app import logs

    monkeypatch.setattr(logs.settings, "database_url", url, raising=False)
    _reset_pool(logs)
    with logs._cursor() as cur:
        cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    logs.init_schema()
    yield logs
    _reset_pool(logs)


def _reset_pool(logs) -> None:
    pool, logs._pool = logs._pool, None
    if pool is not None:
        try:
            pool.closeall()
        except Exception:  # pragma: no cover - already closed
            pass
