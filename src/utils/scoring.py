"""Distance calculation and provider recommendation scoring.

DESIGN NOTE: Recommendation Scoring Algorithm
==============================================

This module implements a weighted multi-criteria scoring system for ranking healthcare
providers based on their suitability for patient referrals.

Scoring Factors:
---------------
1. **Distance**: Proximity to patient location (haversine formula for geographic distance)
   - Normalized inverse: closer providers score higher
   - Range: 0 (farthest) to 1 (closest)

2. **Client Count**: Provider experience (number of clients handled)
   - Normalized direct: more clients score higher
   - Range: 0 (minimum) to 1 (maximum)
   - Rationale: Higher client counts indicate more experience

Normalization Strategy:
----------------------
Each factor is normalized to [0, 1] using rank-based (percentile) normalization within
the candidate pool. This is robust to outliers: one distant provider does not compress
the scores of nearby providers.

Cold-start handling: providers with zero clients receive an experience floor score
(default 0.25) instead of 0.0, keeping them competitive when geographically close.

Final Score Calculation:
-----------------------
Score = w_dist * rank_dist + w_client * max(rank_client, floor) + w_star * rank_star + w_spec * specialty_score

Where:
- rank_* values are [0, 1] percentile ranks within the candidate pool
- specialty_score is 1.0 (primary match), 0.5 (secondary match), or 0.0
- Weights are normalized to sum to 1.0

Trade-offs and Limitations:
---------------------------
- Min-max normalization can be sensitive to outliers in small datasets
- Geographic distance uses haversine formula (great-circle distance), which may not
  reflect actual driving distance or transit time
- Client counts are not time-weighted, so recent activity has same weight as old
- No consideration of provider availability, wait times, or patient reviews

How This Fits Into The App:
---------------------------
1. Search page (pages/1_🔎_Search.py): User sets weight preferences via presets or sliders
2. App logic (src/app_logic.py): run_recommendation() orchestrates filtering and scoring
3. This module: Performs distance calculation and weighted scoring
4. Results page (pages/2_📄_Results.py): Displays ranked results with score explanations
"""
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import rankdata


def _rank_normalize(values: np.ndarray, higher_is_better: bool = True) -> np.ndarray:
    """Convert values to [0, 1] percentile ranks within the array.

    higher_is_better=True: largest value → 1.0, smallest → 0.0.
    higher_is_better=False: smallest value → 1.0, largest → 0.0.
    Single-element arrays always return [1.0].
    Tied values receive the average of their ranks (scipy default).
    """
    n = len(values)
    if n == 0:
        return values.copy()
    if n == 1:
        return np.array([1.0])
    ranks = rankdata(values, method="average")  # 1..N, 1 = smallest
    if higher_is_better:
        return (ranks - 1) / (n - 1)
    else:
        return (n - ranks) / (n - 1)


def calculate_distances(user_lat: float, user_lon: float, provider_df: pd.DataFrame) -> List[Optional[float]]:
    lat_arr = np.radians(provider_df["Latitude"].to_numpy(dtype=float))
    lon_arr = np.radians(provider_df["Longitude"].to_numpy(dtype=float))
    user_lat_rad = np.radians(user_lat)
    user_lon_rad = np.radians(user_lon)

    valid = ~np.isnan(lat_arr) & ~np.isnan(lon_arr)
    dlat = lat_arr[valid] - user_lat_rad
    dlon = lon_arr[valid] - user_lon_rad
    a = np.sin(dlat / 2) ** 2 + np.cos(user_lat_rad) * np.cos(lat_arr[valid]) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    distances = np.full(len(provider_df), np.nan)
    distances[valid] = 3958.8 * c

    return [None if np.isnan(d) else float(d) for d in distances]


def _specialty_scores(
    df: pd.DataFrame, selected_specialties: Optional[List[str]]
) -> np.ndarray:
    """Return specialty match quality per row: 1.0 primary, 0.5 secondary, 0.0 none."""
    n = len(df)
    if not selected_specialties or "Specialty" not in df.columns:
        return np.ones(n)

    selected_set = {s.strip() for s in selected_specialties}
    sec_cols = [c for c in ["sec_spec_1", "sec_spec_2", "sec_spec_3", "sec_spec_4"] if c in df.columns]
    scores = np.zeros(n)

    for i, (_, row) in enumerate(df.iterrows()):
        pri = str(row.get("Specialty", "")).strip()
        if pri in selected_set:
            scores[i] = 1.0
            continue
        for col in sec_cols:
            sec = str(row.get(col, "")).strip()
            if sec and sec in selected_set:
                scores[i] = 0.5
                break

    return scores


EXPERIENCE_FLOOR: float = 0.25


def recommend_provider(
    provider_df: pd.DataFrame,
    distance_weight: float = 0.5,
    client_weight: float = 0.3,
    star_weight: float = 0.0,
    specialty_weight: float = 0.2,
    selected_specialties: Optional[List[str]] = None,
    experience_floor: float = EXPERIENCE_FLOOR,
    min_clients: Optional[int] = None,
) -> Tuple[Optional[pd.Series], Optional[pd.DataFrame]]:
    df = provider_df.copy(deep=True)
    df = df[df["Distance (Miles)"].notnull() & df["Client Count"].notnull()]
    if min_clients is not None:
        df = df[df["Client Count"] >= min_clients]
    if df.empty:
        return None, None

    n = len(df)

    # Rank-normalize distance (lower = better)
    dist_arr = df["Distance (Miles)"].to_numpy(dtype=float)
    rank_dist = _rank_normalize(dist_arr, higher_is_better=False)

    # Rank-normalize client count (higher = better); apply experience floor
    client_arr = df["Client Count"].to_numpy(dtype=float)
    rank_client = np.maximum(_rank_normalize(client_arr, higher_is_better=True), experience_floor)

    # Rank-normalize star rating (higher = better); fill missing with median
    if "Rating" in df.columns and star_weight > 0:
        star_arr = df["Rating"].to_numpy(dtype=float)
        median_star = float(np.nanmedian(star_arr)) if not np.all(np.isnan(star_arr)) else 0.0
        star_arr = np.where(np.isnan(star_arr), median_star, star_arr)
        rank_star = _rank_normalize(star_arr, higher_is_better=True)
    else:
        rank_star = np.ones(n)

    # Specialty match quality
    spec_scores = _specialty_scores(df, selected_specialties)

    # Normalize weights to sum to 1.0
    total = distance_weight + client_weight + star_weight + specialty_weight
    if total == 0:
        return None, None
    w_dist = distance_weight / total
    w_client = client_weight / total
    w_star = star_weight / total
    w_spec = specialty_weight / total

    df = df.copy()
    df["Score"] = (
        w_dist * rank_dist
        + w_client * rank_client
        + w_star * rank_star
        + w_spec * spec_scores
    )

    if distance_weight > client_weight:
        sort_keys = ["Score", "Distance (Miles)", "Client Count"]
        ascending = [False, True, False]
    else:
        sort_keys = ["Score", "Client Count", "Distance (Miles)"]
        ascending = [False, False, True]

    if "Full Name" in df.columns:
        sort_keys.append("Full Name")
        ascending.append(True)

    sort_keys_final = [k for k in sort_keys if k in df.columns]
    ascending_final = ascending[: len(sort_keys_final)]

    df_sorted = df.sort_values(by=sort_keys_final, ascending=ascending_final).reset_index(drop=True)
    return df_sorted.iloc[0], df_sorted
