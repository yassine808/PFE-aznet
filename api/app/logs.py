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

-- The human. Split from `technicians` (the channel identities) because one
-- person reaches us on more than one channel: a WhatsApp number and a Telegram
-- chat id are two identities, one colleague. Name, role and everything we
-- remember about them belong to the person, so what they told us on Telegram is
-- still known when they write on WhatsApp.
-- `profile` is what the extraction prompt is given about this person: a short
-- French paragraph written nightly by app/memory.py from their own past
-- reports. Derived, never authoritative -- the reports in the Sheet are the
-- record, this is a summary of them. Deleting it costs nothing; the next run
-- rebuilds it.
CREATE TABLE IF NOT EXISTS persons (
    id                 BIGSERIAL PRIMARY KEY,
    name               TEXT NOT NULL,
    role               TEXT,
    profile            TEXT,
    profile_updated_at TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Who is allowed to send reports. This is the directory the reception workflow
-- checks before processing: a sender absent from it is logged with
-- stage="denied" and never reaches the LLM, which is what keeps an unknown
-- number from burning free-tier quota.
-- (channel, external_id) is unique because one phone number or chat id is one
-- identity; several rows may point at the same person_id.
CREATE TABLE IF NOT EXISTS technicians (
    id          BIGSERIAL PRIMARY KEY,
    person_id   BIGINT REFERENCES persons(id) ON DELETE CASCADE,
    channel     TEXT NOT NULL,
    external_id TEXT NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel, external_id)
);

-- There is deliberately NO table of remembered facts here. Everything a
-- profile is built from is already in the Sheet: every report a technician
-- ever sent, with their own words in `rapport_complet`. A second store of
-- facts derived from those rows would be a cache with all the usual
-- invalidation problems and no hot path to justify it.

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

-- Operator preferences: report schedule, notification recipients, export format.
-- Key/JSON rather than typed columns because these are settings, not domain data:
-- adding one must not require a migration.
CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
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


# Moves an existing `technicians` table from "one row per person per channel,
# name and role on the row" to "identity rows pointing at a person".
# `CREATE TABLE IF NOT EXISTS` cannot do this: it skips a table that already
# exists, so a deployed database would keep the old shape forever and the API
# would query columns that are not there.
#
# Written to be safely re-runnable, because it runs on every startup: every
# statement is guarded (`IF EXISTS` / `IF NOT EXISTS`), and the backfill only
# touches rows that have no person yet. On a fresh database `technicians` is
# empty and all of this is a no-op.
_MIGRATE_PERSONS = """
ALTER TABLE technicians ADD COLUMN IF NOT EXISTS person_id BIGINT REFERENCES persons(id) ON DELETE CASCADE;
ALTER TABLE persons ADD COLUMN IF NOT EXISTS profile TEXT;
ALTER TABLE persons ADD COLUMN IF NOT EXISTS profile_updated_at TIMESTAMPTZ;
DROP TABLE IF EXISTS person_memory;

-- Everything below reads technicians.name, which this migration itself drops at
-- the end. Postgres plans the whole statement before running it, so once the
-- column is gone a bare reference to it fails to *parse* -- aborting the
-- transaction and, with it, every statement above. Guarding the block on the
-- column's existence and deferring the plan to EXECUTE is what makes the
-- migration survive its own success.
DO $$
BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_name = 'technicians' AND column_name = 'name') THEN

-- One person per distinct NAME. Matching on name alone, not on (name, role),
-- because the old rows carried a role per channel and they disagree in
-- practice: the same colleague was "directeur" on WhatsApp and "tech" on
-- Telegram. Keying on the pair splits that human into two persons with two
-- separate memories, which is the exact failure this table exists to prevent.
-- `upsert_technician` matches on name only for the same reason; the two must
-- agree or a migrated database behaves differently from a fresh one.
-- max(role) is arbitrary but deterministic; the operator fixes it once in the
-- dashboard, and it is one field on one person rather than a lost memory.
INSERT INTO persons (name, role)
SELECT t.name, max(t.role)
  FROM technicians t
 WHERE t.person_id IS NULL
   AND t.name IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM persons p WHERE p.name = t.name)
 GROUP BY t.name;

UPDATE technicians t
   SET person_id = p.id
  FROM persons p
 WHERE t.person_id IS NULL
   AND p.name = t.name;

-- Dropped only after the backfill above has read them. Keeping them would leave
-- two sources of truth for a name, and they would drift the first time someone
-- corrects a spelling in one place.
ALTER TABLE technicians DROP COLUMN name;
ALTER TABLE technicians DROP COLUMN IF EXISTS role;

END IF;
END $$;
"""


def init_schema() -> None:
    """Create tables/indexes if absent, then migrate. Called once at API startup."""
    with _cursor() as cur:
        cur.execute(_SCHEMA)
        cur.execute(_MIGRATE_PERSONS)


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


def _iso(row: dict) -> dict:
    for key, value in row.items():
        if isinstance(value, datetime):
            row[key] = value.isoformat()
    return row


