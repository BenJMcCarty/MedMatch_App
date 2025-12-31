"""Provider utilities: counting, loading and small helpers.

This module contains provider-focused helpers that operate on pandas
DataFrames produced by the ingestion pipeline. Functions are typed and
documented to improve clarity and maintainability.
"""

import logging
from datetime import datetime
from typing import Any, List, Optional, Tuple

import pandas as pd
import streamlit as st

from .addressing import validate_address as _validate_address
from .cleaning import safe_numeric_conversion
from .cleaning import validate_and_clean_coordinates as _validate_and_clean_coordinates
from .cleaning import validate_provider_data as _validate_provider_data
try:
    from .geocoding import cached_geocode_address as _cached_geocode_address
    from .geocoding import geocode_address_with_cache as _geocode_address_with_cache
except Exception:
    # Graceful fallback when geopy/geocoding is unavailable at import time
    def _cached_geocode_address(address: str):  # type: ignore[no-redef]
        st.warning(
            "Geocoding unavailable at import time. Install 'geopy' to enable address lookups."
        )
        return None

    def _geocode_address_with_cache(address: str):  # type: ignore[no-redef]
        st.warning(
            "Geocoding unavailable at import time. Install 'geopy' to enable address lookups."
        )
        return None
from .scoring import calculate_distances as _calculate_distances
from .scoring import recommend_provider as _recommend_provider
from .validation import validate_address_input

logger = logging.getLogger(__name__)


# --- Data Loading ---
# Data loading functions have been moved to src.data.ingestion for better performance
# and centralized management. These functions are now handled by DataIngestionManager.


def _detect_date_column(df: pd.DataFrame) -> Optional[str]:
    """Return the best candidate date column name or None if not found."""
    if df.index.name == "Date of Intake":
        return "Date of Intake"
    for candidate in ("Referral Date", "Date of Intake"):
        if candidate in df.columns:
            return candidate
    return None


def calculate_time_based_referral_counts(
    detailed_df: pd.DataFrame, start_date: Optional[datetime], end_date: Optional[datetime]
) -> pd.DataFrame:
    """Calculate referral counts for providers within a specific time period.

    If no suitable date column is available the function returns aggregated
    counts for the whole input DataFrame.
    """

    if detailed_df.empty:
        return pd.DataFrame()

    df_copy = detailed_df.copy()
    date_col = _detect_date_column(df_copy)

    if date_col == df_copy.index.name:
        df_copy = df_copy.reset_index()

    if start_date and end_date and date_col:
        start_ts = pd.to_datetime(start_date)
        end_ts = pd.to_datetime(end_date)
        mask = (df_copy[date_col] >= start_ts) & (df_copy[date_col] <= end_ts)
        filtered_df = df_copy.loc[mask]
    else:
        filtered_df = df_copy

    if filtered_df.empty:
        return pd.DataFrame()

    # Group by provider and count referrals
    # Use the actual column names from our processed data
    provider_cols = [
        "Full Name",
        "Work Address",
        "Work Phone",
        "Latitude",
        "Longitude",
    ]

    # Only include columns that exist in the DataFrame
    available_cols = [col for col in provider_cols if col in filtered_df.columns]

    if not available_cols or "Full Name" not in available_cols:
        return pd.DataFrame()

    time_based_counts = (
        filtered_df.groupby(available_cols, as_index=False)
        .size()
        .rename(columns={"size": "Client Count"})
        .sort_values(by="Client Count", ascending=False)
    )

    return time_based_counts


