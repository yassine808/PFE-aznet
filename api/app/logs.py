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
import re
import os
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

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

# The archive tables age out on their own clocks, deliberately NOT on
# `RETENTION_DAYS`: the raw media blobs are the cheapest thing to drop (every
# audio row already has a durable Drive link, so the blob is a cache), chat
# holds the conversation history, and notifications prune *read* rows only —
# an unread alert must never be deleted under the operator. `manager_reports`
# and `report_versions` have no clock: the digest history is the one record of
# what each manager was sent, and the edit history is append-only evidence.
ARCHIVE_RETENTION_DAYS = int(os.getenv("MEDIA_RETENTION_DAYS", "30"))
CHAT_RETENTION_DAYS = int(os.getenv("CHAT_RETENTION_DAYS", "90"))
NOTIF_RETENTION_DAYS = int(os.getenv("NOTIF_RETENTION_DAYS", "30"))

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

-- Messages whose /process failed and will be retried. Distinct from
-- `failed_writes`, which holds an already-parsed report Google refused: this
-- holds a message that never became a report at all, so it carries the raw
-- input instead. Two queues, one per stage; merging them would put an audio
-- blob and a finished report in the same row.
--
-- `media_id` rather than the bytes: /process archives the blob in media_files
-- BEFORE transcribing (since 2026-08-20 — it used to archive after, so a failed
-- voice note left nothing to retry and both channels' media URLs expire within
-- the hour). One copy, referenced.
--
-- `technicien` is indexed because it is the blocking key: ordering is enforced
-- per person, so every /process asks "does this technician already have
-- something stuck?" before doing any work.
CREATE TABLE IF NOT EXISTS message_queue (
    id             BIGSERIAL PRIMARY KEY,
    correlation_id TEXT UNIQUE,
    technicien     TEXT NOT NULL,
    channel        TEXT,
    message_id     TEXT,
    kind           TEXT NOT NULL,
    text_input     TEXT,
    caption        TEXT,
    media_id       BIGINT,
    mime           TEXT,
    sent_date      TEXT,
    sent_heure     TEXT,
    attempts       INTEGER NOT NULL DEFAULT 0,
    next_try_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    status         TEXT NOT NULL DEFAULT 'queued',
    last_error     TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS message_queue_pending_idx
    ON message_queue (technicien, created_at)
    WHERE status IN ('queued', 'retrying');

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

-- Edited report versions: the manager's own drafts of a daily or weekly
-- report, one row per save, never overwritten.
--
-- Separate from `manager_reports`, which holds what the *model* produced for a
-- period and is keyed one-row-per-manager-per-period. This is the human's
-- editing history on top of that: the model writes a first draft, a manager
-- corrects a site name or softens a sentence, and both versions have to remain
-- readable — the machine's output is evidence, and silently replacing it with
-- an edit destroys the only record of what the pipeline actually said.
--
-- `image` is the illustrated summary card, embedded in the exported .docx. It
-- is stored per version because a version is meant to reproduce a document
-- exactly, and a document whose picture changed underneath it is not the
-- document that was signed off.
CREATE TABLE IF NOT EXISTS report_versions (
    id           BIGSERIAL PRIMARY KEY,
    kind         TEXT NOT NULL,               -- 'daily' | 'weekly'
    period       TEXT NOT NULL,               -- the date, or the week's first day
    version      INTEGER NOT NULL,            -- 1, 2, 3 … per (kind, period)
    objet        TEXT NOT NULL,
    corps        TEXT NOT NULL,
    image        TEXT,                        -- data: URI of the summary card
    author       TEXT NOT NULL DEFAULT 'inconnu',
    note         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (kind, period, version)
);
CREATE INDEX IF NOT EXISTS report_versions_doc_idx
    ON report_versions (kind, period, version DESC);

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

-- The Drive file id of the copy minted for the Sheet, when there is one.
--
-- This is the join the Inbox needs and had no way to make: a Sheet row carries
-- `lien_audio` and nothing else, so "play this row's voice note" could only ever
-- be answered by Drive — and a Drive share link is not a media source (see
-- app/drive.download). With the id recorded here, the share link in the Sheet
-- resolves back to the blob we already hold, and Drive becomes the fallback
-- rather than the only path.
--
-- Nullable on purpose: the Drive upload is best-effort and runs *after* the
-- archive, so a Drive outage leaves a perfectly good blob with no id. Those
-- rows are still reachable by message_id.
DO $$ BEGIN
    ALTER TABLE media_files ADD COLUMN IF NOT EXISTS drive_file_id TEXT;
END $$;
CREATE INDEX IF NOT EXISTS media_files_drive_idx ON media_files (drive_file_id)
    WHERE drive_file_id IS NOT NULL;

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

-- The conversation log: what a technician sent that never became a Sheet row,
-- and what the bot answered. The Sheet only ever holds extracted reports, so a
-- "who are you?" or a bare "ok" has no row to appear in the inbox — this is
-- that record. Written by n8n on the no_report_content branch of the workflow,
-- after the reply (reply-first ordering: recording an exchange must never cost
-- the technician their summary). `date`/`heure` are what n8n's $now said at
-- reply time, so they match the Sheet's calendar rather than the server clock
-- of whoever inserts the row later. `kind` is derived in the workflow from the
-- /process output ('text' | 'audio' | 'image').
CREATE TABLE IF NOT EXISTS exchanges (
    id             BIGSERIAL PRIMARY KEY,
    ts             TIMESTAMPTZ NOT NULL DEFAULT now(),
    date           TEXT,
    heure          TEXT,
    channel        TEXT,
    external_id    TEXT,
    message_id     TEXT,
    technicien     TEXT,
    kind           TEXT,
    text           TEXT,           -- what the technician sent (transcript for audio)
    reply          TEXT,           -- what the bot answered
    correlation_id TEXT
);
CREATE INDEX IF NOT EXISTS exchanges_ts_idx ON exchanges (ts DESC);

-- Which STT engine produced `text`, for the audio rows. The Rapports mirror
-- has carried this since the flat row existed (`STT_model`), but an exchange
-- is precisely a message that never became a Rapports row — so without this
-- column the inbox can show the engine for a filed report and not for the
-- "aucun rapport détecté" note next to it, which is the one an operator is
-- most likely to be re-reading. NULL for text and photo, which never touch STT.
DO $$ BEGIN
    ALTER TABLE exchanges ADD COLUMN IF NOT EXISTS stt_engine TEXT;
END $$;

-- The journal write mirrors a flat row to the Rapports tab; its row number is
-- recorded here by whoever performed the append (the API on the happy path,
-- the retry drain after a Sheets outage). It is the only key that ties a
-- dashboard feed row back to the message it came from, which is how
-- `GET /audio/row/{rapports_row}` finds the archived voice note to play.
-- NULL when the mirror failed. `linked_at` is when the link was recorded.
ALTER TABLE processed_messages ADD COLUMN IF NOT EXISTS linked_at TIMESTAMPTZ;
ALTER TABLE processed_messages ADD COLUMN IF NOT EXISTS rapports_row BIGINT;
-- Dropped 2026-08-15 with the /modify and /supprimer chat commands: the row
-- and tab a message became were read by nothing else, so keeping them would
-- have left two write-only columns behind.
ALTER TABLE processed_messages DROP COLUMN IF EXISTS sheet_row;
ALTER TABLE processed_messages DROP COLUMN IF EXISTS sheet_tab;

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


# One company runs several sites at once, and the director tracks each in its
# own tab. A chantier is therefore a real entity, not a string typed into a
# report: the tab a row lands in has to be decided before the row is written.
#
# `persons.chantier_id` is set on the *chef*; their technicians inherit it via
# manager_id. That is one edit to move a crew, and it reuses the org chart
# rather than adding a second place to forget to update. The chantier is then
# snapshotted onto the row, so reassigning a chef never rewrites history.
_MIGRATE_CHANTIERS = """
CREATE TABLE IF NOT EXISTS chantiers (
    id          BIGSERIAL PRIMARY KEY,
    nom         TEXT NOT NULL UNIQUE,
    client      TEXT,
    sheet_tab   TEXT NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE persons ADD COLUMN IF NOT EXISTS chantier_id BIGINT
    REFERENCES chantiers(id) ON DELETE SET NULL;

-- The bordereau (marché) per chantier. `qte_marche` is the contract quantity,
-- entered once by the director. Installed quantity is never stored here: it is
-- summed from the journal, so the two can never disagree. `champ` names the
-- journal field an article accumulates from; NULL means the article has no
-- daily counterpart (a switch, an onduleur) and is followed by hand.
CREATE TABLE IF NOT EXISTS articles (
    id           BIGSERIAL PRIMARY KEY,
    chantier_id  BIGINT NOT NULL REFERENCES chantiers(id) ON DELETE CASCADE,
    numero       INT,
    designation  TEXT NOT NULL,
    unite        TEXT NOT NULL DEFAULT 'U',
    qte_marche   NUMERIC,
    champ        TEXT,
    UNIQUE (chantier_id, designation)
);
CREATE INDEX IF NOT EXISTS articles_chantier_idx ON articles(chantier_id);

-- ACAPS groups its bordereau by task ("Aménagement L.T du 1er 2eme Etage",
-- "Recadres entre 1er et 2eme Etage") and repeats materials across groups.
-- DGH and Extralait have no such grouping, so this is nullable: a NULL tache
-- means the bordereau is a flat list, not that the task is unknown.
ALTER TABLE articles ADD COLUMN IF NOT EXISTS tache TEXT;

-- A site the pipeline created on its own, because a technician named it in a
-- voice note and it matched nothing existing. It gets a tab and works on the
-- first message (the alternative — routing it to `Non affecté` — loses the
-- site's identity), but the director confirms it afterwards in the dashboard.
-- Default true so every seeded and hand-created site stays verified: only the
-- machine-created path passes false.
ALTER TABLE chantiers ADD COLUMN IF NOT EXISTS verifie BOOLEAN NOT NULL DEFAULT true;

-- Material *received* on a site, one row per article per delivery. Deliberately
-- not the journal: a bon de livraison is not a day's work, and adding it to the
-- installed columns is what made 500 m delivered read as 500 m posed.
--
-- With this, stock stops being guessable and becomes arithmetic:
--   reste = SUM(receptions.qte) - SUM(journal installed)
-- which is why `qte` is signed — a return to the depot is a negative reception,
-- not a row someone has to remember to delete.
--
-- Never pruned. It is a ledger, the same rule `manager_reports` follows: a
-- balance computed from a partially retained history is wrong in a way nobody
-- can see. `correlation_id` ties the line back to the message that declared it,
-- so a wrong figure can always be traced to the photo it came from.
CREATE TABLE IF NOT EXISTS receptions (
    id             BIGSERIAL PRIMARY KEY,
    chantier_id    BIGINT REFERENCES chantiers(id) ON DELETE SET NULL,
    chantier       TEXT NOT NULL,
    champ          TEXT NOT NULL,
    qte            NUMERIC NOT NULL,
    date           TEXT NOT NULL,
    technicien     TEXT,
    canal          TEXT,
    correlation_id TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Articles a technician reported that no bordereau lists.
--
-- The catalogue came from three cabling bordereaux, so electricity, CCTV and
-- plumbing are barely in it: a real report listing four double sockets, nine
-- switches and two electrical panels had nowhere to put a single one of them
-- and lost forty items to prose. A new article now becomes a column on the
-- site's own tab and a row here.
--
-- Global rather than per-chantier on purpose: the column belongs to the site
-- that reported it, but the NAME is shared, so a second site reporting the
-- same thing reuses the wording instead of inventing a parallel spelling.
-- `slug` is the normalised form and the identity; `designation` is what the
-- sheet shows and what a confirmation can rewrite.
CREATE TABLE IF NOT EXISTS article_registry (
    slug        TEXT PRIMARY KEY,
    designation TEXT NOT NULL,
    unite       TEXT,
    confirmed   BOOLEAN NOT NULL DEFAULT FALSE,
    seen        INTEGER NOT NULL DEFAULT 0,
    first_seen  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per filed report, holding every figure the Sheet holds.
--
-- The Rapports tab used to be both things at once: the flat feed a human
-- reads, and the only place the daily mail, the weekly mail, the .docx tables
-- and the dashboard metrics could add a quantity up. That made it 65 columns
-- wide, most of them unreadable, and it meant every figure cost a Google read
-- on a free quota. Splitting the two jobs: the Sheet keeps what a person
-- reads, this table keeps what a machine counts.
--
-- `data` is the whole ExtractedReport as JSON rather than 35 typed columns —
-- the schema gains article fields regularly (25 arrived in one day), and a
-- table that has to be migrated for each one is a table that silently lags
-- the schema. Totals are summed in Python from this, where `NUMERIC_COLUMNS`
-- already says which keys are quantities.
--
-- `correlation_id` is UNIQUE for the same reason `receptions` keys on it: n8n
-- retries, and the drain replays parked payloads. A doubled report is the one
-- error that makes every total wrong without looking wrong.
CREATE TABLE IF NOT EXISTS report_rows (
    id             BIGSERIAL PRIMARY KEY,
    correlation_id TEXT UNIQUE,
    date           TEXT NOT NULL,
    heure          TEXT,
    technicien     TEXT,
    chantier       TEXT,
    canal          TEXT,
    role           TEXT,
    stt_engine     TEXT,
    confidence     NUMERIC,
    flag_review    BOOLEAN NOT NULL DEFAULT FALSE,
    motif_flag     TEXT,
    resume         TEXT,
    rapport_complet TEXT,
    rapports_row   INTEGER,
    -- Where the detail sits, so a message whose articles were lost to a
    -- quota outage can be filled in later rather than filed twice.
    journal_tab    TEXT,
    journal_row    INTEGER,
    data           JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE report_rows ADD COLUMN IF NOT EXISTS journal_tab TEXT;
ALTER TABLE report_rows ADD COLUMN IF NOT EXISTS journal_row INTEGER;
CREATE INDEX IF NOT EXISTS report_rows_date_idx ON report_rows (date);
CREATE INDEX IF NOT EXISTS report_rows_chantier_idx ON report_rows (chantier);

-- One row per model API call: what it cost us, and what the vendor said was
-- left. The whole project runs on free tiers and nothing measured how close any
-- of them was to its ceiling — a quota running out shows up as the chain
-- falling through to the next vendor, which looks exactly like a working day.
--
-- The quota columns are only ever filled from a response header (Groq is the
-- one vendor that sends them). Gemini leaves them NULL, and `usage.py` reports
-- its ceiling as documented rather than measured, so a NULL here can never be
-- mistaken for "the vendor said zero".
--
-- Time-series, so it is pruned with the logs and the samples.
CREATE TABLE IF NOT EXISTS api_usage (
    id                 BIGSERIAL PRIMARY KEY,
    ts                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    provider           TEXT NOT NULL,
    model              TEXT,
    kind               TEXT,
    tokens_in          INT,
    tokens_out         INT,
    limit_requests     INT,
    remaining_requests INT,
    limit_tokens       BIGINT,
    remaining_tokens   BIGINT,
    reset_requests     TEXT,
    reset_tokens       TEXT
);
CREATE INDEX IF NOT EXISTS api_usage_ts_idx ON api_usage(ts);

CREATE INDEX IF NOT EXISTS receptions_chantier_idx ON receptions(chantier, champ);
-- One delivery message must not be ledgered twice. n8n retries, the drain
-- replays a parked payload, and an operator can re-run a job: without this a
-- retried reception silently doubles the stock it reports.
CREATE UNIQUE INDEX IF NOT EXISTS receptions_once_idx
    ON receptions(correlation_id, champ) WHERE correlation_id IS NOT NULL;
"""

# Seeded from the director's own file so the first boot mirrors what he tracks
# today. Guarded on emptiness: this is a starting point, not a fixture that
# fights an operator who renames or removes a site.
_SEED_CHANTIERS = (
    ("DGH", None, "DGH"),
    ("Extralait", None, "Extralait"),
    ("ACAPS", None, "ACAPS"),
)

# DGH's bordereau, transcribed from the director's file. `champ` links an
# article to the journal field that accumulates it; the ones left None (a
# switch, an onduleur) have no daily counterpart and stay hand-followed —
# `qte_installee: null` there means "not tracked here", never "none installed".
_SEED_ARTICLES_DGH = (
    (1, "Switch fédérateur", "U", 2, "switch_federateur_u"),
    (2, "Switch d'accès", "U", 11, "switch_acces_u"),
    (3, "Modules optiques SFP+", "U", 50, "module_sfp_plus_u"),
    (4, "Modules optiques SFP", "U", 10, "module_sfp_u"),
    # Two DAC articles, one `cable_dac_u` field: a technician saying "câble DAC"
    # names neither variant, so attributing the count to either line would be a
    # guess written into a contract total. Both stay hand-followed.
    (5, "Câble DAC SFP56 to SFP56", "U", 2, None),
    (6, "Modules optiques SFP-RJ45", "U", 10, "module_sfp_rj45_u"),
    (7, "Câble DAC SFP to SFP", "U", 11, None),
    (8, "Point d'accès AP Aruba IAP 515", "U", 6, "point_acces_ap_u"),
    (9, "Tiroir optique 24", "U", 2, "tiroir_optique_24_u"),
    (10, "Tiroir optique 12", "U", 11, "tiroir_optique_12_u"),
    (11, "Câble fibre optique", "ML", 2500, "fibre_m"),
    (12, "Jarretière F.O", "U", 70, None),
    (13, "Goulotte", "ML", 800, "goulotte_m"),
    (14, "Prises RJ45 CAT.6A complète", "U", 150, "prises_connectees"),
    (15, "Câble CAT.6A", "ML", 5000, "cables_installes_m"),
    (16, "Cordons de brassage Cat6A", "U", 150, None),
    (17, "Panneau de brassage Cat6A", "U", 10, "panneaux_prises_brassees"),
    (18, "Guide de câble à balais 19''", "U", 10, "guide_cable_u"),
    (19, "Onduleur 40kva", "U", 1, "onduleur_u"),
)

# Extralait's bordereau. Flat like DGH's, so every `tache` is None. Article 13
# is the works package ("Travaux : pose du câble FO, fusions optiques…") sold as
# a lump sum: unit F, no quantity, no `champ` — there is nothing to count, and a
# 0 there would read as "no work done" rather than "not measured this way".
_SEED_ARTICLES_EXTRALAIT = (
    (1, "Coffret 12U 2S IPS", "U", 1, "coffret_12u_u"),
    (2, "Panneau de brassage 24 ports Catégorie 6 IPS", "U", 1, "panneaux_prises_brassees"),
    (3, "Prise informatique Catégorie 6 IPS", "U", 11, "prises_connectees"),
    (4, "Câble informatique Catégorie 6 IPS", "ML", 100, "cables_installes_m"),
    (5, "Cordons de brassage 1M Catégorie 6 IPS", "U", 20, "cordons_brassage_1m_u"),
    (6, "Cordons de liaison 3M Catégorie 6 IPS", "U", 21, "cordons_liaison_3m_u"),
    (7, "Flexible armé D16", "ML", 180, "flexible_arme_d16_m"),
    (8, "Câble Fibre Optique OM3 12 brins CORNING", "ML", 250, "fibre_m"),
    (9, "Tiroir optique 24 ports SC CORNING", "U", 2, "tiroir_optique_24_u"),
    (10, "Jarretières OM3 CORNING", "U", 2, "jarretiere_om3_u"),
    (11, "Switch HPE Ion 1830 24G + 2 SFP", "U", 1, "switch_acces_u"),
    (12, "Onduleur Eaton 700 VA", "U", 1, "onduleur_u"),
    (13, "Travaux (pose FO, fusions, paramétrage, tests)", "F", None, None),
)

# ACAPS is grouped by task, which is why `articles.tache` exists. Two quantities
# in the real file are blank in the Besoin column (jarretières, goulotte, borne)
# — material used but never contracted for. `qte_marche` is None there, not 0:
# "hors marché" and "zéro prévu" are different facts, and the bordereau view
# must not display a 100% overrun for an article nobody ever budgeted.
_ACAPS_LT = "Aménagement L.T du 1er et 2ème étage"
_ACAPS_RECADRE = "Recadres entre 1er et 2ème étage"
_SEED_ARTICLES_ACAPS = (
    (1, "Cordons 1m cat 6A", "U", 144, "cordons_brassage_1m_u", _ACAPS_LT),
    (2, "Cordons 3m cat 6A", "U", 10, "cordons_liaison_3m_u", _ACAPS_LT),
    (3, "Cable Elec 3x2,5", "ML", 15, "cable_elec_3x2_5_m", _ACAPS_LT),
    (4, "Fiche F 2P+T", "U", 2, "fiche_2p_t_u", _ACAPS_LT),
    (5, "Disjoncteur 2x16A", "U", 2, "disjoncteur_2x16a_u", _ACAPS_LT),
    (6, "Bandeau Elec 12P", "U", 2, "bandeau_elec_12p_u", _ACAPS_LT),
    (7, "Passe Cable", "U", 2, "passe_cable_u", _ACAPS_LT),
    (8, "Jarretier SC/LC", "U", None, "jarretiere_sc_lc_u", _ACAPS_LT),
    (9, "Jarretière LC/LC", "U", None, "jarretiere_lc_lc_u", _ACAPS_LT),
    (10, "Goulotte 100*45", "ML", None, "goulotte_m", _ACAPS_LT),
    (11, "Borne 2,5", "U", None, "borne_2_5_u", _ACAPS_LT),
    (12, "FO 12 Brins MM", "ML", 60, "fibre_m", _ACAPS_RECADRE),
    (13, "Tiroir Optique 24P", "U", 2, "tiroir_optique_24_u", _ACAPS_RECADRE),
    (14, "Pigtail SC", "U", 48, "pigtail_sc_u", _ACAPS_RECADRE),
    (15, "Fusion", "U", 48, "connexions_optiques_brins", _ACAPS_RECADRE),
    (16, "Cable UTP", "ML", 720, "cables_installes_m", _ACAPS_RECADRE),
    (17, "Panneau Brassage Modulaire pleine cat 6A", "U", 2,
     "panneaux_prises_brassees", _ACAPS_RECADRE),
)

# Which seed belongs to which site, so the loop below has no site-specific
# branch. DGH and Extralait rows carry no `tache`, padded here rather than in
# every literal above.
_SEEDS_BY_CHANTIER = {
    "DGH": tuple(row + (None,) for row in _SEED_ARTICLES_DGH),
    "Extralait": tuple(row + (None,) for row in _SEED_ARTICLES_EXTRALAIT),
    "ACAPS": _SEED_ARTICLES_ACAPS,
}


def init_schema() -> None:
    """Create tables/indexes if absent, then migrate. Called once at API startup."""
    with _cursor() as cur:
        cur.execute(_SCHEMA)
        cur.execute(_MIGRATE_PERSONS)
        cur.execute(_MIGRATE_ACCOUNTS)
        cur.execute(_MIGRATE_CHANTIERS)
        cur.execute("SELECT COUNT(*) AS n FROM chantiers")
        existing = _one(cur) or {"n": 0}
        if existing["n"] == 0:
            cur.executemany(
                "INSERT INTO chantiers (nom, client, sheet_tab) VALUES (%s, %s, %s)",
                _SEED_CHANTIERS,
            )
        # Articles are seeded outside the chantiers-empty guard above: on a box
        # that already ran the first version, `chantiers` is non-empty and the
        # Extralait and ACAPS bordereaux would never arrive. The guard is per
        # chantier and per emptiness instead — a site that already has articles
        # is left alone, so deleting one by hand does not resurrect it on the
        # next restart.
        for nom, rows in _SEEDS_BY_CHANTIER.items():
            cur.execute("SELECT id FROM chantiers WHERE nom = %s", (nom,))
            chantier = _one(cur)
            if chantier is not None:
                cur.execute(
                    "SELECT COUNT(*) AS n FROM articles WHERE chantier_id = %s",
                    (chantier["id"],),
                )
                if (_one(cur) or {"n": 1})["n"] == 0:
                    cur.executemany(
                        """
                        INSERT INTO articles
                            (chantier_id, numero, designation, unite, qte_marche, champ, tache)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (chantier_id, designation) DO NOTHING
                        """,
                        [(chantier["id"],) + row for row in rows],
                    )


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


def last_job_runs() -> Dict[str, datetime]:
    """When each scheduled job last ran, across process restarts.

    `jobs._record` already writes one `job:<name>` row per run through
    `write_safe`, so the history is durable — it simply was never read back. The
    scheduler needs it: seeding its in-memory `last_run` from process start made
    a morning restart cancel that day's report, and seeding from `None` made an
    evening restart send it twice.
    """
    with _cursor() as cur:
        cur.execute(
            """
            SELECT stage, max(ts) AS ts
              FROM pipeline_logs
             WHERE stage LIKE 'job:%%'
             GROUP BY stage
            """
        )
        rows = cur.fetchall()
    out: Dict[str, datetime] = {}
    for row in rows:
        item = dict(row)
        ts = item.get("ts")
        if isinstance(ts, datetime):
            # Naive local time: the scheduler compares against datetime.now().
            out[str(item["stage"])[len("job:"):]] = ts.astimezone().replace(tzinfo=None)
    return out


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


def in_flight(max_age_minutes: int = 15) -> List[dict]:
    """Messages that arrived and have not been answered yet.

    Derived, not stored: n8n already logs `received` when a message lands and
    `replied` when the technician gets their summary, both under the same
    correlation_id, and the API logs its own failures under that id too. A
    correlation with a `received` row and no terminal row is therefore a
    message still in the pipeline — which is what the inbox shows a ⏳ for.

    A second table would have to be cleaned up after every crash; these rows
    already exist and age out on their own. `max_age_minutes` is that ageing:
    a run that died without ever logging an outcome must stop being "in
    progress" eventually, and the slowest real path (a cold local STT load)
    is ~4 minutes, so 15 is generous without being permanent.
    """
    with _cursor() as cur:
        cur.execute(
            """
            SELECT r.correlation_id, r.technicien, r.channel,
                   MIN(r.ts) AS since
              FROM pipeline_logs r
             WHERE r.stage = 'received'
               AND r.ts > now() - (%s || ' minutes')::interval
               AND NOT EXISTS (
                     SELECT 1 FROM pipeline_logs d
                      WHERE d.correlation_id = r.correlation_id
                        AND (d.stage = 'replied' OR d.level = 'error')
                   )
             GROUP BY r.correlation_id, r.technicien, r.channel
             ORDER BY since
            """,
            (max(1, min(max_age_minutes, 240)),),
        )
        rows = [dict(r) for r in cur.fetchall()]
    for row in rows:
        if isinstance(row.get("since"), datetime):
            row["since"] = row["since"].isoformat()
    return rows


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


def save_exchange(
    date: Optional[str],
    heure: Optional[str],
    channel: Optional[str],
    external_id: Optional[str],
    message_id: Optional[str],
    technicien: Optional[str],
    kind: str,
    text: Optional[str],
    reply: Optional[str],
    correlation_id: Optional[str],
    stt_engine: Optional[str] = None,
) -> int:
    """One exchange that never became a Sheet row (message + the reply the
    technician actually got). Written by n8n, best-effort, after the reply."""
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO exchanges
                (date, heure, channel, external_id, message_id, technicien, kind, text, reply, correlation_id, stt_engine)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (date, heure, channel, external_id, message_id, technicien, kind, text, reply,
             correlation_id, stt_engine),
        )
        return (_one(cur) or {})["id"]


