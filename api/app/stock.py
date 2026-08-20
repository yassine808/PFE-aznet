"""Is anything about to run out?

The director's question is not "how much was posed" — the journal already
answers that — but "what do I need to order, and when". This module answers it
from data the pipeline already has, and refuses to answer when it does not.

**Python decides, the model phrases.** Every number here is arithmetic over the
journal, the receptions ledger and the bordereau. The report model is handed
these findings as facts to write French around; it is never asked whether
something is running low, because a hallucinated shortage becomes a purchase
order and nobody downstream can tell it apart from a real one. The model's own
contribution stays qualitative and sourced — see `daily_report`.

**Three sources, ranked, and the answer says which one it used.** Same shape as
`journal.resolve_site` and for the same reason: a figure whose provenance is not
printed cannot be argued with when it is wrong.

    1. the stock followed on the tab   — a human on site counted it
    2. Σ receptions − Σ posé           — the ledger, exact when deliveries are photographed
    3. qte_marche − installé           — what the contract still owes, not what is on the pallet
    4. nothing                         — no warning at all, never a zero

**Days of cover, not a flat percentage.** 10% of 2000 m of cable is two days of
work; 10% of 20 switches is meaningless. The rate comes from the journal itself
— installed per *active* day, not per calendar day, because a crew that works
Monday and Thursday has a pace of two days, not seven, and dividing by seven
would silently push every warning below its threshold. A material with less than
`MIN_ACTIVE_DAYS` of history has no meaningful rate and falls back to the
percentage floor.

A chantier with no bordereau, no receptions and no declared stock produces
nothing. Silence is the honest output there: it has no idea what is on site, and
a row of zeros would read as "nothing left".
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Sequence, Tuple

from app import journal, sheets

# Defaults, overridable per install in `app_settings` without a restart — the
# same contract the report hours follow. Two days is "order today"; five is
# "put it on this week's list".
JOURS_CRITIQUE = 2.0
JOURS_BAS = 5.0
PCT_CRITIQUE = 5.0
PCT_BAS = 10.0

# The other end of the same question. Material on site is money in a chalet and
# a theft risk, so "far more than the work left needs" is worth saying — but
# only as a multiple of the work that remains, because an absolute quantity
# means nothing across metres, brins and switches. Twice what is left to pose
# is the point where it stops looking like ordering ahead.
SURPLUS_FACTEUR = 2.0

# Below this, an average is one number pretending to be a trend: a material
# installed on a single day gives a rate that is just that day's quantity.
MIN_ACTIVE_DAYS = 2

# `GET /alerts` is a dashboard poll and each assessment is a full tab read per
# site. Short enough that a correction shows up while the operator is still
# looking at the screen, long enough that a 30 s poll is not 30 s of Sheets
# quota. The scheduler pays for its own read once a day either way.
CACHE_TTL_SECONDS = 120.0

_cache: Optional[Tuple[float, List[dict]]] = None


def _thresholds() -> Dict[str, float]:
    from app import logs

    try:
        row = logs.get_settings()
    except Exception:  # noqa: BLE001 - an unreachable store must not cost the alerts
        row = {}

    def read(key: str, fallback: float) -> float:
        try:
            return float(row.get(key))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return fallback

    return {
        "jours_critique": read("stock_jours_critique", JOURS_CRITIQUE),
        "jours_bas": read("stock_jours_bas", JOURS_BAS),
        "pct_critique": read("stock_pct_critique", PCT_CRITIQUE),
        "pct_bas": read("stock_pct_bas", PCT_BAS),
        "surplus_facteur": read("stock_surplus_facteur", SURPLUS_FACTEUR),
    }


def followed_stock(rows: Sequence[dict]) -> Dict[str, Tuple[float, str, str]]:
    """The stock the tab follows, keyed by the field it draws down.

    Deliberately not called "declared": `journal.reconcile_stock` writes the
    running baseline into these columns even on a day nobody counted anything,
    so the cell means "stock as of that row", not "someone said this". The
    provenance string below says exactly that and credits the row, not a claim
    the technician may never have made.

    Tab order is append order, so the last row carrying a value wins.
    """
    out: Dict[str, Tuple[float, str, str]] = {}
    for row in rows:
        for _field, (column, consumed) in journal.STOCK_COLUMNS.items():
            value = journal.parse_number(row.get(column))
            if value is not None:
                out[consumed] = (
                    value,
                    str(row.get(journal.COL_DATE) or ""),
                    str(row.get(journal.COL_TECHNICIEN) or ""),
                )
    return out


def pace(rows: Sequence[dict]) -> Dict[str, Tuple[float, int]]:
    """field -> (installed per active day, how many active days).

    Active days only. A crew on site Monday and Thursday has a two-day pace;
    averaging over the seven calendar days between would quarter every rate and
    push every warning quietly under its threshold.
    """
    per_day: Dict[str, Dict[str, float]] = {}
    for row in rows:
        day = journal.norm_date(row.get(journal.COL_DATE)) or str(row.get(journal.COL_DATE) or "")
        for field, column in journal.NUMERIC_COLUMNS.items():
            if field in journal._TOTAL_EXCLUDED:
                continue
            value = journal.parse_number(row.get(column))
            if value:
                days = per_day.setdefault(field, {})
                days[day] = days.get(day, 0.0) + value
    return {
        field: (sum(days.values()) / len(days), len(days))
        for field, days in per_day.items()
        if days
    }


def resolve_stock(
    champ: str,
    followed: Dict[str, Tuple[float, str, str]],
    received: Dict[str, float],
    posed: Optional[float],
    marche: Optional[float],
) -> Tuple[Optional[float], Optional[str]]:
    """How much is left, and where that number came from. Never guesses."""
    if champ in followed:
        value, date, technicien = followed[champ]
        who = f" (rapport de {technicien})" if technicien else ""
        when = f" au {date}" if date else ""
        return value, f"stock relevé sur le chantier{when}{who}"
    if champ in received:
        used = posed or 0.0
        return received[champ] - used, (
            f"calculé : {journal._fmt(received[champ])} reçus, {journal._fmt(used)} posés"
        )
    if marche:
        return float(marche) - (posed or 0.0), "estimé d'après le marché"
    return None, None


def _level(
    reste: float, marche: Optional[float], rate: Optional[Tuple[float, int]],
    limits: Dict[str, float], besoin: Optional[float] = None,
) -> Tuple[Optional[str], Optional[float]]:
    """(niveau, jours de couverture). `None` means nothing worth saying."""
    if rate and rate[1] >= MIN_ACTIVE_DAYS and rate[0] > 0:
        jours = reste / rate[0]
        # Too much, before too little: with the work nearly done a material can
        # be under two days of cover *and* several times what is left to pose,
        # and "commandez-en" would be exactly the wrong sentence. Silence until
        # the crew has a real pace — a site whose whole delivery landed on day
        # one is stocked, not oversupplied, and only the journal can tell the
        # difference. The excess must also be a visible share of the contract,
        # or 2 m over a 1 m remainder becomes an alert.
        if (
            besoin is not None and marche
            # `.get` with the module default, not `[...]`: callers build their
            # own limits dict — the tests do, and so could a future caller —
            # and a new threshold must not turn every one of them into a
            # KeyError the moment it is added.
            and reste > besoin * limits.get("surplus_facteur", SURPLUS_FACTEUR)
            and reste - besoin > float(marche) * limits.get("pct_bas", PCT_BAS) / 100.0
        ):
            return "surplus", jours
        if jours <= limits["jours_critique"]:
            return "critique", jours
        if jours <= limits["jours_bas"]:
            return "bas", jours
        return None, jours
    # No usable rate: fall back to the share of the contract still owed. Without
    # a contract quantity there is no denominator and therefore no threshold —
    # silence rather than a number invented to have something to compare to.
    if not marche:
        return None, None
    pct = reste / float(marche) * 100.0
    if pct <= limits["pct_critique"]:
        return "critique", None
    if pct <= limits["pct_bas"]:
        return "bas", None
    return None, None


def assess_chantier(chantier: dict, limits: Optional[Dict[str, float]] = None) -> List[dict]:
    """Every material on one site that needs saying something about."""
    from app import logs

    limits = limits or _thresholds()
    rows = sheets.read_tab(chantier["sheet_tab"])
    installed = journal.totals(rows)
    followed = followed_stock(rows)
    rates = pace(rows)
    try:
        received = logs.received_totals(chantier["nom"])
        articles = {
            a["champ"]: a for a in logs.list_articles(chantier["id"]) if a.get("champ")
        }
    except Exception:  # noqa: BLE001 - a site still gets its journal-only view
        received, articles = {}, {}

    out: List[dict] = []
    for champ in sorted(set(articles) | set(received) | set(followed)):
        label, unit = journal.article_label(champ)
        posed = installed.get(champ)
        marche = articles.get(champ, {}).get("qte_marche")
        marche = float(marche) if marche else None
        # What the contract still owes: the yardstick a surplus is measured
        # against. Unknown without a bordereau, and it stays None there rather
        # than becoming a zero that would make every leftover an excédent.
        besoin = marche - (posed or 0.0) if marche else None
        common = {
            "chantier": chantier["nom"], "champ": champ, "article": label,
            "unite": unit, "installe": posed, "marche": marche, "besoin": besoin,
        }

        # Over the contract is its own finding and does not depend on knowing
        # the stock: it is either over-consumption or a data error, and the
        # director wants to hear about it either way. "A lot of merchandise."
        if marche and posed and posed > marche:
            out.append({
                **common, "niveau": "depassement",
                "reste": marche - posed, "jours": None,
                "rythme": rates.get(champ, (None, 0))[0],
                "source": f"{journal._fmt(posed)} posés pour {journal._fmt(marche)} au marché",
            })
            continue

        reste, source = resolve_stock(champ, followed, received, posed, marche)
        if reste is None:
            continue
        niveau, jours = _level(reste, marche, rates.get(champ), limits, besoin)
        if niveau is None:
            continue
        out.append({
            **common, "niveau": niveau, "reste": reste, "jours": jours,
            "rythme": rates.get(champ, (None, 0))[0], "source": source,
        })

    return out


_ORDER = {"depassement": 0, "critique": 1, "bas": 2, "surplus": 3}


def assess(chantiers: Optional[Sequence[dict]] = None) -> List[dict]:
    """Every site's findings, worst first. TTL-cached for the dashboard poll."""
    global _cache
    from app import logs

    if chantiers is None:
        now = time.monotonic()
        if _cache is not None and now - _cache[0] < CACHE_TTL_SECONDS:
            return list(_cache[1])
        try:
            chantiers = [c for c in logs.list_chantiers() if c.get("active", True)]
        except Exception:  # noqa: BLE001
            chantiers = []
        found = _collect(chantiers)
        _cache = (time.monotonic(), found)
        return list(found)
    return _collect(chantiers)


