"""The org chart, the sites, the bordereau and the operator settings, over HTTP.

Every endpoint here is a thin translation between a `logs.*` call and a status
code, and the translation is the thing worth holding: which failure is the
caller's mistake (422), which is the store being unreachable (502), and which
writes are director-only. So the store is faked at the module boundary and the
tests assert on the codes and on what reached `logs`.

Auth is overridden per test rather than once for the module: half of these
endpoints exist to refuse a chef, and a module-level override would hide that.
`test_auth_gates.py` covers the anonymous case.
"""
import pytest
from fastapi.testclient import TestClient

import app.main as main

client = TestClient(main.app)

DIRECTOR = {"id": 1, "name": "Directrice", "email": "boss@example.com",
            "role": "directeur"}
CHEF = {"id": 2, "name": "Karim", "email": "chef@example.com", "role": "chef"}


@pytest.fixture(autouse=True)
def _as_director(monkeypatch):
    """Signed in as the director unless a test says otherwise."""
    for dep in (main.auth.current_user, main.auth.require_user,
                main.auth.require_human, main.auth.require_director):
        monkeypatch.setitem(main.app.dependency_overrides, dep, lambda: DIRECTOR)
    monkeypatch.setattr(main.auth, "record", lambda *a, **k: None)


@pytest.fixture
def as_chef(monkeypatch):
    for dep in (main.auth.current_user, main.auth.require_user,
                main.auth.require_human):
        monkeypatch.setitem(main.app.dependency_overrides, dep, lambda: CHEF)
    # The real director gate runs, so a chef is refused rather than waved through.
    monkeypatch.delitem(main.app.dependency_overrides,
                        main.auth.require_director, raising=False)


def boom(*_a, **_k):
    raise main.logs.LogStoreError("cannot reach postgres")


def refuse(message):
    def _refuse(*_a, **_k):
        raise main.logs.LogStoreError(message)

    return _refuse


# --- the org chart ---------------------------------------------------------

def test_technicians_are_people_with_their_identities(monkeypatch):
    monkeypatch.setattr(main.logs, "list_persons",
                        lambda: [{"id": 1, "name": "Yassine", "identities": []}])
    assert client.get("/technicians").json()["technicians"][0]["name"] == "Yassine"


def test_an_unreachable_store_is_a_502_not_a_500(monkeypatch):
    monkeypatch.setattr(main.logs, "list_persons", boom)
    r = client.get("/technicians")
    assert r.status_code == 502
    assert "cannot reach postgres" in r.json()["detail"]


def test_adding_a_channel_identity_passes_the_whole_payload_through(monkeypatch):
    seen = {}

    def upsert(*args):
        seen["args"] = args
        return {"id": 3}

    monkeypatch.setattr(main.logs, "upsert_technician", upsert)
    r = client.post("/technicians", json={"channel": "telegram", "external_id": "555",
                                          "name": "Yassine", "role": "tech"})
    assert r.status_code == 200
    assert seen["args"][:4] == ("telegram", "555", "Yassine", "tech")


@pytest.mark.parametrize("message,status", [
    ("unknown channel: signal", 422),   # the caller's mistake
    ("name is required", 422),
    ("cannot reach postgres", 502),     # the store's
])
def test_a_bad_identity_is_the_callers_fault_an_outage_is_not(monkeypatch, message, status):
    monkeypatch.setattr(main.logs, "upsert_technician", refuse(message))
    r = client.post("/technicians", json={"channel": "signal", "external_id": "x",
                                          "name": "Y"})
    assert r.status_code == status


def test_removing_an_identity_reports_whether_it_existed(monkeypatch):
    monkeypatch.setattr(main.logs, "delete_technician", lambda tid: tid == 3)
    assert client.delete("/technicians/3").json() == {"deleted": True}
    assert client.delete("/technicians/9").json() == {"deleted": False}


def test_removing_a_person_takes_their_identities_and_memory(monkeypatch):
    monkeypatch.setattr(main.logs, "delete_person", lambda pid: True)
    assert client.delete("/persons/3").json() == {"deleted": True}


