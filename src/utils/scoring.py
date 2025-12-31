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
Each factor is normalized to [0, 1] scale using min-max normalization within the
candidate pool. This ensures:
- All factors contribute proportionally based on their weights
- Weights can be interpreted as relative importance percentages
- Score ranges are consistent across different search radii and datasets

Final Score Calculation:
-----------------------
Score = (distance_weight × norm_distance) + (client_weight × norm_client)

Where all weights sum to 1.0 (normalized by the calling code).

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


def recommend_provider(
    provider_df: pd.DataFrame,
    distance_weight: float = 0.5,
    client_weight: float = 0.5,
    min_clients: Optional[int] = None,
) -> Tuple[Optional[pd.Series], Optional[pd.DataFrame]]:
    df = provider_df.copy(deep=True)
    df = df[df["Distance (Miles)"].notnull() & df["Client Count"].notnull()]
    if min_clients is not None:
        df = df[df["Client Count"] >= min_clients]

    if df.empty:
        return None, None

    client_range = df["Client Count"].max() - df["Client Count"].min()
    dist_range = df["Distance (Miles)"].max() - df["Distance (Miles)"].min()

    # Normalize client counts: higher client count = HIGHER (better) score
    # More clients indicates more experience
    df["norm_rank"] = (df["Client Count"] - df["Client Count"].min()) / client_range if client_range != 0 else 0
    # Normalize distance: closer = HIGHER (better) score
    df["norm_dist"] = (df["Distance (Miles)"].max() - df["Distance (Miles)"]) / dist_range if dist_range != 0 else 0

    df["Score"] = distance_weight * df["norm_dist"] + client_weight * df["norm_rank"]

    if distance_weight > client_weight:
        sort_keys = ["Score", "Distance (Miles)", "Client Count"]
    else:
        sort_keys = ["Score", "Client Count", "Distance (Miles)"]

    candidate_keys = sort_keys + ["Full Name"]
    sort_keys_final = [k for k in candidate_keys if k in df.columns]
    ascending = [False] * len(sort_keys_final)  # Higher scores are better, so descending sort
    # Exception: Full Name should still be ascending for alphabetical tie-breaking
    for i, key in enumerate(sort_keys_final):
        if key == "Full Name":
            ascending[i] = True

    df_sorted = df.sort_values(by=sort_keys_final, ascending=ascending).reset_index(drop=True)
    best = df_sorted.iloc[0]
    return best, df_sorted
