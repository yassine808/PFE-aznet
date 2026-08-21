"""Accounts, sessions and the audit trail, against a real Postgres.

Every test here is `integration`: it needs TEST_DATABASE_URL and is skipped
without it (see the `db` fixture in conftest). A psycopg2 fake would run the
Python around these statements and prove nothing about the statements, which is
where the behaviour lives — `password_hash IS NOT NULL` as the whole definition
of "this row is an account", the DELETE that must not cascade a person away,
and the join that makes a session die with its account.

`test_auth_gates.py` covers the FastAPI dependencies; this file covers the
storage underneath them.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app import auth

pytestmark = pytest.mark.integration


@pytest.fixture
def account(db):
    return auth.create_user("chef@example.com", "Karim", "un-mot-de-passe", "chef")


# --- passwords -------------------------------------------------------------

def test_a_password_round_trips_and_a_wrong_one_does_not():
    hashed = auth.hash_password("un-mot-de-passe")
    assert auth.verify_password("un-mot-de-passe", hashed) is True
    assert auth.verify_password("autre-chose", hashed) is False


def test_a_corrupt_hash_is_not_a_valid_login():
    """A malformed row is a corrupt row, never an accepted password."""
    assert auth.verify_password("x", "not-a-bcrypt-hash") is False


def test_a_password_longer_than_bcrypts_limit_is_truncated_not_rejected():
    long_password = "a" * 200
    assert auth.verify_password(long_password, auth.hash_password(long_password))


# --- create_user -----------------------------------------------------------

def test_creating_an_account_returns_the_person_without_their_hash(db):
    user = auth.create_user("chef@example.com", "Karim", "un-mot-de-passe")
    assert user["email"] == "chef@example.com"
    assert user["role"] == "chef"
    # Every path out of this module strips it, so it cannot ride out to a browser.
    assert "password_hash" not in user


def test_the_address_is_stored_folded_and_trimmed(db):
    assert auth.create_user("  Chef@Example.COM ", " Karim ",
                            "un-mot-de-passe")["email"] == "chef@example.com"


def test_granting_access_to_an_existing_colleague_credentials_that_person(db):
    """Matched on name, the same rule `logs.upsert_technician` uses — keying on
    anything else makes one human two boxes on the org chart."""
    person = db.create_person("Karim", role="tech")
    user = auth.create_user("chef@example.com", "karim", "un-mot-de-passe")
    assert user["id"] == person["id"]
    assert len(db.list_persons()) == 1


def test_a_second_account_for_the_same_person_is_refused(db, account):
    with pytest.raises(auth.AuthError, match="already has an account"):
        auth.create_user("autre@example.com", "Karim", "un-mot-de-passe")


def test_a_second_account_on_the_same_address_is_refused(db, account):
    with pytest.raises(auth.AuthError, match="an account already exists"):
        auth.create_user("chef@example.com", "Sara", "un-mot-de-passe")


@pytest.mark.parametrize("kwargs,message", [
    ({"role": "technicien"}, "unknown role"),
    ({"email": "  "}, "email and name are required"),
    ({"name": "  "}, "email and name are required"),
    ({"password": "court"}, "at least 8 characters"),
])
def test_what_create_user_refuses(db, kwargs, message):
    args = {"email": "a@example.com", "name": "Karim",
            "password": "un-mot-de-passe", **kwargs}
    with pytest.raises(auth.AuthError, match=message):
        auth.create_user(**args)


# --- list_users / delete_user ---------------------------------------------

def test_only_people_who_can_sign_in_are_users(db, account):
    """Without the hash filter this returns every colleague who ever sent a
    voice note and calls them users."""
    db.create_person("Yassine", role="tech")
    assert [u["name"] for u in auth.list_users()] == ["Karim"]


def test_revoking_access_keeps_the_human_on_the_org_chart(db, account):
    assert auth.delete_user(account["id"]) is True
    assert auth.list_users() == []
    # The person, their channels and their profile all survive.
    assert [p["name"] for p in db.list_persons()] == ["Karim"]


def test_revoking_access_closes_every_open_browser(db, account):
    session = auth.login("chef@example.com", "un-mot-de-passe")
    assert session is not None
    auth.delete_user(account["id"])
    assert auth.user_for_token(session["token"]) is None


def test_revoking_access_twice_reports_that_nothing_changed(db, account):
    assert auth.delete_user(account["id"]) is True
    assert auth.delete_user(account["id"]) is False


def test_revoking_access_from_a_person_who_never_had_it_changes_nothing(db):
    person = db.create_person("Yassine", role="tech")
    assert auth.delete_user(person["id"]) is False


# --- login -----------------------------------------------------------------

def test_a_correct_password_opens_a_session(db, account):
    out = auth.login("  Chef@Example.com ", "un-mot-de-passe")
    assert out is not None
    assert out["user"]["name"] == "Karim"
    assert auth.user_for_token(out["token"])["id"] == account["id"]


@pytest.mark.parametrize("email,password", [
    ("chef@example.com", "mauvais-mot-de-passe"),
    ("inconnu@example.com", "un-mot-de-passe"),
])
def test_every_refusal_looks_the_same_from_outside(db, account, email, password):
    assert auth.login(email, password) is None


def test_a_technician_address_is_refused_rather_than_crashing(db):
    """Most rows in `persons` have no credentials. Reaching `None.encode()`
    raised AttributeError, which the except clause misses — a 500 that
    confirms the address exists."""
    person = db.create_person("Yassine", role="tech")
    with db._cursor() as cur:
        cur.execute("UPDATE persons SET email = %s WHERE id = %s",
                    ("tech@example.com", person["id"]))
    assert auth.login("tech@example.com", "n'importe quoi") is None


def test_a_disabled_account_cannot_sign_in(db, account):
    with db._cursor() as cur:
        cur.execute("UPDATE persons SET active = false WHERE id = %s", (account["id"],))
    assert auth.login("chef@example.com", "un-mot-de-passe") is None


# --- sessions --------------------------------------------------------------

def test_logging_out_ends_that_browsers_session_only(db, account):
    first = auth.login("chef@example.com", "un-mot-de-passe")
    second = auth.login("chef@example.com", "un-mot-de-passe")
    auth.logout(first["token"])
    assert auth.user_for_token(first["token"]) is None
    assert auth.user_for_token(second["token"]) is not None


def test_logging_out_with_no_token_is_a_no_op(db):
    auth.logout(None)
    auth.logout("")


@pytest.mark.parametrize("token", [None, "", "pas-un-jeton"])
def test_an_unknown_token_is_nobody(db, token):
    assert auth.user_for_token(token) is None


def test_an_expired_session_is_nobody(db, account):
    out = auth.login("chef@example.com", "un-mot-de-passe")
    with db._cursor() as cur:
        cur.execute("UPDATE sessions SET expires_at = %s WHERE token = %s",
                    (datetime.now(timezone.utc) - timedelta(minutes=1), out["token"]))
    assert auth.user_for_token(out["token"]) is None


def test_a_session_carries_no_hash_out(db, account):
    out = auth.login("chef@example.com", "un-mot-de-passe")
    assert "password_hash" not in out["user"]
    assert "password_hash" not in auth.user_for_token(out["token"])


def test_last_seen_is_written_at_most_once_a_minute(db, account):
    """Auth sits on the read path of every request; an unconditional UPDATE is
    one write per poll per open panel, forever."""
    out = auth.login("chef@example.com", "un-mot-de-passe")
    with db._cursor() as cur:
        cur.execute("UPDATE persons SET last_seen_at = now() - interval '2 hours'"
                    " WHERE id = %s", (account["id"],))
    auth.user_for_token(out["token"])
    with db._cursor() as cur:
        cur.execute("SELECT last_seen_at FROM persons WHERE id = %s", (account["id"],))
        fresh = db._one(cur)["last_seen_at"]
    auth.user_for_token(out["token"])
    with db._cursor() as cur:
        cur.execute("SELECT last_seen_at FROM persons WHERE id = %s", (account["id"],))
        assert db._one(cur)["last_seen_at"] == fresh


# --- seed_admin ------------------------------------------------------------

def test_the_first_director_is_seeded_on_an_empty_database(db, monkeypatch, capsys):
    monkeypatch.setattr(auth.settings, "admin_email", "boss@example.com")
    monkeypatch.setattr(auth.settings, "admin_password", "un-mot-de-passe")
    monkeypatch.setattr(auth.settings, "admin_name", "Directrice")
    auth.seed_admin()
    assert [(u["name"], u["role"]) for u in auth.list_users()] == [
        ("Directrice", "directeur")]
    assert "seeded first director" in capsys.readouterr().out


def test_seeding_is_skipped_once_any_account_exists(db, account, monkeypatch, capsys):
    """It must never resurrect a deleted admin or reset a changed password."""
    monkeypatch.setattr(auth.settings, "admin_email", "boss@example.com")
    monkeypatch.setattr(auth.settings, "admin_password", "un-mot-de-passe")
    auth.seed_admin()
    assert len(auth.list_users()) == 1
    assert "seed skipped" in capsys.readouterr().out


def test_no_admin_settings_says_the_dashboard_is_unusable(db, monkeypatch, capsys):
    monkeypatch.setattr(auth.settings, "admin_email", "")
    monkeypatch.setattr(auth.settings, "admin_password", "")
    auth.seed_admin()
    assert "dashboard login unusable" in capsys.readouterr().out


def test_a_rejected_seed_password_is_loud_but_never_fatal(db, monkeypatch, capsys):
    """It would otherwise propagate out of startup and take the pipeline down
    with the dashboard."""
    monkeypatch.setattr(auth.settings, "admin_email", "boss@example.com")
    monkeypatch.setattr(auth.settings, "admin_password", "court")
    auth.seed_admin()
    assert auth.list_users() == []
    assert "could not seed" in capsys.readouterr().out


# --- the audit trail -------------------------------------------------------

def test_an_action_is_appended_with_the_callers_name_denormalised(db, account):
    """The trail still reads correctly after an account is deleted."""
    auth.record(account, "report_edited", target="Rapports!12",
                before="40", after="80", detail={"champ": "goulotte_m"})
    out = auth.history()
    assert out["actions"][0]["action"] == "report_edited"
    assert out["actions"][0]["user_name"] == "Karim"
    assert out["totals"] == {"report_edited": 1}


def test_no_caller_records_nothing(db):
    auth.record(None, "report_edited")
    assert auth.history()["actions"] == []


def test_an_audit_write_never_fails_the_thing_it_audits(db, account, monkeypatch, capsys):
    def boom(*_a, **_k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(auth.logs, "_cursor", boom)
    auth.record(account, "report_edited")
    auth.record_visit(account["id"], "/inbox", 30)
    out = capsys.readouterr().out
    assert "audit write failed" in out
    assert "visit write failed" in out


def test_page_time_is_recorded_and_an_open_tab_is_capped(db, account):
    auth.record_visit(account["id"], "/inbox", 30)
    auth.record_visit(account["id"], "/inbox", 99_999)
    pages = auth.history()["pages"]
    assert pages[0]["route"] == "/inbox"
    assert int(pages[0]["seconds"]) == 30 + 3600
    assert int(pages[0]["visits"]) == 2


@pytest.mark.parametrize("user_id,seconds", [(None, 30), (1, 0), (1, -5)])
def test_a_visit_with_nothing_to_record_is_dropped(db, user_id, seconds):
    auth.record_visit(user_id, "/inbox", seconds)
    assert auth.history()["pages"] == []


def test_history_can_be_narrowed_to_one_person(db, account):
    other = auth.create_user("chef2@example.com", "Sara", "un-mot-de-passe")
    auth.record(account, "login")
    auth.record(other, "login")
    auth.record_visit(other["id"], "/daily", 10)

    mine = auth.history(user_id=account["id"])
    assert [a["user_name"] for a in mine["actions"]] == ["Karim"]
    assert mine["pages"] == []
    assert mine["total_seconds"] == 0

    theirs = auth.history(user_id=other["id"])
    assert theirs["total_seconds"] == 10
    # 14 days of daily activity for the sparkline, zero-filled in the client.
    assert theirs["daily"][0]["n"] == 1


def test_history_is_newest_first_and_capped(db, account):
    for i in range(5):
        auth.record(account, f"action_{i}")
    out = auth.history(limit=2)
    assert [a["action"] for a in out["actions"]] == ["action_4", "action_3"]
    assert len(out["totals"]) == 5