def test_adding_a_person_is_director_only(as_chef):
    assert client.post("/persons", json={"name": "Sara", "role": "chef"}).status_code == 403


def test_adding_a_person_creates_a_box_with_no_channel_and_no_login(monkeypatch):
    monkeypatch.setattr(main.logs, "create_person",
                        lambda name, role: {"id": 4, "name": name, "role": role})
    assert client.post("/persons", json={"name": "Sara", "role": "chef"}).json() == {
        "id": 4, "name": "Sara", "role": "chef"}


def test_a_person_with_no_name_is_a_422(monkeypatch):
    monkeypatch.setattr(main.logs, "create_person", refuse("name is required"))
    assert client.post("/persons", json={"name": " "}).status_code == 422


def test_reassigning_someone_to_a_chef(monkeypatch):
    seen = {}
    monkeypatch.setattr(main.logs, "set_manager",
                        lambda pid, mid: seen.update(pid=pid, mid=mid) or True)
    r = client.patch("/persons/5/manager", json={"manager_id": 2})
    assert r.json() == {"id": 5, "manager_id": 2}
    assert seen == {"pid": 5, "mid": 2}


def test_reassigning_to_nobody_is_allowed(monkeypatch):
    monkeypatch.setattr(main.logs, "set_manager", lambda pid, mid: True)
    assert client.patch("/persons/5/manager", json={"manager_id": None}).json()[
        "manager_id"] is None


def test_reassigning_an_unknown_person_is_a_404(monkeypatch):
    monkeypatch.setattr(main.logs, "set_manager", lambda pid, mid: False)
    assert client.patch("/persons/99/manager", json={"manager_id": 2}).status_code == 404


def test_self_parenting_is_refused_as_the_callers_mistake(monkeypatch):
    monkeypatch.setattr(main.logs, "set_manager",
                        refuse("a person cannot manage themselves"))
    assert client.patch("/persons/5/manager", json={"manager_id": 5}).status_code == 422


def test_reassignment_is_director_only(as_chef):
    r = client.patch("/persons/5/manager", json={"manager_id": 2})
    assert r.status_code == 403


# --- chantiers -------------------------------------------------------------

def test_sites_can_be_narrowed_to_the_active_ones(monkeypatch):
    seen = {}

    def listing(active=False):
        seen["active"] = active
        return []

    monkeypatch.setattr(main.logs, "list_chantiers", listing)
    client.get("/chantiers?active_only=true")
    assert seen["active"] is True


def test_creating_a_site(monkeypatch):
    monkeypatch.setattr(main.logs, "create_chantier",
                        lambda nom, tab, client_: {"id": 7, "nom": nom,
                                                   "sheet_tab": tab, "client": client_})
    r = client.post("/chantiers", json={"nom": "ACAPS 2", "client": "ACAPS",
                                        "sheet_tab": "ACAPS 2"})
    assert r.json()["id"] == 7


def test_creating_a_site_is_director_only(as_chef):
    assert client.post("/chantiers", json={"nom": "ACAPS 2"}).status_code == 403


def test_confirming_a_site_the_pipeline_invented(monkeypatch):
    monkeypatch.setattr(main.logs, "verify_chantier", lambda cid: cid == 7)
    assert client.patch("/chantiers/7").json() == {"id": 7, "verifie": True}
    assert client.patch("/chantiers/99").status_code == 404


def test_deleting_a_site_leaves_the_journal_tab_alone(monkeypatch):
    """The tab is the director's record; deleting a dashboard row must never
    erase months of reports in his file."""
    monkeypatch.setattr(main.logs, "delete_chantier", lambda cid: True)
    assert client.delete("/chantiers/7").json() == {"deleted": True}


