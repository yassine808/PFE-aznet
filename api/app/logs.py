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
from datetime import datetime, timedelta, timezone
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
-- Credentials live here too, nullable. The earlier split (a separate `users`
-- table) argued from lifecycle: a technician sends reports and never logs in, a
-- chef logs in and never sends reports. That is an argument about *credentials*,
-- not about identity -- it proves a technician needs no password, never that a
-- technician and a chef are different kinds of thing. Two tables for one human
-- meant every org-chart node was a LEFT JOIN plus a tiebreak rule for whose
-- name and role won when they disagreed, which is precisely the disagreement
-- _MIGRATE_PERSONS below records happening on live data.
-- `password_hash IS NULL` is the whole of "this human cannot sign in".
--
-- `manager_id` is the org chart: it only ever points a tech at a chef. Nothing
-- in Postgres forbids a cycle on a self-reference, but the renderer draws three
-- fixed bands keyed on `role`, so a cycle has nowhere to be drawn and cannot
-- hang anything. If the chart ever goes recursive, that guard has to be added.
CREATE TABLE IF NOT EXISTS persons (
    id                 BIGSERIAL PRIMARY KEY,
    name               TEXT NOT NULL,
    role               TEXT NOT NULL DEFAULT 'tech',   -- 'directeur' | 'chef' | 'tech'
    manager_id         BIGINT REFERENCES persons(id) ON DELETE SET NULL,
    email              TEXT UNIQUE,     -- NULL for everyone who never signs in
    password_hash      TEXT,            -- NULL = no dashboard access, ever
    active             BOOLEAN NOT NULL DEFAULT true,
    last_seen_at       TIMESTAMPTZ,
    profile            TEXT,
    profile_updated_at TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- The index on manager_id is NOT here: on an existing database the CREATE TABLE
-- above is skipped but an index statement beside it would still run, against a
-- table that has no manager_id until _MIGRATE_ACCOUNTS adds it. That error
-- aborts the whole init_schema transaction -- schema and migration together --
-- and the API comes up with `[logs] DISABLED`. It lives with its column.

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

-- Opaque session tokens rather than JWTs, so a session can actually be revoked:
-- deleting the row logs that browser out on its next request. A signed token
-- stays valid until it expires no matter what the database says, which is the
-- wrong behaviour the day an account has to be shut off.
CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id);

