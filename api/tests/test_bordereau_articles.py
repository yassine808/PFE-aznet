"""The bordereau article fields: schema, journal columns, and the seeds.

The 25 article fields exist so the contract line items each site is delivered
against stop being followed by hand. Three things have to hold or the
bordereau's `qte_installee` becomes wrong in a way nobody notices:

- an article's `champ` must name a real schema field (a typo maps a whole
  contract line to nothing, silently, forever);
- two articles on the same site must not share a `champ`, or one day's work is
  counted twice in the same total;
- the fields must accumulate like every other numeric column, because a second
  voice note the same day is normal and a replace would lose the first.

No Sheets, no Postgres — the seeds are module constants and the merge is pure.
"""
import pytest

from app.journal import (
    ARTICLE_COLUMNS,
    HEADERS,
    NUMERIC_COLUMNS,
    RAPPORTS_COLUMNS,
    _rapports_cells,
    merge_rows,
    quantity_columns,
    report_cells,
)
from app.logs import _SEEDS_BY_CHANTIER
from app.schemas import ARTICLE_FIELDS, DATA_FIELDS, QUANTITY_FIELDS, ExtractedReport


def rep(**kw):
    kw.setdefault("resume", "Résumé.")
    return ExtractedReport(**kw)


# --- schema ---------------------------------------------------------------


def test_every_article_field_exists_on_the_model():
    missing = [f for f in ARTICLE_FIELDS if f not in ExtractedReport.model_fields]
    assert missing == []


def test_article_fields_count_as_data():
    """A note that only reports material posed is still a report."""
    assert set(ARTICLE_FIELDS) <= set(DATA_FIELDS)
    assert rep(pigtail_sc_u=36).has_data() is True


def test_a_greeting_is_still_not_a_report():
    """The 25 new nullable fields must not weaken the has_data gate."""
    assert rep().has_data() is False


def test_counted_articles_reject_a_negative():
    with pytest.raises(ValueError):
        rep(onduleur_u=-1)


def test_absent_article_is_none_not_zero():
    assert rep(pigtail_sc_u=36).onduleur_u is None


# --- journal columns ------------------------------------------------------


def test_article_columns_are_in_the_header_and_unique():
    assert len(HEADERS) == len(set(HEADERS))
    for column in ARTICLE_COLUMNS.values():
        assert column in HEADERS


def test_articles_sit_after_the_directors_own_columns():
    """His part of the tab has to read like the file he already knows."""
    assert HEADERS.index("Goulotte installée") < HEADERS.index("Pigtail SC")


def test_every_article_field_has_a_journal_column():
    assert set(ARTICLE_FIELDS) <= set(NUMERIC_COLUMNS)


def test_every_article_field_reaches_the_rapports_mirror():
    assert set(ARTICLE_FIELDS) <= set(RAPPORTS_COLUMNS)


def test_every_data_field_reaches_the_rapports_mirror():
    """The mirror map is derived from the schema, so nothing can be left out.

    Kept by hand it silently dropped eight fields — fibre, tested sockets,
    prepared cable, interconnections, optical strands, the three location lists
    and the three stock columns. Their columns exist in the live Rapports tab
    and every one of them was empty, so the dashboard and every report built on
    it were structurally blind to that work.
    """
    assert set(DATA_FIELDS) == set(RAPPORTS_COLUMNS)


def test_location_lists_reach_the_mirror_as_text():
    cells = _rapports_cells({"report": rep(etages=["E1", "E2"], fibre_m=120)}, "DGH", [])
    assert cells["etages"] == "E1, E2"
    assert cells["fibre_m"] == 120
    # An empty list is absence. Written through, it puts a literal "[]" in the
    # cell, which reads as data to anyone scanning the column.
    assert "ailes" not in cells


def test_quantity_fields_match_the_journal_columns():
    """`schemas.QUANTITY_FIELDS` exists because `journal` imports `schemas` and
    not the other way round. Two lists of the same 35 names drift; this pins
    them, so an article added to one and forgotten in the other fails here."""
    assert tuple(QUANTITY_FIELDS) == tuple(NUMERIC_COLUMNS)


def test_quantity_catalogue_is_one_row_per_column_with_its_unit():
    catalogue = quantity_columns()
    columns = [column for column, _label, _unit in catalogue]
    assert len(columns) == len(set(columns)) == len(NUMERIC_COLUMNS)
    units = {label: unit for _column, label, unit in catalogue}
    assert units["Fibre installée"] == "m"
    assert units["Pigtail SC"] == "u"
    # A label that already carries its unit gets none appended, or the cell
    # would read "8 (ml) m". `_min` is matched before `_m`, so an arrêt in
    # minutes is not reported in metres.
    assert units["Câble élec 3x2,5 (ml)"] == ""
    assert units["Arrêt (min)"] == ""
    # A count has no unit at all.
    assert units["Connexion des prises informatiques"] == ""