def test_a_store_outage_on_any_site_write_is_a_502(monkeypatch):
    monkeypatch.setattr(main.logs, "verify_chantier", boom)
    monkeypatch.setattr(main.logs, "delete_chantier", boom)
    monkeypatch.setattr(main.logs, "list_chantiers", boom)
    assert client.patch("/chantiers/7").status_code == 502
    assert client.delete("/chantiers/7").status_code == 502
    assert client.get("/chantiers").status_code == 502


# --- the bordereau ---------------------------------------------------------

@pytest.fixture
def bordereau(monkeypatch):
    monkeypatch.setattr(main.logs, "list_chantiers",
                        lambda active=False: [{"id": 7, "nom": "DGH", "sheet_tab": "DGH"}])
    monkeypatch.setattr(main.logs, "list_articles", lambda cid: [
        {"id": 1, "designation": "Câble UTP", "champ": "cables_installes_m",
         "qte_marche": 1000},
        {"id": 2, "designation": "Switch 24 ports", "champ": None, "qte_marche": 4},
        {"id": 3, "designation": "Goulotte", "champ": "goulotte_m", "qte_marche": 0},
    ])
    monkeypatch.setattr(main.sheets, "read_tab_cached", lambda tab: [])
    monkeypatch.setattr(main.journal, "totals",
                        lambda rows: {"cables_installes_m": 250.0})


def test_progress_is_computed_on_every_call_and_stored_nowhere(bordereau):
    out = client.get("/chantiers/7/bordereau").json()
    cable, switch, goulotte = out["articles"]
    assert (cable["qte_installee"], cable["avancement"]) == (250.0, 0.25)
    # No `champ` means "not tracked here", never "none installed".
    assert (switch["qte_installee"], switch["avancement"]) == (None, None)
    # A zero contract quantity has no ratio rather than a division by zero.
    assert goulotte["avancement"] is None


def test_a_bordereau_for_an_unknown_site_is_a_404(bordereau):
    assert client.get("/chantiers/99/bordereau").status_code == 404


def test_a_sheets_outage_on_the_bordereau_is_a_502(bordereau, monkeypatch):
    def sheets_down(_tab):
        raise main.sheets.SheetsError("403 forbidden")

    monkeypatch.setattr(main.sheets, "read_tab_cached", sheets_down)
    assert client.get("/chantiers/7/bordereau").status_code == 502


def test_adding_and_removing_a_bordereau_article(monkeypatch):
    seen = {}

    def upsert(*args):
        seen["args"] = args
        return {"id": 1}

    monkeypatch.setattr(main.logs, "upsert_article", upsert)
    monkeypatch.setattr(main.logs, "delete_bordereau_article", lambda aid: True)

    client.post("/chantiers/7/articles",
                json={"designation": "Câble UTP", "unite": "ml", "qte_marche": 1000,
                      "numero": 3, "champ": "cables_installes_m"})
    assert seen["args"] == (7, "Câble UTP", "ml", 1000, 3, "cables_installes_m")
    # `/bordereau-articles/…` and not `/articles/{id}`: `{slug}` matches
    # anything, so the two resources cannot share one path shape.
    assert client.delete("/bordereau-articles/1").json() == {"deleted": True}


def test_bordereau_writes_are_director_only(as_chef):
    assert client.post("/chantiers/7/articles",
                       json={"designation": "x"}).status_code == 403
    assert client.delete("/bordereau-articles/1").status_code == 403


# --- free articles ---------------------------------------------------------

@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setattr(main.logs, "list_article_registry", lambda: [
        {"slug": "prise-double", "designation": "Prise double étanche",
         "confirmed": False}])
    monkeypatch.setattr(main.logs, "confirm_article", lambda slug: slug == "prise-double")
    monkeypatch.setattr(main.logs, "rename_article",
                        lambda slug, name: {"slug": slug, "rows": 12})
    monkeypatch.setattr(main.sheets, "rename_column", lambda old, new: 2)
    monkeypatch.setattr(main.sheets, "delete_column", lambda name: 1)


def test_a_free_article_can_be_accepted_as_it_stands(registry):
    assert client.patch("/articles/prise-double").json() == {
        "ok": True, "slug": "prise-double"}


