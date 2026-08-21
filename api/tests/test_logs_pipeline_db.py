"""Pipeline log storage, against a real Postgres.

Every test here is `integration`: it needs TEST_DATABASE_URL and is skipped
without it (see the `db` fixture in conftest). The point of using a real
database rather than a psycopg2 fake is that these functions are mostly SQL —
a fake would run the Python around the statements and prove nothing about the
statements themselves, which is where the behaviour actually lives.
"""
import pytest

pytestmark = pytest.mark.integration


def test_write_returns_an_id_and_read_finds_the_row(db):
    row_id = db.write("received", channel="telegram", technicien="Yassine",
                      correlation_id="c-1", message="voice note in")
    assert row_id > 0

    rows = db.read(correlation_id="c-1")
    assert len(rows) == 1
    assert rows[0]["stage"] == "received"
    assert rows[0]["technicien"] == "Yassine"
    # ts is serialized for the browser, not handed over as a datetime.
    assert isinstance(rows[0]["ts"], str)


def test_an_unknown_level_is_stored_as_info(db):
    """The column is free text; `write` is what keeps the dashboard's filter
    meaningful, so an invented level must not reach the row."""
    db.write("stage", level="catastrophe", correlation_id="c-2")
    assert db.read(correlation_id="c-2")[0]["level"] == "info"


def test_read_filters_compose(db):
    db.write("received", level="info", channel="telegram", correlation_id="a")
    db.write("journal", level="error", channel="whatsapp",
             technicien="Sara", message="Sheets refused", correlation_id="b")

    assert [r["correlation_id"] for r in db.read(level="error")] == ["b"]
    assert [r["correlation_id"] for r in db.read(channel="telegram")] == ["a"]
    assert [r["correlation_id"] for r in db.read(stage="journal")] == ["b"]
    # search covers message OR technicien, case-insensitively
    assert [r["correlation_id"] for r in db.read(search="refused")] == ["b"]
    assert [r["correlation_id"] for r in db.read(search="sara")] == ["b"]
    assert db.read(level="error", channel="telegram") == []


def test_read_is_newest_first_and_capped(db):
    for i in range(5):
        db.write("received", correlation_id=f"n-{i}")
    rows = db.read(limit=2)
    assert [r["correlation_id"] for r in rows] == ["n-4", "n-3"]
    # A caller asking for a million rows gets 1000, not a dead dashboard.
    assert len(db.read(limit=10_000)) == 5


def test_write_safe_never_raises_when_the_database_is_gone(db, monkeypatch, capsys):
    """The one place a swallowed error is correct: losing a log entry must not
    cost the technician their reply."""
    def boom(*_a, **_k):
        raise db.LogStoreError("postgres went away")

    monkeypatch.setattr(db, "write", boom)
    db.write_safe("received", correlation_id="c-3")
    assert "dropped received/info event" in capsys.readouterr().out


def test_in_flight_lists_a_received_with_no_outcome(db):
    db.write("received", correlation_id="pending", technicien="Yassine",
             channel="telegram")
    db.write("received", correlation_id="answered", technicien="Sara")
    db.write("replied", correlation_id="answered", technicien="Sara")

    assert [r["correlation_id"] for r in db.in_flight()] == ["pending"]


def test_an_error_also_ends_a_message(db):
    """`replied` is not the only terminal state — a message that failed is not
    still in the pipeline, and showing it as ⏳ forever is what a stored flag
    would have done."""
    db.write("received", correlation_id="failed")
    db.write("journal", level="error", correlation_id="failed")
    assert db.in_flight() == []


def test_stats_counts_by_level_and_pending_writes(db):
    db.write("received")
    db.write("received")
    db.write("journal", level="error")
    db.queue_failed_write({"technicien": "Yassine"}, "Sheets 503")

    out = db.stats()
    assert out["last_24h"] == {"info": 2, "error": 1}
    assert out["pending_sheet_writes"] == 1
    assert out["retention_days"] == db.RETENTION_DAYS


def test_prune_returns_the_number_deleted(db):
    db.write("received")
    # Nothing is old enough yet, so a prune is a no-op rather than a purge.
    assert db.prune(days=30) == 0
    with db._cursor() as cur:
        cur.execute("UPDATE pipeline_logs SET ts = now() - interval '40 days'")
    assert db.prune(days=30) == 1
    assert db.read() == []


def test_claim_message_is_won_once(db):
    """WhatsApp retries the same webhook; the second claim must lose, or the
    technician gets two replies and the Sheet gets two rows."""
    assert db.claim_message("wamid.1", "whatsapp") is True
    assert db.claim_message("wamid.1", "whatsapp") is False
    assert db.claim_message("wamid.2", "whatsapp") is True
