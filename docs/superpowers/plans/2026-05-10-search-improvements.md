# Search Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden geocoding (consolidate two functions → one 24hr-cached function with address normalization) and overhaul provider scoring (rank-based normalization, experience floor, star rating dimension, specialty match quality).

**Architecture:** Geocoding changes are isolated to `src/utils/geocoding.py` with import site updates. Scoring changes are isolated to `src/utils/scoring.py`, with a wrapper fix in `src/utils/providers.py`. The ingestion pipeline already maps `star_value → Rating` and `pri_spec → Specialty`; secondary specialties are available as `sec_spec_1..4` columns. `app_logic.py` and the Results page are unchanged.

**Tech Stack:** Python 3.11+, pandas, numpy, scipy (new), geopy, streamlit, pytest

---

## File Map

| File | Change |
|------|--------|
| `requirements.txt` | Add `scipy>=1.11.0`, `pytest>=8.0.0`, `pytest-mock>=3.14.0` |
| `pyproject.toml` | Add `scipy>=1.11.0` to dependencies |
| `tests/__init__.py` | Create (empty) |
| `tests/utils/__init__.py` | Create (empty) |
| `tests/conftest.py` | Create — mock streamlit for unit tests |
| `tests/utils/test_geocoding.py` | Create — tests for `_normalize_address` and `geocode_address` |
| `tests/utils/test_scoring.py` | Create — tests for `_rank_normalize` and updated `recommend_provider` |
| `src/utils/geocoding.py` | Replace dual functions with single `geocode_address`; add `_normalize_address` |
| `src/utils/scoring.py` | Add `_rank_normalize`, `_specialty_scores`, rewrite `recommend_provider` |
| `src/utils/providers.py` | Fix `recommend_provider` wrapper signature |
| `pages/1_🔎_Search.py` | Update import: `geocode_address_with_cache` → `geocode_address` |

---

## Task 1: Add dependencies and bootstrap test infrastructure

**Files:**
- Modify: `requirements.txt`
- Modify: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/utils/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Add scipy and test deps to requirements.txt**

Append after the last line of `requirements.txt`:

```
scipy>=1.11.0
psutil>=5.9.0
pytest>=8.0.0
pytest-mock>=3.14.0
```

- [ ] **Step 2: Add scipy to pyproject.toml**

In `pyproject.toml`, add `"scipy>=1.11.0"` to the `dependencies` list:

```toml
dependencies = [
    "boto3>=1.28.0",
    "cachetools>=5.0.7",
    "geopy>=2.3.0",
    "numpy>=1.23.0",
    "openpyxl>=3.0.10",
    "pandas>=1.5.0",
    "plotly>=5.0.0",
    "pyarrow>=8.0.0",
    "pydeck>=0.9.1",
    "python-docx>=0.8.11",
    "scipy>=1.11.0",
    "streamlit>=1.18.0",
    "tqdm>=4.67.1",
    "watchdog>=6.0.0",
]
```

- [ ] **Step 3: Create test directories and conftest**

Create `tests/__init__.py` as an empty file.

Create `tests/utils/__init__.py` as an empty file.

Create `tests/conftest.py`:

```python
import sys
from unittest.mock import MagicMock

# Mock streamlit before any src.utils module is imported.
# @st.cache_data(ttl=...) becomes a passthrough decorator in tests.
_st = MagicMock()
_st.cache_data = lambda **kwargs: (lambda func: func)
_st.warning = lambda *a, **k: None
_st.error = lambda *a, **k: None
sys.modules["streamlit"] = _st
```

- [ ] **Step 4: Verify pytest can collect (zero tests is fine)**

```
pytest tests/ -v
```

Expected output: `no tests ran` or `collected 0 items` — no errors.

- [ ] **Step 5: Commit**

```
git add requirements.txt pyproject.toml tests/
git commit -m "chore: add scipy and pytest deps; bootstrap test infrastructure"
```

---

## Task 2: Geocoding — `_normalize_address` (TDD)

**Files:**
- Modify: `tests/utils/test_geocoding.py` (create)
- Modify: `src/utils/geocoding.py`