def test_an_empty_rename_is_read_as_a_confirmation(registry):
    assert client.patch("/articles/prise-double",
                        json={"designation": "   "}).status_code == 200


def test_renaming_moves_the_column_in_every_tab_that_carries_it(registry):
    out = client.patch("/articles/prise-double",
                       json={"designation": "Prise double"}).json()
    assert out == {"ok": True, "tabs": 2, "slug": "prise-double", "rows": 12}


def test_confirming_or_renaming_an_unknown_article_is_a_404(registry, monkeypatch):
    monkeypatch.setattr(main.logs, "confirm_article", lambda slug: False)
    assert client.patch("/articles/inconnu").status_code == 404
    assert client.patch("/articles/inconnu",
                        json={"designation": "Autre"}).status_code == 404


def test_rejecting_an_article_drops_its_column_and_says_how_much_moved(registry, monkeypatch):
    monkeypatch.setattr(main.logs, "delete_article",
                        lambda slug: ("Prise double étanche", 12))
    assert client.delete("/articles/prise-double").json() == {
        "ok": True, "tabs": 1, "rows": 12}


def test_rejecting_an_unknown_article_is_a_404(registry, monkeypatch):
    monkeypatch.setattr(main.logs, "delete_article", lambda slug: None)
    assert client.delete("/articles/inconnu").status_code == 404


def test_the_article_queue_is_readable_by_anyone_signed_in(registry, as_chef):
    assert client.get("/articles").status_code == 200


def test_article_decisions_are_director_only(registry, as_chef):
    assert client.patch("/articles/prise-double").status_code == 403
    assert client.delete("/articles/prise-double").status_code == 403


# --- material alerts -------------------------------------------------------

ALERT = {"chantier": "DGH", "champ": "cables_installes_m", "niveau": "bas",
         "reste": 120.0}


def test_alerts_come_from_the_servers_own_assessment(monkeypatch):
    monkeypatch.setattr(main.stock, "assess", lambda: [ALERT])
    monkeypatch.setattr(main.stock, "apply_mutes", lambda found: found)
    assert client.get("/alerts").json() == {"alerts": [ALERT]}


def test_muting_snapshots_the_servers_figures_never_the_clients(monkeypatch):
    """A client-supplied figure would let a stale tab mute a shortage against a
    number that has not been true for an hour."""
    seen = {}
    monkeypatch.setattr(main.stock, "assess", lambda: [ALERT])
    monkeypatch.setattr(main.logs, "mute_alert",
                        lambda *args: seen.update(args=args))
    r = client.post("/alerts/mute", json={"chantier": "DGH",
                                          "champ": "cables_installes_m",
                                          "niveau": "epuise", "reste": 0})
    assert r.json() == {"ok": True}
    assert seen["args"][:4] == ("DGH", "cables_installes_m", "bas", 120.0)


def test_a_finding_that_is_not_live_cannot_be_muted(monkeypatch):
    """There would be nothing to snapshot, and the row would pre-emptively hide
    an alert nobody has seen yet."""
    monkeypatch.setattr(main.stock, "assess", lambda: [])
    r = client.post("/alerts/mute", json={"chantier": "DGH", "champ": "fibre_m"})
    assert r.status_code == 404


def test_unmuting_brings_a_finding_back_for_everyone(monkeypatch):
    monkeypatch.setattr(main.logs, "unmute_alert", lambda c, f: True)
    r = client.delete("/alerts/mute?chantier=DGH&champ=cables_installes_m")
    assert r.json() == {"ok": True, "removed": True}


def test_unmuting_something_that_was_not_muted_is_not_an_error(monkeypatch):
    monkeypatch.setattr(main.logs, "unmute_alert", lambda c, f: False)
    assert client.delete("/alerts/mute?chantier=DGH&champ=x").json()["removed"] is False