def update_exchange_text(exchange_id: int, text: str) -> Optional[dict]:
    """Correct the transcript of a logged exchange.

    Returns `{"before": <old text>}`, or None when there is no such exchange —
    a dict rather than the string itself, because an exchange whose text was
    NULL is a real row and must not read as "not found".

    The old value comes back so the caller can record `before`/`after`: the
    column is overwritten, not versioned, and this is the only moment the
    previous transcript still exists. A per-message version table for a fixed
    spelling would be a second store to prune and to reason about; the audit
    trail already answers "what did it say before, and who changed it".
    """
    with _cursor() as cur:
        cur.execute("SELECT text FROM exchanges WHERE id = %s", (exchange_id,))
        row = _one(cur)
        if row is None:
            return None
        cur.execute("UPDATE exchanges SET text = %s WHERE id = %s", (text, exchange_id))
        return {"before": row["text"]}


def list_exchanges(limit: int = 200) -> List[dict]:
    """Conversation log, newest first. Each row carries the archived media id
    (audio/image) when that message had one, so the inbox can play a voice note
    that never became a Sheet row."""
    with _cursor() as cur:
        cur.execute(
            """
            SELECT e.id, e.ts, e.date, e.heure, e.channel, e.external_id, e.message_id,
                   e.technicien, e.kind, e.text, e.reply, e.correlation_id, e.stt_engine,
                   (SELECT m.id FROM media_files m
                     WHERE m.message_id = e.message_id AND m.kind = e.kind
                     ORDER BY m.created_at DESC LIMIT 1) AS media_id
            FROM exchanges e
            ORDER BY e.ts DESC
            LIMIT %s
            """,
            (max(1, min(limit, 500)),),
        )
        rows = [_iso(dict(r)) for r in cur.fetchall()]
    return rows


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