- [ ] **Step 1: Write the failing test**

Create `tests/utils/test_geocoding.py`:

```python
import pytest
from src.utils.geocoding import _normalize_address


def test_strips_leading_trailing_whitespace():
    assert _normalize_address("  100 N Charles St  ") == "100 N Charles St"


def test_collapses_internal_whitespace():
    assert _normalize_address("100  N   Charles   St") == "100 N Charles St"


def test_handles_mixed_whitespace():
    assert _normalize_address("100 N Charles St,  Baltimore,  MD  21201") == (
        "100 N Charles St, Baltimore, MD 21201"
    )


def test_empty_string_stays_empty():
    assert _normalize_address("   ") == ""


def test_already_normalized_unchanged():
    addr = "100 N Charles St, Baltimore, MD 21201"
    assert _normalize_address(addr) == addr
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/utils/test_geocoding.py -v
```

Expected: `ImportError` — `_normalize_address` does not exist yet.

- [ ] **Step 3: Implement `_normalize_address` in `src/utils/geocoding.py`**

Add this function near the top of `geocoding.py`, after the imports:

```python
import re

def _normalize_address(address: str) -> str:
    """Collapse whitespace for consistent geocoder cache keys."""
    return re.sub(r"\s+", " ", address.strip())
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/utils/test_geocoding.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```
git add tests/utils/test_geocoding.py src/utils/geocoding.py
git commit -m "feat: add _normalize_address helper to geocoding"
```

---

## Task 3: Geocoding — unified `geocode_address` function (TDD)

**Files:**
- Modify: `tests/utils/test_geocoding.py`
- Modify: `src/utils/geocoding.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/utils/test_geocoding.py`:

```python
from unittest.mock import MagicMock, patch
from src.utils.geocoding import geocode_address


def _make_location(lat, lon):
    loc = MagicMock()
    loc.latitude = lat
    loc.longitude = lon
    return loc


def test_geocode_address_returns_lat_lon():
    with patch("src.utils.geocoding._get_rate_limited_geocoder") as mock_factory:
        mock_factory.return_value = lambda addr, timeout=10: _make_location(39.29, -76.61)
        result = geocode_address("100 N Charles St, Baltimore, MD 21201")
    assert result == pytest.approx((39.29, -76.61))


def test_geocode_address_returns_none_when_not_found():
    with patch("src.utils.geocoding._get_rate_limited_geocoder") as mock_factory:
        mock_factory.return_value = lambda addr, timeout=10: None
        result = geocode_address("zzzz not a real address")
    assert result is None


def test_geocode_address_normalizes_before_lookup():
    """Extra whitespace is collapsed before the API call."""
    received = []

    def capture(addr, timeout=10):
        received.append(addr)
        return _make_location(39.29, -76.61)

    with patch("src.utils.geocoding._get_rate_limited_geocoder") as mock_factory:
        mock_factory.return_value = capture
        geocode_address("  100 N Charles St  ,  Baltimore  ,  MD  21201  ")

    assert received[0] == "100 N Charles St , Baltimore , MD 21201"
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/utils/test_geocoding.py::test_geocode_address_returns_lat_lon -v
```

Expected: `ImportError` — `geocode_address` does not exist yet.

- [ ] **Step 3: Add `geocode_address` and remove old functions from `src/utils/geocoding.py`**

Replace the existing `geocode_address_with_cache` and `cached_geocode_address` functions with:

```python
@st.cache_data(ttl=60 * 60 * 24)
def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """Geocode an address; returns (lat, lon) or None. Cached 24hr.

    Normalizes whitespace before the API call so minor formatting
    differences hit the same cache entry.
    """
    normalized = _normalize_address(address)
    try:
        geocode_fn = _get_rate_limited_geocoder()
        location = geocode_fn(normalized)
        if location:
            return location.latitude, location.longitude
        return None
    except (GeocoderTimedOut, GeocoderServiceError):
        st.warning("Geocoding service temporarily unavailable. Please try again.")
        return None
    except Exception as e:
        st.error(f"Error geocoding address: {str(e)}")
        return None
