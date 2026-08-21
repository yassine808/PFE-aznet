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


def test_save_carries_the_manager_and_the_document(sql):
    """A chef's history is their own, and the version stores the file it made.

    Both are one statement's parameters, so the check is on the parameters: a
    version filed under the wrong manager appends into somebody else's history,
    and a version with no document is one the Reports page cannot show as it
    was sent.
    """
    logs.save_report_version(
        "daily", "2026-08-04", "Rapport", "Texte", manager_id=7, docx=b"PK\x03\x04"
    )

    statement, params = sql[0]
    assert "manager_id" in statement and "docx" in statement
    # The numbering sub-select has to be scoped the same way, or two chefs on
    # one day would fight over the same version number.
    assert "WHERE kind = %s AND period = %s AND manager_id = %s" in statement
    assert 7 in params


def test_listing_is_scoped_to_one_manager_and_never_selects_the_file(sql):
    """Ten stored documents must not travel to draw a list of ten dates."""
    logs.list_report_versions("daily", "2026-08-04", with_body=True, manager_id=7)

    statement, params = sql[0]
    assert "(docx IS NOT NULL) AS has_docx" in statement
    assert ", docx" not in statement, "the bytes themselves must stay in the row"
    assert "manager_id = %s" in statement
    assert params[-1] == 7


def test_a_version_with_no_document_is_a_404(client, monkeypatch):
    """Versions stored before the column existed have none; 404 says so."""
    monkeypatch.setattr(logs, "report_version_docx", lambda _id: None)
    assert client.get("/report-versions/12/docx").status_code == 404


def test_the_stored_document_is_served_as_is(client, monkeypatch):
    """Served from the row, never re-rendered: a re-render is a different file."""
    monkeypatch.setattr(logs, "report_version_docx", lambda _id: ("Rapport", b"PK\x03\x04zip"))
    res = client.get("/report-versions/12/docx")
    assert res.status_code == 200
    assert res.content == b"PK\x03\x04zip"
    # Inline by default so the dashboard's preview can render it; the download
    # button asks for the other disposition explicitly.
    assert res.headers["content-disposition"].startswith("inline;")
    assert client.get("/report-versions/12/docx?download=true").headers[
        "content-disposition"
    ].startswith("attachment;")


def test_the_period_document_falls_back_to_the_stored_text(client, monkeypatch):
    """A period whose report predates the `docx` column still has a document.

    Otherwise the Daily page of every past day shows nothing and reads as
    broken, while the report itself has been in `manager_reports` all along.
    """
    monkeypatch.setattr(logs, "list_report_versions", lambda *a, **k: [])
    # The renderer derives its tables from the period's rows; none here.
    monkeypatch.setattr(logs, "list_report_rows", lambda *a, **k: [])
    monkeypatch.setattr(
        logs,
        "list_manager_reports",
        lambda: [
            {"period": "2026-08-04", "period_type": "weekly", "objet": "Semaine", "corps": "x"},
            {"period": "2026-08-04", "period_type": "daily", "objet": "Jour",
             "corps": "Texte", "generated_by": "Yassine"},
        ],
    )
    res = client.get("/reports/document?kind=daily&period=2026-08-04")
    assert res.status_code == 200
    # A .docx is a zip; the weekly row above must not be the one picked.
    assert res.content[:2] == b"PK"
    assert "jour" in res.headers["content-disposition"].lower()


def test_the_period_document_prefers_the_stored_bytes(client, monkeypatch):
    """When a version has a file, that file is served — never a fresh render."""
    monkeypatch.setattr(
        logs, "list_report_versions", lambda *a, **k: [{"id": 5, "has_docx": True}]
    )
    monkeypatch.setattr(logs, "report_version_docx", lambda _id: ("Jour", b"PKstored"))
    monkeypatch.setattr(logs, "list_manager_reports", lambda: [])
    res = client.get("/reports/document?kind=daily&period=2026-08-04")
    assert res.content == b"PKstored"


def test_a_period_with_no_report_at_all_is_a_404(client, monkeypatch):
    monkeypatch.setattr(logs, "list_report_versions", lambda *a, **k: [])
    monkeypatch.setattr(logs, "list_manager_reports", lambda: [])
    assert client.get("/reports/document?kind=daily&period=2026-08-04").status_code == 404
