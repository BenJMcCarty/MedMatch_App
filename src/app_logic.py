"""Core application logic for provider recommendation system.

This module orchestrates the main recommendation workflow, connecting data loading,
filtering, scoring, and result ranking.
"""

import pandas as pd
import streamlit as st

from src.data.ingestion import load_detailed_referrals
from src.utils.cleaning import (
    build_full_address,
    clean_address_data,
    validate_and_clean_coordinates,
    validate_provider_data,
)
from src.utils.providers import (
    calculate_time_based_referral_counts,
    load_and_validate_provider_data,
)
from src.utils.scoring import calculate_distances, recommend_provider

__all__ = [
    "load_application_data",
    "apply_time_filtering",
    "filter_providers_by_radius",
    "get_unique_specialties",
    "get_unique_genders",
    "filter_providers_by_specialty",
    "filter_providers_by_gender",
    "run_recommendation",
    "validate_provider_data",
]


def _clean_provider_addresses(provider_df: pd.DataFrame) -> pd.DataFrame:
    """Clean and standardize provider address data.

    Handles address field cleaning, full address construction, and phone number formatting.

    Args:
        provider_df: Provider DataFrame with address columns

    Returns:
        pd.DataFrame: Provider DataFrame with cleaned address data
    """
    # Clean address field values
    for col in ["Street", "City", "State", "Zip", "Full Address"]:
        if col in provider_df.columns:
            provider_df[col] = provider_df[col].astype(str).replace(["nan", "None", "NaN"], "").fillna("")

    # Build full address if missing or incomplete
    if "Full Address" not in provider_df.columns or provider_df["Full Address"].isna().any():
        provider_df = build_full_address(provider_df)

    # Remove duplicate providers by name
    if "Full Name" in provider_df.columns:
        provider_df = provider_df.drop_duplicates(subset=["Full Name"], keep="first")

    # Standardize phone number formatting
    phone_candidates = [
        col for col in ["Work Phone Number", "Work Phone", "Phone Number", "Phone 1"] if col in provider_df.columns
    ]
    if phone_candidates:
        from src.utils.io_utils import format_phone_number

        phone_source = phone_candidates[0]
        provider_df["Work Phone Number"] = provider_df[phone_source].apply(format_phone_number)
        if "Work Phone" not in provider_df.columns:
            provider_df["Work Phone"] = provider_df["Work Phone Number"]
        if "Phone Number" not in provider_df.columns:
            provider_df["Phone Number"] = provider_df["Work Phone Number"]

    return provider_df


def _ensure_client_counts(provider_df: pd.DataFrame) -> pd.DataFrame:
    """Ensure client count columns exist and contain valid numeric data.

    Args:
        provider_df: Provider DataFrame

    Returns:
        pd.DataFrame: Provider DataFrame with validated client counts
    """
    # Ensure client counts are numeric and fill missing with zero
    if "Client Count" in provider_df.columns:
        provider_df["Client Count"] = pd.to_numeric(provider_df["Client Count"], errors="coerce").fillna(0)
    else:
        provider_df["Client Count"] = 0

    return provider_df


@st.cache_data(ttl=3600)
def load_application_data():
    """Load and enrich provider and referral data for the application.

    This function is the primary data loader for the app, performing:
    1. Provider data loading and validation
    2. Coordinate and address cleaning
    3. Client count validation

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame]: (provider_df, detailed_referrals_df)
            - provider_df: Complete provider data with all enrichments
            - detailed_referrals_df: Detailed outbound referral records

    Raises:
        Exception: If data loading fails completely (caught by calling code)
    """
    import logging

    logger = logging.getLogger(__name__)

    # Load and validate base provider data
    provider_df = load_and_validate_provider_data()

    if provider_df.empty:
        logger.warning("load_and_validate_provider_data() returned empty DataFrame, trying fallback loader")
        try:
            from src.data.ingestion import load_provider_data as _fallback_loader

            provider_df = _fallback_loader()
            logger.info(f"Fallback loader returned {len(provider_df)} providers")
        except Exception as e:
            logger.error(f"Fallback loader failed: {type(e).__name__}: {e}")
            raise

    # Clean and standardize provider data
    if not provider_df.empty:
        provider_df = validate_and_clean_coordinates(provider_df)
        provider_df = clean_address_data(provider_df)
        provider_df = _clean_provider_addresses(provider_df)

    # Load referral data
    detailed_referrals_df = load_detailed_referrals()

    # Enrich provider data with client counts
    if not provider_df.empty:
        provider_df = _ensure_client_counts(provider_df)

    return provider_df, detailed_referrals_df