```

Also update the module-level `__all__` (if present) or add one:

```python
__all__ = ["geocode_address", "handle_geocoding_error"]
```

Delete `geocode_address_with_cache` and `cached_geocode_address` entirely.

- [ ] **Step 4: Run all geocoding tests**

```
pytest tests/utils/test_geocoding.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```
git add tests/utils/test_geocoding.py src/utils/geocoding.py
git commit -m "feat: consolidate geocoding to single geocode_address with 24hr cache"
```

---

## Task 4: Update geocoding import sites

**Files:**
- Modify: `src/utils/providers.py`
- Modify: `pages/1_🔎_Search.py`

No new tests needed — the geocoding behavior is already covered. These are import renames.

- [ ] **Step 1: Update `src/utils/providers.py`**

Find these lines in `providers.py`:

```python
try:
    from .geocoding import cached_geocode_address as _cached_geocode_address
    from .geocoding import geocode_address_with_cache as _geocode_address_with_cache
except Exception:
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
```

Replace with:

```python
try:
    from .geocoding import geocode_address as _geocode_address
except Exception:
    def _geocode_address(address: str):  # type: ignore[no-redef]
        st.warning(
            "Geocoding unavailable at import time. Install 'geopy' to enable address lookups."
        )
        return None
```

Then find these two wrapper functions at the bottom of `providers.py`:

```python
def geocode_address_with_cache(address: str) -> Optional[Tuple[float, float]]:
    ...
    return _geocode_address_with_cache(address)


def cached_geocode_address(address: str) -> Any:
    ...
    return _cached_geocode_address(address)
```

Replace both with a single wrapper:

```python
def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """Geocode an address with 24hr caching; returns (lat, lon) or None."""
    return _geocode_address(address)
```

Update the `__all__` list in `providers.py` — remove `"geocode_address_with_cache"` and `"cached_geocode_address"`, add `"geocode_address"`.

- [ ] **Step 2: Update `pages/1_🔎_Search.py`**

Find:

```python
try:
    from src.utils.geocoding import geocode_address_with_cache

    GEOCODE_AVAILABLE = True
except Exception:
    geocode_address_with_cache = None
    GEOCODE_AVAILABLE = False
```

Replace with:

```python
try:
    from src.utils.geocoding import geocode_address

    GEOCODE_AVAILABLE = True
except Exception:
    geocode_address = None
    GEOCODE_AVAILABLE = False
```

Find in the search button handler:

```python
if not GEOCODE_AVAILABLE or geocode_address_with_cache is None:
    st.error("❌ Geocoding service unavailable. Please contact support.")
    st.info("Technical note: geopy package is not installed")
    st.stop()

with st.spinner("🌍 Looking up address coordinates..."):
    coords = geocode_address_with_cache(full_address)
```

Replace with:

```python
if not GEOCODE_AVAILABLE or geocode_address is None:
    st.error("❌ Geocoding service unavailable. Please contact support.")
    st.info("Technical note: geopy package is not installed")
    st.stop()

with st.spinner("🌍 Looking up address coordinates..."):
    coords = geocode_address(full_address)
```

- [ ] **Step 3: Verify tests still pass**

```
pytest tests/ -v
```

Expected: all 8 tests PASS.

- [ ] **Step 4: Commit**

```
git add src/utils/providers.py pages/1_🔎_Search.py
git commit -m "refactor: update import sites to use unified geocode_address"
```

---

## Task 5: Scoring — `_rank_normalize` helper (TDD)

**Files:**
- Create: `tests/utils/test_scoring.py`
- Modify: `src/utils/scoring.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/utils/test_scoring.py`:

```python
import numpy as np
import pandas as pd
import pytest

from src.utils.scoring import _rank_normalize


def test_rank_normalize_distance_lower_is_better():
    """Closest provider (lowest distance) gets score 1.0."""
    values = np.array([1.0, 5.0, 10.0])
    result = _rank_normalize(values, higher_is_better=False)
    assert result[0] == pytest.approx(1.0)
    assert result[1] == pytest.approx(0.5)
    assert result[2] == pytest.approx(0.0)


def test_rank_normalize_clients_higher_is_better():
    """Provider with most clients gets score 1.0."""
    values = np.array([0.0, 5.0, 20.0])
    result = _rank_normalize(values, higher_is_better=True)
    assert result[0] == pytest.approx(0.0)
    assert result[1] == pytest.approx(0.5)
    assert result[2] == pytest.approx(1.0)


def test_rank_normalize_single_provider_scores_one():
    result = _rank_normalize(np.array([42.0]), higher_is_better=True)
    assert result[0] == pytest.approx(1.0)


def test_rank_normalize_outlier_does_not_compress_others():
    """An outlier 1000 miles away should not compress nearby providers' scores."""
    values = np.array([1.0, 2.0, 3.0, 1000.0])
    result = _rank_normalize(values, higher_is_better=False)
    # Scores should be distinct and well-spread, not all near 1.0
    assert result[0] == pytest.approx(1.0)
    assert result[1] == pytest.approx(2 / 3)
    assert result[2] == pytest.approx(1 / 3)
    assert result[3] == pytest.approx(0.0)


def test_rank_normalize_ties_get_average_rank():
    """Tied values receive the average of the ranks they span."""
    values = np.array([1.0, 1.0, 3.0])
    result = _rank_normalize(values, higher_is_better=True)
    # ranks from scipy: [1.5, 1.5, 3] → normalized (higher=better): [(1.5-1)/2, (1.5-1)/2, (3-1)/2]
    assert result[0] == pytest.approx(0.25)
    assert result[1] == pytest.approx(0.25)
    assert result[2] == pytest.approx(1.0)
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/utils/test_scoring.py -v
```

Expected: `ImportError` — `_rank_normalize` does not exist.

- [ ] **Step 3: Implement `_rank_normalize` in `src/utils/scoring.py`**

Add this import at the top of `scoring.py`:

```python
from scipy.stats import rankdata
```

Add this function before `calculate_distances`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/utils/test_scoring.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```
git add tests/utils/test_scoring.py src/utils/scoring.py
git commit -m "feat: add _rank_normalize helper to scoring module"
```

---

## Task 6: Scoring — rewrite `recommend_provider` with rank normalization and experience floor (TDD)

**Files:**
- Modify: `tests/utils/test_scoring.py`
- Modify: `src/utils/scoring.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/utils/test_scoring.py`:

```python
from src.utils.scoring import recommend_provider


@pytest.fixture
def three_providers():
    return pd.DataFrame({
        "Full Name": ["Alice", "Bob", "Carol"],
        "Distance (Miles)": [1.0, 5.0, 10.0],
        "Client Count": [0, 5, 20],
    })


def test_closest_provider_wins_with_distance_only(three_providers):
    _, df = recommend_provider(
        three_providers, distance_weight=1.0, client_weight=0.0, specialty_weight=0.0
    )
    assert df.iloc[0]["Full Name"] == "Alice"


def test_most_experienced_wins_with_client_only(three_providers):
    _, df = recommend_provider(
        three_providers, distance_weight=0.0, client_weight=1.0, specialty_weight=0.0
    )
    assert df.iloc[0]["Full Name"] == "Carol"


def test_experience_floor_zero_client_provider(three_providers):
    """Zero-client provider should receive at least the experience_floor score."""
    _, df = recommend_provider(
        three_providers,
        distance_weight=0.0,
        client_weight=1.0,
        specialty_weight=0.0,
        experience_floor=0.25,
    )
    alice_score = df.loc[df["Full Name"] == "Alice", "Score"].iloc[0]
    assert alice_score >= 0.25


def test_rank_normalization_outlier_does_not_flatten_nearby_scores():
    """An outlier far provider should not collapse nearby providers to the same score."""
    df = pd.DataFrame({
        "Full Name": ["Alice", "Bob", "Carol", "Outlier"],
        "Distance (Miles)": [1.0, 2.0, 3.0, 500.0],
        "Client Count": [10, 10, 10, 10],
    })
    _, scored = recommend_provider(
        df, distance_weight=1.0, client_weight=0.0, specialty_weight=0.0
    )
    scores = scored.set_index("Full Name")["Score"]
    assert scores["Alice"] > scores["Bob"] > scores["Carol"]


def test_recommend_provider_returns_none_when_empty():
    empty = pd.DataFrame({"Full Name": [], "Distance (Miles)": [], "Client Count": []})
    best, scored = recommend_provider(empty)
    assert best is None
    assert scored is None


def test_best_is_first_row_of_scored_df(three_providers):
    best, scored = recommend_provider(
        three_providers, distance_weight=1.0, client_weight=0.0, specialty_weight=0.0
    )
    assert best["Full Name"] == scored.iloc[0]["Full Name"]
```

