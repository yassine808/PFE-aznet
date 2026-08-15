"""A1 ranges quote the tab name.

`Non affecté` — the documented fallback tab for an unrouted technician — is an
invalid A1 range unquoted, so every write for a sender with no chef used to 400
out of Google, park in `failed_writes` and fail identically on every drain.
"""
from app.sheets import _a1


def test_tab_with_a_space_is_quoted():
    assert _a1("Non affecté", "1:1") == "'Non affecté'!1:1"


def test_bare_tab_range_is_quoted_too():
    assert _a1("Non affecté") == "'Non affecté'"


def test_apostrophe_in_a_tab_name_is_doubled():
    assert _a1("Chantier d'Anfa", "A2") == "'Chantier d''Anfa'!A2"
