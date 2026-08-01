"""Phone-number canonicalization for the technician directory.

One form — 12 digits, `2126…`/`2127…` — so the dedupe guard and the directory
lookup match a number no matter how the operator keyed it in.
"""
import pytest

from app.logs import normalize_external_id


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+212661234567", "212661234567"),
        ("+212 6 61 23 45 67", "212661234567"),
        ("0661234567", "212661234567"),
        ("661234567", "212661234567"),
        ("00212661234567", "212661234567"),
        ("+212 (0) 661-234-567", "212661234567"),
        ("706123456", "212706123456"),
        ("+212706123456", "212706123456"),
        ("212661234567", "212661234567"),
    ],
)
def test_whatsapp_phone_variants_are_canonical(raw, expected):
    assert normalize_external_id("whatsapp", raw) == expected


def test_telegram_ids_are_never_touched():
    assert normalize_external_id("telegram", "+212661234567") == "+212661234567"
    assert normalize_external_id("telegram", "-1001234567890") == "-1001234567890"


def test_unrecognizable_input_is_left_as_is():
    assert normalize_external_id("whatsapp", "abc") == "abc"