def calculate_inbound_referral_counts(
    inbound_df: pd.DataFrame, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
) -> pd.DataFrame:
    """Calculate inbound referral counts for each provider.

    Accepts both raw and already-processed inbound referral exports. When
    raw columns are present the function will normalize and combine primary
    and secondary referral sources before aggregation.
    """
    if inbound_df.empty:
        return pd.DataFrame()

    df_copy = inbound_df.copy()
    date_col = _detect_date_column(df_copy)

    if date_col == df_copy.index.name:
        df_copy = df_copy.reset_index()

    if start_date and end_date and date_col:
        start_ts = pd.to_datetime(start_date)
        end_ts = pd.to_datetime(end_date)
        mask = (df_copy[date_col] >= start_ts) & (df_copy[date_col] <= end_ts)
        filtered_df = df_copy.loc[mask]
    else:
        filtered_df = df_copy

    if filtered_df.empty:
        return pd.DataFrame()

    # Check if this is raw data with original column names or processed data
    has_raw_columns = "Referred From Full Name" in filtered_df.columns

    if not has_raw_columns:
        # This is already processed data - just aggregate by provider
        provider_cols = ["Full Name"]

        # Add other available columns
        additional_cols = ["Street", "City", "State", "Zip", "Latitude", "Longitude", "Work Address", "Work Phone"]
        for col in additional_cols:
            if col in filtered_df.columns:
                provider_cols.append(col)

        available_cols = [col for col in provider_cols if col in filtered_df.columns]

        if not available_cols:
            return pd.DataFrame()

        inbound_counts = (
            filtered_df.groupby(available_cols, as_index=False)
            .size()
            .rename(columns={"size": "Inbound Referral Count"})
            .sort_values(by="Inbound Referral Count", ascending=False)
        )

        # Add Full Address if not present and components are available
        if "Full Address" not in inbound_counts.columns:
            if "Work Address" in inbound_counts.columns:
                inbound_counts["Full Address"] = inbound_counts["Work Address"]

        return inbound_counts

    # Process primary referral source
    primary_cols = {
        "Referred From Full Name": "Full Name",
        "Referred From Address 1 Line 1": "Street",
        "Referred From Address 1 City": "City",
        "Referred From Address 1 State": "State",
        "Referred From Address 1 Zip": "Zip",
        "Referred From's Details: Latitude": "Latitude",
        "Referred From's Details: Longitude": "Longitude",
    }

    # Create primary referrals dataframe
    primary_df = filtered_df.copy()
    for old_col, new_col in primary_cols.items():
        if old_col in primary_df.columns:
            primary_df[new_col] = primary_df[old_col]

    # Process secondary referral source if available
    secondary_cols = {
        "Secondary Referred From Full Name": "Full Name",
        "Secondary Referred From Address 1 Line 1": "Street",
        "Secondary Referred From Address 1 City": "City",
        "Secondary Referred From Address 1 State": "State",
        "Secondary Referred From Address 1 Zip": "Zip",
        "Secondary Referred From's Details: Latitude": "Latitude",
        "Secondary Referred From's Details: Longitude": "Longitude",
    }

    secondary_df = filtered_df.copy()
    for old_col, new_col in secondary_cols.items():
        if old_col in secondary_df.columns:
            secondary_df[new_col] = secondary_df[old_col]

    # Remove rows where secondary referral data is missing
    if "Secondary Referred From Full Name" in secondary_df.columns:
        secondary_df = secondary_df.dropna(subset=["Secondary Referred From Full Name"])
    else:
        secondary_df = pd.DataFrame()  # No secondary data available

    # Combine primary and secondary referrals
    provider_cols = ["Full Name", "Street", "City", "State", "Zip", "Latitude", "Longitude"]
    available_cols = [col for col in provider_cols if col in primary_df.columns]

    if not available_cols:
        return pd.DataFrame()

    # Count inbound referrals for each provider
    all_referrals = []

    # Add primary referrals
    primary_subset = primary_df[available_cols].dropna(subset=["Full Name"])
    if not primary_subset.empty:
        all_referrals.append(primary_subset)

    # Add secondary referrals if they exist
    if not secondary_df.empty:
        secondary_subset = secondary_df[available_cols].dropna(subset=["Full Name"])
        if not secondary_subset.empty:
            all_referrals.append(secondary_subset)

    if not all_referrals:
        return pd.DataFrame()

    # Combine all referrals
    combined_df = pd.concat(all_referrals, ignore_index=True)

    # Group by provider and count inbound referrals
    inbound_counts = (
        combined_df.groupby(available_cols, as_index=False)
        .size()
        .rename(columns={"size": "Inbound Referral Count"})
        .sort_values(by="Inbound Referral Count", ascending=False)
    )

    # Add Full Address if components are available
    if all(col in inbound_counts.columns for col in ["Street", "City", "State", "Zip"]):
        # Ensure all address columns are strings to prevent concatenation errors
        for col in ["Street", "City", "State", "Zip"]:
            inbound_counts[col] = inbound_counts[col].astype(str).replace(["nan", "None", "NaN"], "").fillna("")

        inbound_counts["Full Address"] = (
            inbound_counts["Street"].fillna("")
            + ", "
            + inbound_counts["City"].fillna("")
            + ", "
            + inbound_counts["State"].fillna("")
            + " "
            + inbound_counts["Zip"].fillna("")
        )
        inbound_counts["Full Address"] = (
            inbound_counts["Full Address"].str.replace(r",\s*,", ",", regex=True).str.replace(r",\s*$", "", regex=True)
        )

    return inbound_counts


