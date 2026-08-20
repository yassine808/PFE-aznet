"""The report_rows INSERT names as many values as it names columns.

On 2026-08-19 `journal_tab` and `journal_row` were added to the column list and
to the ON CONFLICT clause, and not to VALUES. Postgres answered "INSERT has more
target columns than expressions" on every single call, `record_report_row`
swallowed it by design — a mirror never costs a report — and for a day every
filed report reached the Sheet, the technician and the Rapports tab while the
store the totals are computed from received nothing at all.

Nothing caught it: the suite runs with no database, and a fake cursor records
the statement without parsing it, so the mismatch is invisible to an assertion
about behaviour. It is visible in the SQL, which is what these tests read.
"""
import re
from contextlib import contextmanager

from app import logs


class _Cur:
    def __init__(self):
        self.statements = []

    def execute(self, sql, args=None):
        self.statements.append((sql, args))

    def fetchone(self):
        return None

    def fetchall(self):
        return []


def _capture(monkeypatch):
    cur = _Cur()

    @contextmanager
    def fake():
        yield cur

    monkeypatch.setattr(logs, "_cursor", fake)
    monkeypatch.setattr(logs, "write_safe", lambda *a, **k: None)
    return cur


ROW = {
    "correlation_id": "c-1", "date": "2026-08-17", "heure": "03:09",
    "technicien": "Yassine", "chantier": "DGH", "canal": "whatsapp",
    "role": None, "stt_engine": None, "confidence": None,
    "flag_review": False, "motif_flag": None, "resume": "r",
    "rapport_complet": "texte", "rapports_row": 8,
    "journal_tab": "DGH", "journal_row": 8,
}


def _insert(monkeypatch):
    cur = _capture(monkeypatch)
    logs.record_report_row(dict(ROW), {"goulotte_m": 12})
    assert cur.statements, "record_report_row swallowed the call entirely"
    return cur.statements[0]


def test_columns_and_values_are_the_same_count(monkeypatch):
    """The exact fault: 17 columns, 15 placeholders, rejected by Postgres."""
    sql, _ = _insert(monkeypatch)
    columns = re.search(r"INSERT INTO report_rows\s*\((.*?)\)\s*VALUES", sql, re.S).group(1)
    values = re.search(r"VALUES\s*\((.*?)\)\s*ON CONFLICT", sql, re.S).group(1)
    names = [c.strip() for c in columns.split(",")]
    holders = re.findall(r"%\((\w+)\)s", values)
    assert len(names) == len(holders), (
        f"{len(names)} columns but {len(holders)} values; "
        f"missing: {sorted(set(names) - set(holders))}"
    )
    # Same order, not merely the same count — a swap writes each value into
    # the neighbouring column and every row is quietly wrong instead of absent.
    assert names == holders


def test_every_placeholder_has_a_value(monkeypatch):
    """A named placeholder with no key raises the same way, one layer earlier."""
    sql, args = _insert(monkeypatch)
    for name in set(re.findall(r"%\((\w+)\)s", sql)):
        assert name in args, f"placeholder %({name})s has no key in the args dict"


def test_data_is_serialised_json(monkeypatch):
    """`data` is a jsonb column: the dict has to arrive as text, not as a dict."""
    _, args = _insert(monkeypatch)
    assert isinstance(args["data"], str)
    assert "goulotte_m" in args["data"]
