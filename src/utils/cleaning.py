"""Data loading and address cleaning helpers."""
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

STATE_MAPPING = {
    "ALABAMA": "AL",
    "ALASKA": "AK",
    "ARIZONA": "AZ",
    "ARKANSAS": "AR",
    "CALIFORNIA": "CA",
    "COLORADO": "CO",
    "CONNECTICUT": "CT",
    "DELAWARE": "DE",
    "FLORIDA": "FL",
    "GEORGIA": "GA",
    "HAWAII": "HI",
    "IDAHO": "ID",
    "ILLINOIS": "IL",
    "INDIANA": "IN",
    "IOWA": "IA",
    "KANSAS": "KS",
    "KENTUCKY": "KY",
    "LOUISIANA": "LA",
    "MAINE": "ME",
    "MARYLAND": "MD",
    "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI",
    "MINNESOTA": "MN",
    "MISSISSIPPI": "MS",
    "MISSOURI": "MO",
    "MONTANA": "MT",
    "NEBRASKA": "NE",
    "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM",
    "NEW YORK": "NY",
    "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND",
    "OHIO": "OH",
    "OKLAHOMA": "OK",
    "OREGON": "OR",
    "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN",
    "TEXAS": "TX",
    "UTAH": "UT",
    "VERMONT": "VT",
    "VIRGINIA": "VA",
    "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI",
    "WYOMING": "WY",
    "DISTRICT OF COLUMBIA": "DC",
}


@st.cache_data(ttl=3600)
def load_provider_data(filepath: str) -> pd.DataFrame:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File {filepath} does not exist")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path)
    elif suffix == ".xlsx":
        df = pd.read_excel(path)
    elif suffix == ".feather":
        df = pd.read_feather(path)
    elif suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")

    df.columns = [col.strip() for col in df.columns]
    df = df.drop(columns="Preference", errors="ignore")

    # Ensure address columns are strings
    for col in ("Street", "City", "State", "Zip"):
        if col in df.columns:
            df[col] = df[col].astype(str).replace(["nan", "None", "NaN"], "").fillna("")

    if "Client Count" in df.columns:
        df["Client Count"] = pd.to_numeric(df["Client Count"], errors="coerce")

    if "Full Address" not in df.columns:
        # build naïve address
        df["Street"] = df.get("Street", pd.Series([""] * len(df)))
        df["City"] = df.get("City", pd.Series([""] * len(df)))
        df["State"] = df.get("State", pd.Series([""] * len(df)))
        df["Zip"] = df.get("Zip", pd.Series([""] * len(df)))
        df["Full Address"] = (
            df["Street"].fillna("")
            + ", "
            + df["City"].fillna("")
            + ", "
            + df["State"].fillna("")
            + " "
            + df["Zip"].fillna("")
        )
        # apply replacements on separate lines to stay within line-length limits
        df["Full Address"] = df["Full Address"].str.replace(r",\s*,", ",", regex=True)
        df["Full Address"] = df["Full Address"].str.replace(r",\s*$", "", regex=True)

    return df


