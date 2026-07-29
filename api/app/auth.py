"""Dashboard accounts, sessions and the audit trail.

The dashboard is no longer a page on one PC that only the admin can reach: the
director and the chefs use it, and the history has to say who did what. That
means the gate lives on the **API**, not on the login form. A React bundle can
be bypassed with devtools; a `Depends` cannot.

Two ways through that gate:

- a **session cookie**, for humans. The token is opaque and stored in Postgres,
  so deleting the row logs that browser out on its next request. A signed JWT
  would stay valid until it expired no matter what the database said, which is
  the wrong behaviour on the day an account has to be shut off.
- an **API key header**, for n8n. The workflow calls /process, /logs,
  /logs/claim, /sheet-queue, /technicians/lookup and /profiles/refresh on every
  message and has no browser to hold a cookie.

Everything here is written so publishing the dashboard later is configuration,
not a rewrite: `COOKIE_SECURE` and `SameSite` flip on, and the CORS origin
narrows. What cannot be retrofitted -- hashing, revocable sessions, an API-side
gate -- is done properly now.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Cookie, Depends, Header, HTTPException, Response

from app import logs
from app.config import settings

COOKIE_NAME = "aznet_session"
SESSION_DAYS = 7

# bcrypt hashes at most 72 bytes and raises on more. Truncating is the standard
# handling and is safe: 72 bytes of password is far beyond any real one, and
# silently accepting a longer string while ignoring the tail would be worse.
BCRYPT_MAX_BYTES = 72

ROLES = ("directeur", "chef")


class AuthError(RuntimeError):
    pass


# ── passwords ──────────────────────────────────────────────────────────────


def hash_password(raw: str) -> str:
    import bcrypt

    return bcrypt.hashpw(raw.encode("utf-8")[:BCRYPT_MAX_BYTES], bcrypt.gensalt()).decode()


def verify_password(raw: str, hashed: str) -> bool:
    import bcrypt

    try:
        return bcrypt.checkpw(raw.encode("utf-8")[:BCRYPT_MAX_BYTES], hashed.encode())
    except (ValueError, TypeError):
        # A malformed hash in the database is a corrupt row, not a valid login.
        return False


# ── accounts ───────────────────────────────────────────────────────────────


def _public(row: dict) -> dict:
    """A user row without its hash. Every path out of this module goes through
    here, so the hash cannot reach an API response by someone forgetting."""
    out = {k: v for k, v in row.items() if k != "password_hash"}
    for key, value in out.items():
        if isinstance(value, datetime):
            out[key] = value.isoformat()
    return out


def list_users() -> List[dict]:
    with logs._cursor() as cur:
        cur.execute("SELECT * FROM users ORDER BY role, name")
        return [_public(dict(r)) for r in cur.fetchall()]


def create_user(email: str, name: str, password: str, role: str = "chef") -> dict:
    if role not in ROLES:
        raise AuthError(f"unknown role: {role} (expected one of {', '.join(ROLES)})")
    if not email.strip() or not name.strip():
        raise AuthError("email and name are required")
    if len(password) < 8:
        # The only password rule enforced. Composition rules (a digit, a symbol)
        # push people towards "Password1!" and buy less than length does.
        raise AuthError("password must be at least 8 characters")
    with logs._cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (email, name, role, password_hash)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (email) DO NOTHING
            RETURNING *
            """,
            (email.strip().lower(), name.strip(), role, hash_password(password)),
        )
        row = logs._one(cur)
    if row is None:
        raise AuthError(f"an account already exists for {email.strip().lower()}")
    return _public(dict(row))


def delete_user(user_id: int) -> bool:
    with logs._cursor() as cur:
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        return cur.rowcount > 0