def test_a_store_outage_while_muting_is_a_502(monkeypatch):
    monkeypatch.setattr(main.stock, "assess", lambda: [ALERT])
    monkeypatch.setattr(main.logs, "mute_alert", boom)
    monkeypatch.setattr(main.logs, "unmute_alert", boom)
    assert client.post("/alerts/mute",
                       json={"chantier": "DGH",
                             "champ": "cables_installes_m"}).status_code == 502
    assert client.delete("/alerts/mute?chantier=DGH&champ=x").status_code == 502


# --- receptions ------------------------------------------------------------

def test_receptions_are_read_only_and_filterable_by_site(monkeypatch):
    seen = {}

    def listing(chantier=None):
        seen["chantier"] = chantier
        return []

    monkeypatch.setattr(main.logs, "list_receptions", listing)
    client.get("/receptions?chantier=DGH")
    assert seen["chantier"] == "DGH"
    # A second way to enter one is a second way for the ledger to disagree with
    # the messages, so there is no POST at all.
    assert client.post("/receptions", json={}).status_code == 405


# --- profiles --------------------------------------------------------------

@pytest.fixture
def profiles(monkeypatch):
    monkeypatch.setattr(main.logs, "list_persons",
                        lambda: [{"id": 1, "name": "Yassine", "role": "tech"}])
    monkeypatch.setattr(main.sheets, "read_reports", lambda: [{"technicien": "Yassine"}])
    monkeypatch.setattr(main.memory, "refresh_person",
                        lambda person, rows: {"person_id": person["id"], "updated": True})


def test_one_profile_can_be_rebuilt_without_waiting_for_the_cron(profiles):
    assert client.post("/persons/1/profile").json()["updated"] is True


def test_rebuilding_the_profile_of_someone_who_is_not_there(profiles):
    assert client.post("/persons/99/profile").status_code == 404


def test_a_sheets_outage_is_a_502_not_a_500(profiles, monkeypatch):
    """The profile is built from the Sheet: a Google outage must read as "try
    again", never as our bug."""
    def sheets_down():
        raise main.sheets.SheetsError("429 quota")

    monkeypatch.setattr(main.sheets, "read_reports", sheets_down)
    assert client.post("/persons/1/profile").status_code == 502
    assert client.post("/profiles/refresh").status_code == 502


def test_the_sheet_is_read_once_for_every_profile(profiles, monkeypatch):
    reads = []
    monkeypatch.setattr(main.logs, "list_persons",
                        lambda: [{"id": i, "name": f"T{i}"} for i in range(3)])
    monkeypatch.setattr(main.sheets, "read_reports", lambda: reads.append(1) or [])
    out = client.post("/profiles/refresh").json()
    assert out["refreshed"] == 3
    assert reads == [1]


def test_a_store_outage_while_listing_people_is_a_502(profiles, monkeypatch):
    monkeypatch.setattr(main.logs, "list_persons", boom)
    assert client.post("/persons/1/profile").status_code == 502
    assert client.post("/profiles/refresh").status_code == 502


# --- the authorization lookup n8n makes -----------------------------------

def test_the_lookup_answers_found_false_rather_than_a_404(monkeypatch):
    monkeypatch.setattr(main.logs, "find_technician",
                        lambda channel, ext: None if ext == "999" else {"name": "Yassine"})
    ok = client.get("/technicians/lookup?channel=telegram&external_id=555").json()
    assert ok == {"found": True, "technician": {"name": "Yassine"}}
    assert client.get(
        "/technicians/lookup?channel=telegram&external_id=999").json() == {
            "found": False, "technician": None}


def test_a_store_outage_on_the_lookup_is_a_502(monkeypatch):
    monkeypatch.setattr(main.logs, "find_technician", boom)
    assert client.get(
        "/technicians/lookup?channel=telegram&external_id=1").status_code == 502


# --- settings --------------------------------------------------------------

