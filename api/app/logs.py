"""Pipeline event log — PostgreSQL store behind POST/GET /logs.

Why a real DB and not the Sheet: the single most important thing to log is
"the Google Sheet write failed". A Sheets-backed log goes blind during exactly
the outage it exists to record. Postgres is independent of that failure domain.

Every event carries a `correlation_id` minted by n8n at reception, so the six
per-message stage rows (received → authorized → transcribed → extracted →
replied → sheet_written) plus any API-side error join into one traceable story
across two separate processes (n8n container + this FastAPI process).

psycopg2 is imported lazily inside functions so the test suite keeps running
with no database and no API keys (see CLAUDE.md).
"""
import json
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from app.config import settings

# Stages a message walks through. Free-form strings are accepted (the API logs
# its own errors with stage="api"), this list documents the happy path.
STAGES = (
    "received",
    "authorized",
    "denied",
    "transcribed",
    "extracted",
    "replied",
    "sheet_written",
    "sheet_failed",
    "duplicate",
    "api",
    "workflow_error",
)

LEVELS = ("info", "warn", "error")

RETENTION_DAYS = 30

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pipeline_logs (
    id             BIGSERIAL PRIMARY KEY,
    ts             TIMESTAMPTZ NOT NULL DEFAULT now(),
    correlation_id TEXT,
    channel        TEXT,
    technicien     TEXT,
    stage          TEXT NOT NULL,
    level          TEXT NOT NULL DEFAULT 'info',
    message        TEXT,
    duration_ms    INTEGER,
    payload        JSONB
);
CREATE INDEX IF NOT EXISTS pipeline_logs_ts_idx ON pipeline_logs (ts DESC);
CREATE INDEX IF NOT EXISTS pipeline_logs_corr_idx ON pipeline_logs (correlation_id);
CREATE INDEX IF NOT EXISTS pipeline_logs_level_idx ON pipeline_logs (level);

-- Idempotency guard: Meta retries the WhatsApp webhook when it does not get a
-- fast 200, which otherwise means duplicate Sheet rows, duplicate replies and
-- duplicate Groq/Gemini quota burn on a zero-budget project.
CREATE TABLE IF NOT EXISTS processed_messages (
    message_id   TEXT PRIMARY KEY,
    channel      TEXT,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Reply-first means the Sheet write is a recoverable side effect: failed
-- payloads park here and a cron workflow drains them.
CREATE TABLE IF NOT EXISTS failed_writes (
    id             BIGSERIAL PRIMARY KEY,
    correlation_id TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempts       INTEGER NOT NULL DEFAULT 0,
    last_error     TEXT,
    payload        JSONB NOT NULL
);

-- Who is allowed to send reports, and under what name they appear in the Sheet.
-- This is the directory the reception workflow checks before processing: a
-- sender absent from it is logged with stage="denied" and never reaches the
-- LLM, which is what keeps an unknown number from burning free-tier quota.
-- (channel, external_id) is unique because one phone number or chat id is one
-- person per channel; the same human on both channels is two rows.
CREATE TABLE IF NOT EXISTS technicians (
    id          BIGSERIAL PRIMARY KEY,
    channel     TEXT NOT NULL,
    external_id TEXT NOT NULL,
    name        TEXT NOT NULL,
    role        TEXT,
    active      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel, external_id)
);