def link_media_drive(media_id: int, drive_file_id: str) -> None:
    """Record which Drive copy a stored blob was published as.

    Called after the upload, because the id does not exist before it. Failing
    here costs the fast playback path, never the archive.
    """
    with _cursor() as cur:
        cur.execute(
            "UPDATE media_files SET drive_file_id = %s WHERE id = %s",
            (drive_file_id, media_id),
        )


def find_media_by_drive_id(drive_file_id: str) -> Optional[dict]:
    """The archived blob behind a Sheet row's `lien_audio`, if we still hold it.

    `created_at DESC` because the same file could in principle be uploaded
    twice; the newest row is the one the current Sheet link points at.
    """
    with _cursor() as cur:
        cur.execute(
            "SELECT * FROM media_files WHERE drive_file_id = %s "
            "ORDER BY created_at DESC LIMIT 1",
            (drive_file_id,),
        )
        row = _one(cur)
    if row is None:
        return None
    out = _iso(dict(row))
    out["data"] = bytes(out["data"])
    return out


def find_media_by_rapports_row(rapports_row: int, kind: str = "audio") -> Optional[dict]:
    """The archived blob behind a row of the Rapports tab.

    The other half of playback, for the rows `find_media_by_drive_id` cannot
    answer: the Drive upload is best-effort, so a Drive outage leaves a Sheet
    row with no `lien_audio` at all — and the voice note is sitting in
    `media_files` the whole time with no way to ask for it.

    `processed_messages` already records which Sheet row a message produced
    (that is what `/modify` navigates by), and `media_files` records the
    message a blob arrived with, so the two join on `message_id` and no new
    bookkeeping is needed. Newest first, because a message that was re-processed
    has more than one blob and the current row reflects the last run.
    """
    with _cursor() as cur:
        cur.execute(
            """
            SELECT m.* FROM media_files m
            JOIN processed_messages p ON p.message_id = m.message_id
            WHERE p.rapports_row = %s AND m.kind = %s
            ORDER BY m.created_at DESC LIMIT 1
            """,
            (rapports_row, kind),
        )
        row = _one(cur)
    if row is None:
        return None
    out = _iso(dict(row))
    out["data"] = bytes(out["data"])
    return out


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