def test_settings_round_trip(monkeypatch):
    stored = {}
    monkeypatch.setattr(main.logs, "get_settings", lambda: {"daily_time": "19:00"})
    monkeypatch.setattr(main.logs, "put_settings",
                        lambda values: stored.update(values) or stored)
    assert client.get("/settings").json() == {"settings": {"daily_time": "19:00"}}
    r = client.put("/settings", json={"values": {"daily_time": "18:30"}})
    assert r.json() == {"settings": {"daily_time": "18:30"}}


def test_reordering_the_stt_chain_is_director_only(as_chef, monkeypatch):
    monkeypatch.setattr(main.logs, "put_settings", lambda values: values)
    r = client.put("/settings", json={"values": {"stt_chain": "groq,gemini"}})
    assert r.status_code == 403
    # …while the rest of the object is writable by any account.
    assert client.put("/settings",
                      json={"values": {"daily_time": "18:30"}}).status_code == 200


@pytest.mark.parametrize("chain", ["grok,gemini", "", "  ,  "])
def test_a_typo_in_the_stt_chain_is_rejected_not_stored(monkeypatch, chain):
    """An unknown name is skipped at transcription time, so it would quietly
    run one engine short."""
    monkeypatch.setattr(main.logs, "put_settings",
                        lambda values: pytest.fail("must not be stored"))
    r = client.put("/settings", json={"values": {"stt_chain": chain}})
    assert r.status_code == 422


def test_a_valid_chain_is_normalised_before_it_is_stored(monkeypatch):
    stored = {}
    monkeypatch.setattr(main.logs, "put_settings",
                        lambda values: stored.update(values) or values)
    client.put("/settings", json={"values": {"stt_chain": " gemini , local ,groq "}})
    assert stored["stt_chain"] == "gemini,local,groq"


def test_a_store_outage_on_settings_is_a_502(monkeypatch):
    monkeypatch.setattr(main.logs, "get_settings", boom)
    monkeypatch.setattr(main.logs, "put_settings", boom)
    assert client.get("/settings").status_code == 502
    assert client.put("/settings", json={"values": {}}).status_code == 502


# --- the STT panel ---------------------------------------------------------

def test_the_stt_panel_renders_without_postgres_and_without_the_sidecar(monkeypatch):
    def store_down(days):
        raise RuntimeError("cannot reach postgres")

    monkeypatch.setattr(main.logs, "stt_usage", store_down)
    monkeypatch.setattr(main.settings, "stt_local_url", "")
    out = client.get("/stt/status").json()
    assert out["usage"]["error"] == "cannot reach postgres"
    assert out["local"] == {"url_set": False, "status": "not_configured"}
    # Labelled asymmetrically on purpose: Gemini exposes no quota at all.
    assert out["quota_reporting"]["gemini"] == "none"
    assert set(out["available"]) >= {"gemini", "groq", "local"}


def test_the_sidecar_being_off_is_a_state_not_an_error(monkeypatch):
    import httpx

    monkeypatch.setattr(main.logs, "stt_usage", lambda days: {"engines": []})
    monkeypatch.setattr(main.settings, "stt_local_url", "http://stt-local:8100/")
    monkeypatch.setattr(httpx, "get", lambda url, timeout=0: (_ for _ in ()).throw(
        OSError("connection refused")))
    assert client.get("/stt/status").json()["local"]["status"] == "down"


@pytest.mark.parametrize("status_code,payload,expected", [
    (200, {"status": "ok"}, "ok"),
    (200, {}, "unknown"),
    (503, {}, "down"),
])
def test_the_sidecar_reports_its_own_state(monkeypatch, status_code, payload, expected):
    import types

    import httpx

    monkeypatch.setattr(main.logs, "stt_usage", lambda days: {"engines": []})
    monkeypatch.setattr(main.settings, "stt_local_url", "http://stt-local:8100")
    monkeypatch.setattr(httpx, "get", lambda url, timeout=0: types.SimpleNamespace(
        status_code=status_code, json=lambda: payload))
    assert client.get("/stt/status").json()["local"]["status"] == expected


# --- the mail probe --------------------------------------------------------