-- Service reachability samples, one row per service per minute, written by the
-- dashboard. Kept out of pipeline_logs deliberately: those rows describe what
-- happened to a technician's message, these describe whether infrastructure was
-- answering. Mixing them would make both harder to query and would drown the
-- pipeline timeline in telemetry.
CREATE TABLE IF NOT EXISTS service_samples (
    id      BIGSERIAL PRIMARY KEY,
    ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
    service TEXT NOT NULL,
    state   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS service_samples_svc_ts_idx ON service_samples (service, ts DESC);
"""


class LogStoreError(RuntimeError):
    """Database unreachable or misconfigured — surfaced as 502, never swallowed."""


def database_url() -> str:
    url = settings.database_url
    if not url:
        raise LogStoreError(
            "DATABASE_URL is not set — start the postgres service "
            "(docker compose up -d postgres) and set it in .env"
        )
    return url


_pool = None


def _get_pool():
    """Lazily build a connection pool, once per process.

    A pool rather than connect-per-call: this module is written to several
    times per voice note, and psycopg2's `with conn:` commits the transaction
    but does NOT close the connection — so a naive connect-per-call exhausts
    Postgres's max_connections (default 100) within minutes under load.
    """
    global _pool
    if _pool is not None:
        return _pool
    try:
        from psycopg2.extras import RealDictCursor  # lazy: tests run with no DB
        from psycopg2.pool import ThreadedConnectionPool
    except ImportError as exc:  # pragma: no cover - dependency missing
        raise LogStoreError("psycopg2 is not installed (pip install -r requirements.txt)") from exc

    try:
        _pool = ThreadedConnectionPool(
            minconn=1, maxconn=10, dsn=database_url(), cursor_factory=RealDictCursor
        )
    except Exception as exc:
        raise LogStoreError(f"cannot reach postgres: {exc}") from exc
    return _pool


@contextmanager
def _cursor():
    """Pooled cursor with transaction handling and uniform error typing.

    `with conn:` commits on clean exit and rolls back on exception; the finally
    returns the connection to the pool either way. Every failure — connect-time
    or mid-query — surfaces as LogStoreError so callers have exactly one
    exception type to handle.
    """
    pool = _get_pool()
    try:
        conn = pool.getconn()
    except Exception as exc:
        raise LogStoreError(f"cannot acquire a postgres connection: {exc}") from exc

    try:
        with conn:
            with conn.cursor() as cur:
                yield cur
    except LogStoreError:
        raise
    except Exception as exc:
        raise LogStoreError(f"postgres query failed: {exc}") from exc
    finally:
        try:
            pool.putconn(conn)
        except Exception:  # pragma: no cover - pool already closed
            pass


def _one(cur) -> Optional[dict]:
    """fetchone() as a plain dict (RealDictCursor rows are dict-like)."""
    row = cur.fetchone()
    return cast(Optional[dict], row)


def init_schema() -> None:
    """Create tables/indexes if absent. Called once at API startup."""
    with _cursor() as cur:
        cur.execute(_SCHEMA)


def write(
    stage: str,
    level: str = "info",
    message: Optional[str] = None,
    correlation_id: Optional[str] = None,
    channel: Optional[str] = None,
    technicien: Optional[str] = None,
    duration_ms: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> int:
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO pipeline_logs
                (correlation_id, channel, technicien, stage, level, message, duration_ms, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                correlation_id,
                channel,
                technicien,
                stage,
                level if level in LEVELS else "info",
                message,
                duration_ms,
                json.dumps(payload) if payload is not None else None,
            ),
        )
        return (_one(cur) or {})["id"]


def write_safe(stage: str, level: str = "info", **kwargs: Any) -> None:
    """Best-effort log used from inside request handlers.

    The one place a swallowed error is correct: failing to WRITE a log must not
    turn a working /process call into a 502 for the technician. The swallow is
    loud — it prints to stderr, which lands in the uvicorn console.

    Catches BaseException-minus-Exception deliberately widely: anything at all
    that goes wrong while recording an event is less important than the report
    the technician just sent.
    """
    try:
        write(stage, level, **kwargs)
    except Exception as exc:  # noqa: BLE001 - see docstring; logging must never break /process
        print(f"[logs] dropped {stage}/{level} event: {exc}")


def read(
    limit: int = 200,
    level: Optional[str] = None,
    channel: Optional[str] = None,
    stage: Optional[str] = None,
    correlation_id: Optional[str] = None,
    search: Optional[str] = None,
) -> List[dict]:
    where: List[str] = []
    args: List[Any] = []
    if level:
        where.append("level = %s")
        args.append(level)
    if channel:
        where.append("channel = %s")
        args.append(channel)
    if stage:
        where.append("stage = %s")
        args.append(stage)
    if correlation_id:
        where.append("correlation_id = %s")
        args.append(correlation_id)
    if search:
        where.append("(message ILIKE %s OR technicien ILIKE %s)")
        args.extend(["%" + search + "%", "%" + search + "%"])

    sql = "SELECT * FROM pipeline_logs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY ts DESC, id DESC LIMIT %s"
    args.append(max(1, min(limit, 1000)))

    with _cursor() as cur:
        cur.execute(sql, args)
        rows = cur.fetchall()

    out: List[dict] = []
    for row in rows:
        item = dict(row)
        ts = item.get("ts")
        if isinstance(ts, datetime):
            item["ts"] = ts.isoformat()
        out.append(item)
    return out


def stats() -> dict:
    """Counters for the dashboard tiles (last 24 h)."""
    with _cursor() as cur:
        cur.execute(
            """
            SELECT level, COUNT(*) AS n
            FROM pipeline_logs
            WHERE ts > now() - interval '24 hours'
            GROUP BY level
            """
        )
        by_level = {d["level"]: d["n"] for d in (cast(dict, r) for r in cur.fetchall())}
        cur.execute("SELECT COUNT(*) AS n FROM failed_writes")
        pending = (_one(cur) or {"n": 0})["n"]
    return {
        "last_24h": by_level,
        "pending_sheet_writes": pending,
        "retention_days": RETENTION_DAYS,
    }


def prune(days: int = RETENTION_DAYS) -> int:
    """Delete rows older than `days`. Called by the daily cron workflow."""
    with _cursor() as cur:
        cur.execute(
            "DELETE FROM pipeline_logs WHERE ts < now() - (%s || ' days')::interval",
            (str(days),),
        )
        return cur.rowcount


# ── idempotency ────────────────────────────────────────────────────────────

def claim_message(message_id: str, channel: Optional[str] = None) -> bool:
    """Return True if this message_id is new (caller should process it).

    ON CONFLICT DO NOTHING makes the check atomic, so two concurrent webhook
    retries cannot both win the race.
    """
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO processed_messages (message_id, channel)
            VALUES (%s, %s)
            ON CONFLICT (message_id) DO NOTHING
            RETURNING message_id
            """,
            (message_id, channel),
        )
        return _one(cur) is not None