-- What a human deliberately changed. `before`/`after` are filled for edits so
-- the history reads "goulottes_m: 40 -> 45" rather than "someone edited a row".
-- ON DELETE SET NULL, not CASCADE: removing an account must not erase the record
-- of what it did, which is the one thing an audit trail exists to prevent.
CREATE TABLE IF NOT EXISTS user_actions (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT REFERENCES persons(id) ON DELETE SET NULL,
    user_name  TEXT,
    action     TEXT NOT NULL,
    target     TEXT,
    before_val TEXT,
    after_val  TEXT,
    detail     JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS user_actions_user_idx ON user_actions (user_id, created_at DESC);

-- Navigation, kept apart from user_actions because it is ~20x the volume and a
-- different shape (it has a duration). Merged, every "what did she change?"
-- query would need to filter out page views and the timeline would be noise.
-- Duration is measured in the browser: the server cannot see how long a page
-- stayed open.
CREATE TABLE IF NOT EXISTS page_visits (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT REFERENCES persons(id) ON DELETE SET NULL,
    route      TEXT NOT NULL,
    seconds    INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS page_visits_user_idx ON page_visits (user_id, created_at DESC);

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

-- Per-account dashboard preferences (clock format, density, confidence
-- threshold): one JSONB blob per person, same key/JSON rationale as
-- app_settings. One row, whole settings object — not key/value — because only
-- the person's own browser ever reads it; there is no query that wants one key
-- across accounts.
CREATE TABLE IF NOT EXISTS person_settings (
    person_id  BIGINT PRIMARY KEY REFERENCES persons(id) ON DELETE CASCADE,
    value      JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The last generated report per site manager, one row per period. The
-- technicians' /rapport command answers from here: the reply must be the last
-- *generated* version, not a regeneration — the daily mail and the command
-- must show the same text, or the manager and their team are looking at two
-- reports that disagree about the same day. Written by the scheduler only;
-- dashboard manual runs stay company-wide on purpose.
CREATE TABLE IF NOT EXISTS manager_reports (
    manager_id   BIGINT NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    period       TEXT NOT NULL,
    period_type  TEXT NOT NULL DEFAULT 'daily',
    objet        TEXT NOT NULL,
    corps        TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    generated_by TEXT NOT NULL DEFAULT 'automatique',
    PRIMARY KEY (manager_id, period)
);
CREATE INDEX IF NOT EXISTS manager_reports_mgr_idx ON manager_reports (manager_id, generated_at DESC);

-- Media archive: every voice note / photo /document the pipeline receives,
-- copied into Postgres while it is still downloadable. Telegram file_ids and
-- WhatsApp media ids are tickets, not URLs — Meta's media URLs expire within
-- minutes, so without a durable copy the only trace left of a technician's
-- message is its transcript. Rows are small (Telegram caps voice notes at
-- ~1.5 MB, photos at a few hundred KB), which keeps a BYTEA column honest.
CREATE TABLE IF NOT EXISTS media_files (
    id          BIGSERIAL PRIMARY KEY,
    channel     TEXT,
    external_id TEXT,
    message_id  TEXT,
    kind        TEXT NOT NULL,               -- 'audio' | 'image'
    mime_type   TEXT,
    size_bytes  INTEGER NOT NULL DEFAULT 0,
    data        BYTEA NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS media_files_ts_idx ON media_files (created_at DESC);

-- Raw chat archive: every typed message, so the conversation survives the
-- Sheet (the Sheet only ever holds extracted reports).
CREATE TABLE IF NOT EXISTS chat_messages (
    id          BIGSERIAL PRIMARY KEY,
    channel     TEXT,
    external_id TEXT,
    message_id  TEXT,
    text        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_messages_ts_idx ON chat_messages (created_at DESC);

-- The /modify command: a technician replies to their own message and the row
-- it became has to be found by the id of that message. The claim already
-- stores `channel:msgid`; these two columns record which Sheet row it landed
-- on, written by whoever performed the append (n8n on the happy path, the
-- retry drain after a Sheets outage).
ALTER TABLE processed_messages ADD COLUMN IF NOT EXISTS sheet_row BIGINT;
ALTER TABLE processed_messages ADD COLUMN IF NOT EXISTS linked_at TIMESTAMPTZ;

-- Per-account in-app notifications (the dashboard bell). Every row is owned
-- by exactly one person; pipeline events (a new report for the chef, a row
-- flagged for review, a Sheets failure) land here beside task reminders, so
-- each account sees its own history and nothing else.
CREATE TABLE IF NOT EXISTS notifications (
    id          BIGSERIAL PRIMARY KEY,
    person_id   BIGINT NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,          -- 'report' | 'review' | 'error' | 'reminder'
    title       TEXT NOT NULL,
    body        TEXT,
    route       TEXT,                   -- dashboard hash route to jump to, e.g. '#/reports'
    ref_id      TEXT,                   -- sheet row / correlation id for the jump target
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS notifications_person_idx
    ON notifications (person_id, created_at DESC);

-- Shared to-do list with recurring reminders. Global on purpose: the org is
-- small enough that one list every account can edit beats five copies of it.
-- `repeat` is how the scheduler advances due_at after firing a reminder;
-- `remind_before_value`/`remind_before_unit` open the reminder early (X
-- days/weeks/months before the due moment); `repeat_every`/`repeat_unit` add
-- custom intervals (every 3 days, every 2 weeks, ...) beside the presets.
-- `last_notified_at` records the DUE MOMENT of the last occurrence that fired,
-- not the firing time, so the once-per-occurrence guard `last_notified_at <
-- due_at` survives advance reminders (a fire at due-3d must not re-fire every
-- tick just because the stamp time is before the due moment).
CREATE TABLE IF NOT EXISTS tasks (
    id                   BIGSERIAL PRIMARY KEY,
    title                TEXT NOT NULL,
    notes                TEXT,
    due_at               TIMESTAMPTZ,
    repeat               TEXT NOT NULL DEFAULT 'none' CHECK (repeat IN ('none','daily','weekly','monthly')),
    remind_before_value  INT CHECK (remind_before_value IS NULL OR remind_before_value >= 0),
    remind_before_unit   TEXT CHECK (remind_before_unit IN ('day','week','month')),
    repeat_every         INT CHECK (repeat_every IS NULL OR repeat_every >= 1),
    repeat_unit          TEXT CHECK (repeat_unit IN ('day','week','month')),
    done_at              TIMESTAMPTZ,
    last_notified_at     TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tasks_due_idx ON tasks (due_at) WHERE done_at IS NULL;

-- The live table predates these columns: CREATE TABLE IF NOT EXISTS is a no-op
-- on it, so add the columns and their constraints explicitly. Postgres has no
-- `ADD CONSTRAINT IF NOT EXISTS`, hence the pg_constraint lookups.
DO $$ BEGIN
    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS remind_before_value INT;
    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS remind_before_unit TEXT;
    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS repeat_every INT;
    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS repeat_unit TEXT;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tasks_remind_before_value_check') THEN
        ALTER TABLE tasks ADD CONSTRAINT tasks_remind_before_value_check
            CHECK (remind_before_value IS NULL OR remind_before_value >= 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tasks_remind_before_unit_check') THEN
        ALTER TABLE tasks ADD CONSTRAINT tasks_remind_before_unit_check
            CHECK (remind_before_unit IN ('day','week','month'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tasks_repeat_every_check') THEN
        ALTER TABLE tasks ADD CONSTRAINT tasks_repeat_every_check
            CHECK (repeat_every IS NULL OR repeat_every >= 1);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tasks_repeat_unit_check') THEN
        ALTER TABLE tasks ADD CONSTRAINT tasks_repeat_unit_check
            CHECK (repeat_unit IN ('day','week','month'));
    END IF;
END $$;
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


# Folds the old `users` table into `persons`. Same reasoning as above: the
# CREATE above is `IF NOT EXISTS`, so a database that already has both tables
# keeps them and the API starts querying columns that live on the wrong one.
#
# Guarded on `users` existing and re-runnable: once the table is dropped the
# whole block is skipped. Ordering matters -- the FKs on sessions /
# user_actions / page_visits still point at users(id) at this moment, so ids
# have to be preserved rather than reallocated, and the constraints have to be
# repointed before the drop.
_MIGRATE_ACCOUNTS = """
ALTER TABLE persons ADD COLUMN IF NOT EXISTS manager_id BIGINT REFERENCES persons(id) ON DELETE SET NULL;
ALTER TABLE persons ADD COLUMN IF NOT EXISTS email TEXT UNIQUE;
ALTER TABLE persons ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE persons ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE persons ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;
UPDATE persons SET role = 'tech' WHERE role IS NULL;
ALTER TABLE persons ALTER COLUMN role SET DEFAULT 'tech';
ALTER TABLE persons ALTER COLUMN role SET NOT NULL;
CREATE INDEX IF NOT EXISTS persons_manager_idx ON persons (manager_id);

DO $$
BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users') THEN

-- An account whose name already exists as a person IS that person: this is the
-- whole point of folding, and it is why the chef who also sends voice notes
-- stops being two boxes on the chart. Matched on name for the same reason
-- upsert_technician does, and the two must keep agreeing.
UPDATE persons p
   SET email         = u.email,
       password_hash = u.password_hash,
       role          = u.role,
       active        = u.active,
       last_seen_at  = u.last_seen_at
  FROM users u
 WHERE lower(p.name) = lower(u.name)
   AND p.password_hash IS NULL;

-- Accounts with no matching person become persons, keeping their id so the
-- audit trail and any live session still resolve. setval afterwards, or the
-- next BIGSERIAL insert collides with a transplanted id.
INSERT INTO persons (id, name, role, email, password_hash, active, last_seen_at, created_at)
SELECT u.id, u.name, u.role, u.email, u.password_hash, u.active, u.last_seen_at, u.created_at
  FROM users u
 WHERE NOT EXISTS (SELECT 1 FROM persons p WHERE p.email = u.email)
   AND NOT EXISTS (SELECT 1 FROM persons p WHERE p.id = u.id);
PERFORM setval('persons_id_seq', GREATEST((SELECT max(id) FROM persons), 1));

ALTER TABLE sessions     DROP CONSTRAINT IF EXISTS sessions_user_id_fkey;
ALTER TABLE user_actions DROP CONSTRAINT IF EXISTS user_actions_user_id_fkey;
ALTER TABLE page_visits  DROP CONSTRAINT IF EXISTS page_visits_user_id_fkey;
ALTER TABLE sessions     ADD CONSTRAINT sessions_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES persons(id) ON DELETE CASCADE;
ALTER TABLE user_actions ADD CONSTRAINT user_actions_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES persons(id) ON DELETE SET NULL;
ALTER TABLE page_visits  ADD CONSTRAINT page_visits_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES persons(id) ON DELETE SET NULL;

DROP TABLE users;

END IF;
END $$;
"""


def init_schema() -> None:
    """Create tables/indexes if absent, then migrate. Called once at API startup."""
    with _cursor() as cur:
        cur.execute(_SCHEMA)
        cur.execute(_MIGRATE_PERSONS)
        cur.execute(_MIGRATE_ACCOUNTS)


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


# ── media + chat archive ───────────────────────────────────────────────────
# Every voice note, photo and typed message is copied into Postgres as it
# arrives (see the media_files / chat_messages comments in _SCHEMA for why).
# These functions raise LogStoreError like the rest of the module; the /process
# handler wraps them in best-effort calls because archiving must never cost a
# technician their reply.


def save_media(
    channel: Optional[str],
    external_id: Optional[str],
    message_id: Optional[str],
    kind: str,
    mime_type: Optional[str],
    data: bytes,
) -> int:
    with _cursor() as cur:
        from psycopg2 import Binary  # lazy: tests run with no DB

        cur.execute(
            """
            INSERT INTO media_files
                (channel, external_id, message_id, kind, mime_type, size_bytes, data)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (channel, external_id, message_id, kind, mime_type, len(data), Binary(data)),
        )
        return (_one(cur) or {})["id"]


def save_message(
    channel: Optional[str],
    external_id: Optional[str],
    message_id: Optional[str],
    text: str,
) -> int:
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO chat_messages (channel, external_id, message_id, text)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (channel, external_id, message_id, text),
        )
        return (_one(cur) or {})["id"]


def list_media(limit: int = 50) -> List[dict]:
    """Archive listing — metadata only, never the blob.

    A dashboard grid does not need to download every file to know they exist;
    GET /media/{id}/file fetches one on demand.
    """
    with _cursor() as cur:
        cur.execute(
            "SELECT id, channel, external_id, message_id, kind, mime_type, "
            "size_bytes, created_at FROM media_files ORDER BY created_at DESC LIMIT %s",
            (max(1, min(limit, 200)),),
        )
        rows = [_iso(dict(r)) for r in cur.fetchall()]
    return rows


def get_media(media_id: int) -> Optional[dict]:
    """One archived file, blob included, for GET /media/{id}/file."""
    with _cursor() as cur:
        cur.execute("SELECT * FROM media_files WHERE id = %s", (media_id,))
        row = _one(cur)
    if row is None:
        return None
    out = _iso(dict(row))
    out["data"] = bytes(out["data"])
    return out


def list_messages(
    limit: int = 100, channel: Optional[str] = None, search: Optional[str] = None
) -> List[dict]:
    with _cursor() as cur:
        where: List[str] = []
        args: List[Any] = []
        if channel:
            where.append("channel = %s")
            args.append(channel)
        if search:
            where.append("text ILIKE %s")
            args.append("%" + search + "%")
        sql = "SELECT id, channel, external_id, message_id, text, created_at FROM chat_messages"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT %s"
        args.append(max(1, min(limit, 500)))
        cur.execute(sql, args)
        rows = [_iso(dict(r)) for r in cur.fetchall()]
    return rows


# ── message → Sheet row link (the /modify command) ─────────────────────────
# The /modify reply has to find the row its report landed on, and the only id
# it carries is the origin message's — the same `channel:msgid` string the
# claim stores. The link is written by whoever performed the append.

def link_message_row(message_id: str, row: Optional[int]) -> bool:
    """Remember which Sheet row a processed message landed on; None clears it.

    Upsert-free by design: the row already exists (the claim inserted it), so
    this is an UPDATE — clearing with None is how /supprimer unlinks a row.
    """
    with _cursor() as cur:
        cur.execute(
            "UPDATE processed_messages SET sheet_row = %s, linked_at = now() "
            "WHERE message_id = %s",
            (row, message_id),
        )
        return cur.rowcount > 0


def message_row(message_id: str) -> Optional[int]:
    """The Sheet row a message landed on, if anyone linked it."""
    with _cursor() as cur:
        cur.execute("SELECT sheet_row FROM processed_messages WHERE message_id = %s", (message_id,))
        row = _one(cur)
    if row is None or row["sheet_row"] is None:
        return None
    return int(row["sheet_row"])


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
        # Columns named, not `*`: since accounts folded into this table a
        # `SELECT *` would ship password_hash to the browser. `has_login` is
        # derived here so the dashboard can show who can sign in without the
        # hash ever leaving Postgres.
        cur.execute(
            """
            SELECT id, name, role, manager_id, email, active, last_seen_at,
                   profile, profile_updated_at, created_at,
                   (password_hash IS NOT NULL) AS has_login
              FROM persons ORDER BY name
            """
        )
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


def normalize_external_id(channel: str, external_id: str) -> str:
    """Bring a channel identity to the form the rest of the pipeline expects.

    WhatsApp numbers are phones, and operators type them every way imaginable
    (`+212 6 61 23 45 67`, `0661234567`, `661234567`, `00212…`). One canonical
    form — 12 digits starting `2126`/`2127` — makes the dedupe guard and the
    directory lookup match regardless of how the number was keyed in. Telegram
    chat ids are not phones and are left untouched.
    """
    if channel != "whatsapp":
        return external_id.strip()
    digits = "".join(c for c in external_id if c.isdigit())
    if not digits:
        return external_id.strip()
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("2120") and len(digits) == 13:
        digits = "212" + digits[4:]
    if digits.startswith("0"):
        digits = "212" + digits[1:]
    if len(digits) == 9 and digits.startswith(("6", "7")):
        digits = "212" + digits
    return digits


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
    external_id = normalize_external_id(channel, external_id)
    if not external_id or not name.strip():
        raise LogStoreError("external_id and name are required")

    with _cursor() as cur:
        cur.execute("SELECT * FROM persons WHERE name = %s", (name.strip(),))
        person = _one(cur)
        if person is None:
            # `or "tech"`: role is NOT NULL since accounts folded in, and an
            # auto-created sender must land as a technician with no manager --
            # i.e. in the chart's "unassigned" column, never as a chef.
            cur.execute(
                "INSERT INTO persons (name, role) VALUES (%s, %s) RETURNING *",
                (name.strip(), role or "tech"),
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


def create_person(name: str, role: str = "chef") -> dict:
    """A person with no channel and no login yet — the org chart's "+".

    Name only on purpose: sketching the org must not require inventing a
    password for everyone in it. `auth.grant_access` adds credentials later, and
    a chef accepts technicians the moment the box exists.
    """
    if not name.strip():
        raise LogStoreError("name is required")
    with _cursor() as cur:
        cur.execute(
            "INSERT INTO persons (name, role) VALUES (%s, %s) RETURNING id", (name.strip(), role)
        )
        person_id = dict(_one(cur) or {})["id"]
    return {"id": person_id, "name": name.strip(), "role": role}


def set_manager(person_id: int, manager_id: Optional[int]) -> bool:
    """Move someone under a chef, or out to unassigned with None.

    Refuses self-parenting, the one cycle a three-band chart can actually
    produce (A under A renders as a person who is their own crew). Deeper cycles
    are not reachable: the renderer keys bands on `role`, so a chef never gets a
    manager_id in the first place.
    """
    if manager_id is not None and manager_id == person_id:
        raise LogStoreError("a person cannot report to themselves")
    with _cursor() as cur:
        cur.execute("UPDATE persons SET manager_id = %s WHERE id = %s", (manager_id, person_id))
        return cur.rowcount > 0


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

    The incoming id goes through the same normalization as writes, or a sender
    whose number was keyed in differently than the directory would be denied
    — one form, stored and looked up alike.
    """
    external_id = normalize_external_id(channel, external_id)
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


def person_by_name(name: str) -> Optional[dict]:
    """The person behind a Sheet name, with their channel identities.

    The inbox replies by name because that is what the Sheet rows carry — n8n
    resolved identities to people during access control, so Telegram and
    WhatsApp both arrive here as the same string. Columns named (the hash
    never rides out to the browser, same rule as list_persons).
    """
    with _cursor() as cur:
        cur.execute(
            """
            SELECT id, name, role, manager_id, email, active, last_seen_at,
                   profile, profile_updated_at, created_at
              FROM persons WHERE name = %s
            """,
            (name.strip(),),
        )
        person = _one(cur)
        if person is None:
            return None
        person = _iso(dict(person))
        cur.execute(
            "SELECT id, channel, external_id, active, person_id FROM technicians WHERE person_id = %s",
            (person["id"],),
        )
        person["identities"] = [_iso(dict(raw)) for raw in cur.fetchall()]
    return person


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


def prune_meta(days: int = RETENTION_DAYS) -> dict:
    """Retention sweep for the tables that would otherwise grow forever: expired
    sessions, idempotency claims, the audit trail and page visits.

    Sessions prune on expiry (they are dead the moment `expires_at` passes)
    rather than on age: an account that logs in every six days keeps a live
    session past any age cutoff, and cutting it would force an early logout.
    The others age out exactly like the pipeline logs — a 30-day audit trail is
    the same bargain `pipeline_logs` makes.
    """
    with _cursor() as cur:
        cur.execute("DELETE FROM sessions WHERE expires_at < now()")
        sessions = cur.rowcount
        cur.execute(
            "DELETE FROM processed_messages WHERE processed_at < now() - (%s * interval '1 day')",
            (days,),
        )
        claims = cur.rowcount
        cur.execute(
            "DELETE FROM user_actions WHERE created_at < now() - (%s * interval '1 day')",
            (days,),
        )
        actions = cur.rowcount
        cur.execute(
            "DELETE FROM page_visits WHERE created_at < now() - (%s * interval '1 day')",
            (days,),
        )
        visits = cur.rowcount
    return {
        "sessions_deleted": sessions,
        "claims_deleted": claims,
        "actions_deleted": actions,
        "visits_deleted": visits,
    }


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


# ── Per-account settings ────────────────────────────────────────────────────
# One JSONB blob per person. The browser owns the defaults and merges what it
# gets over them; the server just stores what each account chose.

def get_person_settings(person_id: int) -> dict:
    with _cursor() as cur:
        cur.execute("SELECT value FROM person_settings WHERE person_id = %s", (person_id,))
        row = _one(cur)
    return dict(row)["value"] if row else {}


def put_person_settings(person_id: int, values: Dict[str, Any]) -> dict:
    """Merge every supplied key into the account's blob. Absent keys are left
    untouched, never cleared — `||` on JSONB keeps what we already had."""
    if not values:
        return get_person_settings(person_id)
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO person_settings (person_id, value) VALUES (%s, %s)
            ON CONFLICT (person_id) DO UPDATE
                SET value = person_settings.value || EXCLUDED.value, updated_at = now()
            """,
            (person_id, json.dumps(values)),
        )
    return get_person_settings(person_id)


def account_emails() -> List[str]:
    """Emails of every account (admin + site managers), for the report mail.

    `password_hash IS NOT NULL` is the whole of "this row is an account" since
    the users table folded into persons; technicians never sign in and their
    email stays NULL, so this is automatically "the people who should read the
    end-of-day report" — no role list to keep in sync with the org chart.
    """
    with _cursor() as cur:
        cur.execute(
            "SELECT email FROM persons "
            "WHERE email IS NOT NULL AND password_hash IS NOT NULL ORDER BY name"
        )
        return [dict(r)["email"] for r in cur.fetchall()]


# ── Per-manager reports (the /rapport command) ──────────────────────────────

def person_by_id(person_id: int) -> Optional[dict]:
    """One person row, named columns — used to resolve a manager's identity."""
    with _cursor() as cur:
        cur.execute(
            "SELECT id, name, role, manager_id, email, "
            "(password_hash IS NOT NULL) AS has_login FROM persons WHERE id = %s",
            (person_id,),
        )
        row = _one(cur)
    return _iso(dict(row)) if row else None


def save_manager_report(
    manager_id: int,
    period: str,
    objet: str,
    corps: str,
    generated_by: str = "automatique",
    period_type: str = "daily",
) -> None:
    """Store the last generated report for a manager, one row per period.

    UPSERT rather than INSERT: when a manager's report is regenerated for the
    same period, the newest text wins — that is what "last version" means to
    the /rapport command. `period_type` separates daily from weekly periods
    for the dashboard's generated-reports list.
    """
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO manager_reports (manager_id, period, period_type, objet, corps, generated_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (manager_id, period) DO UPDATE
                SET period_type = EXCLUDED.period_type, objet = EXCLUDED.objet,
                    corps = EXCLUDED.corps, generated_by = EXCLUDED.generated_by,
                    generated_at = now()
            """,
            (manager_id, period, period_type, objet, corps, generated_by),
        )


def latest_manager_report(manager_id: int) -> Optional[dict]:
    """The newest stored report for a manager, whichever period it covers."""
    with _cursor() as cur:
        cur.execute(
            "SELECT manager_id, period, period_type, objet, corps, generated_at, generated_by "
            "FROM manager_reports WHERE manager_id = %s "
            "ORDER BY generated_at DESC LIMIT 1",
            (manager_id,),
        )
        row = _one(cur)
    return _iso(dict(row)) if row else None


def list_manager_reports() -> List[dict]:
    """Every stored report, newest first, with the manager's name attached.

    The dashboard's reports page renders daily + weekly versions from here —
    the same rows the mail and the /rapport command use, so nothing a report
    showed was generated twice with a different text. A manager whose person
    row vanished keeps their row, under a placeholder name.
    """
    with _cursor() as cur:
        cur.execute(
            """
            SELECT m.manager_id, m.period, m.period_type, m.objet, m.corps,
                   m.generated_at, m.generated_by,
                   COALESCE(p.name, '—') AS manager_name
            FROM manager_reports m
            LEFT JOIN persons p ON p.id = m.manager_id
            ORDER BY m.generated_at DESC
            """
        )
        rows = [_iso(dict(r)) for r in cur.fetchall()]
    return rows


# ── In-app notifications (the dashboard bell) ───────────────────────────────


def create_notification(
    person_id: int,
    kind: str,
    title: str,
    body: Optional[str] = None,
    route: Optional[str] = None,
    ref_id: Optional[str] = None,
) -> None:
    """Append one notification for one person."""
    with _cursor() as cur:
        cur.execute(
            "INSERT INTO notifications (person_id, kind, title, body, route, ref_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (person_id, kind, title, body, route, ref_id),
        )


def account_people() -> List[dict]:
    """Accounts (people who can sign in) — the audience of the bell.

    Same rule as `account_emails`: `password_hash IS NOT NULL` is the whole of
    "this row is an account". Technicians never sign in, so they neither read
    the bell nor get reminder mail.
    """
    with _cursor() as cur:
        cur.execute(
            "SELECT id, name, email FROM persons "
            "WHERE password_hash IS NOT NULL ORDER BY name"
        )
        return [_iso(dict(r)) for r in cur.fetchall()]


def notify_accounts(
    kind: str,
    title: str,
    body: Optional[str] = None,
    route: Optional[str] = None,
    ref_id: Optional[str] = None,
) -> int:
    """One notification for every account. Returns how many rows were written."""
    people = account_people()
    if not people:
        return 0
    with _cursor() as cur:
        cur.executemany(
            "INSERT INTO notifications (person_id, kind, title, body, route, ref_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            [(p["id"], kind, title, body, route, ref_id) for p in people],
        )
    return len(people)


def notify_technician_manager(
    technicien: Optional[str],
    kind: str,
    title: str,
    body: Optional[str] = None,
    route: Optional[str] = None,
    ref_id: Optional[str] = None,
) -> Optional[int]:
    """Bell target for a report: the sender's manager, nobody else.

    Resolution key is the person's name — the same key the directory and the
    channel tables use — and only an account manager gets the row (a manager
    who never signs in cannot read a bell). When the sender is unknown or has
    no manager (a directeur's own report), the notification escalates to every
    manager account rather than dying silently. Returns the rows written, or
    None when there is no account to notify.
    """
    manager_id: Optional[int] = None
    if technicien:
        with _cursor() as cur:
            cur.execute(
                "SELECT manager_id FROM persons WHERE name = %s ORDER BY id LIMIT 1",
                (technicien,),
            )
            row = cur.fetchone()
            if row is not None:
                manager_id = row[0]
    if manager_id is not None:
        with _cursor() as cur:
            cur.execute(
                "SELECT 1 FROM persons WHERE id = %s AND password_hash IS NOT NULL",
                (manager_id,),
            )
            if cur.fetchone() is not None:
                return create_notification(manager_id, kind, title, body, route, ref_id)
    return notify_managers(kind, title, body, route, ref_id)


def notify_managers(
    kind: str,
    title: str,
    body: Optional[str] = None,
    route: Optional[str] = None,
    ref_id: Optional[str] = None,
) -> int:
    """Notify every chef/directeur account about their team's activity.

    The kind of event that concerns management (a new report, a row flagged
    for review) has no business in a technician's bell, and a chef without an
    account cannot read one anyway — so only accounts get rows.
    """
    with _cursor() as cur:
        cur.execute(
            "SELECT id, name FROM persons "
            "WHERE password_hash IS NOT NULL AND role IN ('chef', 'directeur')"
        )
        people = [dict(r) for r in cur.fetchall()]
    if not people:
        return 0
    with _cursor() as cur:
        cur.executemany(
            "INSERT INTO notifications (person_id, kind, title, body, route, ref_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            [(p["id"], kind, title, body, route, ref_id) for p in people],
        )
    return len(people)


def list_notifications(person_id: int, limit: int = 50) -> List[dict]:
    with _cursor() as cur:
        cur.execute(
            "SELECT id, kind, title, body, route, ref_id, created_at, read_at "
            "FROM notifications WHERE person_id = %s "
            "ORDER BY created_at DESC LIMIT %s",
            (person_id, limit),
        )
        return [_iso(dict(r)) for r in cur.fetchall()]


def unread_notifications(person_id: int) -> int:
    with _cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM notifications "
            "WHERE person_id = %s AND read_at IS NULL",
            (person_id,),
        )
        row = _one(cur)
    return int(row["n"]) if row else 0


def mark_notifications_read(person_id: int, ids: Optional[List[int]] = None) -> int:
    """Mark the given ids read, or everything when ids is None. Returns count."""
    with _cursor() as cur:
        if ids:
            cur.execute(
                "UPDATE notifications SET read_at = now() "
                "WHERE person_id = %s AND id = ANY(%s) AND read_at IS NULL",
                (person_id, list(ids)),
            )
        else:
            cur.execute(
                "UPDATE notifications SET read_at = now() "
                "WHERE person_id = %s AND read_at IS NULL",
                (person_id,),
            )
        return cur.rowcount


# ── Shared to-do tasks ──────────────────────────────────────────────────────


_TASK_COLUMNS = (
    "title", "notes", "due_at", "repeat",
    "remind_before_value", "remind_before_unit",
    "repeat_every", "repeat_unit",
)


def shift_months(dt: datetime, n: int) -> datetime:
    """Add n months (negative subtracts), clamping to the month's real length.

    Jan 31 + 1 month → Feb 28, never March 3: a monthly task on the 31st must
    not silently skip February. Shared by the repeat advance and the advance
    reminder offset, so both sides of the calendar math cannot drift apart.
    """
    import calendar

    month = dt.month + n
    year = dt.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def notify_time(due_at: Optional[datetime], value: Optional[int],
                unit: Optional[str]) -> Optional[datetime]:
    """When this occurrence's reminder should fire: due minus the lead time.

    The scheduler fires as soon as `notify_time(due_at) <= now`, which is the
    whole of the "remind X days/weeks/months before" feature — with no lead the
    window opens exactly at the due moment, preserving the old behaviour.
    """
    if due_at is None or not value or unit not in ("day", "week", "month"):
        return due_at
    if unit == "day":
        return due_at - timedelta(days=value)
    if unit == "week":
        return due_at - timedelta(weeks=value)
    return shift_months(due_at, -value)


def create_task(title: str, notes: Optional[str] = None,
                due_at: Optional[datetime] = None, repeat: str = "none",
                remind_before_value: Optional[int] = None,
                remind_before_unit: Optional[str] = None,
                repeat_every: Optional[int] = None,
                repeat_unit: Optional[str] = None) -> int:
    with _cursor() as cur:
        cur.execute(
            "INSERT INTO tasks (title, notes, due_at, repeat, "
            "remind_before_value, remind_before_unit, repeat_every, repeat_unit) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (title, notes, due_at, repeat, remind_before_value,
             remind_before_unit, repeat_every, repeat_unit),
        )
        row = _one(cur)
    return int(row["id"])


def update_task(task_id: int, fields: dict) -> bool:
    """Update whitelisted columns. `done` toggles done_at; done=false reopens."""
    allowed = {k: v for k, v in fields.items() if k in _TASK_COLUMNS or k == "done"}
    if not allowed:
        return False
    sets = []
    values = []
    if "done" in allowed:
        if allowed.pop("done"):
            sets.append("done_at = now()")
        else:
            sets.append("done_at = NULL")
    for col in sorted(allowed):
        sets.append(f"{col} = %s")
        values.append(allowed[col])
    sets.append("updated_at = now()")
    values.append(task_id)
    with _cursor() as cur:
        cur.execute(
            f"UPDATE tasks SET {', '.join(sets)} WHERE id = %s", values
        )
        return cur.rowcount > 0


def delete_task(task_id: int) -> bool:
    with _cursor() as cur:
        cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
        return cur.rowcount > 0


def get_task(task_id: int) -> Optional[dict]:
    with _cursor() as cur:
        cur.execute(
            "SELECT id, title, notes, due_at, repeat, "
            "remind_before_value, remind_before_unit, repeat_every, repeat_unit, "
            "done_at, last_notified_at, created_at, updated_at FROM tasks "
            "WHERE id = %s",
            (task_id,),
        )
        row = cur.fetchone()
        return _iso(dict(row)) if row else None


def list_tasks() -> List[dict]:
    """Every task, open first then done, each group by due date."""
    with _cursor() as cur:
        cur.execute(
            "SELECT id, title, notes, due_at, repeat, "
            "remind_before_value, remind_before_unit, repeat_every, repeat_unit, "
            "done_at, last_notified_at, created_at, updated_at FROM tasks "
            "ORDER BY (done_at IS NOT NULL), COALESCE(due_at, 'infinity'::timestamptz)"
        )
        return [_iso(dict(r)) for r in cur.fetchall()]


def due_tasks(now: datetime) -> List[dict]:
    """Tasks whose reminder window is open and not fired for this occurrence.

    The window opens at `notify_time(due_at)` (due minus the lead time), so an
    advance reminder fires before the due moment. The guard is `last_notified_at
    < window start`: after a fire the stamp records the occurrence's DUE MOMENT,
    which always lies after the window start, so a restart can never re-send the
    same reminder — and the window of the next occurrence opens later still,
    because the API refuses a lead as long as the repeat period (overlapping
    windows would re-fire every tick).

    The scheduler wakes with a naive `datetime.now()`, but TIMESTAMPTZ columns
    come back timezone-aware — comparing them raw raises TypeError. A naive
    `now` is treated as UTC, which reproduces the old SQL comparison exactly
    (psycopg2 sent the naive value and Postgres cast it in the session
    timezone, UTC on this stack): the reminder fires at the wall-clock moment
    the user picked, never a tick early or late because of the machine offset.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    with _cursor() as cur:
        cur.execute(
            "SELECT id, title, notes, due_at, repeat, "
            "remind_before_value, remind_before_unit, repeat_every, repeat_unit, "
            "last_notified_at FROM tasks "
            "WHERE due_at IS NOT NULL AND done_at IS NULL ORDER BY due_at",
        )
        rows = [dict(r) for r in cur.fetchall()]
    due = []
    for row in rows:
        when = notify_time(row["due_at"], row["remind_before_value"],
                           row["remind_before_unit"])
        last = row["last_notified_at"]
        if when <= now and (last is None or last < when):
            due.append(row)
    return due


def stamp_task_notified(task_id: int, next_due: Optional[datetime]) -> None:
    """Record that a reminder fired; `next_due` advances a recurring task.

    `last_notified_at = due_at` in the UPDATE refers to the OLD due value (all
    SET expressions see the pre-update row), so the stamp always stores the
    occurrence's due moment — the value the once-per-occurrence guard compares
    against — regardless of how early the reminder fired.
    """
    with _cursor() as cur:
        if next_due is None:
            cur.execute(
                "UPDATE tasks SET last_notified_at = due_at, updated_at = now() "
                "WHERE id = %s",
                (task_id,),
            )
        else:
            cur.execute(
                "UPDATE tasks SET due_at = %s, last_notified_at = due_at, "
                "updated_at = now() WHERE id = %s",
                (next_due, task_id),
            )
