# Search Improvements Design

**Date:** 2026-05-10
**Scope:** `src/utils/geocoding.py`, `src/utils/scoring.py`, `src/utils/providers.py`, `pages/1_🔎_Search.py`
**Goals:** Proactive performance hardening (geocoding) + search quality improvement (ranking, cold start, additional scoring dimensions)

---

## 1. Geocoding Hardening

### Problem
Two overlapping cached geocoding functions exist with inconsistent return types and TTLs:
- `geocode_address_with_cache` — 1hr TTL, returns `(lat, lon)` tuple
- `cached_geocode_address` — 24hr TTL, returns raw geopy `Location` object, silently swallows all exceptions

Cache miss rate is higher than necessary because minor address variations (extra spaces, lowercase state) bypass the Streamlit cache.

### Changes to `src/utils/geocoding.py`

**Delete:** `cached_geocode_address` and `geocode_address_with_cache`

**Add:** Single unified function:
```python
@st.cache_data(ttl=60 * 60 * 24)
def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """Geocode a normalized address; returns (lat, lon) or None. Cached 24hr."""
```

**Add:** Pre-call normalizer:
```python
def _normalize_address(address: str) -> str:
    """Strip, collapse whitespace, uppercase state abbreviation."""
```
`geocode_address` calls `_normalize_address` on the input before hitting Nominatim, so `"100 N Charles St , baltimore , md  21201"` and `"100 N Charles St, Baltimore, MD 21201"` resolve to the same cache key.

**Keep unchanged:** `_get_rate_limited_geocoder`, `handle_geocoding_error`, Nominatim singleton, RateLimiter retry logic.

**Update import sites:**
- `src/utils/providers.py` — replace both old function references with `geocode_address`
- `pages/1_🔎_Search.py` — replace `geocode_address_with_cache` with `geocode_address`

---

## 2. Scoring Overhaul

### Problem

**Ranking:** Current min-max normalization is sensitive to outliers. A single provider 80 miles away compresses all nearby providers' distance scores toward 1.0, making the distance dimension nearly useless for differentiating them.

**Cold start:** Providers with zero clients receive a normalized score of `0.0` on the experience dimension regardless of how close they are. This buries potentially appropriate new providers.

**Flat scoring:** Only two dimensions (distance, client count). The dataset includes `star_value` (quality rating) and structured specialty columns (`pri_spec`, `sec_spec_1..4`) that go unused in ranking.

### Changes to `src/utils/scoring.py`

#### Rank-based normalization (replaces min-max)

Use `scipy.stats.rankdata` to convert each dimension to a [0, 1] percentile rank within the current candidate pool.

- Rank 1 (best) → `1.0`; rank N (worst) → `0.0`
- Ties broken by `method='average'` (scipy default)
- Robust to outliers: one distant provider no longer compresses the rest

For distance, "best" = smallest value (closest). For client count and star rating, "best" = largest value.

#### Experience floor (cold start)

Constant `EXPERIENCE_FLOOR: float = 0.25` (module-level, overridable via parameter).

Applied after rank normalization: `effective_client_score = max(rank_client, experience_floor)`.

Providers with non-zero client counts remain ranked relative to each other; zero-client providers receive the floor instead of `0.0`. The floor makes a zero-client provider roughly equivalent to the 25th percentile of experienced providers — competitive if they're geographically close, not dominant.

#### Star rating dimension

Column: `star_value` (float, already in the combined dataset).

- Rank-normalized within the candidate pool.
- Missing values filled with the pool median before ranking.
- Controlled by `star_weight` parameter (default `0.0` — off unless explicitly enabled).

#### Specialty match quality

Column: `pri_spec`, `sec_spec_1..4`.

When `selected_specialties` is provided, compute a `specialty_score` per row:
- Primary specialty matches any selected → `1.0`
- Only a secondary specialty matches → `0.5`
- No match (provider survived the pre-filter but has ambiguous data) → `0.0`

This replaces the existing binary filter behavior within the scoring step (the pre-filter in `app_logic.py` still removes providers with no specialty match at all).

Controlled by `specialty_weight` parameter (default `0.2`).

#### Updated `recommend_provider` signature

```python
def recommend_provider(
    provider_df: pd.DataFrame,
    distance_weight: float = 0.5,
    client_weight: float = 0.3,
    star_weight: float = 0.0,
    specialty_weight: float = 0.2,
    selected_specialties: list[str] | None = None,
    experience_floor: float = 0.25,
    min_clients: int | None = None,
) -> Tuple[Optional[pd.Series], Optional[pd.DataFrame]]:
```

Weights are normalized to sum to 1.0 inside the function before computing the final score.

#### Score formula

```
norm_weights = normalize([distance_weight, client_weight, star_weight, specialty_weight])

Score = norm_weights[0] * rank_dist
      + norm_weights[1] * max(rank_client, experience_floor)
      + norm_weights[2] * rank_star
      + norm_weights[3] * specialty_score
```

Where `rank_*` values are [0, 1] percentile ranks and `specialty_score` is the match-quality value above.

#### Sort behavior (unchanged logic, updated keys)

If `distance_weight > client_weight`: primary sort `Score` DESC, secondary `Distance (Miles)` ASC, tertiary `Client Count` DESC.
Otherwise: primary `Score` DESC, secondary `Client Count` DESC, tertiary `Distance (Miles)` ASC.
`Full Name` ASC used as final tiebreaker.

### Changes to `src/utils/providers.py`

Fix the `recommend_provider` wrapper signature mismatch: remove `inbound_weight` parameter (which the underlying function never accepted) and align the wrapper with the new `scoring.py` signature.

---

## 3. What Does Not Change

- `calculate_distances` in `scoring.py` — already vectorized haversine, no changes needed
- `src/app_logic.py` pre-filters (specialty, gender, radius, min_clients) — these remain unchanged; the scoring overhaul operates on the already-filtered candidate pool
- `src/utils/addressing.py` — no changes
- `src/utils/performance.py` — no changes (benchmark accuracy is a separate concern)
- All other utils — no changes

---

## 4. Dependencies

`scipy` is used for `rankdata` in the scoring overhaul. It is already installed in the project environment but is not listed in `requirements.txt`. Adding `scipy` to `requirements.txt` is part of the implementation.

---

## 5. Testing Considerations

- Rank normalization should be verified: given a pool of N providers, scores should span the full [0,1] range.
- Cold start: a pool with one zero-client provider and several experienced ones should have the zero-client provider at `experience_floor`, not `0.0`.
- Specialty scoring: a provider matching `pri_spec` should outscore one matching only `sec_spec_1` when `specialty_weight > 0`.
- Geocoding: the same address entered with/without extra spaces should return the same coordinates (cache hit).
- The `providers.py` wrapper should accept the same arguments as `scoring.py`'s `recommend_provider` without error.