- [ ] **Step 2: Run to verify failures**

```
pytest tests/utils/test_scoring.py -k "recommend_provider" -v
```

Expected: failures because `recommend_provider` signature doesn't accept `specialty_weight` yet.

- [ ] **Step 3: Rewrite `recommend_provider` in `src/utils/scoring.py`**

Replace the entire existing `recommend_provider` function with:

```python
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
```

Also add `_specialty_scores` immediately before `recommend_provider`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/utils/test_scoring.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```
git add tests/utils/test_scoring.py src/utils/scoring.py
git commit -m "feat: rewrite recommend_provider with rank normalization and experience floor"
```

---

## Task 7: Scoring — star rating and specialty match quality (TDD)

**Files:**
- Modify: `tests/utils/test_scoring.py`
- No new implementation needed — `recommend_provider` already handles these; tests validate the behavior.

- [ ] **Step 1: Write the failing tests**

Append to `tests/utils/test_scoring.py`:

```python
def test_star_weight_higher_rated_provider_wins():
    df = pd.DataFrame({
        "Full Name": ["LowStar", "HighStar"],
        "Distance (Miles)": [1.0, 2.0],
        "Client Count": [10, 10],
        "Rating": [2.0, 5.0],
    })
    _, scored = recommend_provider(
        df, distance_weight=0.0, client_weight=0.0, star_weight=1.0, specialty_weight=0.0
    )
    assert scored.iloc[0]["Full Name"] == "HighStar"


def test_star_missing_rating_gets_median_not_zero():
    """Provider with NaN Rating is not floored to 0 — it gets the pool median."""
    df = pd.DataFrame({
        "Full Name": ["HasRating", "NoRating"],
        "Distance (Miles)": [1.0, 1.0],
        "Client Count": [10, 10],
        "Rating": [4.0, float("nan")],
    })
    _, scored = recommend_provider(
        df, distance_weight=0.0, client_weight=0.0, star_weight=1.0, specialty_weight=0.0
    )
    no_rating_score = scored.loc[scored["Full Name"] == "NoRating", "Score"].iloc[0]
    # median fill gives same value as HasRating → tied rank → score 0.5, not 0.0
    assert no_rating_score > 0.0


def test_specialty_primary_outscores_secondary_match():
    """Primary specialty match (1.0) outranks secondary match (0.5) when weights favor specialty."""
    df = pd.DataFrame({
        "Full Name": ["PrimaryMatch", "SecondaryMatch"],
        "Distance (Miles)": [5.0, 1.0],  # SecondaryMatch is closer
        "Client Count": [10, 10],
        "Specialty": ["Cardiology", "Oncology"],
        "sec_spec_1": ["", "Cardiology"],
    })
    _, scored = recommend_provider(
        df,
        distance_weight=0.0,
        client_weight=0.0,
        star_weight=0.0,
        specialty_weight=1.0,
        selected_specialties=["Cardiology"],
    )
    assert scored.iloc[0]["Full Name"] == "PrimaryMatch"


def test_specialty_scores_all_ones_when_no_filter():
    """No selected_specialties means all providers score equally on specialty."""
    df = pd.DataFrame({
        "Full Name": ["A", "B"],
        "Distance (Miles)": [1.0, 2.0],
        "Client Count": [10, 5],
        "Specialty": ["Cardiology", "Oncology"],
    })
    from src.utils.scoring import _specialty_scores
    scores = _specialty_scores(df, selected_specialties=None)
    assert np.all(scores == 1.0)
```