def clean_address_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ("Street", "City", "State", "Zip"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace(["nan", "None", "NaN", ""], pd.NA).fillna("")

    if "State" in df.columns:
        df["State"] = df["State"].str.upper().map(STATE_MAPPING).fillna(df["State"])

    return df


def build_full_address(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    def _construct(row):
        parts = []
        for c in ("Street", "City", "State", "Zip"):
            if c in row and pd.notna(row[c]) and str(row[c]).strip():
                parts.append(str(row[c]).strip())
        return ", ".join(parts) if parts else ""

    # Build the constructed address for every row
    constructed = df.apply(_construct, axis=1)

    # Helper to detect empty-like values
    def _is_empty_series(s: pd.Series) -> pd.Series:
        return s.astype(str).fillna("").str.strip().isin(["", "nan", "None", "NaN"]) | s.isna()

    if "Full Address" in df.columns:
        df["Full Address"] = df["Full Address"].astype(str).fillna("").str.strip()
        empty_mask = _is_empty_series(df["Full Address"])
    else:
        df["Full Address"] = ""
        empty_mask = pd.Series(True, index=df.index)

    # If Work Address exists, use it to fill empty Full Address entries
    if "Work Address" in df.columns:
        work_not_empty_mask = ~_is_empty_series(df["Work Address"])
        use_work_mask = empty_mask & work_not_empty_mask
        if use_work_mask.any():
            df.loc[use_work_mask, "Full Address"] = df.loc[use_work_mask, "Work Address"].astype(str).str.strip()
            # Update empty mask after filling
            empty_mask = _is_empty_series(df["Full Address"])

    # Fill any remaining empty Full Address entries with constructed components
    if empty_mask.any():
        df.loc[empty_mask, "Full Address"] = constructed.loc[empty_mask]

    # Cleanup possible duplicate commas or trailing commas
    df["Full Address"] = (
        df["Full Address"].astype(str)
        .str.replace(r",\s*,", ",", regex=True)
        .str.replace(r",\s*$", "", regex=True)
    )

    return df


def safe_numeric_conversion(value: Any, default: float = 0.0) -> float:
    import pandas as _pd

    try:
        if _pd.isna(value):
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def validate_and_clean_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()
    if "Latitude" in df.columns:
        df["Latitude"] = df["Latitude"].apply(lambda x: safe_numeric_conversion(x, 0.0))
    if "Longitude" in df.columns:
        df["Longitude"] = df["Longitude"].apply(lambda x: safe_numeric_conversion(x, 0.0))

    # Reasonable US bounds check
    if "Latitude" in df.columns and "Longitude" in df.columns:
        invalid_lat = (df["Latitude"] < 20) | (df["Latitude"] > 70) | df["Latitude"].isna()
        invalid_lon = (df["Longitude"] < -180) | (df["Longitude"] > -60) | df["Longitude"].isna()
        invalid_coords = invalid_lat | invalid_lon
        if invalid_coords.any():
            invalid_count = int(invalid_coords.sum())
            st.warning(
                (
                    "⚠️ %d providers have invalid or missing coordinates; "
                    "they may be excluded from distance calculations."
                )
                % (invalid_count,)
            )

    return df


def validate_provider_data(df: pd.DataFrame) -> tuple[bool, str]:
    if df.empty:
        return False, "❌ **Error**: No provider data available. Please check data files."

    issues = []
    info = []

    required_cols = ["Full Name"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        issues.append(f"Missing required columns: {', '.join(missing_cols)}")

    if "Latitude" in df.columns and "Longitude" in df.columns:
        missing_coords = (df["Latitude"].isna() | df["Longitude"].isna()).sum()
        if missing_coords > 0:
            issues.append(f"{missing_coords} providers missing geographic coordinates")
    else:
        missing_geo_cols = []
        if "Latitude" not in df.columns:
            missing_geo_cols.append("Latitude")
        if "Longitude" not in df.columns:
            missing_geo_cols.append("Longitude")
        if missing_geo_cols:
            info.append(f"Geographic columns missing: {', '.join(missing_geo_cols)} (may need geocoding)")

    if "Referral Count" in df.columns:
        invalid_counts = df["Referral Count"].isna().sum()
        if invalid_counts > 0:
            issues.append(f"{invalid_counts} providers have invalid referral counts")

        zero_referrals = (df["Referral Count"] == 0).sum()
        if zero_referrals > 0:
            info.append(f"{zero_referrals} providers have zero referrals")

        avg_referrals = df["Referral Count"].mean()
        max_referrals = df["Referral Count"].max()
        info.append(f"Average referrals per provider: {avg_referrals:.1f}")
        info.append(f"Most referred provider has: {max_referrals} referrals")
    else:
        info.append("Referral Count column not found - will be calculated from detailed referral data")

    total_providers = len(df)
    info.append(f"Total providers in database: {total_providers}")

    message_parts = []
    if issues:
        message_parts.append("⚠️ **Data Quality Issues**: " + "; ".join(issues))
    if info:
        message_parts.append("ℹ️ **Data Summary**: " + "; ".join(info))

    is_valid = len(issues) == 0
    message = "\n\n".join(message_parts)
    return is_valid, message


# End of cleaning utilities