def _collect(chantiers: Sequence[dict]) -> List[dict]:
    found: List[dict] = []
    for chantier in chantiers:
        try:
            found.extend(assess_chantier(chantier))
        except Exception as exc:  # noqa: BLE001
            # One unreadable tab must not cost every other site its alerts —
            # and it is printed rather than swallowed, because a site that
            # silently stops being assessed looks exactly like a site with
            # nothing wrong.
            print(f"[stock] {chantier.get('nom')}: {exc}")
    return sorted(
        found,
        key=lambda a: (_ORDER.get(a["niveau"], 9), a["jours"] if a["jours"] is not None else 1e9),
    )


#: Worst first. Used to decide whether a muted finding has got worse — a
#: `bas` that became `critique` is a different fact and must be heard again.
_SEVERITY = {"depassement": 0, "critique": 1, "bas": 2, "surplus": 3}


def apply_mutes(alerts: Sequence[dict]) -> List[dict]:
    """Mark each finding `ignored`, rather than dropping the muted ones.

    Nothing is removed from the payload. The dashboard hides an ignored line
    from the panel that shouts and keeps it reachable in the full list, which
    is the difference between "we have dealt with this" and "this stopped
    existing" — and it is what lets somebody un-ignore a line they cannot see.

    A mute expires by itself: it holds only while the level is the one that was
    dismissed and the remainder has not fallen below what it was when the
    decision was taken. Any worsening surfaces the alert again, so an ignore
    can never bury a shortage that got worse. A missing remainder on either
    side is not treated as a change — `None` means "not known", and a mute must
    not evaporate because a tab briefly stopped reporting a figure.
    """
    from app import logs

    try:
        mutes = {(m["chantier"], m["champ"]): m for m in logs.list_alert_mutes()}
    except Exception as exc:  # noqa: BLE001 — a panel is not worth a 502
        print(f"[stock] list_alert_mutes failed: {exc}"[:200], flush=True)
        mutes = {}

    out: List[dict] = []
    for a in alerts:
        m = mutes.get((a["chantier"], a["champ"]))
        out.append({**a, "ignored": bool(m) and not _worse_than(a, m)})
    return out