def list_persons() -> List[dict]:
    """Every person with their channel identities and remembered facts.

    One query per table rather than a three-way JOIN: joining identities and
    memory in one statement multiplies the rows (2 channels x 5 facts = 10 rows
    for one person) and the de-duplication in Python costs more than the extra
    round trip at this size.
    """
    with _cursor() as cur:
        cur.execute("SELECT * FROM persons ORDER BY name")
        persons = {}
        for raw in cur.fetchall():
            person = _iso(dict(raw))
            person["identities"] = []
            persons[person["id"]] = person

        cur.execute("SELECT * FROM technicians ORDER BY channel, external_id")
        for raw in cur.fetchall():
            row = _iso(dict(raw))
            owner = persons.get(row["person_id"])
            if owner is not None:
                owner["identities"].append(row)
    return list(persons.values())


def upsert_technician(
    channel: str, external_id: str, name: str, role: Optional[str] = None, active: bool = True
) -> dict:
    """Attach a channel identity to a person, creating the person if new.

    The person is matched on name, so adding a second channel for someone
    already known links it to the existing person — which is the whole point:
    what they said on Telegram has to be known when they write on WhatsApp.
    Two genuinely different people with the same name need distinct names; that
    is a real limit, and the alternative (an operator picking a person id from a
    dropdown) is a worse trade at a company with a dozen technicians.

    Upsert rather than insert so re-adding a number that already exists corrects
    it instead of failing with a constraint error the operator cannot act on.
    """
    if channel not in CHANNELS:
        raise LogStoreError(f"unknown channel: {channel} (expected one of {', '.join(CHANNELS)})")
    if not external_id.strip() or not name.strip():
        raise LogStoreError("external_id and name are required")

    with _cursor() as cur:
        cur.execute("SELECT * FROM persons WHERE name = %s", (name.strip(),))
        person = _one(cur)
        if person is None:
            cur.execute(
                "INSERT INTO persons (name, role) VALUES (%s, %s) RETURNING *",
                (name.strip(), role),
            )
            person = _one(cur)
        elif role is not None and person["role"] != role:
            cur.execute(
                "UPDATE persons SET role = %s WHERE id = %s RETURNING *", (role, person["id"])
            )
            person = _one(cur)
        person = dict(person or {})

        cur.execute(
            """
            INSERT INTO technicians (person_id, channel, external_id, active)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (channel, external_id)
            DO UPDATE SET person_id = EXCLUDED.person_id, active = EXCLUDED.active
            RETURNING *
            """,
            (person["id"], channel, external_id.strip(), active),
        )
        row = _iso(dict(_one(cur) or {}))
    row["name"], row["role"] = person["name"], person["role"]
    return row


def delete_technician(tech_id: int) -> bool:
    """Remove one channel identity. The person and their memory survive: losing
    everything a colleague ever told us because a phone number changed would be
    a surprising amount of damage for a routine edit."""
    with _cursor() as cur:
        cur.execute("DELETE FROM technicians WHERE id = %s", (tech_id,))
        return cur.rowcount > 0


def delete_person(person_id: int) -> bool:
    """Remove the person, their identities and their memory (ON DELETE CASCADE)."""
    with _cursor() as cur:
        cur.execute("DELETE FROM persons WHERE id = %s", (person_id,))
        return cur.rowcount > 0


def find_technician(channel: str, external_id: str) -> Optional[dict]:
    """Lookup used by the reception workflow to authorize an incoming sender.

    Returns the *person* behind the identity, with their profile — so the same
    context comes back whichever channel the message arrived on.

    Filters on `active`: deactivating an identity in the dashboard has to
    actually revoke access. Without this an inactive row still answers
    `found: true` and the operator's click does nothing they can observe.
    """
    with _cursor() as cur:
        cur.execute(
            """
            SELECT p.id AS person_id, p.name, p.role, p.profile,
                   t.id, t.channel, t.external_id, t.active
              FROM technicians t
              JOIN persons p ON p.id = t.person_id
             WHERE t.channel = %s AND t.external_id = %s AND t.active
            """,
            (channel, external_id.strip()),
        )
        row = _one(cur)
    return _iso(dict(row)) if row else None


def profile_for(name: Optional[str]) -> Optional[str]:
    """The profile of whoever is sending, by name.

    By name rather than by (channel, external_id) because /process is given the
    technician's name — n8n resolved the identity to a person during access
    control, so both channels arrive here as the same string, which is exactly
    what makes one profile serve both.
    """
    if not name or not name.strip():
        return None
    with _cursor() as cur:
        cur.execute("SELECT profile FROM persons WHERE name = %s", (name.strip(),))
        row = _one(cur)
    return dict(row)["profile"] if row else None


def save_profile(person_id: int, profile: Optional[str]) -> bool:
    """Store (or clear, with None) the nightly summary for a person."""
    with _cursor() as cur:
        cur.execute(
            "UPDATE persons SET profile = %s, profile_updated_at = now() WHERE id = %s",
            (profile, person_id),
        )
        return cur.rowcount > 0


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


# ── Application settings ───────────────────────────────────────────────────
# One row per key, JSON value. Small and generic on purpose: report schedule,
# notification recipients and export format are operator preferences, not
# domain data, and they change without a migration.


def get_settings() -> dict:
    with _cursor() as cur:
        cur.execute("SELECT key, value FROM app_settings")
        return {r["key"]: r["value"] for r in (cast(dict, x) for x in cur.fetchall())}


def put_settings(values: Dict[str, Any]) -> dict:
    """Upsert every supplied key. Absent keys are left untouched, never cleared."""
    if not values:
        return get_settings()
    with _cursor() as cur:
        for key, value in values.items():
            cur.execute(
                """
                INSERT INTO app_settings (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
                """,
                (key, json.dumps(value)),
            )
    return get_settings()
