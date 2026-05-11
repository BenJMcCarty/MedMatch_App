import pytest
from src.utils.geocoding import _normalize_address


def test_strips_leading_trailing_whitespace():
    assert _normalize_address("  100 N Charles St  ") == "100 N Charles St"


def test_collapses_internal_whitespace():
    assert _normalize_address("100  N   Charles   St") == "100 N Charles St"


def test_handles_mixed_whitespace():
    assert _normalize_address("100 N Charles St,  Baltimore,  MD  21201") == (
        "100 N Charles St, Baltimore, MD 21201"
    )


def test_empty_string_stays_empty():
    assert _normalize_address("   ") == ""


def test_already_normalized_unchanged():
    addr = "100 N Charles St, Baltimore, MD 21201"
    assert _normalize_address(addr) == addr