- [ ] **Step 2: Run to verify tests pass immediately**

```
pytest tests/utils/test_scoring.py -v
```

Expected: all tests PASS (implementation is already in place from Task 6).

If any fail, debug the `_specialty_scores` or `recommend_provider` implementation.

- [ ] **Step 3: Commit**

```
git add tests/utils/test_scoring.py
git commit -m "test: add star rating and specialty match quality test coverage"
```

---

## Task 8: Fix `providers.py` recommend_provider wrapper

**Files:**
- Modify: `src/utils/providers.py`

The existing wrapper accepts `referral_weight` and `inbound_weight` (which don't exist in the underlying function) and passes them positionally, which would raise a `TypeError` at runtime. Fix the wrapper to match the new `scoring.py` signature.

- [ ] **Step 1: Replace the wrapper in `src/utils/providers.py`**

Find:

```python
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
```

Replace with:

```python
def recommend_provider(
    provider_df: pd.DataFrame,
    distance_weight: float = 0.5,
    client_weight: float = 0.3,
    star_weight: float = 0.0,
    specialty_weight: float = 0.2,
    selected_specialties: Optional[List[str]] = None,
    experience_floor: float = 0.25,
    min_clients: Optional[int] = None,
) -> Tuple[Optional[pd.Series], Optional[pd.DataFrame]]:
    """Recommend a provider using the scoring algorithm in src.utils.scoring."""
    return _recommend_provider(
        provider_df,
        distance_weight=distance_weight,
        client_weight=client_weight,
        star_weight=star_weight,
        specialty_weight=specialty_weight,
        selected_specialties=selected_specialties,
        experience_floor=experience_floor,
        min_clients=min_clients,
    )
```

Also add `List` to the imports at the top of `providers.py` if not already present:

```python
from typing import Any, List, Optional, Tuple
```

- [ ] **Step 2: Run full test suite**

```
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```
git add src/utils/providers.py
git commit -m "fix: align providers.py recommend_provider wrapper with scoring.py signature"
```

---

## Task 9: Final verification

**Files:** none changed

- [ ] **Step 1: Run full test suite**

```
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 2: Verify the app can be imported without errors**

```
python -c "from src.utils.scoring import recommend_provider, _rank_normalize, _specialty_scores; print('scoring OK')"
python -c "from src.utils.geocoding import geocode_address, _normalize_address; print('geocoding OK')"
python -c "from src.utils.providers import recommend_provider, geocode_address; print('providers OK')"
python -c "from src.app_logic import run_recommendation, load_application_data; print('app_logic OK')"
```

Expected: all four lines print `OK` with no import errors.

- [ ] **Step 3: Final commit**

```
git add .
git commit -m "feat: complete search improvements — geocoding hardening and scoring overhaul"
```

---

## Self-Review Notes

**Spec coverage check:**
- Geocoding consolidation → Tasks 2, 3, 4 ✓
- Address normalization before API call → Task 2, 3 ✓
- 24hr cache TTL → Task 3 ✓
- Rank-based normalization → Tasks 5, 6 ✓
- Experience floor → Task 6 ✓
- Star rating dimension → Task 7 ✓
- Specialty match quality (primary vs secondary) → Task 7 ✓
- Fix providers.py wrapper → Task 8 ✓
- scipy added to requirements → Task 1 ✓

**Type consistency:** `_rank_normalize` takes `np.ndarray`, returns `np.ndarray`. `_specialty_scores` takes `pd.DataFrame` + `Optional[List[str]]`, returns `np.ndarray`. `recommend_provider` signature is consistent across `scoring.py` and `providers.py` wrapper after Task 8. ✓

**No placeholders:** All steps contain concrete code or commands. ✓