def apply_time_filtering(provider_df, detailed_referrals_df, start_date, end_date):
    """Apply time-based filtering for outbound referrals.

    Recalculates client counts based on a specific date range, replacing
    the full-time counts with time-filtered values.

    Args:
        provider_df: Provider DataFrame with existing client counts
        detailed_referrals_df: Detailed outbound referral records
        start_date: Start date for filtering (inclusive)
        end_date: End date for filtering (inclusive)

    Returns:
        pd.DataFrame: Provider DataFrame with time-filtered client counts
    """
    working_df = provider_df.copy()
    if not detailed_referrals_df.empty:
        time_filtered_outbound = calculate_time_based_referral_counts(detailed_referrals_df, start_date, end_date)
        if not time_filtered_outbound.empty:
            working_df = working_df.drop(columns=["Client Count"], errors="ignore").merge(
                time_filtered_outbound[["Full Name", "Client Count"]], on="Full Name", how="left"
            )
            working_df["Client Count"] = working_df["Client Count"].fillna(0)
    return working_df


def filter_providers_by_radius(df: pd.DataFrame, max_radius_miles: float) -> pd.DataFrame:
    """Filter providers by maximum radius distance.

    Args:
        df: Provider DataFrame with "Distance (Miles)" column
        max_radius_miles: Maximum distance threshold in miles

    Returns:
        pd.DataFrame: Filtered DataFrame with only providers within radius
    """
    if df is None or df.empty or "Distance (Miles)" not in df.columns:
        return df
    return df[df["Distance (Miles)"] <= max_radius_miles].copy()


def get_unique_specialties(provider_df: pd.DataFrame) -> list[str]:
    """Extract unique specialties from provider DataFrame.

    Handles multiple specialties per provider (comma-separated values).

    Args:
        provider_df: Provider DataFrame with optional "Specialty" column

    Returns:
        Sorted list of unique specialty strings
    """
    if provider_df.empty or "Specialty" not in provider_df.columns:
        return []

    # Get all non-null specialty values
    specialties_series = provider_df["Specialty"].dropna()

    if specialties_series.empty:
        return []

    # Split comma-separated specialties and collect unique values
    unique_specialties = set()
    for specialty_str in specialties_series:
        if pd.notna(specialty_str) and str(specialty_str).strip():
            # Split by comma and strip whitespace from each specialty
            parts = [s.strip() for s in str(specialty_str).split(",")]
            unique_specialties.update(part for part in parts if part)

    return sorted(list(unique_specialties))


def get_unique_genders(provider_df: pd.DataFrame) -> list[str]:
    """Extract unique gender values from provider DataFrame.

    Args:
        provider_df: Provider DataFrame with optional "Gender" column

    Returns:
        Sorted list of unique gender strings
    """
    if provider_df.empty or "Gender" not in provider_df.columns:
        return []

    # Get all non-null gender values
    genders_series = provider_df["Gender"].dropna()

    if genders_series.empty:
        return []

    # Collect unique gender values (standardize to title case)
    unique_genders = set()
    for gender_str in genders_series:
        if pd.notna(gender_str) and str(gender_str).strip():
            gender_clean = str(gender_str).strip().title()
            if gender_clean:
                unique_genders.add(gender_clean)

    return sorted(list(unique_genders))


