"""Utilities package for Provider Recommender.

Re-export stable helper functions from the canonical utilities module.
"""
# This module intentionally re-exports symbols from submodules. Flake8 F401
# warnings are expected for re-exported names and are silenced locally.
# flake8: noqa: F401

from .addressing import validate_coordinates  # noqa: F401 (re-exported API)
from .addressing import validate_phone_number  # noqa: F401 (re-exported API)
from .addressing import validate_address, validate_address_input
from .cleaning import safe_numeric_conversion  # noqa: F401 (re-exported API)
from .cleaning import (
    build_full_address,
    clean_address_data,
    load_provider_data,
    validate_and_clean_coordinates,
    validate_provider_data,
)
from .geocoding import cached_geocode_address, geocode_address_with_cache, handle_geocoding_error  # noqa: F401
from .io_utils import get_word_bytes, handle_streamlit_error, sanitize_filename

# Provider-specific helpers
from .providers import (
    calculate_inbound_referral_counts,
    calculate_time_based_referral_counts,
    load_and_validate_provider_data,
)
from .scoring import calculate_distances, recommend_provider

__all__ = [
    # From consolidated_functions
    "build_full_address",
    "calculate_distances",
    "clean_address_data",
    "geocode_address_with_cache",
    "cached_geocode_address",
    "get_word_bytes",
    "handle_streamlit_error",
    "load_provider_data",
    "recommend_provider",
    "sanitize_filename",
    "validate_address",
    "validate_address_input",
    "validate_and_clean_coordinates",
    "validate_provider_data",
    # From providers module
    "calculate_inbound_referral_counts",
    "calculate_time_based_referral_counts",
    "load_and_validate_provider_data",
]
