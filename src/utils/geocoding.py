"""Geocoding helpers with caching and rate limiting."""
import re
from typing import Any, Optional, Tuple

import pandas as pd

import streamlit as st
from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
from geopy.geocoders import Nominatim

# Cached factory
_RATE_LIMITED_GEOCODER = None


def _normalize_address(address: str) -> str:
    """Collapse whitespace for consistent geocoder cache keys."""
    return re.sub(r"\s+", " ", address.strip())


def _get_rate_limited_geocoder(min_delay_seconds: float = 1.0, max_retries: int = 3):
    global _RATE_LIMITED_GEOCODER
    if _RATE_LIMITED_GEOCODER is not None:
        return _RATE_LIMITED_GEOCODER

    try:
        from geopy.extra.rate_limiter import RateLimiter

        geolocator = Nominatim(user_agent="provider_recommender")
        rate_limited = RateLimiter(geolocator.geocode, min_delay_seconds=min_delay_seconds, max_retries=max_retries)

        def geocode_fn(q, timeout=10):
            return rate_limited(q, timeout=timeout)

        _RATE_LIMITED_GEOCODER = geocode_fn
        return _RATE_LIMITED_GEOCODER
    except Exception:

        def fallback(q, timeout=10):
            geolocator = Nominatim(user_agent="provider_recommender")
            return geolocator.geocode(q)

        _RATE_LIMITED_GEOCODER = fallback
        return _RATE_LIMITED_GEOCODER


def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """Geocode an address; returns (lat, lon) or None. Cached 24hr.

    Normalizes whitespace before lookup so minor formatting differences
    hit the same cache entry.
    """
    return _geocode_address_cached(_normalize_address(address))


@st.cache_data(ttl=60 * 60 * 24)
def _geocode_address_cached(normalized: str) -> Optional[Tuple[float, float]]:
    try:
        geocode_fn = _get_rate_limited_geocoder()
        location = geocode_fn(normalized)
        if location:
            return location.latitude, location.longitude
        return None
    except (GeocoderTimedOut, GeocoderServiceError):
        st.warning("Geocoding service temporarily unavailable. Please try again.")
        return None
    except Exception as e:
        st.error(f"Error geocoding address: {str(e)}")
        return None


def handle_geocoding_error(address: str, error: Exception) -> str:
    et = str(error).lower()
    if "timeout" in et:
        return "⏱️ **Geocoding Timeout**: The address lookup service is taking too long. Please try again in a moment."
    if "unavailable" in et or "service" in et:
        return "🔌 **Service Unavailable**: The geocoding service is temporarily unavailable. Please try again later."
    if "rate" in et or "limit" in et:
        return "🚦 **Rate Limited**: Too many requests to the geocoding service. Please wait a moment and try again."
    if "network" in et or "connection" in et:
        return "🌐 **Network Error**: Cannot connect to the geocoding service. Please check your internet connection."
    return f"❌ **Geocoding Error**: Unable to find location for '{address}'. (Error: {type(error).__name__})"


def geocode_provider_dataframe(
    df: pd.DataFrame,
    force: bool = False,
    progress_callback=None,
) -> pd.DataFrame:
    """Geocode provider Full Address values and annotate with source/timestamp.

    For each row (skipping geocode_source=='nominatim' rows unless force=True):
      - Nominatim returns location → update latitude/longitude, source='nominatim'
      - Nominatim returns None     → keep existing coords, source='cms'
      - Nominatim raises exception → keep existing coords, source='failed'
    geocode_verified_at is set to the current UTC timestamp in all processed rows.

    Args:
        df: DataFrame with 'Full Address', 'latitude', 'longitude' columns.
        force: Re-geocode rows already marked 'nominatim' when True.
        progress_callback: Optional callable(current, total, name, source).

    Returns:
        Copy of df with updated latitude, longitude, geocode_source, geocode_verified_at.
    """
    from datetime import datetime, timezone

    result = df.copy()
    if "geocode_source" not in result.columns:
        result["geocode_source"] = "cms"
    if "geocode_verified_at" not in result.columns:
        result["geocode_verified_at"] = None

    geocode_fn = _get_rate_limited_geocoder()
    total = len(result)

    for i, (idx, row) in enumerate(result.iterrows()):
        if not force and row.get("geocode_source") == "nominatim":
            if progress_callback:
                progress_callback(i + 1, total, str(row.get("Full Name", "")), "nominatim")
            continue

        address = str(row.get("Full Address", "")).strip()
        now = datetime.now(timezone.utc).isoformat()

        if not address:
            result.at[idx, "geocode_source"] = "failed"
            result.at[idx, "geocode_verified_at"] = now
            if progress_callback:
                progress_callback(i + 1, total, str(row.get("Full Name", "")), "failed")
            continue

        try:
            location = geocode_fn(_normalize_address(address))
            if location:
                result.at[idx, "latitude"] = location.latitude
                result.at[idx, "longitude"] = location.longitude
                source = "nominatim"
            else:
                source = "cms"
        except Exception:
            source = "failed"

        result.at[idx, "geocode_source"] = source
        result.at[idx, "geocode_verified_at"] = now

        if progress_callback:
            progress_callback(i + 1, total, str(row.get("Full Name", "")), source)

    return result


__all__ = ["geocode_address", "geocode_provider_dataframe", "handle_geocoding_error"]
