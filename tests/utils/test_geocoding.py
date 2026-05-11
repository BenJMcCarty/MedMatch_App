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


import pandas as pd
from src.utils.geocoding import geocode_provider_dataframe


def _provider_df(**overrides):
    defaults = {
        "Full Address": ["100 N Charles St, Baltimore, MD 21201"],
        "Full Name": ["Dr. Test"],
        "latitude": [39.29],
        "longitude": [-76.61],
        "geocode_source": ["cms"],
        "geocode_verified_at": [None],
    }
    defaults.update(overrides)
    return pd.DataFrame(defaults)


def test_geocode_provider_dataframe_skips_nominatim_rows():
    df = _provider_df(geocode_source=["nominatim"])
    call_count = [0]

    def fake_geocoder():
        def geocode(addr, timeout=10):
            call_count[0] += 1
            loc = MagicMock()
            loc.latitude = 99.0
            loc.longitude = 99.0
            return loc
        return geocode

    with patch("src.utils.geocoding._get_rate_limited_geocoder", fake_geocoder):
        result = geocode_provider_dataframe(df, force=False)

    assert call_count[0] == 0
    assert result.loc[0, "latitude"] == pytest.approx(39.29)


def test_geocode_provider_dataframe_force_regeocodesall():
    df = _provider_df(geocode_source=["nominatim"])
    call_count = [0]

    def fake_geocoder():
        def geocode(addr, timeout=10):
            call_count[0] += 1
            loc = MagicMock()
            loc.latitude = 40.0
            loc.longitude = -77.0
            return loc
        return geocode

    with patch("src.utils.geocoding._get_rate_limited_geocoder", fake_geocoder):
        result = geocode_provider_dataframe(df, force=True)

    assert call_count[0] == 1
    assert result.loc[0, "latitude"] == pytest.approx(40.0)
    assert result.loc[0, "geocode_source"] == "nominatim"


def test_geocode_provider_dataframe_updates_coords_on_success():
    df = _provider_df(latitude=[0.0], longitude=[0.0])

    def fake_geocoder():
        def geocode(addr, timeout=10):
            loc = MagicMock()
            loc.latitude = 39.29
            loc.longitude = -76.61
            return loc
        return geocode

    with patch("src.utils.geocoding._get_rate_limited_geocoder", fake_geocoder):
        result = geocode_provider_dataframe(df)

    assert result.loc[0, "latitude"] == pytest.approx(39.29)
    assert result.loc[0, "longitude"] == pytest.approx(-76.61)
    assert result.loc[0, "geocode_source"] == "nominatim"
    assert result.loc[0, "geocode_verified_at"] is not None


def test_geocode_provider_dataframe_sets_cms_on_none():
    df = _provider_df()

    with patch("src.utils.geocoding._get_rate_limited_geocoder", lambda: (lambda addr, timeout=10: None)):
        result = geocode_provider_dataframe(df)

    assert result.loc[0, "geocode_source"] == "cms"
    assert result.loc[0, "latitude"] == pytest.approx(39.29)


def test_geocode_provider_dataframe_sets_failed_on_exception():
    df = _provider_df()

    def fake_geocoder():
        def raise_timeout(addr, timeout=10):
            raise GeocoderTimedOut("timeout")
        return raise_timeout

    with patch("src.utils.geocoding._get_rate_limited_geocoder", fake_geocoder):
        result = geocode_provider_dataframe(df)

    assert result.loc[0, "geocode_source"] == "failed"
    assert result.loc[0, "latitude"] == pytest.approx(39.29)


def test_geocode_provider_dataframe_initializes_missing_columns():
    df = pd.DataFrame({
        "Full Address": ["100 N Charles St, Baltimore, MD 21201"],
        "Full Name": ["Dr. Test"],
        "latitude": [39.29],
        "longitude": [-76.61],
    })

    with patch("src.utils.geocoding._get_rate_limited_geocoder", lambda: (lambda addr, timeout=10: None)):
        result = geocode_provider_dataframe(df)

    assert "geocode_source" in result.columns
    assert "geocode_verified_at" in result.columns