def test_the_probe_sends_the_shape_of_a_real_report(monkeypatch):
    sent = {}
    monkeypatch.setattr(main.settings, "smtp_user", "bot@example.com")
    monkeypatch.setattr(main.settings, "smtp_password", "app-password")
    monkeypatch.setattr(main.mailer, "sample_report", lambda to: ("Sujet", "<p>x</p>"))
    monkeypatch.setattr(main.mailer, "send",
                        lambda to, subject, body, html_body=None:
                        sent.update(to=to, subject=subject, html=html_body))
    r = client.post("/notify/test", json={"to": "chef@example.com"})
    assert r.json() == {"sent": True, "to": "chef@example.com"}
    assert sent["to"] == ["chef@example.com"]
    # The plain part stays plain: it is the fallback, and it says outright that
    # the numbers are invented.
    assert sent["html"] == "<p>x</p>"


def test_an_unconfigured_relay_names_the_missing_variables(monkeypatch):
    monkeypatch.setattr(main.settings, "smtp_user", "")
    monkeypatch.setattr(main.settings, "smtp_password", "")
    r = client.post("/notify/test", json={"to": "chef@example.com"})
    assert r.status_code == 422
    assert "SMTP_USER" in r.json()["detail"]


def test_a_relay_refusal_is_a_502_not_the_callers_mistake(monkeypatch):
    monkeypatch.setattr(main.settings, "smtp_user", "bot@example.com")
    monkeypatch.setattr(main.settings, "smtp_password", "app-password")
    monkeypatch.setattr(main.mailer, "sample_report", lambda to: ("S", "<p>x</p>"))
    monkeypatch.setattr(main.mailer, "send", lambda *a, **k: (_ for _ in ()).throw(
        main.mailer.MailError("envoi échoué: 535")))
    assert client.post("/notify/test",
                       json={"to": "chef@example.com"}).status_code == 502


# --- uptime samples --------------------------------------------------------

def test_samples_round_trip(monkeypatch):
    written = {}

    def record(rows):
        written["rows"] = rows
        return len(rows)

    monkeypatch.setattr(main.logs, "record_samples", record)
    monkeypatch.setattr(main.logs, "read_samples", lambda hours: [{"service": "api"}])
    r = client.post("/service-samples",
                    json={"samples": [{"service": "api", "state": "ok"}]})
    assert r.json() == {"written": 1}
    assert written["rows"] == [{"service": "api", "state": "ok"}]
    assert client.get("/service-samples?hours=6").json()["samples"][0]["service"] == "api"


def test_a_store_outage_on_samples_is_a_502(monkeypatch):
    monkeypatch.setattr(main.logs, "record_samples", boom)
    monkeypatch.setattr(main.logs, "read_samples", boom)
    assert client.post("/service-samples", json={"samples": []}).status_code == 502
    assert client.get("/service-samples").status_code == 502


# --- re-styling the spreadsheet -------------------------------------------

def test_formatting_covers_rapports_and_every_site_tab_once(monkeypatch):
    styled = []
    monkeypatch.setattr(main.logs, "list_chantiers", lambda active=False: [
        {"sheet_tab": "DGH"}, {"sheet_tab": "DGH"}, {"sheet_tab": None}])
    monkeypatch.setattr(main.sheets, "style_tab", lambda tab: styled.append(tab))
    out = client.post("/sheets/format").json()
    assert out["tabs"] == [main.sheets.RAPPORTS_TAB, "DGH"]
    assert styled == out["tabs"]


def test_no_chantier_list_is_no_reason_to_leave_rapports_unstyled(monkeypatch):
    monkeypatch.setattr(main.logs, "list_chantiers", boom)
    monkeypatch.setattr(main.sheets, "style_tab", lambda tab: None)
    assert client.post("/sheets/format").json()["tabs"] == [main.sheets.RAPPORTS_TAB]


def test_formatting_is_director_only(as_chef):
    assert client.post("/sheets/format").status_code == 403