# ── message → Rapports mirror row link ─────────────────────────────────────
# The dashboard plays a message's voice note from `GET /audio/row/{row}`, and
# the only thing tying a Rapports feed row back to the message that produced it
# is this link. Written by whoever performed the write: the API after a journal
# write, the retry drain after a Sheets outage.

def link_message_row(message_id: str, rapports_row: Optional[int]) -> bool:
    """Remember which Rapports row a processed message mirrored to.

    Upsert-free by design: the row already exists (the claim inserted it), so
    this is an UPDATE. None when the mirror failed — the journal row is still
    written, there is simply nothing on the flat feed to point audio at.
    """
    with _cursor() as cur:
        cur.execute(
            "UPDATE processed_messages SET rapports_row = %s, linked_at = now() "
            "WHERE message_id = %s",
            (rapports_row, message_id),
        )
        return cur.rowcount > 0


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


# ── Message retry queue ─────────────────────────────────────────────────────
# Six attempts over roughly forty minutes, then the message is abandoned and the
# technician is told. The cap exists for the same reason MAX_WRITE_ATTEMPTS
# does, and it bites harder here: ordering is enforced per technician, so a
# message that can never succeed would otherwise block every later report from
# that person forever. Giving up is what releases them.
MAX_MESSAGE_ATTEMPTS = 6
#: Seconds to wait before attempt N+1. Front-loaded — most /process failures are
#: a vendor hiccup that is over in seconds — then flat, because anything still
#: failing at ten minutes is an outage and polling it faster changes nothing.
RETRY_BACKOFF_S = (30, 120, 300, 600, 600, 600)


def backoff_for(attempts: int) -> int:
    return RETRY_BACKOFF_S[min(attempts, len(RETRY_BACKOFF_S) - 1)]


def blocked_technician(technicien: Optional[str]) -> Optional[dict]:
    """The oldest unresolved queued message for this technician, if any.

    The gate for ordering. A new message arriving while one is stuck must join
    the queue behind it, or it overtakes the message it followed and the journal
    records the day out of order — which is the whole point of the queue.
    Unknown sender (no name) is never blocked: there is nothing to order.
    """
    if not technicien:
        return None
    with _cursor() as cur:
        cur.execute(
            """SELECT id, correlation_id, attempts, status FROM message_queue
               WHERE technicien = %s AND status IN ('queued','retrying')
               ORDER BY created_at ASC LIMIT 1""",
            (technicien,),
        )
        row = cur.fetchone()
    return dict(cast(dict, row)) if row else None


def enqueue_message(item: Dict[str, Any]) -> Optional[int]:
    """Park a message for retry. Idempotent on correlation_id.

    ON CONFLICT DO NOTHING rather than an upsert: n8n retries its HTTP call and
    the drain replays, so the same message arrives more than once — and a second
    row would be a second place the queue thinks work is pending, which both
    blocks the technician twice and files the report twice when it drains.
    """
    fields = ("correlation_id", "technicien", "channel", "message_id", "kind",
              "text_input", "caption", "media_id", "mime", "sent_date", "sent_heure")
    cols = ", ".join(fields)
    holders = ", ".join(f"%({f})s" for f in fields)
    with _cursor() as cur:
        cur.execute(
            f"""INSERT INTO message_queue ({cols}, next_try_at)
                VALUES ({holders}, now() + make_interval(secs => %(delay)s))
                ON CONFLICT (correlation_id) DO NOTHING
                RETURNING id""",
            {**{f: item.get(f) for f in fields}, "delay": backoff_for(0)},
        )
        row = cur.fetchone()
    return cast(dict, row)["id"] if row else None


def due_messages(limit: int = 10) -> List[dict]:
    """Messages ready for another attempt, oldest first, one per technician.

    One per technician is the ordering rule expressed as a query: taking two
    from the same person in one pass would run them concurrently and let the
    later one win the race. DISTINCT ON picks each person's oldest.
    """
    with _cursor() as cur:
        cur.execute(
            """SELECT DISTINCT ON (technicien) *
               FROM message_queue
               WHERE status IN ('queued','retrying') AND next_try_at <= now()
               ORDER BY technicien, created_at ASC
               LIMIT %s""",
            (max(1, min(limit, 50)),),
        )
        rows = [dict(cast(dict, r)) for r in cur.fetchall()]
    rows.sort(key=lambda r: r["created_at"])
    for r in rows:
        for k in ("created_at", "next_try_at"):
            if isinstance(r.get(k), datetime):
                r[k] = r[k].isoformat()
    return rows


def resolve_message(queue_id: int, ok: bool, error: Optional[str] = None,
                    count_attempt: bool = True) -> str:
    """Close, reschedule or abandon one queued message. Returns the new status.

    `count_attempt=False` is the quota case, the same rule `resolve_write`
    follows: a vendor refusing everyone is not this message's fault, and burning
    six attempts on a rate-limit window abandons a report that was never
    malformed and would have succeeded ten minutes later.

    Read-then-write rather than one clever UPDATE: the next delay depends on the
    incremented attempt count, and SQL cannot read a column it is setting in the
    same statement. Two plain statements beat three that hide the arithmetic.
    """
    if ok:
        with _cursor() as cur:
            cur.execute("DELETE FROM message_queue WHERE id = %s", (queue_id,))
        return "done"
    with _cursor() as cur:
        cur.execute("SELECT attempts, status FROM message_queue WHERE id = %s", (queue_id,))
        row = cur.fetchone()
        if not row:
            return "gone"
        attempts = cast(dict, row)["attempts"] + (1 if count_attempt else 0)
        status = "abandoned" if attempts >= MAX_MESSAGE_ATTEMPTS else "retrying"
        if not count_attempt:
            # A quota refusal buys the row a fresh wait and nothing else: not an
            # attempt, and never a promotion to 'abandoned'.
            status = cast(dict, row).get("status") or "queued"
        cur.execute(
            """UPDATE message_queue
               SET attempts = %s, last_error = %s, status = %s,
                   next_try_at = now() + make_interval(secs => %s)
               WHERE id = %s""",
            (attempts, (error or "")[:2000], status, backoff_for(attempts), queue_id),
        )
    return status


def list_message_queue(limit: int = 50) -> List[dict]:
    """The queue as the dashboard shows it — abandoned rows included.

    Same rule as `pending_writes(include_retired=True)`: a message that stopped
    being retried is precisely the one an operator has to act on, and hiding it
    is how a lost report looks like an empty queue.
    """
    with _cursor() as cur:
        cur.execute(
            """SELECT id, correlation_id, technicien, channel, kind, attempts,
                      status, last_error, sent_date, sent_heure, media_id,
                      next_try_at, created_at
               FROM message_queue ORDER BY created_at ASC LIMIT %s""",
            (max(1, min(limit, 200)),),
        )
        rows = [dict(cast(dict, r)) for r in cur.fetchall()]
    for r in rows:
        for k in ("created_at", "next_try_at"):
            if isinstance(r.get(k), datetime):
                r[k] = r[k].isoformat()
    return rows


