"""Utilities for calculating and displaying data freshness indicators.

This module provides functions to determine whether provider data is fresh or stale
based on Last Verified Date.
"""

from datetime import datetime
from typing import Optional, Tuple

import pandas as pd


def calculate_data_age_days(last_verified_date: Optional[pd.Timestamp]) -> Optional[int]:
    """Calculate the age of data in days from the Last Verified Date.

    Args:
        last_verified_date: The Last Verified Date as a pandas Timestamp or None

    Returns:
        Number of days since last verification, or None if date is missing
    """
    if pd.isna(last_verified_date):
        return None

    try:
        age = (datetime.now() - last_verified_date).days
        return max(0, age)  # Ensure non-negative
    except (TypeError, AttributeError):
        return None


def get_freshness_indicator(
    last_verified_date: Optional[pd.Timestamp],
    stale_threshold_days: int = 90,
    very_stale_threshold_days: int = 180
) -> Tuple[str, str]:
    """Get a freshness indicator and status for a Last Verified Date.

    Args:
        last_verified_date: The Last Verified Date as a pandas Timestamp or None
        stale_threshold_days: Number of days after which data is considered stale (default: 90)
        very_stale_threshold_days: Number of days after which data is very stale (default: 180)

    Returns:
        Tuple of (indicator_emoji, status_text)
        - indicator_emoji: Visual emoji indicator (✅, ⚠️, or ❌)
        - status_text: Human-readable status ("Fresh", "Stale", "Very Stale", or "Unknown")
    """
    age_days = calculate_data_age_days(last_verified_date)

    if age_days is None:
        return "❓", "Unknown"

    if age_days <= stale_threshold_days:
        return "✅", "Fresh"
    elif age_days <= very_stale_threshold_days:
        return "⚠️", "Stale"
    else:
        return "❌", "Very Stale"


def format_last_verified_display(
    last_verified_date: Optional[pd.Timestamp],
    include_age: bool = True,
    include_indicator: bool = True,
    stale_threshold_days: int = 90,
    very_stale_threshold_days: int = 180
) -> str:
    """Format Last Verified Date for display with freshness indicator.

    Args:
        last_verified_date: The Last Verified Date as a pandas Timestamp or None
        include_age: Whether to include age in days in the display
        include_indicator: Whether to include freshness indicator emoji
        stale_threshold_days: Number of days after which data is considered stale (default: 90)
        very_stale_threshold_days: Number of days after which data is very stale (default: 180)

    Returns:
        Formatted string for display, e.g., "✅ 2024-01-15 (45 days ago)"
    """
    if pd.isna(last_verified_date):
        return "Not Available"

    try:
        date_str = last_verified_date.strftime("%Y-%m-%d")
    except (AttributeError, ValueError):
        return "Invalid Date"

    parts = []

    if include_indicator:
        indicator, _ = get_freshness_indicator(
            last_verified_date,
            stale_threshold_days,
            very_stale_threshold_days
        )
        parts.append(indicator)

    parts.append(date_str)

    if include_age:
        age_days = calculate_data_age_days(last_verified_date)
        if age_days is not None:
            parts.append(f"({age_days} days ago)")

    return " ".join(parts)
