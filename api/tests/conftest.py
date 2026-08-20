"""Shared fixtures.

`chantier_table` exists because routing stopped being a string pass-through on
2026-08-15: `journal.resolve_site` now checks every name against the `chantiers`
table before it becomes a Google Sheet tab. Tests run with no database, so a
test that files a report needs this stand-in — without it Postgres is
unreachable and every row lands (correctly) in `Non affecté`.
"""
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