def pending_writes(limit: int = 20, include_retired: bool = False) -> List[dict]:
    """Drainable queue rows.

    The attempts cap matters: without it a permanently malformed payload is
    retried every 5 minutes forever AND, being the oldest row, permanently
    occupies the head of the window — starving newer recoverable reports.
    Rows past the cap stay in the table for inspection but stop being retried.

    `include_retired=True` lifts that filter for the dashboard: a row that
    stopped being retried is exactly the one an operator has to see, and the
    drain's own view must stay the filtered one.
    """
    sql = "SELECT * FROM failed_writes {} ORDER BY created_at ASC LIMIT %s".format(
        "" if include_retired else "WHERE attempts < %s"
    )
    args: tuple = ((max(1, min(limit, 100)),) if include_retired
                   else (MAX_WRITE_ATTEMPTS, max(1, min(limit, 100))))
    with _cursor() as cur:
        cur.execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].isoformat()
        # The state a human reads, derived rather than stored: a second column
        # holding what `attempts` already says is a column that can disagree
        # with it.
        attempts = r.get("attempts") or 0
        r["status"] = ("queued" if attempts == 0
                       else "retrying" if attempts < MAX_WRITE_ATTEMPTS
                       else "abandoned")
    return rows


def resolve_write(write_id: int, ok: bool, error: Optional[str] = None,
                  retry: bool = True, count_attempt: bool = True) -> None:
    """Drop the row on success, otherwise bump attempts so the cron can back off.

    `retry=False` retires the row instead of counting one more attempt: a
    payload the schema cannot parse will never parse, and `pending_writes`
    orders oldest-first, so counting attempts left it at the head of every
    batch for ten more drains — the starvation `MAX_WRITE_ATTEMPTS` exists to
    prevent, delayed rather than avoided. The row stays in the table with its
    error, so the dashboard still shows what was dropped and why.

    `count_attempt=False` records the error without spending an attempt: a
    Sheets quota refusal is not the row's fault, and burning ten of them on a
    minute-long rate limit retires a payload that was never malformed.
    """
    with _cursor() as cur:
        if ok:
            cur.execute("DELETE FROM failed_writes WHERE id = %s", (write_id,))
        elif retry and count_attempt:
            cur.execute(
                "UPDATE failed_writes SET attempts = attempts + 1, last_error = %s WHERE id = %s",
                (error, write_id),
            )
        elif retry:
            cur.execute(
                "UPDATE failed_writes SET last_error = %s WHERE id = %s",
                (error, write_id),
            )
        else:
            cur.execute(
                "UPDATE failed_writes SET attempts = %s, last_error = %s WHERE id = %s",
                (MAX_WRITE_ATTEMPTS, error, write_id),
            )


# ── Report versions ────────────────────────────────────────────────────────
# The manager's editing history for one daily or weekly report. Append-only:
# there is no update and no delete, because the point of the table is that an
# earlier wording can always be recovered.

def list_report_versions(kind: str, period: str, with_body: bool = True) -> List[dict]:
    """Every saved version for one report, newest first.

    `with_body=False` returns the index alone — id, version, author, timestamp.
    A version list beside an editor is opened far more often than any single old
    version is read, and shipping every stored body (plus its embedded image) to
    draw a list of dates is how a small feature becomes a slow page.
    """
    columns = (
        "id, kind, period, version, objet, corps, image, author, note, created_at"
        if with_body
        else "id, kind, period, version, objet, author, note, created_at"
    )
    with _cursor() as cur:
        cur.execute(
            "SELECT {} FROM report_versions WHERE kind = %s AND period = %s "
            "ORDER BY version DESC".format(columns),
            (kind, period),
        )
        return [_iso(dict(r)) for r in cur.fetchall()]


def save_report_version(
    kind: str,
    period: str,
    objet: str,
    corps: str,
    image: Optional[str] = None,
    author: str = "inconnu",
    note: Optional[str] = None,
) -> dict:
    """Append one version, numbering it from whatever is already stored.

    The number is computed inside the INSERT rather than read first and written
    second: two managers saving the same report at the same moment would both
    read version 3 and both try to write 4, and the loser would take a unique
    violation rather than simply becoming version 5. The sub-select plus the
    UNIQUE constraint make the race a retryable error at worst, never a
    silently lost edit.
    """
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO report_versions (kind, period, version, objet, corps, image, author, note)
            VALUES (
                %s, %s,
                (SELECT COALESCE(MAX(version), 0) + 1 FROM report_versions WHERE kind = %s AND period = %s),
                %s, %s, %s, %s, %s
            )
            RETURNING id, kind, period, version, objet, corps, image, author, note, created_at
            """,
            (kind, period, kind, period, objet, corps, image, author, note),
        )
        return _iso(dict(_one(cur) or {}))


# ── Technician directory ───────────────────────────────────────────────────
# The dashboard writes it; the reception workflow reads it to decide whether a
# sender is known. Kept deliberately small: identity and role, no PII beyond
# the channel handle the technician already sends from.

CHANNELS = ("telegram", "whatsapp")


def _iso(row: dict) -> dict:
    """Row values turned into things JSON can carry without lying about them.

    `Decimal` is the one that bites: psycopg2 hands back every NUMERIC column
    (`articles.qte_marche`, `receptions.qte`) as a `Decimal`, and FastAPI
    serialises that as a *string* — so `qte_marche: 144` left here and arrived
    in the browser as `"144"`. The dashboard's own type said `number`, so
    nothing typechecked it, and the Chantiers page called `.toFixed()` on a
    string the moment a site was opened: a TypeError during render, no error
    boundary above it, and the whole app unmounted to a blank page. Unwrapped
    here rather than in each endpoint because this is the one place every row
    leaves the store through.
    """
    for key, value in row.items():
        if isinstance(value, datetime):
            row[key] = value.isoformat()
        elif isinstance(value, Decimal):
            # int when it is one, so a count of switches is not `2.0`.
            row[key] = int(value) if value == value.to_integral_value() else float(value)
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
            SELECT p.id, p.name, p.role, p.manager_id, p.email, p.active,
                   p.last_seen_at, p.profile, p.profile_updated_at, p.created_at,
                   (p.password_hash IS NOT NULL) AS has_login,
                   p.chantier_id, c.nom AS chantier,
                   -- what their reports actually route to, own site or chef's
                   COALESCE(c.nom, mc.nom) AS chantier_effectif
              FROM persons p
              LEFT JOIN persons m    ON m.id = p.manager_id
              LEFT JOIN chantiers c  ON c.id = p.chantier_id
              LEFT JOIN chantiers mc ON mc.id = m.chantier_id
             ORDER BY p.name
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


def list_chantiers(active_only: bool = False) -> List[dict]:
    with _cursor() as cur:
        cur.execute(
            "SELECT * FROM chantiers %s ORDER BY nom"
            % ("WHERE active" if active_only else "")
        )
        return [_iso(dict(r)) for r in cur.fetchall()]


def create_chantier(nom: str, sheet_tab: Optional[str] = None,
                    client: Optional[str] = None, verifie: bool = True) -> dict:
    """Add a site. The tab defaults to the name — that is what the director's
    own file does, and a tab named after something else is a tab nobody finds.

    `verifie=False` is the machine path: a name heard in a voice note that
    matched nothing. It is written, not dropped, and flagged for the director.
    The UPDATE branch never *lowers* an existing site's verified state — a
    confirmed site re-heard on a voice note must not become unverified again.
    """
    nom = nom.strip()
    if not nom:
        raise LogStoreError("nom is required")
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO chantiers (nom, client, sheet_tab, verifie)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (nom) DO UPDATE
               SET client = EXCLUDED.client,
                   verifie = chantiers.verifie OR EXCLUDED.verifie
            RETURNING *
            """,
            (nom, (client or None), (sheet_tab or nom).strip(), verifie),
        )
        return _iso(dict(_one(cur) or {}))


def normalize_site_name(name: str) -> str:
    """A spoken site name reduced to what two spellings of it have in common.

    Accents, case, punctuation, spacing and a leading article are all things
    STT gets wrong (or right in a different way) on the same site, so "la DGH",
    "d.g.h", " dgh " and "DGH" must all reduce to `dgh`. Spacing is removed
    last and completely, which is what makes the dotted form match.

    Deliberately NOT fuzzy: no edit distance, no prefix matching. "ACAPS" and
    "ACAPS 2" stay two sites, because collapsing two real sites into one is a
    silent wrong row, while failing to match creates a visible unverified one.
    """
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = "".join(c if c.isalnum() else " " for c in text)
    words = text.split()
    # Only *leading* articles: "de"/"du" are not dropped, because they can
    # carry the name itself ("de la ferme" is not "la ferme").
    while words and words[0] in {"la", "le", "les", "l", "the", "chantier", "site"}:
        words.pop(0)
    return "".join(words)


def find_chantier_by_name(nom: str) -> Optional[dict]:
    """The existing site a spoken name refers to, or None.

    Matching happens in Python over the whole (tiny) table rather than in SQL:
    the normalization above is the contract, and duplicating it as a Postgres
    expression is how the two would drift apart.
    """
    key = normalize_site_name(nom)
    if not key:
        return None
    for chantier in list_chantiers():
        if normalize_site_name(chantier.get("nom", "")) == key:
            return chantier
    return None


def verify_chantier(chantier_id: int) -> bool:
    """Confirm a site the pipeline created from a spoken name.

    One-way on purpose: un-verifying an existing site would say the record is
    wrong without saying what is right. A site that should not exist is deleted,
    not demoted.
    """
    with _cursor() as cur:
        cur.execute(
            "UPDATE chantiers SET verifie = true WHERE id = %s", (chantier_id,)
        )
        return cur.rowcount > 0