def test_article_quantity_lands_in_its_column():
    cells = report_cells(rep(pigtail_sc_u=36, cable_elec_3x2_5_m=8))
    assert cells["Pigtail SC"] == "36"
    assert cells["Câble élec 3x2,5 (ml)"] == "8"


def test_unmentioned_article_writes_no_cell():
    cells = report_cells(rep(pigtail_sc_u=36))
    assert "Onduleur" not in cells


def test_articles_accumulate_across_two_notes_the_same_day():
    """Two messages, one row: 36 then 12 pigtails is 48, not 12."""
    merged = merge_rows({"Pigtail SC": "36"}, {"Pigtail SC": "12"})
    assert merged["Pigtail SC"] == "48"


# --- seeds ----------------------------------------------------------------


@pytest.mark.parametrize("nom", sorted(_SEEDS_BY_CHANTIER))
def test_seed_champ_names_a_real_field(nom):
    champs = [row[4] for row in _SEEDS_BY_CHANTIER[nom] if row[4]]
    unknown = [c for c in champs if c not in ExtractedReport.model_fields]
    assert unknown == []


@pytest.mark.parametrize("nom", sorted(_SEEDS_BY_CHANTIER))
def test_no_two_articles_on_a_site_share_a_champ(nom):
    """Two lines drawing on one field would double-count the same day's work."""
    champs = [row[4] for row in _SEEDS_BY_CHANTIER[nom] if row[4]]
    assert len(champs) == len(set(champs))


@pytest.mark.parametrize("nom", sorted(_SEEDS_BY_CHANTIER))
def test_seed_rows_match_the_insert_arity(nom):
    """(numero, designation, unite, qte_marche, champ, tache) — the INSERT
    binds seven columns counting chantier_id, so a short row fails at boot."""
    for row in _SEEDS_BY_CHANTIER[nom]:
        assert len(row) == 6, row


@pytest.mark.parametrize("nom", sorted(_SEEDS_BY_CHANTIER))
def test_designations_are_unique_per_site(nom):
    """UNIQUE (chantier_id, designation): a duplicate would be dropped by the
    ON CONFLICT and the article would silently never exist."""
    names = [row[1] for row in _SEEDS_BY_CHANTIER[nom]]
    assert len(names) == len(set(names))


def test_only_acaps_carries_a_tache():
    """DGH and Extralait are flat lists; NULL there means 'no grouping',
    not 'grouping unknown'."""
    for nom in ("DGH", "Extralait"):
        assert all(row[5] is None for row in _SEEDS_BY_CHANTIER[nom])
    assert all(row[5] is not None for row in _SEEDS_BY_CHANTIER["ACAPS"])


def test_unbudgeted_article_has_no_contract_quantity():
    """ACAPS used jarretières and goulotte that the Besoin column never
    budgeted. None means 'hors marché'; 0 would render as a 100% overrun."""
    acaps = {row[1]: row[3] for row in _SEEDS_BY_CHANTIER["ACAPS"]}
    assert acaps["Jarretier SC/LC"] is None
    assert acaps["Goulotte 100*45"] is None
    assert acaps["Cable UTP"] == 720


# --- why a row is flagged --------------------------------------------------
#
# The flag column was a bare TRUE: it told a reader something was wrong and not
# what, so the cheapest response to a flagged row was to believe it anyway.


def test_flag_reason_is_human_readable():
    from app.journal import flag_reason
    assert flag_reason(["chantier_cree_non_verifie"]) == "Chantier non confirmé"


def test_flag_reason_keeps_order_and_deduplicates():
    from app.journal import flag_reason
    got = flag_reason(["image_input", "image_input", "photo_zones_partielles"])
    assert got == "Lu sur une photo · Zones lues sur une photo : la liste peut être incomplète"


def test_an_unlabelled_warning_falls_through_by_name():
    """A reason nobody wrote a label for still beats a blank cell — a silent
    omission here hides exactly what the column exists for."""
    from app.journal import flag_reason
    assert flag_reason(["quelque_chose_de_neuf"]) == "quelque_chose_de_neuf"


def test_a_warning_with_a_payload_is_labelled_by_its_key():
    """`stock_ecart:-40` carries its delta; the label is about the kind."""
    from app.journal import flag_reason
    assert flag_reason(["stock_ecart:-40"]) == "Écart de stock"


def test_a_clean_row_has_no_reason():
    from app.journal import flag_reason
    assert flag_reason([]) == ""


def test_the_motif_column_sits_next_to_the_flag():
    from app.journal import COL_FLAG, COL_MOTIF_FLAG, HEADERS
    assert HEADERS.index(COL_MOTIF_FLAG) == HEADERS.index(COL_FLAG) + 1
