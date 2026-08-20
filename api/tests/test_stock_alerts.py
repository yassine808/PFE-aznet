"""What is about to run out — and the refusal to guess when nothing says.

Every number here is arithmetic, deliberately: a hallucinated shortage becomes a
purchase order and nobody downstream can tell it apart from a real one. So what
these tests pin is not phrasing but the three rules that make the arithmetic
trustworthy:

- the precedence between the three sources, and that the answer says which one
  it used;
- days of cover measured over *active* days, because averaging a two-day-a-week
  crew over seven would quarter every rate and push every warning under its
  threshold;
- silence when nothing is known. A site with no bordereau, no receptions and no
  followed stock produces no findings — a row of zeros there would read as
  "nothing left".

No Sheets and no Postgres: both boundaries are faked.
"""
import pytest

from app import journal, logs, stock

LIMITS = {"jours_critique": 2.0, "jours_bas": 5.0, "pct_critique": 5.0, "pct_bas": 10.0}

CABLE = journal.NUMERIC_COLUMNS["cables_installes_m"]
STOCK_CABLE = journal.STOCK_COLUMNS["stock_cable_m"][0]


def row(date, **cells):
    return {journal.COL_DATE: date, journal.COL_TECHNICIEN: "Yassine", **cells}


# --- the rate -------------------------------------------------------------


def test_pace_averages_over_active_days_not_calendar_days():
    """Monday and Thursday is a two-day pace, not a seven-day one."""
    rows = [row("2026-08-10", **{CABLE: "80"}), row("2026-08-13", **{CABLE: "120"})]
    rate, days = stock.pace(rows)["cables_installes_m"]
    assert (rate, days) == (100.0, 2)


def test_two_technicians_on_one_day_are_one_active_day():
    """The journal is one row per (date, technicien); the pace is per day."""
    rows = [row("2026-08-10", **{CABLE: "80"}),
            {**row("2026-08-10", **{CABLE: "40"}), journal.COL_TECHNICIEN: "Ahmed"}]
    assert stock.pace(rows)["cables_installes_m"] == (120.0, 1)


def test_an_arret_is_never_a_rate():
    """Minutes lost are not an installed quantity — the same exclusion the
    bordereau applies."""
    rows = [row("2026-08-10", **{journal.NUMERIC_COLUMNS["temps_arret_min"]: "90"})]
    assert "temps_arret_min" not in stock.pace(rows)


# --- the precedence chain -------------------------------------------------


def test_followed_stock_wins_and_names_itself():
    reste, source = stock.resolve_stock(
        "cables_installes_m",
        followed={"cables_installes_m": (160.0, "2026-08-14", "Yassine")},
        received={"cables_installes_m": 900.0}, posed=500.0, marche=2000.0,
    )
    assert reste == 160.0
    # Not "déclaré par": reconcile_stock writes the running baseline into that
    # column even on a day nobody counted, so the label credits the row rather
    # than a claim the technician may never have made.
    assert source == "stock relevé sur le chantier au 2026-08-14 (rapport de Yassine)"


def test_ledger_is_next_and_shows_its_arithmetic():
    reste, source = stock.resolve_stock(
        "cables_installes_m", followed={},
        received={"cables_installes_m": 900.0}, posed=500.0, marche=2000.0,
    )
    assert reste == 400.0
    assert source == "calculé : 900 reçus, 500 posés"


def test_marche_is_the_last_resort_and_says_it_is_an_estimate():
    """What the contract still owes is not what is on the pallet, and the label
    must not let a reader mistake one for the other."""
    reste, source = stock.resolve_stock(
        "cables_installes_m", followed={}, received={}, posed=500.0, marche=2000.0,
    )
    assert (reste, source) == (1500.0, "estimé d'après le marché")


def test_nothing_known_returns_nothing_not_zero():
    assert stock.resolve_stock("pigtail_sc_u", {}, {}, None, None) == (None, None)


# --- the thresholds -------------------------------------------------------


def test_days_of_cover_drives_the_level():
    assert stock._level(160.0, 2000.0, (80.0, 5), LIMITS) == ("critique", 2.0)
    assert stock._level(320.0, 2000.0, (80.0, 5), LIMITS)[0] == "bas"
    assert stock._level(800.0, 2000.0, (80.0, 5), LIMITS)[0] is None


def test_one_active_day_is_not_a_rate_and_falls_back_to_the_percentage():
    """An average over a single day is that day's quantity wearing a trend."""
    niveau, jours = stock._level(80.0, 2000.0, (80.0, 1), LIMITS)
    assert jours is None            # no rate was claimed
    assert niveau == "critique"     # 4% of the marché


def test_no_rate_and_no_marche_says_nothing():
    """There is no denominator, so there is no threshold to cross."""
    assert stock._level(80.0, None, None, LIMITS) == (None, None)


# --- one site end to end --------------------------------------------------