def seed_admin() -> None:
    """Create the first director from .env, only while no account exists.

    Without this the system is unusable on a fresh database: creating an account
    requires being logged in, and logging in requires an account. Skipped
    forever once any row exists, so it cannot silently resurrect a deleted
    admin or reset a changed password.
    """
    email = os.environ.get("ADMIN_EMAIL", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    with logs._cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM users")
        existing = dict(logs._one(cur) or {"n": 0})["n"]
    if existing:
        return
    if not email or not password:
        print("[auth] no accounts and no ADMIN_EMAIL/ADMIN_PASSWORD — dashboard login unusable")
        return
    create_user(email, os.environ.get("ADMIN_NAME", "Directeur"), password, "directeur")
    print(f"[auth] seeded first director account: {email}")


# ── sessions ───────────────────────────────────────────────────────────────


def login(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Return (user, token) on success, None on any failure.

    One indistinguishable failure for "no such account", "wrong password" and
    "account disabled": telling them apart tells an attacker which emails are
    real, and tells a chef whose account was disabled to keep guessing.
    """
    with logs._cursor() as cur:
        cur.execute("SELECT * FROM users WHERE email = %s", (email.strip().lower(),))
        row = logs._one(cur)
        user = dict(row) if row else None
    if user is None or not user["active"] or not verify_password(password, user["password_hash"]):
        return None

    token = secrets.token_urlsafe(32)
    with logs._cursor() as cur:
        cur.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
            (token, user["id"], datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)),
        )
        cur.execute("UPDATE users SET last_seen_at = now() WHERE id = %s", (user["id"],))
    return {"user": _public(user), "token": token}


def logout(token: Optional[str]) -> None:
    if not token:
        return
    with logs._cursor() as cur:
        cur.execute("DELETE FROM sessions WHERE token = %s", (token,))


def user_for_token(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    with logs._cursor() as cur:
        cur.execute(
            """
            SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
             WHERE s.token = %s AND s.expires_at > now() AND u.active
            """,
            (token,),
        )
        row = logs._one(cur)
        if row is None:
            return None
        cur.execute("UPDATE users SET last_seen_at = now() WHERE id = %s", (dict(row)["id"],))
    return _public(dict(row))


def set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,       # unreadable from JavaScript, so an XSS cannot steal it
        samesite="lax",
        secure=settings.cookie_secure,  # off on http://localhost, on once published
        max_age=SESSION_DAYS * 86400,
        path="/",
    )


def clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


# ── the gate ───────────────────────────────────────────────────────────────


def _machine_ok(api_key: Optional[str]) -> bool:
    """n8n's way in. Disabled unless a key is configured, so an unset value can
    never mean 'everyone is a machine'."""
    expected = settings.internal_api_key
    if not expected or not api_key:
        return False
    return secrets.compare_digest(api_key, expected)


def current_user(
    session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    x_api_key: Optional[str] = Header(default=None),
) -> Optional[dict]:
    """Whoever is calling: a logged-in human, a machine, or nobody."""
    user = user_for_token(session)
    if user is not None:
        return user
    return {"id": None, "name": "n8n", "role": "machine"} if _machine_ok(x_api_key) else None


def require_user(caller: Optional[dict] = Depends(current_user)) -> dict:
    """Any authenticated caller: a human session or n8n's key."""
    if caller is None:
        raise HTTPException(401, "authentication required")
    return caller


def require_human(caller: dict = Depends(require_user)) -> dict:
    """A logged-in person. n8n has no business editing settings or accounts."""
    if caller.get("id") is None:
        raise HTTPException(403, "this endpoint is for signed-in users")
    return caller


def require_director(caller: dict = Depends(require_human)) -> dict:
    if caller.get("role") != "directeur":
        raise HTTPException(403, "réservé au directeur")
    return caller


# ── audit trail ────────────────────────────────────────────────────────────


def record(
    caller: Optional[dict],
    action: str,
    target: Optional[str] = None,
    before: Optional[str] = None,
    after: Optional[str] = None,
    detail: Optional[dict] = None,
) -> None:
    """Append one action. Never raises.

    An audit write must not be able to fail the thing it is auditing: losing a
    history row is a nuisance, losing a technician's report edit because the
    history table was unreachable is a bug. `user_name` is denormalised on
    purpose so the trail still reads correctly after an account is deleted.
    """
    if caller is None:
        return
    import json

    try:
        with logs._cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_actions
                       (user_id, user_name, action, target, before_val, after_val, detail)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (caller.get("id"), caller.get("name"), action, target, before, after,
                 json.dumps(detail, ensure_ascii=False) if detail else None),
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[auth] audit write failed ({action}): {exc}")


def record_visit(user_id: Optional[int], route: str, seconds: int) -> None:
    if user_id is None or seconds <= 0:
        return
    try:
        with logs._cursor() as cur:
            cur.execute(
                "INSERT INTO page_visits (user_id, route, seconds) VALUES (%s, %s, %s)",
                (user_id, route, min(seconds, 3600)),  # an hour on one page is a tab left open
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[auth] visit write failed: {exc}")


def history(user_id: Optional[int] = None, limit: int = 100) -> dict:
    """Actions, navigation and totals. Counts are computed here, never stored:
    a counter column drifts the moment a row is deleted or replayed."""
    where, args = ("WHERE user_id = %s", (user_id,)) if user_id is not None else ("", ())
    with logs._cursor() as cur:
        cur.execute(
            f"SELECT * FROM user_actions {where} ORDER BY created_at DESC LIMIT %s",
            args + (limit,),
        )
        actions = [logs._iso(dict(r)) for r in cur.fetchall()]

        cur.execute(
            f"""SELECT action, count(*) AS n FROM user_actions {where}
                GROUP BY action ORDER BY n DESC""",
            args,
        )
        totals = {dict(r)["action"]: dict(r)["n"] for r in cur.fetchall()}

        cur.execute(
            f"""SELECT route, sum(seconds) AS seconds, count(*) AS visits
                  FROM page_visits {where} GROUP BY route ORDER BY seconds DESC""",
            args,
        )
        pages = [dict(r) for r in cur.fetchall()]

        # 14 days of daily activity for the sparkline. Zero-filled in the
        # client, not here: a day with no rows must show as a gap in the graph
        # rather than vanishing and making the week look shorter than it was.
        cur.execute(
            f"""SELECT to_char(created_at, 'YYYY-MM-DD') AS day, count(*) AS n
                  FROM user_actions {where}
                 {'AND' if where else 'WHERE'} created_at > now() - interval '14 days'
                 GROUP BY day ORDER BY day""",
            args,
        )
        daily = [dict(r) for r in cur.fetchall()]

    return {
        "actions": actions,
        "totals": totals,
        "pages": pages,
        "daily": daily,
        "total_seconds": sum(int(p["seconds"] or 0) for p in pages),
    }
