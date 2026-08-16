"""Material received, kept apart from material installed.

`extraction-image.md` told the vision model to read a bon de livraison into the
*installed* article columns, so 500 m of cable delivered was booked as 500 m
posed — inflating the exact number the bordereau's `avancement` and every stock
figure are computed from. It was latent only because no article column had a
value in it yet.

What has to hold, and is tested here:

- a delivery is keyed by the same field vocabulary as an installed quantity, and
  an article the schema does not know **raises** rather than being ledgered
  against nothing;
- a delivery writes **no journal row** — merged in, it would double-count as
  work done;
- a message that declares both a delivery and a day's work loses neither;
- replaying one message does not ledger it twice, because n8n retries and the
  drain replays parked payloads.

No Postgres and no Sheets: both boundaries are faked, the same way the rest of
the suite treats them.
"""
import pytest

from app import journal
from app.schemas import DELIVERABLE_FIELDS, ExtractedReport


def rep(**kw):
    kw.setdefault("resume", "Résumé.")
    return ExtractedReport(**kw)


# --- schema ---------------------------------------------------------------


def test_livraisons_uses_the_installed_field_vocabulary():
    report = rep(nature="livraison", livraisons={"cables_installes_m": 500, "pigtail_sc_u": 24})
    assert report.livraisons == {"cables_installes_m": 500.0, "pigtail_sc_u": 24.0}
    # And the posed columns stay empty: that is the whole point.
    assert report.cables_installes_m is None


def test_unknown_article_raises_instead_of_being_dropped():
    """A ledger line nobody can join to a contract line under-reports silently.

    Same rule as an unrecognized étage: raise, let the extraction chain retry.
    """
    with pytest.raises(ValueError, match="article inconnu"):
        rep(nature="livraison", livraisons={"cable_magique_m": 10})


def test_an_arret_cannot_be_delivered():
    """Minutes lost are not merchandise; no supplier delivers them."""
    assert "temps_arret_min" not in DELIVERABLE_FIELDS
    with pytest.raises(ValueError, match="article inconnu"):
        rep(nature="livraison", livraisons={"temps_arret_min": 90})


def test_zero_and_null_lines_are_dropped_not_ledgered():
    assert rep(nature="livraison", livraisons={"pigtail_sc_u": 0}).livraisons is None


def test_a_delivery_is_a_report():
    """Without this the pipeline files it `no_report_content` and the delivery
    disappears into `exchanges` with no row and no ledger line."""
    assert rep(nature="livraison", livraisons={"pigtail_sc_u": 24}).has_data()
    # And nature alone is not data — a photo the model merely labelled is not a
    # reception until it carries a quantity.
    assert not rep(nature="livraison").has_data()


def test_absent_nature_is_still_a_pose():
    """Every existing row, every voice note, every photo of a wall is unchanged.
    A delivery is only ever a delivery because the model positively said so."""
    assert rep(cables_installes_m=80).nature is None


# --- routing --------------------------------------------------------------


class _Ledger:
    def __init__(self):
        self.calls = []

    def record_receptions(self, chantier, champs, date, **kw):
        self.calls.append((chantier, dict(champs), date, kw))
        return len(champs)

    def write_safe(self, *a, **kw):
        pass


@pytest.fixture
def wired(monkeypatch):
    """journal with its two boundaries faked: the ledger and the Sheet."""
    from app import logs

    ledger = _Ledger()
    appended = []
    # `file_livraison` does `from app import logs`, which hands back the real
    # module object — so the functions are patched on it, not the name swapped.
    monkeypatch.setattr(logs, "record_receptions", ledger.record_receptions)
    monkeypatch.setattr(logs, "write_safe", ledger.write_safe)
    monkeypatch.setattr(journal, "resolve_site",
                        lambda tech, spoken=None, create=True: ("DGH", "DGH", [], "org"))
    monkeypatch.setattr(journal.sheets, "ensure_tab", lambda *a, **k: None)
    monkeypatch.setattr(journal.sheets, "append_row",
                        lambda tab, values, headers: appended.append((tab, values)))
    return ledger, appended


def test_a_delivery_writes_no_journal_row(wired, monkeypatch):
    ledger, appended = wired
    # If the journal path were taken at all, this would blow up loudly.
    monkeypatch.setattr(journal, "write_report", _boom)

    out = journal.file_report({
        "technicien": "Yassine", "date": "2026-08-16", "canal": "whatsapp",
        "correlation_id": "wamid.1",
        "report": rep(nature="livraison", livraisons={"cables_installes_m": 500}),
    })

    assert out["livraison"] is True
    assert out["row"] is None and out["rapports_row"] is None
    assert ledger.calls[0][0] == "DGH"
    assert ledger.calls[0][1] == {"cables_installes_m": 500.0}
    # Mirrored to the flat Livraisons tab with the director's own label.
    tab, values = appended[0]
    assert tab == journal.LIVRAISONS_TAB
    assert values["Article"] == "Câble installé"
    assert values["Quantité"] == "500" and values["Unité"] == "m"


def test_a_sheet_failure_never_costs_the_reception(wired, monkeypatch):
    """Postgres is the ledger; the tab is a mirror, on the same contract as the
    Rapports mirror. The balance is computed from the ledger, so a tab Google
    refuses must not take the delivery down with it."""
    ledger, _ = wired
    monkeypatch.setattr(journal.sheets, "ensure_tab", _boom)

    out = journal.file_report({
        "technicien": "Yassine", "date": "2026-08-16",
        "report": rep(nature="livraison", livraisons={"pigtail_sc_u": 24}),
    })
    assert out["livraison"] is True
    assert ledger.calls  # ledgered before the mirror was even attempted


def test_a_message_carrying_both_loses_neither(wired, monkeypatch):
    """« On a reçu 500 m et on a posé 80 » is two facts, not one."""
    ledger, _ = wired
    written = {}

    def fake_write(tab, date, tech, chantier, report, meta, known, rows):
        written["posed"] = report.cables_installes_m
        return 7, []

    monkeypatch.setattr(journal, "write_report", fake_write)
    monkeypatch.setattr(journal, "resolve_tab",
                        lambda tech, spoken=None: ("DGH", "DGH", []))
    monkeypatch.setattr(journal.sheets, "read_tab", lambda tab: [])
    monkeypatch.setattr(journal, "_mirror_rapports", lambda *a: 12)

    out = journal.file_report({
        "technicien": "Yassine", "date": "2026-08-16",
        # nature stays null: the day's work is still a pose.
        "report": rep(cables_installes_m=80, livraisons={"cables_installes_m": 500}),
    })

    assert written["posed"] == 80          # the journal row is the work done
    assert out["row"] == 7
    assert ledger.calls[0][1] == {"cables_installes_m": 500.0}   # and the ledger has the delivery
    assert out["livraison"]["lignes"] == 1


def _boom(*a, **kw):
    raise AssertionError("this path must not be taken for a delivery")