def load_and_validate_provider_data(
    start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
) -> pd.DataFrame:
    """
    Load provider data with optional time filtering and validation.
    Uses the optimized DataIngestionManager for consistent data loading.

    Args:
        start_date: Start date for filtering referrals
        end_date: End date for filtering referrals

    Returns:
        Validated provider dataframe

    Raises:
        Exception: If data loading or validation fails
    """
    from ..data.ingestion import DataIngestionManager, DataSource

    manager = DataIngestionManager()
    df = manager.load_data(DataSource.PROVIDER_DATA, show_status=False)

    if df.empty:
        logger.warning("DataIngestionManager returned empty DataFrame for PROVIDER_DATA")
        return df

    if start_date or end_date:
        logger.debug("Time filtering requested but should be performed during data preparation")

    is_valid, issues = validate_provider_data(df)
    if not is_valid:
        logger.warning(f"Provider data validation issues: {issues}")

    # Normalize coordinates
    if "Latitude" in df.columns:
        df["Latitude"] = df["Latitude"].apply(lambda x: safe_numeric_conversion(x, 0.0))
    if "Longitude" in df.columns:
        df["Longitude"] = df["Longitude"].apply(lambda x: safe_numeric_conversion(x, 0.0))

    if "Latitude" in df.columns and "Longitude" in df.columns:
        df = df[(df["Latitude"] != 0) & (df["Longitude"] != 0)]

    logger.info(f"Loaded and validated {len(df)} providers with valid coordinates")
    return df


def handle_streamlit_error(error: Exception, context: str = "operation") -> None:
    """
    Handle errors gracefully in Streamlit with user-friendly messages.

    Args:
        error: The exception that occurred
        context: Context description for the error
    """
    # error_type is unused here; keep only the message for display
    error_message = str(error)

    if "geocod" in error_message.lower():
        st.error("❌ Geocoding Error: Unable to find coordinates for the provided address. Please check the address.")
    elif "network" in error_message.lower() or "connection" in error_message.lower():
        st.error("❌ Network Error: Unable to connect to geocoding service. Check your internet connection.")
    elif "timeout" in error_message.lower():
        st.error("❌ Timeout: Geocoding service is slow or unresponsive. Try again later.")
    elif "file" in error_message.lower() or "not found" in error_message.lower():
        st.error("❌ Data Error: Required data files are missing. Please contact support.")
    else:
        st.error(f"❌ **Error during {context}**: {error_message}")

    # Log the full error details
    st.exception(error)


# Note: provider data validation is implemented centrally in
# src.utils.consolidated_functions.validate_provider_data.
# A thin wrapper exported later in this module forwards calls there.


# canonical implementations were imported at the top of this module


def calculate_distances(user_lat: float, user_lon: float, provider_df: pd.DataFrame) -> List[Optional[float]]:
    """Calculate distances (miles) from a user coordinate to providers.

    This is a thin wrapper that preserves the historic import path
    `src.utils.providers.calculate_distances` while delegating the
    implementation to `src.utils.consolidated_functions.calculate_distances`.

    Args:
        user_lat: Latitude of the user
        user_lon: Longitude of the user
        provider_df: DataFrame containing provider 'Latitude' and 'Longitude'

    Returns:
        A list of distances in miles (None for rows with invalid coords).
    """
    return _calculate_distances(user_lat, user_lon, provider_df)


def recommend_provider(
    provider_df: pd.DataFrame,
    distance_weight: float = 0.5,
    referral_weight: float = 0.5,
    inbound_weight: float = 0.0,
    min_referrals: Optional[int] = None,
) -> Tuple[Optional[pd.Series], Optional[pd.DataFrame]]:
    """Recommend a provider using the consolidated scoring algorithm.

    This wrapper preserves the legacy import while delegating to the
    canonical implementation in `consolidated_functions`.
    """
    return _recommend_provider(provider_df, distance_weight, referral_weight, inbound_weight, min_referrals)


def validate_address(address: str) -> Tuple[bool, str]:
    """Validate a free-form address string.

    Delegates to `consolidated_functions.validate_address` and returns
    (is_valid, message).
    """
    return _validate_address(address)


def validate_and_clean_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and clean provider coordinates in a DataFrame.

    Returns a DataFrame with latitude/longitude converted to numeric and
    warnings emitted for invalid ranges. See consolidated implementation
    for details.
    """
    return _validate_and_clean_coordinates(df)


def validate_provider_data(df: pd.DataFrame) -> tuple[bool, str]:
    """Validate provider DataFrame quality and return (is_valid, message).

    This wrapper ensures the function signature remains stable for callers
    that import it from `src.utils.providers`.
    """
    return _validate_provider_data(df)


def geocode_address_with_cache(address: str) -> Optional[Tuple[float, float]]:
    """Geocode an address with caching; returns (lat, lon) or None.

    Thin wrapper to preserve prior import behavior.
    """
    return _geocode_address_with_cache(address)


def cached_geocode_address(address: str) -> Any:
    """Return a geopy Location (or None) cached for longer TTL.

    Return type is intentionally broad to match geopy Location objects.
    """
    return _cached_geocode_address(address)


__all__ = [
    "calculate_inbound_referral_counts",
    "calculate_time_based_referral_counts",
    "load_and_validate_provider_data",
    # Backwards-compatible wrappers
    "calculate_distances",
    "recommend_provider",
    "validate_address",
    "validate_address_input",
    "validate_and_clean_coordinates",
    "validate_provider_data",
    "geocode_address_with_cache",
    "cached_geocode_address",
]