def delete_chantier(chantier_id: int) -> bool:
    with _cursor() as cur:
        cur.execute("DELETE FROM chantiers WHERE id = %s", (chantier_id,))
        return cur.rowcount > 0


def set_chantier(person_id: int, chantier_id: Optional[int]) -> bool:
    """Assign a site to a person — in practice, to a chef.

    Their technicians inherit it through manager_id, so this is the single edit
    that moves a whole crew. Setting it on a technician is allowed and wins over
    the chef's, which covers the one tech lent to another site without forcing a
    reorganisation of the chart.
    """
    with _cursor() as cur:
        cur.execute(
            "UPDATE persons SET chantier_id = %s WHERE id = %s",
            (chantier_id, person_id),
        )
        return cur.rowcount > 0


def resolve_chantier(person_id: int) -> Optional[dict]:
    """The site a person's reports belong to: their own, else their chef's.

    Returns None when neither is set — deliberately, rather than guessing a
    default site. A row filed to the wrong chantier is worse than a row the
    dashboard shows as unrouted.
    """
    with _cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(c.id, mc.id)               AS id,
                   COALESCE(c.nom, mc.nom)             AS nom,
                   COALESCE(c.sheet_tab, mc.sheet_tab) AS sheet_tab
              FROM persons p
              LEFT JOIN persons m    ON m.id = p.manager_id
              LEFT JOIN chantiers c  ON c.id = p.chantier_id
              LEFT JOIN chantiers mc ON mc.id = m.chantier_id
             WHERE p.id = %s
            """,
            (person_id,),
        )
        row = _one(cur)
    if row is None or row["id"] is None:
        return None
    return dict(row)


def record_usage(provider: str, model: Optional[str] = None, kind: Optional[str] = None,
                 **fields) -> None:
    """One API call. Called on every model request, so it must stay cheap."""
    cols = ("tokens_in", "tokens_out", "limit_requests", "remaining_requests",
            "limit_tokens", "remaining_tokens", "reset_requests", "reset_tokens")
    with _cursor() as cur:
        cur.execute(
            f"INSERT INTO api_usage (provider, model, kind, {', '.join(cols)}) "
            f"VALUES (%s, %s, %s, {', '.join(['%s'] * len(cols))})",
            (provider, model, kind, *(fields.get(c) for c in cols)),
        )


def usage_since(since) -> List[dict]:
    """Calls and tokens per (provider, model) over a window."""
    with _cursor() as cur:
        cur.execute(
            """
            SELECT provider, model, COUNT(*) AS calls,
                   COALESCE(SUM(COALESCE(tokens_in,0) + COALESCE(tokens_out,0)), 0) AS tokens
            FROM api_usage WHERE ts >= %s GROUP BY provider, model
            """,
            (since,),
        )
        return [dict(r) for r in cur.fetchall()]


def latest_usage_quota() -> Dict[str, dict]:
    """The most recent row per provider that actually carried a quota header.

    `WHERE limit_requests IS NOT NULL` on purpose: a provider that sends no
    headers must come back absent, so the caller reports a documented ceiling
    instead of presenting a NULL as though the vendor had answered.
    """
    with _cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (provider) provider, ts, limit_requests, remaining_requests,
                   limit_tokens, remaining_tokens, reset_requests, reset_tokens
            FROM api_usage WHERE limit_requests IS NOT NULL
            ORDER BY provider, ts DESC
            """
        )
        return {r["provider"]: _iso(dict(r)) for r in cur.fetchall()}


def whatsapp_sent_since(since) -> int:
    """Our own WhatsApp message count — Meta gives the ceiling, not the usage."""
    with _cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM pipeline_logs WHERE ts >= %s AND channel = 'whatsapp'",
            (since,),
        )
        return int((_one(cur) or {"n": 0})["n"])


def record_receptions(chantier: str, champs: Dict[str, float], date: str,
                      technicien: Optional[str] = None, canal: Optional[str] = None,
                      correlation_id: Optional[str] = None,
                      chantier_id: Optional[int] = None) -> int:
    """Ledger one delivery. Returns how many lines were newly recorded.

    `ON CONFLICT DO NOTHING` against the per-message unique index: replaying the
    same message — an n8n retry, a drained parked payload, an operator re-run —
    must leave the balance where it was. A silently doubled reception is the one
    error that makes every stock figure downstream wrong without looking wrong.
    """
    if not champs:
        return 0
    with _cursor() as cur:
        cur.executemany(
            """
            INSERT INTO receptions
                (chantier_id, chantier, champ, qte, date, technicien, canal, correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            [
                (chantier_id, chantier, champ, qte, date, technicien, canal, correlation_id)
                for champ, qte in champs.items()
            ],
        )
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0


def list_receptions(chantier: Optional[str] = None) -> List[dict]:
    """The ledger, newest first — one site's or every site's."""
    with _cursor() as cur:
        if chantier:
            cur.execute(
                "SELECT * FROM receptions WHERE chantier = %s ORDER BY date DESC, id DESC",
                (chantier,),
            )
        else:
            cur.execute("SELECT * FROM receptions ORDER BY date DESC, id DESC")
        return [_iso(dict(r)) for r in cur.fetchall()]


def received_totals(chantier: str) -> Dict[str, float]:
    """Total received per article on one site — half of `reçu − posé`.

    Summed on read like the bordereau's `qte_installee`: the ledger is where a
    reception is entered, so a stored total could only drift from it.
    """
    with _cursor() as cur:
        cur.execute(
            "SELECT champ, SUM(qte) AS total FROM receptions WHERE chantier = %s GROUP BY champ",
            (chantier,),
        )
        return {r["champ"]: float(r["total"]) for r in cur.fetchall()}


def list_articles(chantier_id: int) -> List[dict]:
    with _cursor() as cur:
        cur.execute(
            "SELECT * FROM articles WHERE chantier_id = %s ORDER BY numero NULLS LAST, designation",
            (chantier_id,),
        )
        return [_iso(dict(r)) for r in cur.fetchall()]


def upsert_article(chantier_id: int, designation: str, unite: str = "U",
                   qte_marche: Optional[float] = None, numero: Optional[int] = None,
                   champ: Optional[str] = None) -> dict:
    designation = designation.strip()
    if not designation:
        raise LogStoreError("designation is required")
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO articles (chantier_id, numero, designation, unite, qte_marche, champ)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (chantier_id, designation) DO UPDATE
               SET numero = EXCLUDED.numero, unite = EXCLUDED.unite,
                   qte_marche = EXCLUDED.qte_marche, champ = EXCLUDED.champ
            RETURNING *
            """,
            (chantier_id, numero, designation, unite.strip() or "U", qte_marche, champ),
        )
        return _iso(dict(_one(cur) or {}))


