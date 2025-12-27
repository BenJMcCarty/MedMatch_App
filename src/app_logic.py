import pandas as pd
import streamlit as st

from src.data.ingestion import load_detailed_referrals, load_inbound_referrals
from src.utils.cleaning import (
    build_full_address,
    clean_address_data,
    validate_and_clean_coordinates,
    validate_provider_data,
)
from src.utils.providers import (
    calculate_inbound_referral_counts,
    calculate_time_based_referral_counts,
    load_and_validate_provider_data,
)
from src.utils.scoring import calculate_distances, recommend_provider

__all__ = [
    "load_application_data",
    "apply_time_filtering",
    "filter_providers_by_radius",
    "get_unique_specialties",
    "filter_providers_by_specialty",
    "run_recommendation",
    "validate_provider_data",
]


# Flag to ensure preferred percentage warning is logged only once per app session
_preferred_pct_warning_logged = False


@st.cache_data(ttl=3600)
def load_application_data():
    """Load and enrich provider and referral data for the application.

    This function is the primary data loader for the app, performing:
    1. Provider data loading and validation
    2. Coordinate and address cleaning
    3. Inbound referral count enrichment
    4. Preferred provider list integration

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame]: (provider_df, detailed_referrals_df)
            - provider_df: Complete provider data with all enrichments
            - detailed_referrals_df: Detailed outbound referral records

    Raises:
        Exception: If data loading fails completely (caught by calling code)
    """
    import logging

    logger = logging.getLogger(__name__)

    provider_df = load_and_validate_provider_data()

    if provider_df.empty:
        logger.warning("load_and_validate_provider_data() returned empty DataFrame, trying fallback loader")
        try:
            from src.data.ingestion import load_provider_data as _fallback_loader

            provider_df = _fallback_loader()
            logger.info(f"Fallback loader returned {len(provider_df)} providers")
        except Exception as e:
            logger.error(f"Fallback loader failed: {type(e).__name__}: {e}")
            # Don't silently swallow the exception - let calling code handle it
            raise

    if not provider_df.empty:
        provider_df = validate_and_clean_coordinates(provider_df)
        provider_df = clean_address_data(provider_df)
        for col in ["Street", "City", "State", "Zip", "Full Address"]:
            if col in provider_df.columns:
                provider_df[col] = provider_df[col].astype(str).replace(["nan", "None", "NaN"], "").fillna("")
        if "Full Address" not in provider_df.columns or provider_df["Full Address"].isna().any():
            provider_df = build_full_address(provider_df)
        if "Full Name" in provider_df.columns:
            provider_df = provider_df.drop_duplicates(subset=["Full Name"], keep="first")
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

    detailed_referrals_df = load_detailed_referrals()
    inbound_referrals_df = load_inbound_referrals()

    if not provider_df.empty:
        if not inbound_referrals_df.empty:
            inbound_counts_df = calculate_inbound_referral_counts(inbound_referrals_df)
            if (
                not inbound_counts_df.empty
                and "Full Name" in provider_df.columns
                and "Full Name" in inbound_counts_df.columns
            ):
                provider_df = provider_df.merge(
                    inbound_counts_df[["Full Name", "Inbound Referral Count"]],
                    on="Full Name",
                    how="left",
                )
                provider_df["Inbound Referral Count"] = provider_df["Inbound Referral Count"].fillna(0)
            else:
                provider_df["Inbound Referral Count"] = 0
    # --- Preferred providers: include the preferred list and mark providers ---
    try:
        from src.data.ingestion import load_preferred_providers

        preferred_df = load_preferred_providers()
        if preferred_df is not None and not preferred_df.empty and "Full Name" in preferred_df.columns:
            # Select columns to merge from preferred providers (include Specialty if available)
            pref_cols = ["Full Name"]
            if "Specialty" in preferred_df.columns:
                pref_cols.append("Specialty")
            pref_data = preferred_df[pref_cols].drop_duplicates(subset=["Full Name"], keep="first")

            # Log preferred providers information for verification
            logger.info(f"Loaded {len(pref_data)} unique preferred providers from preferred providers file")
            logger.debug(f"Preferred providers: {pref_data['Full Name'].tolist()[:10]}...")  # Show first 10

            # Merge outer so preferred-only providers are included
            provider_df = provider_df.merge(
                pref_data, on="Full Name", how="outer", indicator=True, suffixes=("", "_pref")
            )
            # Mark preferred where the merge shows presence in preferred list (boolean)
            provider_df["Preferred Provider"] = provider_df["_merge"].apply(
                lambda v: True if v in ("both", "right_only") else False
            )

            # Count and log preferred provider attribution
            preferred_count = provider_df["Preferred Provider"].sum()
            total_count = len(provider_df)
            preferred_pct = (preferred_count / total_count * 100) if total_count > 0 else 0

            logger.info(f"Marked {preferred_count} out of {total_count} providers as preferred ({preferred_pct:.1f}%)")

            # Validation: Warn if suspiciously high percentage of providers are marked as preferred
            if preferred_pct > 80:
                global _preferred_pct_warning_logged

                if not _preferred_pct_warning_logged:
                    logger.warning(
                        f"WARNING: {preferred_pct:.1f}% of providers are marked as preferred. "
                        "This is unusually high and may indicate that the preferred providers file "
                        "contains all providers instead of just the preferred ones. "
                        "Please verify the preferred providers data source."
                    )
                    _preferred_pct_warning_logged = True  # Set flag to prevent future duplicate warnings

            provider_df = provider_df.drop(columns=["_merge"])

            # If Specialty column exists from preferred providers, use it
            # (prioritize preferred provider specialty)
            if "Specialty_pref" in provider_df.columns:
                provider_df["Specialty"] = provider_df["Specialty_pref"]
                provider_df = provider_df.drop(columns=["Specialty_pref"])
        else:
            # No preferred list available or no Full Name column
            # Ensure the column exists as boolean; default to False when missing
            if "Preferred Provider" not in provider_df.columns:
                provider_df["Preferred Provider"] = False
            logger.info("No preferred providers list available - all providers marked as not preferred")
    except Exception as e:
        logger.error(f"Error processing preferred providers: {e}")
        if "Preferred Provider" not in provider_df.columns:
            provider_df["Preferred Provider"] = False

    # Ensure referral counts are numeric and fill missing with zero (important when preferred list added new rows)
    if "Referral Count" in provider_df.columns:
        provider_df["Referral Count"] = pd.to_numeric(provider_df["Referral Count"], errors="coerce").fillna(0)
    else:
        provider_df["Referral Count"] = 0

    # Ensure inbound referral count exists
    if "Inbound Referral Count" in provider_df.columns:
        provider_df["Inbound Referral Count"] = pd.to_numeric(
            provider_df["Inbound Referral Count"], errors="coerce"
        ).fillna(0)
    else:
        provider_df["Inbound Referral Count"] = 0

    return provider_df, detailed_referrals_df