@pytest.fixture
def site(monkeypatch):
    def wire(rows, received=None, articles=None):
        from app import logs

        monkeypatch.setattr(stock.sheets, "read_tab", lambda tab: rows)
        monkeypatch.setattr(logs, "received_totals", lambda nom: received or {})
        monkeypatch.setattr(logs, "list_articles", lambda cid: articles or [])
        return stock.assess_chantier({"id": 1, "nom": "DGH", "sheet_tab": "DGH"}, LIMITS)
    return wire


def test_a_site_running_low_is_reported_with_its_provenance(site):
    found = site(
        rows=[row("2026-08-10", **{CABLE: "800"}),
              row("2026-08-13", **{CABLE: "1040", STOCK_CABLE: "160"})],
        articles=[{"champ": "cables_installes_m", "qte_marche": 2000}],
    )
    alert = next(a for a in found if a["champ"] == "cables_installes_m")
    assert alert["niveau"] == "critique"
    assert alert["reste"] == 160.0
    assert alert["article"] == "Câble installé"
    assert alert["unite"] == "m"
    assert "stock relevé" in alert["source"]
    assert "CRITIQUE" in stock.line(alert)
    assert "160 m" in stock.line(alert)


def test_over_the_contract_is_its_own_finding(site):
    """« A lot of merchandise » — either over-consumption or a data error, and
    the director wants to hear about it either way."""
    found = site(
        rows=[row("2026-08-10", **{CABLE: "2100"})],
        articles=[{"champ": "cables_installes_m", "qte_marche": 2000}],
    )
    alert = next(a for a in found if a["champ"] == "cables_installes_m")
    assert alert["niveau"] == "depassement"
    assert alert["reste"] == -100.0
    assert "dépassement du marché de 100 m" in stock.line(alert)


def test_a_site_with_no_bordereau_produces_nothing(site):
    """`مولاي الحسن` has an empty bordereau. Silence, not a row of zeros."""
    assert site(rows=[row("2026-08-10", **{CABLE: "80"})]) == []


def test_a_comfortable_site_produces_nothing(site):
    assert site(
        rows=[row("2026-08-10", **{CABLE: "80"}), row("2026-08-11", **{CABLE: "80"})],
        articles=[{"champ": "cables_installes_m", "qte_marche": 5000}],
    ) == []


def test_one_broken_tab_does_not_cost_the_other_sites(monkeypatch, capsys):
    """A panel that empties when one tab breaks looks exactly like a panel with
    nothing to report."""
    def read(tab):
        if tab == "boom":
            raise RuntimeError("Unable to parse range")
        return []

    monkeypatch.setattr(stock.sheets, "read_tab", read)
    found = stock._collect([{"id": 1, "nom": "KO", "sheet_tab": "boom"},
                            {"id": 2, "nom": "OK", "sheet_tab": "ok"}])
    assert found == []
    assert "KO" in capsys.readouterr().out  # printed, never swallowed


# --- muting: a dismissal that expires by itself ----------------------------


def _muted(monkeypatch, alert, mute):
    """Run one finding through `apply_mutes` against one stored mute."""
    from app import stock as _stock
    monkeypatch.setattr(logs, "list_alert_mutes", lambda: [mute] if mute else [])
    return _stock.apply_mutes([alert])[0]["ignored"]


def _alert(niveau="bas", reste=40.0):
    return {"chantier": "DGH", "champ": "cables_installes_m", "article": "Câble",
            "niveau": niveau, "reste": reste}


def _mute(niveau="bas", reste=40.0):
    return {"chantier": "DGH", "champ": "cables_installes_m",
            "niveau": niveau, "reste": reste}


def test_an_unchanged_finding_stays_dismissed(monkeypatch):
    assert _muted(monkeypatch, _alert(), _mute()) is True


def test_more_stock_does_not_resurface_it(monkeypatch):
    """A delivery landed. The decision ("we ordered it") still holds."""
    assert _muted(monkeypatch, _alert(reste=90.0), _mute(reste=40.0)) is True


def test_less_stock_resurfaces_it(monkeypatch):
    """The one case an ignore must never survive: it got worse."""
    assert _muted(monkeypatch, _alert(reste=12.0), _mute(reste=40.0)) is False


def test_a_worse_level_resurfaces_it(monkeypatch):
    assert _muted(monkeypatch, _alert("critique", 5.0), _mute("bas", 40.0)) is False


def test_another_site_is_not_covered_by_this_mute(monkeypatch):
    other = {**_alert(), "chantier": "ACAPS"}
    assert _muted(monkeypatch, other, _mute()) is False


def test_an_unreadable_mute_table_never_hides_anything(monkeypatch):
    from app import stock as _stock

    def boom():
        raise RuntimeError("postgres down")

    monkeypatch.setattr(logs, "list_alert_mutes", boom)
    assert _stock.apply_mutes([_alert()])[0]["ignored"] is False