def _worse_than(alert: dict, mute: dict) -> bool:
    """Has this finding deteriorated since somebody dismissed it?"""
    if _SEVERITY.get(alert["niveau"], 9) < _SEVERITY.get(mute["niveau"], 9):
        return True
    if alert["niveau"] != mute["niveau"]:
        # Improved, or a different kind of finding entirely. Either way the
        # decision was taken about something else.
        return True
    left, was = alert.get("reste"), mute.get("reste")
    if left is None or was is None:
        return False
    return float(left) < float(was)


def alerts_for_rows(rows: Sequence[dict]) -> List[dict]:
    """The findings for the sites a report actually covers.

    A chef's report must not carry another crew's shortages, and the company
    digest should not list a site nobody worked this period.
    """
    from app import logs

    names = {str(r.get("chantier") or "").strip() for r in rows} - {""}
    if not names:
        return []
    try:
        chantiers = [c for c in logs.list_chantiers() if c["nom"] in names]
    except Exception:  # noqa: BLE001
        return []
    return _collect(chantiers)


def line(alert: dict) -> str:
    """One finding as a sentence, for the prompt and for a log.

    The unit and the source travel with the number on purpose: this string is
    what the report model is allowed to paraphrase, and a figure handed over
    without its provenance is one the model will present as certain.
    """
    reste = journal._fmt(abs(alert["reste"])) if alert["reste"] is not None else "?"
    unit = f" {alert['unite']}" if alert["unite"] else ""
    if alert["niveau"] == "depassement":
        return (
            f"{alert['chantier']} — {alert['article']} : dépassement du marché de "
            f"{reste}{unit} ({alert['source']})"
        )
    if alert["niveau"] == "surplus":
        besoin = journal._fmt(alert["besoin"]) if alert.get("besoin") is not None else "?"
        return (
            f"{alert['chantier']} — {alert['article']} [EXCÉDENT] : reste {reste}{unit} "
            f"sur le chantier pour {besoin}{unit} restant à poser ({alert['source']})"
        )
    couverture = (
        f", {alert['jours']:.1f} jour(s) de couverture au rythme actuel"
        if alert["jours"] is not None else ""
    )
    niveau = "CRITIQUE" if alert["niveau"] == "critique" else "BAS"
    return (
        f"{alert['chantier']} — {alert['article']} [{niveau}] : reste {reste}{unit}"
        f"{couverture} ({alert['source']})"
    )