def delete_bordereau_article(article_id: int) -> bool:
    """Remove one contract line from a site's bordereau.

    Renamed 2026-08-19. It was `delete_article`, and so was the free-article
    reject added the same day — the second definition silently shadowed this
    one, so every call reached the wrong function with the wrong argument type.
    Two things called "article" in this codebase and they are not the same
    thing: a bordereau line is a contract commitment with a quantity, a free
    article is a name a technician used that no bordereau lists.
    """
    with _cursor() as cur:
        cur.execute("DELETE FROM articles WHERE id = %s", (article_id,))
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

    The resolved chantier rides along: this lookup already happens on every
    message, and the routing rule is one COALESCE (own site, else the chef's).
    Fetching it here means the tab is known before the row is built, so the
    reply to the technician can name the site it was filed to.
    """
    external_id = normalize_external_id(channel, external_id)
    with _cursor() as cur:
        cur.execute(
            """
            SELECT p.id AS person_id, p.name, p.role, p.profile,
                   t.id, t.channel, t.external_id, t.active,
                   COALESCE(p.chantier_id, m.chantier_id) AS chantier_id,
                   COALESCE(c.nom, mc.nom)                AS chantier,
                   COALESCE(c.sheet_tab, mc.sheet_tab)    AS sheet_tab
              FROM technicians t
              JOIN persons p       ON p.id = t.person_id
              LEFT JOIN persons m  ON m.id = p.manager_id
              LEFT JOIN chantiers c  ON c.id = p.chantier_id
              LEFT JOIN chantiers mc ON mc.id = m.chantier_id
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
    """Both per-call time series: uptime samples and API usage.

    `api_usage` gets a row on every model call, so it grows faster than anything
    else here. It is only ever read over a 24-hour window and for the latest
    quota header, so nothing is lost by pruning it on the same clock.
    """
    with _cursor() as cur:
        cur.execute("DELETE FROM service_samples WHERE ts < now() - (%s * interval '1 day')", (days,))
        deleted = cur.rowcount
        cur.execute("DELETE FROM api_usage WHERE ts < now() - (%s * interval '1 day')", (days,))
        return deleted + max(0, cur.rowcount)


def prune_meta(days: int = RETENTION_DAYS) -> dict:
    """Retention sweep for the tables that would otherwise grow forever: expired
    sessions, idempotency claims, the audit trail and page visits — plus the
    archive tables on their own clocks (see the constants at module top):
    `media_files` blobs, `chat_messages`, `exchanges` and read `notifications`.

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
        cur.execute(
            "DELETE FROM media_files WHERE created_at < now() - (%s * interval '1 day')",
            (ARCHIVE_RETENTION_DAYS,),
        )
        media = cur.rowcount
        cur.execute(
            "DELETE FROM chat_messages WHERE created_at < now() - (%s * interval '1 day')",
            (CHAT_RETENTION_DAYS,),
        )
        chat = cur.rowcount
        cur.execute(
            "DELETE FROM exchanges WHERE ts < now() - (%s * interval '1 day')",
            (CHAT_RETENTION_DAYS,),
        )
        exchanges = cur.rowcount
        cur.execute(
            "DELETE FROM notifications "
            "WHERE read_at IS NOT NULL AND read_at < now() - (%s * interval '1 day')",
            (NOTIF_RETENTION_DAYS,),
        )
        notifs = cur.rowcount
    return {
        "sessions_deleted": sessions,
        "claims_deleted": claims,
        "actions_deleted": actions,
        "visits_deleted": visits,
        "media_files_deleted": media,
        "chat_messages_deleted": chat,
        "exchanges_deleted": exchanges,
        "notifications_deleted": notifs,
    }


# ── Application settings ───────────────────────────────────────────────────
# One row per key, JSON value. Small and generic on purpose: report schedule,
# notification recipients and export format are operator preferences, not
# domain data, and they change without a migration.


# Machine bookmarks (a poll offset, a resume point) share app_settings' table —
# key/JSONB, no migration to add one — but not its meaning. `CURSOR_PREFIX`
# keeps them out of `get_settings()`, which is what the operator's Settings
# panel renders: a Telegram update id is not a preference and must never appear
# beside the report schedule for someone to "correct".
CURSOR_PREFIX = "cursor:"


def get_settings() -> dict:
    with _cursor() as cur:
        cur.execute("SELECT key, value FROM app_settings WHERE key NOT LIKE %s",
                    (CURSOR_PREFIX + "%",))
        return {r["key"]: r["value"] for r in (cast(dict, x) for x in cur.fetchall())}


def get_cursor(name: str) -> Any:
    """The last bookmark stored under this name, or None.

    Exists because n8n's `$getWorkflowStaticData` does NOT survive a workflow
    push — it is wiped, the Telegram offset falls back to 0, and Telegram
    re-sends up to 24h of updates. The Postgres dedupe absorbs the replay so
    nothing is filed twice, but the workflow still re-runs a day of messages
    every time it is deployed. The bookmark belongs in the store that outlives
    a deploy, beside the dedupe that already lives there.
    """
    with _cursor() as cur:
        cur.execute("SELECT value FROM app_settings WHERE key = %s",
                    (CURSOR_PREFIX + name,))
        row = cur.fetchone()
    return cast(dict, row)["value"] if row else None


def set_cursor(name: str, value: Any) -> None:
    """Move a bookmark forward. Never backwards.

    The guard is the point: a replayed batch, a late execution or a second
    poller can all present a *lower* update id than the one already confirmed,
    and accepting it would re-open a window that was closed — exactly the 24h
    replay this function exists to end. Non-numeric values are stored as-is,
    since only the numeric ones have an ordering to defend.
    """
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO app_settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET
                value = CASE
                    WHEN jsonb_typeof(EXCLUDED.value) = 'number'
                     AND jsonb_typeof(app_settings.value) = 'number'
                     AND (EXCLUDED.value)::text::numeric <= (app_settings.value)::text::numeric
                    THEN app_settings.value
                    ELSE EXCLUDED.value
                END,
                updated_at = now()
            """,
            (CURSOR_PREFIX + name, json.dumps(value)),
        )


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

# One row per (person, event). Shared by the single-person insert and the two
# fan-out helpers, so a column change lands in one place.
_NOTIFY_INSERT = (
    "INSERT INTO notifications (person_id, kind, title, body, route, ref_id) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
)


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
            _NOTIFY_INSERT,
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


def manager_emails() -> List[str]:
    """Where a task reminder goes: every chef and every directeur with an email.

    Deliberately wider than `account_emails`, which requires a login. A chef who
    has been added to the org chart with an address but has never signed in is
    still someone the shared to-do list is asking to do something — mail is the
    one channel that reaches them, and silently skipping them turned "remind the
    managers" into "remind whoever happens to have a password".

    The bell keeps the narrower rule, because reading a bell needs an account.
    """
    with _cursor() as cur:
        cur.execute(
            "SELECT email FROM persons "
            "WHERE email IS NOT NULL AND email <> '' "
            "AND role IN ('chef', 'directeur') ORDER BY name"
        )
        return [dict(r)["email"] for r in cur.fetchall()]


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
            _NOTIFY_INSERT,
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
            # `_one`, and by name rather than by position: the pool sets
            # RealDictCursor, so a row is a dict and `row[0]` raised KeyError —
            # which _cursor() rewrapped as LogStoreError, so /process logged
            # "notification failed" and the bell never rang for a technician we
            # actually knew. The escalation below was unreachable too.
            row = _one(cur)
            if row is not None:
                manager_id = row["manager_id"]
    if manager_id is not None:
        with _cursor() as cur:
            cur.execute(
                "SELECT 1 FROM persons WHERE id = %s AND password_hash IS NOT NULL",
                (manager_id,),
            )
            if cur.fetchone() is not None:
                create_notification(manager_id, kind, title, body, route, ref_id)
                # 1, not create_notification's None: this function documents its
                # return as "rows written", and None is what it means by
                # "nobody to notify" — the exact opposite of what just happened.
                return 1
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
            _NOTIFY_INSERT,
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
        if row is None:
            raise LogStoreError("create_task: no row returned")
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
        if when is None:
            continue
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


