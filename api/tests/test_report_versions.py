"""Report version history: append-only, and numbered by the database.

The one behaviour worth a test is that a save never overwrites and never has to
read-then-write to pick its number — two managers pressing save at the same
moment must not silently collapse into one version.
"""
import pytest
from fastapi.testclient import TestClient

from app import auth, logs
from app.main import app


class _Cur:
    """Records SQL and answers the INSERT with a plausible row."""

    def __init__(self, sink):
        self.sink = sink

    def execute(self, sql, params=None):
        self.sink.append((" ".join(sql.split()), params))

    def fetchone(self):
        return {
            "id": 1,
            "kind": "daily",
            "period": "2026-08-04",
            "version": 3,
            "objet": "Rapport",
            "corps": "Texte",
            "image": None,
            "author": "Yassine",
            "note": None,
            "created_at": None,
        }

    def fetchall(self):
        return [self.fetchone()]


@pytest.fixture
def sql(monkeypatch):
    """Capture the statements `logs` runs, without a database."""
    from contextlib import contextmanager

    sink = []

    @contextmanager
    def fake_cursor():
        yield _Cur(sink)

    monkeypatch.setattr(logs, "_cursor", fake_cursor)
    return sink


def test_version_number_is_computed_in_the_insert(sql):
    """No SELECT-then-INSERT: the number comes from a sub-select in one statement."""
    logs.save_report_version("daily", "2026-08-04", "Rapport", "Texte", author="Yassine")

    assert len(sql) == 1, "a save must be a single statement, or two writers can race"
    statement, params = sql[0]
    assert statement.startswith("INSERT INTO report_versions")
    assert "COALESCE(MAX(version), 0) + 1" in statement
    assert "UPDATE" not in statement
    assert "DELETE" not in statement
    assert "Yassine" in params


def test_index_listing_leaves_out_the_bodies(sql):
    """The list beside the editor must not ship every stored body and image."""
    logs.list_report_versions("daily", "2026-08-04", with_body=False)

    statement, _ = sql[0]
    assert "corps" not in statement
    assert "image" not in statement
    assert "version DESC" in statement


@pytest.fixture
def client():
    """A caller the API accepts, without touching anyone else's overrides.

    Overriding the dependency (rather than patching `auth.require_human`) is
    what FastAPI actually consults — the route captured the original callable
    at import time, so patching the attribute afterwards changes nothing.

    The teardown restores the previous entry instead of calling `.clear()`:
    `dependency_overrides` is one dict shared by every test module, and
    `test_reports_endpoints.py` installs its own override at import time. A
    blanket clear here deleted it, so those tests started 401-ing — but only
    when this file happened to run first, which is the worst kind of failure to
    read.
    """
    previous = app.dependency_overrides.get(auth.require_human)
    app.dependency_overrides[auth.require_human] = lambda: {"id": 1, "name": "Yassine"}
    yield TestClient(app)
    if previous is None:
        app.dependency_overrides.pop(auth.require_human, None)
    else:
        app.dependency_overrides[auth.require_human] = previous


def test_unknown_kind_is_rejected(client, monkeypatch):
    monkeypatch.setattr(auth, "record", lambda *a, **k: None)
    res = client.post(
        "/report-versions",
        json={"kind": "monthly", "period": "2026-08", "objet": "x", "corps": "y"},
    )
    assert res.status_code == 422


def test_empty_body_is_rejected(client, monkeypatch):
    """An empty save would bury the last real version under a blank one."""
    monkeypatch.setattr(auth, "record", lambda *a, **k: None)
    res = client.post(
        "/report-versions",
        json={"kind": "daily", "period": "2026-08-04", "objet": "x", "corps": "   "},
    )
    assert res.status_code == 422
