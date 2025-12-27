"""Geocoding helpers with caching and rate limiting."""
from typing import Any, Optional, Tuple

import streamlit as st
from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
from geopy.geocoders import Nominatim

# Cached factory
_RATE_LIMITED_GEOCODER = None


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


@st.cache_data(ttl=3600)
def geocode_address_with_cache(address: str) -> Optional[Tuple[float, float]]:
    try:
        geocode_fn = _get_rate_limited_geocoder()
        location = geocode_fn(address)
        if location:
            return location.latitude, location.longitude
        return None
    except (GeocoderTimedOut, GeocoderServiceError):
        st.warning("Geocoding service temporarily unavailable. Please try again.")
        return None
    except Exception as e:
        st.error(f"Error geocoding address: {str(e)}")
        return None


@st.cache_data(ttl=60 * 60 * 24)
def cached_geocode_address(address: str) -> Optional[Any]:
    try:
        geocode_fn = _get_rate_limited_geocoder()
        return geocode_fn(address)
    except GeocoderUnavailable:
        return None
    except Exception:
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