def filter_providers_by_specialty(df: pd.DataFrame, selected_specialties: list[str]) -> pd.DataFrame:
    """Filter providers by selected specialties.

    Providers with multiple specialties (comma-separated) match if ANY of their
    specialties is in the selected list.

    Args:
        df: Provider DataFrame with optional "Specialty" column
        selected_specialties: List of specialty strings to filter by

    Returns:
        pd.DataFrame: Filtered DataFrame with providers matching selected specialties
    """
    if df is None or df.empty:
        return df

    # If no specialties selected or Specialty column doesn't exist, return all providers
    if not selected_specialties or "Specialty" not in df.columns:
        return df

    # Create a boolean mask for providers that match any selected specialty
    def matches_specialty(specialty_value):
        if pd.isna(specialty_value):
            return False

        # Split comma-separated specialties
        provider_specialties = [s.strip() for s in str(specialty_value).split(",")]

        # Check if any provider specialty matches any selected specialty
        return any(ps in selected_specialties for ps in provider_specialties if ps)

    mask = df["Specialty"].apply(matches_specialty)
    return df[mask].copy()


def filter_providers_by_gender(df: pd.DataFrame, selected_genders: list[str]) -> pd.DataFrame:
    """Filter providers by selected genders.

    Args:
        df: Provider DataFrame with optional "Gender" column
        selected_genders: List of gender strings to filter by

    Returns:
        pd.DataFrame: Filtered DataFrame with providers matching selected genders
    """
    if df is None or df.empty:
        return df

    # If no genders selected or Gender column doesn't exist, return all providers
    if not selected_genders or "Gender" not in df.columns:
        return df

    # Create a boolean mask for providers that match any selected gender
    def matches_gender(gender_value):
        if pd.isna(gender_value):
            return False

        # Standardize to title case for comparison
        provider_gender = str(gender_value).strip().title()
        return provider_gender in selected_genders

    mask = df["Gender"].apply(matches_gender)
    return df[mask].copy()


def run_recommendation(
    provider_df: pd.DataFrame,
    user_lat: float,
    user_lon: float,
    *,
    min_clients: int,
    max_radius_miles: int,
    alpha: float,
    beta: float,
    selected_specialties: list[str] = None,
    selected_genders: list[str] = None,
):
    """Run the complete provider recommendation workflow.

    This orchestrates the core recommendation algorithm:
    1. Filter by specialty (if specified)
    2. Filter by gender (if specified)
    3. Filter by minimum client threshold
    4. Calculate distances from client location
    5. Filter by maximum radius
    6. Score providers using weighted criteria
    7. Return best match and ranked results

    Args:
        provider_df: Provider data with client counts
        user_lat: Client latitude
        user_lon: Client longitude
        min_clients: Minimum client count threshold
        max_radius_miles: Maximum distance in miles
        alpha: Normalized weight for distance (0-1)
        beta: Normalized weight for client count (0-1)
        selected_specialties: Optional list of specialties to filter by
        selected_genders: Optional list of genders to filter by

    Returns:
        Tuple[Optional[pd.Series], pd.DataFrame]:
            - best: Top-ranked provider (or None if no matches)
            - scored_df: All matching providers with scores (or empty DataFrame)
    """
    working = provider_df.copy()

    # Apply specialty filter first (before other filters)
    if selected_specialties:
        working = filter_providers_by_specialty(working, selected_specialties)
        if working.empty:
            return None, pd.DataFrame()

    # Apply gender filter
    if selected_genders:
        working = filter_providers_by_gender(working, selected_genders)
        if working.empty:
            return None, pd.DataFrame()

    # Apply client count filter
    working = working[working["Client Count"] >= min_clients].copy()
    if working.empty:
        return None, pd.DataFrame()

    # Calculate distances and filter by radius
    working["Distance (Miles)"] = calculate_distances(user_lat, user_lon, working)
    working = filter_providers_by_radius(working, max_radius_miles)
    if working.empty:
        return None, pd.DataFrame()

    # Score and rank providers
    best, scored_df = recommend_provider(
        working,
        distance_weight=alpha,
        client_weight=beta,
        min_clients=min_clients,
    )
    if scored_df is not None and not scored_df.empty and "Full Name" in scored_df.columns:
        scored_df = scored_df.drop_duplicates(subset=["Full Name"], keep="first")
    return best, scored_df
