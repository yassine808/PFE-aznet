"""Shared fixtures.

`chantier_table` exists because routing stopped being a string pass-through on
2026-08-15: `journal.resolve_site` now checks every name against the `chantiers`
table before it becomes a Google Sheet tab. Tests run with no database, so a
test that files a report needs this stand-in — without it Postgres is
unreachable and every row lands (correctly) in `Non affecté`.
"""
import pytest


@pytest.fixture
def chantier_table(monkeypatch):
    """In-memory `chantiers` table plus the org chart that points at it.

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
            self.org = {}       # technicien -> chantier nom
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

        def person_by_name(self, name):
            return {"id": name, "name": name} if name in self.org else None

        def resolve_chantier(self, person_id):
            return self.find(self.org[person_id]) if self.org.get(person_id) else None

    table = Table()
    monkeypatch.setattr(logs, "find_chantier_by_name", table.find)
    monkeypatch.setattr(logs, "create_chantier", table.create)
    monkeypatch.setattr(logs, "person_by_name", table.person_by_name)
    monkeypatch.setattr(logs, "resolve_chantier", table.resolve_chantier)
    return table