def stt_usage(days: int = 7) -> Dict[str, Any]:
    """How often each STT engine actually served, today and over `days`.

    Read from pipeline_logs, where /process already records
    payload->>'engine' on the `transcribed` stage. That is the engine that
    WON the chain, not the configured order — a spike in `local` means the
    two free tiers were failing, which is the operational fact worth seeing.

    Rows whose payload has no engine (text and photo reports never touch STT)
    are excluded by the NOT NULL, so the counts are audio only.
    """
    with _cursor() as cur:
        cur.execute(
            """
            SELECT payload->>'engine' AS engine,
                   COUNT(*) FILTER (WHERE ts >= date_trunc('day', now())) AS today,
                   COUNT(*) AS period
              FROM pipeline_logs
             WHERE stage = 'transcribed'
               AND payload->>'engine' IS NOT NULL
               AND ts >= now() - make_interval(days => %s)
             GROUP BY 1
             ORDER BY 3 DESC
            """,
            (days,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    return {
        "days": days,
        # Keyed by the SELECT's own aliases: RealDictCursor rows are dicts, so
        # positional access raised KeyError and left the panel permanently
        # empty behind an error that read like Postgres was down.
        "engines": [
            {"engine": r["engine"], "today": int(r["today"]), "period": int(r["period"])}
            for r in rows
        ],
    }


# --- the figures, kept where a machine can count them ----------------------


def record_report_row(row: dict, data: dict) -> None:
    """Mirror one filed report into Postgres. Never raises.

    Called beside the Sheet write, not instead of it: the Sheet stays the
    record the director reads and this is the copy every total is computed
    from. Best-effort for the same reason the Rapports mirror is — a report
    that reached the journal must not be lost because a second store was
    unreachable.

    `ON CONFLICT DO UPDATE` rather than DO NOTHING: n8n retries and the retry
    drain replays parked payloads, and a replay carries the same figures, so
    the later write is the corrected one rather than a duplicate to discard.
    """
    try:
        with _cursor() as cur:
            cur.execute(
                """
                INSERT INTO report_rows (correlation_id, date, heure, technicien,
                    chantier, canal, role, stt_engine, confidence, flag_review,
                    motif_flag, resume, rapport_complet, rapports_row,
                    journal_tab, journal_row, data)
                VALUES (%(correlation_id)s, %(date)s, %(heure)s, %(technicien)s,
                    %(chantier)s, %(canal)s, %(role)s, %(stt_engine)s, %(confidence)s,
                    %(flag_review)s, %(motif_flag)s, %(resume)s, %(rapport_complet)s,
                    %(rapports_row)s, %(journal_tab)s, %(journal_row)s, %(data)s)
                ON CONFLICT (correlation_id) DO UPDATE SET
                    date = EXCLUDED.date, heure = EXCLUDED.heure,
                    technicien = EXCLUDED.technicien, chantier = EXCLUDED.chantier,
                    canal = EXCLUDED.canal, role = EXCLUDED.role,
                    stt_engine = EXCLUDED.stt_engine, confidence = EXCLUDED.confidence,
                    flag_review = EXCLUDED.flag_review, motif_flag = EXCLUDED.motif_flag,
                    resume = EXCLUDED.resume, rapport_complet = EXCLUDED.rapport_complet,
                    rapports_row = COALESCE(EXCLUDED.rapports_row, report_rows.rapports_row),
                    journal_tab = COALESCE(EXCLUDED.journal_tab, report_rows.journal_tab),
                    journal_row = COALESCE(EXCLUDED.journal_row, report_rows.journal_row),
                    data = EXCLUDED.data
                """,
                {**row, "data": json.dumps(data, ensure_ascii=False, default=str)},
            )
    except Exception as exc:  # noqa: BLE001 — a mirror never costs a report
        # Loudly, not only on stdout. This swallow hid a *permanent* fault for a
        # day: on 2026-08-19 the column list gained `journal_tab`/`journal_row`
        # and the VALUES list did not, so every insert raised "INSERT has more
        # target columns than expressions" and every filed report stopped
        # reaching the store the totals are computed from — while the Sheet, the
        # reply and the Rapports mirror all still worked. A transient outage and
        # a broken statement print the same line; only one of them stops on its
        # own, so the operator has to be able to see it in the dashboard.
        print(f"[logs] report_rows mirror failed: {exc}"[:200], flush=True)
        write_safe("sheet", "error",
                   message=f"report_rows mirror failed: {exc}"[:400],
                   correlation_id=row.get("correlation_id"))


def list_report_rows(dates: Optional[Sequence[str]] = None,
                     chantier: Optional[str] = None) -> List[dict]:
    """Filed reports as flat dicts, shaped like the Rapports rows they replace.

    Returned with `data` merged into the top level so every existing caller —
    `journal.rapports_totals`, the report payloads, the .docx tables — keeps
    reading `row["goulotte_m"]` exactly as it read the Sheet column. That is
    the whole point of the shape: the figures moved stores, not formats.
    """
    # Unconfigured is not the same as unreachable. With no DATABASE_URL there
    # is no store to ask and the answer is "no rows" — which is what keeps the
    # test suite runnable with no database, the rule this project holds to. A
    # store that IS configured and fails still raises, because a daily report
    # quietly mailed without its figures is worse than one that does not send.
    if not settings.database_url:
        return []
    where, params = [], {}
    if dates:
        where.append("date = ANY(%(dates)s)")
        params["dates"] = list(dates)
    if chantier:
        where.append("chantier = %(chantier)s")
        params["chantier"] = chantier
    sql = "SELECT * FROM report_rows"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY date, heure, id"
    with _cursor() as cur:
        cur.execute(sql, params)
        out = []
        for r in cur.fetchall():
            row = dict(r)
            data = row.pop("data", None) or {}
            row.pop("id", None)
            out.append({**row, **data})
        return out


def register_articles(items: Dict[str, float]) -> Dict[str, str]:
    """Record free articles and hand back {slug: designation to use}.

    The designation returned is the one already registered when the slug is
    known, not the wording of this message: "prises doubles étanches" and
    "prise double étanche encastrée" normalise to the same slug, and the sheet
    must not grow a second column because a technician pluralised differently.
    First spelling wins until someone confirms a better one.
    """
    if not items:
        return {}
    out: Dict[str, str] = {}
    try:
        with _cursor() as cur:
            for designation, _qty in items.items():
                slug = _slug_article(designation)
                if not slug:
                    continue
                cur.execute(
                    """
                    INSERT INTO article_registry (slug, designation, seen)
                    VALUES (%s, %s, 1)
                    ON CONFLICT (slug) DO UPDATE
                       SET seen = article_registry.seen + 1, last_seen = now()
                    RETURNING designation
                    """,
                    (slug, designation.strip()),
                )
                row = _one(cur)
                out[designation] = (row or {}).get("designation", designation.strip())
    except Exception as exc:  # noqa: BLE001 — never costs the report
        print(f"[logs] register_articles failed: {exc}"[:200], flush=True)
        return {d: d.strip() for d in items}
    return out


def list_article_registry(unconfirmed_only: bool = False) -> List[dict]:
    """Every free article, newest first. The Sites page confirms from this."""
    sql = "SELECT * FROM article_registry"
    if unconfirmed_only:
        sql += " WHERE confirmed = FALSE"
    sql += " ORDER BY last_seen DESC"
    with _cursor() as cur:
        cur.execute(sql)
        return [dict(r) for r in cur.fetchall()]


#: Words that carry no article identity. Dropped before comparing, so
#: "chemin de câbles" and "chemin câbles" are one article and not two.
_ARTICLE_STOPWORDS = frozenset({
    "de", "du", "des", "d", "le", "la", "les", "l", "et", "a", "au", "aux",
    "en", "avec", "pour", "un", "une", "type", "sur",
})


def _slug_article(designation: str) -> str:
    """A designation reduced to its identity: accents, case, plural, **order**.

    The words are sorted, and that is the whole point. A technician writes
    "prise double étanche encastrée" one day and "prise étanche double
    encastrée" the next; with the order preserved those were two slugs, two
    columns and one article counted in both — 4 in one column, 13 in the other,
    and a total that is right in neither. Adjective order carries no meaning in
    an article name, so it must not carry identity either.

    Still deliberately not fuzzy, the same rule site names follow: this merges
    two *spellings of the same words*, never two different words. "prise simple
    encastrée" and "prise simple étanche encastrée" stay apart, because
    étanche is a real difference and a real price.
    """
    text = unicodedata.normalize("NFKD", (designation or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9+]+", " ", text).strip()
    words = []
    for w in text.split():
        if w in _ARTICLE_STOPWORDS:
            continue
        # The obvious French plural, so "prises doubles" == "prise double".
        words.append(w[:-1] if len(w) > 3 and w.endswith("s") else w)
    return " ".join(sorted(words))


def _rekey_free_article(slug: str, designation: Optional[str]) -> int:
    """Drop or re-key one free article inside every `report_rows.data`.

    `report_rows` is what the daily mail, the weekly mail, the .docx tables and
    the dashboard metrics count, so the registry row and the Sheet column are
    only two thirds of an article. Deleting or renaming those two and leaving
    the JSONB alone left the figures behind under a name that no longer exists:
    a rejected article kept counting forever, and a renamed one counted under
    its old spelling, both invisibly.

    `designation is None` **deletes**: the quantity is removed, and that does
    change historical totals. It is meant to — the endpoint already deletes the
    Sheet column "figures included", and the two stores disagreeing is worse
    than either answer. The caller records the row count in the audit trail so
    the change is a fact somebody can find.

    A rename **merges by addition**, never by overwrite: a single row can carry
    both spellings ("prise 2P+T" and "prise industrielle 2P+T" on the same
    message), and picking one would silently drop the other's quantity while
    keeping the old key would double-count it. Same rule the journal's daily
    merge follows.

    Matching is by slug rather than by designation because the JSONB key is
    what the technician *said*, not what the registry stored — first spelling
    wins there, so the two are routinely different strings for one article.
    """
    # Same rule the rest of this module follows: unconfigured is not
    # unreachable — with no DATABASE_URL there are no rows to re-key, and the
    # suite has to run without a database.
    if not settings.database_url:
        return 0
    changed = 0
    target_slug = _slug_article(designation) if designation else ""
    with _cursor() as cur:
        cur.execute(
            "SELECT id, data -> 'articles_libres' AS libres FROM report_rows "
            "WHERE data ? 'articles_libres'"
        )
        for r in list(cur.fetchall()):
            libres = dict((r.get("libres") or {}))
            hits = [k for k in libres if _slug_article(k) == slug]
            if not hits:
                continue
            moved = 0.0
            for k in hits:
                try:
                    moved += float(libres.pop(k))
                except (TypeError, ValueError):  # a non-numeric cell is not a quantity
                    pass
            if designation:
                key = next((k for k in libres if _slug_article(k) == target_slug), designation)
                libres[key] = float(libres.get(key) or 0.0) + moved
            cur.execute(
                "UPDATE report_rows SET data = jsonb_set(data, '{articles_libres}', %s::jsonb) "
                "WHERE id = %s",
                (json.dumps(libres, ensure_ascii=False), r["id"]),
            )
            changed += 1
    return changed


def confirm_article(slug: str) -> bool:
    """Mark a free article as accepted. Returns False when it is unknown."""
    with _cursor() as cur:
        cur.execute("UPDATE article_registry SET confirmed = TRUE WHERE slug = %s", (slug,))
        return cur.rowcount > 0


def rename_article(slug: str, designation: str) -> dict:
    """Rename a free article, merging it into another when the name collides.

    Renaming is how a wrong reading gets corrected, and how two spellings that
    the slug could not tell apart get joined by hand — "prise 2P+T" and "prise
    industrielle 2P+T" are the same socket to an electrician and two different
    word sets to a normaliser. So a rename that lands on an existing article is
    a **merge**, not an error: the caller folds the columns, this drops the
    row.

    Returns {"merged_into": slug} or {"slug": new_slug} so the caller knows
    which of the two happened.
    """
    designation = (designation or "").strip()
    if not designation:
        raise LogStoreError("designation is required")
    new_slug = _slug_article(designation)
    if not new_slug:
        raise LogStoreError("designation has no usable words")
    with _cursor() as cur:
        cur.execute("SELECT slug FROM article_registry WHERE slug = %s", (new_slug,))
        exists = _one(cur) is not None
        if exists and new_slug != slug:
            cur.execute("DELETE FROM article_registry WHERE slug = %s", (slug,))
            merged = True
        else:
            cur.execute(
                "UPDATE article_registry SET slug = %s, designation = %s, confirmed = TRUE "
                "WHERE slug = %s",
                (new_slug, designation, slug),
            )
            if cur.rowcount == 0:
                raise LogStoreError(f"no article {slug!r}")
            merged = False
    # After the registry, and outside its transaction on purpose: the figures
    # in `report_rows` are keyed on the old wording too, and a rename that
    # stopped at the registry left every total counting a name nobody could
    # look up any more.
    rows = _rekey_free_article(slug, designation)
    if merged:
        return {"merged_into": new_slug, "rows": rows}
    return {"slug": new_slug, "designation": designation, "rows": rows}


def delete_article(slug: str) -> Optional[Tuple[str, int]]:
    """Drop a free article and its figures. Returns (designation, rows) or None.

    The figures go with it. Rejecting an article is a statement that the thing
    was never real — a misheard word, a duplicate reading — so leaving its
    quantities inside `report_rows.data` would keep them in every total the
    reports compute, under a designation the registry can no longer name. The
    row count comes back so the caller can put it in the audit trail; that
    entry is the only remaining trace, which is why it is not optional.
    """
    with _cursor() as cur:
        cur.execute(
            "DELETE FROM article_registry WHERE slug = %s RETURNING designation", (slug,)
        )
        row = _one(cur)
        if row is None:
            return None
        designation = row.get("designation")
    return designation, _rekey_free_article(slug, None)