def apply_time_filtering(provider_df, detailed_referrals_df, start_date, end_date):
    """Apply time-based filtering for outbound and inbound referrals.

    Recalculates referral counts based on a specific date range, replacing
    the full-time counts with time-filtered values.

    Args:
        provider_df: Provider DataFrame with existing referral counts
        detailed_referrals_df: Detailed outbound referral records
        start_date: Start date for filtering (inclusive)
        end_date: End date for filtering (inclusive)

    Returns:
        pd.DataFrame: Provider DataFrame with time-filtered referral counts
    """
    working_df = provider_df.copy()
    if not detailed_referrals_df.empty:
        time_filtered_outbound = calculate_time_based_referral_counts(detailed_referrals_df, start_date, end_date)
        if not time_filtered_outbound.empty:
            working_df = working_df.drop(columns=["Referral Count"], errors="ignore").merge(
                time_filtered_outbound[["Full Name", "Referral Count"]], on="Full Name", how="left"
            )
            working_df["Referral Count"] = working_df["Referral Count"].fillna(0)

    inbound_referrals_df = load_inbound_referrals()
    if not inbound_referrals_df.empty:
        time_filtered_inbound = calculate_inbound_referral_counts(inbound_referrals_df, start_date, end_date)
        if not time_filtered_inbound.empty:
            working_df = working_df.drop(columns=["Inbound Referral Count"], errors="ignore").merge(
                time_filtered_inbound[["Full Name", "Inbound Referral Count"]], on="Full Name", how="left"
            )
            working_df["Inbound Referral Count"] = working_df["Inbound Referral Count"].fillna(0)
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


def run_recommendation(
    provider_df: pd.DataFrame,
    user_lat: float,
    user_lon: float,
    *,
    min_referrals: int,
    max_radius_miles: int,
    alpha: float,
    beta: float,
    gamma: float,
    preferred_weight: float = 0.1,
    selected_specialties: list[str] = None,
):
    """Run the complete provider recommendation workflow.

    This orchestrates the core recommendation algorithm:
    1. Filter by specialty (if specified)
    2. Filter by minimum referral threshold
    3. Calculate distances from client location
    4. Filter by maximum radius
    5. Score providers using weighted criteria
    6. Return best match and ranked results

    Args:
        provider_df: Provider data with referral counts
        user_lat: Client latitude
        user_lon: Client longitude
        min_referrals: Minimum referral count threshold
        max_radius_miles: Maximum distance in miles
        alpha: Normalized weight for distance (0-1)
        beta: Normalized weight for outbound referrals (0-1)
        gamma: Normalized weight for inbound referrals (0-1)
        preferred_weight: Normalized weight for preferred status (0-1)
        selected_specialties: Optional list of specialties to filter by

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

    # Apply referral count filter
    working = working[working["Referral Count"] >= min_referrals].copy()
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
        referral_weight=beta,
        inbound_weight=gamma,
        preferred_weight=preferred_weight,
        min_referrals=min_referrals,
    )
    if scored_df is not None and not scored_df.empty and "Full Name" in scored_df.columns:
        scored_df = scored_df.drop_duplicates(subset=["Full Name"], keep="first")
    return best, scored_df