# ── sheet retry queue ──────────────────────────────────────────────────────

def queue_failed_write(payload: Dict[str, Any], error: str, correlation_id: Optional[str] = None) -> int:
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO failed_writes (correlation_id, last_error, payload)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (correlation_id, error, json.dumps(payload)),
        )
        return (_one(cur) or {})["id"]


MAX_WRITE_ATTEMPTS = 10


def pending_writes(limit: int = 20) -> List[dict]:
    """Drainable queue rows.

    The attempts cap matters: without it a permanently malformed payload is
    retried every 5 minutes forever AND, being the oldest row, permanently
    occupies the head of the window — starving newer recoverable reports.
    Rows past the cap stay in the table for inspection but stop being retried.
    """
    with _cursor() as cur:
        cur.execute(
            "SELECT * FROM failed_writes WHERE attempts < %s ORDER BY created_at ASC LIMIT %s",
            (MAX_WRITE_ATTEMPTS, max(1, min(limit, 100))),
        )
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].isoformat()
    return rows


def resolve_write(write_id: int, ok: bool, error: Optional[str] = None) -> None:
    """Drop the row on success, otherwise bump attempts so the cron can back off."""
    with _cursor() as cur:
        if ok:
            cur.execute("DELETE FROM failed_writes WHERE id = %s", (write_id,))
        else:
            cur.execute(
                "UPDATE failed_writes SET attempts = attempts + 1, last_error = %s WHERE id = %s",
                (error, write_id),
            )


# ── Technician directory ───────────────────────────────────────────────────
# The dashboard writes it; the reception workflow reads it to decide whether a
# sender is known. Kept deliberately small: identity and role, no PII beyond
# the channel handle the technician already sends from.

CHANNELS = ("telegram", "whatsapp")


def list_technicians() -> List[dict]:
    with _cursor() as cur:
        cur.execute("SELECT * FROM technicians ORDER BY channel, name")
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].isoformat()
    return rows


def upsert_technician(
    channel: str, external_id: str, name: str, role: Optional[str] = None, active: bool = True
) -> dict:
    """Insert, or update the existing row for this (channel, external_id).

    Upsert rather than insert so re-adding a number that already exists corrects
    the name instead of failing with a constraint error the operator cannot act on.
    """
    if channel not in CHANNELS:
        raise LogStoreError(f"unknown channel: {channel} (expected one of {', '.join(CHANNELS)})")
    if not external_id.strip() or not name.strip():
        raise LogStoreError("external_id and name are required")

    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO technicians (channel, external_id, name, role, active)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (channel, external_id)
            DO UPDATE SET name = EXCLUDED.name, role = EXCLUDED.role, active = EXCLUDED.active
            RETURNING *
            """,
            (channel, external_id.strip(), name.strip(), role, active),
        )
        row = dict(_one(cur) or {})
    if isinstance(row.get("created_at"), datetime):
        row["created_at"] = row["created_at"].isoformat()
    return row


def delete_technician(tech_id: int) -> bool:
    with _cursor() as cur:
        cur.execute("DELETE FROM technicians WHERE id = %s", (tech_id,))
        return cur.rowcount > 0


def find_technician(channel: str, external_id: str) -> Optional[dict]:
    """Lookup used by the reception workflow to authorize an incoming sender."""
    with _cursor() as cur:
        cur.execute(
            "SELECT * FROM technicians WHERE channel = %s AND external_id = %s",
            (channel, external_id.strip()),
        )
        row = _one(cur)
    return dict(row) if row else None


# ── Service uptime samples ─────────────────────────────────────────────────


def record_samples(samples: List[dict]) -> int:
    """Append one row per service reading.

    Written by the dashboard every minute. Cheap and append-only: aggregation
    happens at read time, so a sampling gap stays visibly a gap instead of being
    smoothed into fake uptime.
    """
    if not samples:
        return 0
    with _cursor() as cur:
        cur.executemany(
            "INSERT INTO service_samples (service, state) VALUES (%s, %s)",
            [(s["service"], s["state"]) for s in samples],
        )
        return len(samples)


def read_samples(hours: int = 1) -> List[dict]:
    """Samples inside the window, oldest first, for the dashboard's uptime strips."""
    window = max(1, min(hours, 24 * 30))
    with _cursor() as cur:
        cur.execute(
            "SELECT service, state, ts FROM service_samples "
            "WHERE ts > now() - (%s * interval '1 hour') ORDER BY ts ASC",
            (window,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        if isinstance(r.get("ts"), datetime):
            r["ts"] = r["ts"].isoformat()
    return rows


def prune_samples(days: int = RETENTION_DAYS) -> int:
    with _cursor() as cur:
        cur.execute("DELETE FROM service_samples WHERE ts < now() - (%s * interval '1 day')", (days,))
        return cur.rowcount
