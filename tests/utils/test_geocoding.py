import pytest
from unittest.mock import MagicMock, patch
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from src.utils.geocoding import _normalize_address, geocode_address


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


def _make_location(lat, lon):
    loc = MagicMock()
    loc.latitude = lat
    loc.longitude = lon
    return loc


def test_geocode_address_returns_lat_lon():
    with patch("src.utils.geocoding._get_rate_limited_geocoder") as mock_factory:
        mock_factory.return_value = lambda addr, timeout=10: _make_location(39.29, -76.61)
        result = geocode_address("100 N Charles St, Baltimore, MD 21201")
    assert result == pytest.approx((39.29, -76.61))


def test_geocode_address_returns_none_when_not_found():
    with patch("src.utils.geocoding._get_rate_limited_geocoder") as mock_factory:
        mock_factory.return_value = lambda addr, timeout=10: None
        result = geocode_address("zzzz not a real address")
    assert result is None


def test_geocode_address_normalizes_before_lookup():
    """Extra whitespace is collapsed before the API call."""
    received = []

    def capture(addr, timeout=10):
        received.append(addr)
        return _make_location(39.29, -76.61)

    with patch("src.utils.geocoding._get_rate_limited_geocoder") as mock_factory:
        mock_factory.return_value = capture
        geocode_address("  100 N Charles St  ,  Baltimore  ,  MD  21201  ")

    assert received[0] == "100 N Charles St , Baltimore , MD 21201"


def test_geocode_address_returns_none_on_timeout():
    def raise_timeout(addr, timeout=10):
        raise GeocoderTimedOut("timeout")

    with patch("src.utils.geocoding._get_rate_limited_geocoder") as mock_factory:
        mock_factory.return_value = raise_timeout
        result = geocode_address("100 N Charles St, Baltimore, MD 21201")
    assert result is None


def test_geocode_address_returns_none_on_service_error():
    def raise_service_error(addr, timeout=10):
        raise GeocoderServiceError("unavailable")

    with patch("src.utils.geocoding._get_rate_limited_geocoder") as mock_factory:
        mock_factory.return_value = raise_service_error
        result = geocode_address("100 N Charles St, Baltimore, MD 21201")
    assert result is None
