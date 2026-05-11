# Notebook-to-Python Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert notebooks 2–4 in `prepare_contacts/` to standalone Python scripts and add a `pipeline.py` orchestrator that runs all four cleaning steps in sequence.

**Architecture:** Each notebook becomes its own `.py` script (matching the style of the existing `1__Cleaning_Providers_List.py`) with named functions, logging, and a `main()` entry point. A `pipeline.py` imports and calls all four `main()` functions in order, with an optional `--steps` flag to run a subset.

**Tech Stack:** Python 3.11+, pandas, geopy (Nominatim + RateLimiter), tqdm, hashlib, json, pytest

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `prepare_contacts/2__Contact_Geocoding.py` | Geocode cleaned contacts via Nominatim with caching + fallback |
| Create | `prepare_contacts/3__Cleaning_Reviews.py` | Filter and deduplicate raw reviews CSV |
| Create | `prepare_contacts/4__Combining_Contacts_Reviews.py` | Inner-merge geocoded contacts with cleaned reviews |
| Create | `prepare_contacts/pipeline.py` | Orchestrate steps 1–4 in sequence |
| Create | `tests/prepare_contacts/__init__.py` | Test package init |
| Create | `tests/prepare_contacts/test_geocoding_step.py` | Unit tests for step 2 |
| Create | `tests/prepare_contacts/test_cleaning_reviews.py` | Unit tests for step 3 |
| Create | `tests/prepare_contacts/test_combining.py` | Unit tests for step 4 |

---

## Task 1: Test package init + step 3 (`3__Cleaning_Reviews.py`)

Step 3 is the simplest — good starting point. Logic: load CSV → strip column names → drop rows where `star_value` is null → deduplicate on `org_PAC_ID` → save parquet.

**Files:**
- Create: `tests/prepare_contacts/__init__.py`
- Create: `tests/prepare_contacts/test_cleaning_reviews.py`
- Create: `prepare_contacts/3__Cleaning_Reviews.py`

- [ ] **Step 1.1: Create test package init**

Create an empty file at `tests/prepare_contacts/__init__.py`.

- [ ] **Step 1.2: Write failing tests for `clean_reviews`**

Create `tests/prepare_contacts/test_cleaning_reviews.py`:

```python
import pandas as pd
import pytest
from prepare_contacts._3__Cleaning_Reviews import clean_reviews


def _raw_reviews(**overrides):
    data = {
        "org_PAC_ID": [1, 2, 3, 2],
        "star_value": [5.0, 4.0, None, 3.0],
        "patient_count": [100, 200, 50, 200],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def test_drops_rows_with_null_star_value():
    df = _raw_reviews()
    result = clean_reviews(df)
    assert result["star_value"].notna().all()
    assert len(result) == 2  # rows 0 and 1 survive (row 1 deduped to first)


def test_deduplicates_on_org_pac_id():
    df = _raw_reviews()
    result = clean_reviews(df)
    assert result["org_PAC_ID"].nunique() == len(result)


def test_keeps_first_occurrence_on_dedup():
    df = _raw_reviews()
    result = clean_reviews(df)
    # org_PAC_ID=2 appears twice; first has star_value=4.0
    row = result[result["org_PAC_ID"] == 2].iloc[0]
    assert row["star_value"] == 4.0


def test_strips_column_name_whitespace():
    df = pd.DataFrame({" org_PAC_ID ": [1], " star_value ": [5.0], "patient_count": [100]})
    result = clean_reviews(df)
    assert "org_PAC_ID" in result.columns
    assert "star_value" in result.columns


def test_empty_dataframe_returns_empty():
    df = pd.DataFrame({"org_PAC_ID": [], "star_value": [], "patient_count": []})
    result = clean_reviews(df)
    assert len(result) == 0
```

- [ ] **Step 1.3: Run tests to verify they fail**

```
python -m pytest tests/prepare_contacts/test_cleaning_reviews.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` (module doesn't exist yet).

- [ ] **Step 1.4: Implement `3__Cleaning_Reviews.py`**

Create `prepare_contacts/3__Cleaning_Reviews.py`:

```python
"""Reviews data cleaning script.

Loads raw group public reporting CSV, drops records without a star rating,
deduplicates by org_PAC_ID, and saves a compressed parquet file.

Usage:
    python prepare_contacts/3__Cleaning_Reviews.py
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_INPUT_PATH = Path(__file__).parent.parent / "data" / "raw" / "grp_public_reporting.csv"
DEFAULT_OUTPUT_PATH = Path(__file__).parent.parent / "data" / "processed" / "cleaned_reviews.parquet"


def load_reviews(file_path: Path) -> pd.DataFrame:
    if not file_path.exists():
        raise FileNotFoundError(f"Reviews CSV not found: {file_path}")
    logger.info(f"Loading reviews from {file_path}")
    df = pd.read_csv(file_path, low_memory=False)
    logger.info(f"Loaded {len(df)} raw review records")
    return df


def clean_reviews(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=lambda x: x.strip())
    initial = len(df)
    df = df.dropna(subset=["star_value"], ignore_index=True)
    logger.info(f"Dropped {initial - len(df)} records with no star_value")
    df = df.drop_duplicates(subset=["org_PAC_ID"], ignore_index=True)
    logger.info(f"Retained {len(df)} records after deduplication on org_PAC_ID")
    return df


def save_reviews(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False, compression="zstd")
    logger.info(f"Saved {len(df)} cleaned reviews to {output_path}")


def main(
    input_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
) -> None:
    input_path = input_path or DEFAULT_INPUT_PATH
    output_path = output_path or DEFAULT_OUTPUT_PATH
    logger.info("Starting reviews cleaning workflow")
    df = load_reviews(input_path)
    df = clean_reviews(df)
    save_reviews(df, output_path)
    logger.info("Reviews cleaning workflow complete")


if __name__ == "__main__":
    main()
```

- [ ] **Step 1.5: Fix import in test file**

The test imports `from prepare_contacts._3__Cleaning_Reviews import clean_reviews`. Python module names can't start with a digit. Update the import in `tests/prepare_contacts/test_cleaning_reviews.py` to use `importlib`:

```python
import importlib, sys
from pathlib import Path

# Load the module whose filename starts with a digit
spec = importlib.util.spec_from_file_location(
    "step3",
    Path(__file__).parent.parent.parent / "prepare_contacts" / "3__Cleaning_Reviews.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
clean_reviews = mod.clean_reviews
```

Replace the original import line with this block at the top of `test_cleaning_reviews.py`. Remove the `from prepare_contacts._3__Cleaning_Reviews import clean_reviews` line entirely.

- [ ] **Step 1.6: Run tests to verify they pass**

```
python -m pytest tests/prepare_contacts/test_cleaning_reviews.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 1.7: Commit**

```
git add prepare_contacts/3__Cleaning_Reviews.py tests/prepare_contacts/__init__.py tests/prepare_contacts/test_cleaning_reviews.py
git commit -m "feat: add 3__Cleaning_Reviews.py with tests"
```

---

## Task 2: Step 4 (`4__Combining_Contacts_Reviews.py`)

Logic: load geocoded contacts → load reviews (3 columns) → inner merge on pac_id → reset index → save parquet.

**Files:**
- Create: `tests/prepare_contacts/test_combining.py`
- Create: `prepare_contacts/4__Combining_Contacts_Reviews.py`

- [ ] **Step 2.1: Write failing tests for `combine_contacts_reviews`**

Create `tests/prepare_contacts/test_combining.py`:

```python
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location(
    "step4",
    Path(__file__).parent.parent.parent / "prepare_contacts" / "4__Combining_Contacts_Reviews.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
combine_contacts_reviews = mod.combine_contacts_reviews


def _contacts(**overrides):
    data = {
        "Ind_PAC_ID": [1, 2, 3],
        "org_pac_id": [100, 200, 300],
        "latitude": [39.29, 38.90, 39.50],
        "longitude": [-76.61, -76.84, -77.25],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def _reviews(**overrides):
    data = {
        "org_PAC_ID": [100, 200, 999],
        "patient_count": [500.0, 300.0, 100.0],
        "star_value": [4.0, 5.0, 3.0],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def test_inner_merge_drops_unmatched_contacts():
    contacts = _contacts()
    reviews = _reviews()
    result = combine_contacts_reviews(contacts, reviews)
    # org_pac_id=300 has no matching review; org_PAC_ID=999 has no matching contact
    assert set(result["org_pac_id"].tolist()) == {100, 200}


def test_result_has_all_contact_and_review_columns():
    result = combine_contacts_reviews(_contacts(), _reviews())
    for col in ["Ind_PAC_ID", "org_pac_id", "latitude", "org_PAC_ID", "patient_count", "star_value"]:
        assert col in result.columns


def test_index_is_reset():
    result = combine_contacts_reviews(_contacts(), _reviews())
    assert list(result.index) == list(range(len(result)))


def test_empty_reviews_returns_empty():
    contacts = _contacts()
    reviews = pd.DataFrame({"org_PAC_ID": [], "patient_count": [], "star_value": []})
    result = combine_contacts_reviews(contacts, reviews)
    assert len(result) == 0
```

- [ ] **Step 2.2: Run tests to verify they fail**

```
python -m pytest tests/prepare_contacts/test_combining.py -v
```

Expected: module load error (file doesn't exist yet).

- [ ] **Step 2.3: Implement `4__Combining_Contacts_Reviews.py`**

Create `prepare_contacts/4__Combining_Contacts_Reviews.py`:

```python
"""Combine geocoded contacts with cleaned reviews.

Performs an inner merge of geocoded provider contacts with group-level
star ratings, keeping only providers that have matching review data.

Usage:
    python prepare_contacts/4__Combining_Contacts_Reviews.py
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_CONTACTS_PATH = Path(__file__).parent.parent / "data" / "processed" / "Geocoded_Contacts.parquet"
DEFAULT_REVIEWS_PATH = Path(__file__).parent.parent / "data" / "processed" / "cleaned_reviews.parquet"
DEFAULT_OUTPUT_PATH = Path(__file__).parent.parent / "data" / "processed" / "Combined_Contacts_and_Reviews.parquet"

REVIEW_COLUMNS = ["org_PAC_ID", "patient_count", "star_value"]


def load_contacts(file_path: Path) -> pd.DataFrame:
    if not file_path.exists():
        raise FileNotFoundError(f"Geocoded contacts not found: {file_path}")
    logger.info(f"Loading geocoded contacts from {file_path}")
    df = pd.read_parquet(file_path)
    logger.info(f"Loaded {len(df)} contact records")
    return df


def load_reviews(file_path: Path) -> pd.DataFrame:
    if not file_path.exists():
        raise FileNotFoundError(f"Cleaned reviews not found: {file_path}")
    logger.info(f"Loading reviews from {file_path}")
    df = pd.read_parquet(file_path, columns=REVIEW_COLUMNS)
    logger.info(f"Loaded {len(df)} review records")
    return df


def combine_contacts_reviews(contacts: pd.DataFrame, reviews: pd.DataFrame) -> pd.DataFrame:
    df = pd.merge(contacts, reviews, how="inner", left_on="org_pac_id", right_on="org_PAC_ID")
    df = df.reset_index(drop=True)
    logger.info(f"Combined dataset has {len(df)} records")
    return df


def save_combined(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False, compression="zstd")
    logger.info(f"Saved {len(df)} combined records to {output_path}")


def main(
    contacts_path: Optional[Path] = None,
    reviews_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
) -> None:
    contacts_path = contacts_path or DEFAULT_CONTACTS_PATH
    reviews_path = reviews_path or DEFAULT_REVIEWS_PATH
    output_path = output_path or DEFAULT_OUTPUT_PATH
    logger.info("Starting contacts+reviews combine workflow")
    contacts = load_contacts(contacts_path)
    reviews = load_reviews(reviews_path)
    combined = combine_contacts_reviews(contacts, reviews)
    save_combined(combined, output_path)
    logger.info("Combine workflow complete")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2.4: Run tests to verify they pass**

```
python -m pytest tests/prepare_contacts/test_combining.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 2.5: Commit**

```
git add prepare_contacts/4__Combining_Contacts_Reviews.py tests/prepare_contacts/test_combining.py
git commit -m "feat: add 4__Combining_Contacts_Reviews.py with tests"
```

---

## Task 3: Step 2 (`2__Contact_Geocoding.py`)

Most complex step. Converts the geocoding notebook to a CLI script. Key functions: address formatting (3 fallback levels), MD5 cache, Nominatim with rate limiter, batch progress with tqdm, cache save every 50 addresses.

**Files:**
- Create: `tests/prepare_contacts/test_geocoding_step.py`
- Create: `prepare_contacts/2__Contact_Geocoding.py`

- [ ] **Step 3.1: Write failing tests for address formatting**

Create `tests/prepare_contacts/test_geocoding_step.py`:

```python
import importlib.util
from pathlib import Path
import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location(
    "step2",
    Path(__file__).parent.parent.parent / "prepare_contacts" / "2__Contact_Geocoding.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
build_address_string = mod.build_address_string
apply_geocodes_to_df = mod.apply_geocodes_to_df
hash_address = mod.hash_address


def _row(**overrides):
    defaults = {
        "adr_ln_1": "100 N CHARLES ST",
        "adr_ln_2": "SUITE 100",
        "City/Town": "BALTIMORE",
        "State": "MD",
        "ZIP Code": "21201",
    }
    defaults.update(overrides)
    return pd.Series(defaults)


def test_fallback_0_includes_all_components():
    result = build_address_string(_row(), fallback_level=0)
    assert "100 N CHARLES ST" in result
    assert "SUITE 100" in result
    assert "BALTIMORE" in result
    assert "MD" in result
    assert "21201" in result


def test_fallback_0_skips_missing_adr_ln_2():
    result = build_address_string(_row(adr_ln_2=None), fallback_level=0)
    assert "None" not in result
    assert "100 N CHARLES ST" in result


def test_fallback_1_excludes_adr_ln_2():
    result = build_address_string(_row(), fallback_level=1)
    assert "SUITE 100" not in result
    assert "100 N CHARLES ST" in result
    assert "BALTIMORE" in result


def test_fallback_2_is_zip_and_state_only():
    result = build_address_string(_row(), fallback_level=2)
    assert result == "21201, MD"
    assert "100 N CHARLES ST" not in result


def test_hash_address_is_deterministic():
    assert hash_address("100 N Charles St") == hash_address("100 N Charles St")


def test_hash_address_is_case_insensitive():
    assert hash_address("100 N CHARLES ST") == hash_address("100 n charles st")


def test_hash_address_strips_whitespace():
    assert hash_address("  100 N Charles St  ") == hash_address("100 N Charles St")


def _geocoded_df():
    return pd.DataFrame({
        "adr_ln_1": ["100 N CHARLES ST", "200 MAIN ST"],
        "adr_ln_2": ["SUITE 100", None],
        "City/Town": ["BALTIMORE", "ANNAPOLIS"],
        "State": ["MD", "MD"],
        "ZIP Code": ["21201", "21401"],
        "latitude": [None, None],
        "longitude": [None, None],
    })


def test_apply_geocodes_fills_lat_lon():
    df = _geocoded_df()
    df["_full_address"] = df.apply(build_address_string, axis=1)
    coords = {
        df.loc[0, "_full_address"]: (39.29, -76.61),
        df.loc[1, "_full_address"]: (38.97, -76.49),
    }
    result = apply_geocodes_to_df(df.drop(columns=["_full_address"]), coords)
    assert result.loc[0, "latitude"] == pytest.approx(39.29)
    assert result.loc[1, "longitude"] == pytest.approx(-76.49)


def test_apply_geocodes_leaves_none_for_missing():
    df = _geocoded_df()
    result = apply_geocodes_to_df(df, {})
    assert result["latitude"].isna().all()
```

- [ ] **Step 3.2: Run tests to verify they fail**

```
python -m pytest tests/prepare_contacts/test_geocoding_step.py -v
```

Expected: module load error (file doesn't exist yet).

- [ ] **Step 3.3: Implement `2__Contact_Geocoding.py`**

Create `prepare_contacts/2__Contact_Geocoding.py`:

```python
"""Geocode cleaned provider contacts via Nominatim/OpenStreetMap.

Reads cleaned_contacts.parquet, geocodes each unique Full Address using a
three-level fallback strategy, caches results to avoid repeated API calls,
and writes Geocoded_Contacts.parquet.

Usage:
    python prepare_contacts/2__Contact_Geocoding.py
"""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_INPUT_PATH = Path(__file__).parent.parent / "data" / "processed" / "cleaned_contacts.parquet"
DEFAULT_OUTPUT_PATH = Path(__file__).parent.parent / "data" / "processed" / "Geocoded_Contacts.parquet"
DEFAULT_CACHE_PATH = Path(__file__).parent.parent / "data" / "processed" / "geocode_cache.json"

NOMINATIM_DELAY = 1.5  # seconds between API calls
MAX_RETRIES = 3
CACHE_SAVE_INTERVAL = 50  # save cache every N unique addresses processed
USER_AGENT = "MedMatch_Geocoder/1.0 (bmccarty505@gmail.com)"

Coords = Optional[Tuple[Optional[float], Optional[float]]]


def hash_address(address: str) -> str:
    return hashlib.md5(address.lower().strip().encode()).hexdigest()


def build_address_string(row: pd.Series, fallback_level: int = 0) -> str:
    parts = []
    if fallback_level == 0:
        if pd.notna(row["adr_ln_1"]):
            parts.append(str(row["adr_ln_1"]))
        if pd.notna(row.get("adr_ln_2")) and str(row.get("adr_ln_2", "")).strip():
            parts.append(str(row["adr_ln_2"]))
        if pd.notna(row.get("City/Town")):
            parts.append(str(row["City/Town"]))
        if pd.notna(row["State"]):
            parts.append(str(row["State"]))
        if pd.notna(row["ZIP Code"]):
            parts.append(str(row["ZIP Code"]))
    elif fallback_level == 1:
        if pd.notna(row["adr_ln_1"]):
            parts.append(str(row["adr_ln_1"]))
        if pd.notna(row.get("City/Town")):
            parts.append(str(row["City/Town"]))
        if pd.notna(row["State"]):
            parts.append(str(row["State"]))
        if pd.notna(row["ZIP Code"]):
            parts.append(str(row["ZIP Code"]))
    else:
        if pd.notna(row["ZIP Code"]):
            parts.append(str(row["ZIP Code"]))
        if pd.notna(row["State"]):
            parts.append(str(row["State"]))
    return ", ".join(parts)


def load_geocode_cache(cache_path: Path) -> dict:
    if cache_path.exists():
        with open(cache_path) as f:
            cache = json.load(f)
        logger.info(f"Loaded {len(cache)} cached addresses from {cache_path}")
        return cache
    logger.info("No existing geocode cache — starting fresh")
    return {}


def save_geocode_cache(cache: dict, cache_path: Path, silent: bool = True) -> None:
    with open(cache_path, "w") as f:
        json.dump(cache, f, indent=2)
    if not silent:
        logger.info(f"Cache saved ({len(cache)} entries) to {cache_path}")


def _geocode_single(address: str, geocode_fn, cache: dict, show_errors: bool = False) -> Coords:
    addr_hash = hash_address(address)
    if addr_hash in cache:
        cached = cache[addr_hash]
        return cached.get("lat"), cached.get("lon")

    for attempt in range(MAX_RETRIES):
        try:
            location = geocode_fn(address)
            if location:
                lat, lon = location.latitude, location.longitude
            else:
                lat, lon = None, None
            cache[addr_hash] = {
                "lat": lat, "lon": lon, "address": address,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                **({"reason": "not_found"} if lat is None else {}),
            }
            return lat, lon
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if "403" in str(e) or "GeocoderInsufficientPrivileges" in type(e).__name__:
                time.sleep(5)
            if attempt < MAX_RETRIES - 1:
                if show_errors:
                    logger.warning(f"Retry {attempt + 1}/{MAX_RETRIES}: {address[:60]} — {msg}")
                time.sleep(3)
            else:
                if show_errors:
                    logger.warning(f"Failed after {MAX_RETRIES} attempts: {address[:60]} — {msg}")
                cache[addr_hash] = {
                    "lat": None, "lon": None, "address": address,
                    "error": msg, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
    return None, None


def geocode_unique_addresses(
    df: pd.DataFrame,
    geocode_fn,
    cache: dict,
    cache_path: Path,
) -> Dict[str, Coords]:
    df = df.copy()
    df["_addr0"] = df.apply(build_address_string, axis=1, fallback_level=0)
    unique = df["_addr0"].unique()
    logger.info(f"Geocoding {len(unique)} unique addresses ({len(df)} total records)")

    address_coords: Dict[str, Coords] = {}
    error_count = 0

    for i, address in enumerate(tqdm(unique, desc="Geocoding", unit="addr")):
        show_errors = error_count < 5
        lat, lon = _geocode_single(address, geocode_fn, cache, show_errors=show_errors)

        if lat is None:
            error_count += 1
            row_idx = df[df["_addr0"] == address].index[0]
            row = df.loc[row_idx]

            addr1 = build_address_string(row, fallback_level=1)
            if addr1 != address:
                lat, lon = _geocode_single(addr1, geocode_fn, cache, show_errors=show_errors)
                if lat is not None:
                    addr_hash = hash_address(address)
                    cache[addr_hash] = {
                        "lat": lat, "lon": lon, "address": address,
                        "fallback_used": 1, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }

            if lat is None:
                addr2 = build_address_string(row, fallback_level=2)
                if addr2 not in (address, addr1):
                    lat, lon = _geocode_single(addr2, geocode_fn, cache, show_errors=show_errors)
                    if lat is not None:
                        addr_hash = hash_address(address)
                        cache[addr_hash] = {
                            "lat": lat, "lon": lon, "address": address,
                            "fallback_used": 2, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        }

        address_coords[address] = (lat, lon)

        if (i + 1) % CACHE_SAVE_INTERVAL == 0:
            save_geocode_cache(cache, cache_path, silent=True)

    save_geocode_cache(cache, cache_path, silent=False)

    success = sum(1 for lat, _ in address_coords.values() if lat is not None)
    logger.info(
        f"Geocoding complete: {success}/{len(unique)} addresses resolved "
        f"({success / len(unique) * 100:.1f}%)"
    )
    return address_coords


def apply_geocodes_to_df(
    df: pd.DataFrame,
    address_coords: Dict[str, Coords],
) -> pd.DataFrame:
    df = df.copy()
    if "latitude" not in df.columns:
        df["latitude"] = None
    if "longitude" not in df.columns:
        df["longitude"] = None

    addr_col = df.apply(build_address_string, axis=1)
    for idx in df.index:
        address = addr_col[idx]
        coords = address_coords.get(address)
        if coords:
            df.loc[idx, "latitude"] = coords[0]
            df.loc[idx, "longitude"] = coords[1]
    return df


def load_cleaned_contacts(file_path: Path) -> pd.DataFrame:
    if not file_path.exists():
        raise FileNotFoundError(f"Cleaned contacts not found: {file_path}")
    logger.info(f"Loading cleaned contacts from {file_path}")
    df = pd.read_parquet(file_path)
    logger.info(f"Loaded {len(df)} records")
    return df


def save_geocoded_contacts(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False, compression="zstd")
    logger.info(f"Saved {len(df)} geocoded records to {output_path}")


def main(
    input_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
    cache_path: Optional[Path] = None,
) -> None:
    input_path = input_path or DEFAULT_INPUT_PATH
    output_path = output_path or DEFAULT_OUTPUT_PATH
    cache_path = cache_path or DEFAULT_CACHE_PATH

    logger.info("Starting geocoding workflow")
    logger.info("Testing Nominatim connection...")
    geolocator = Nominatim(user_agent=USER_AGENT, timeout=10)
    test = geolocator.geocode("Baltimore, MD")
    if test:
        logger.info(f"Nominatim OK — {test.address} ({test.latitude}, {test.longitude})")
    else:
        logger.warning("Nominatim test returned no result — proceeding anyway")

    geocode_fn = RateLimiter(geolocator.geocode, min_delay_seconds=NOMINATIM_DELAY)

    df = load_cleaned_contacts(input_path)
    cache = load_geocode_cache(cache_path)

    logger.info("Waiting 2s before geocoding to respect rate limits...")
    time.sleep(2)

    address_coords = geocode_unique_addresses(df, geocode_fn, cache, cache_path)
    df = apply_geocodes_to_df(df, address_coords)

    save_geocoded_contacts(df, output_path)
    logger.info("Geocoding workflow complete")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3.4: Run tests to verify they pass**

```
python -m pytest tests/prepare_contacts/test_geocoding_step.py -v
```

Expected: all 10 tests PASS.

- [ ] **Step 3.5: Commit**

```
git add prepare_contacts/2__Contact_Geocoding.py tests/prepare_contacts/test_geocoding_step.py
git commit -m "feat: add 2__Contact_Geocoding.py with tests"
```

---

## Task 4: `pipeline.py` orchestrator

Imports `main()` from all four step scripts and calls them in order. Accepts `--steps` to run a subset.

**Files:**
- Create: `prepare_contacts/pipeline.py`

- [ ] **Step 4.1: Implement `pipeline.py`**

Create `prepare_contacts/pipeline.py`:

```python
"""MedMatch data preparation pipeline.

Runs the four prepare_contacts cleaning steps in sequence:
  1. Clean raw provider list → cleaned_contacts.parquet
  2. Geocode contacts → Geocoded_Contacts.parquet
  3. Clean reviews → cleaned_reviews.parquet
  4. Combine contacts + reviews → Combined_Contacts_and_Reviews.parquet

Usage:
    python prepare_contacts/pipeline.py              # run all steps
    python prepare_contacts/pipeline.py --steps 3,4 # run steps 3 and 4 only
"""

import argparse
import importlib.util
import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent


def _load_step(filename: str):
    """Load a step module by filename (handles digit-prefixed names)."""
    path = _HERE / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


STEPS = {
    1: ("1__Cleaning_Providers_List.py", "Clean provider list"),
    2: ("2__Contact_Geocoding.py", "Geocode contacts"),
    3: ("3__Cleaning_Reviews.py", "Clean reviews"),
    4: ("4__Combining_Contacts_Reviews.py", "Combine contacts and reviews"),
}


def run_pipeline(steps_to_run: list[int]) -> None:
    for step_num in steps_to_run:
        filename, label = STEPS[step_num]
        logger.info(f"{'='*60}")
        logger.info(f"Step {step_num}: {label}")
        logger.info(f"{'='*60}")
        t0 = time.monotonic()
        mod = _load_step(filename)
        mod.main()
        elapsed = time.monotonic() - t0
        logger.info(f"Step {step_num} complete in {elapsed:.1f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MedMatch data preparation pipeline.")
    parser.add_argument(
        "--steps",
        type=str,
        default="1,2,3,4",
        help="Comma-separated step numbers to run (default: 1,2,3,4)",
    )
    args = parser.parse_args()

    try:
        steps_to_run = [int(s.strip()) for s in args.steps.split(",")]
    except ValueError:
        parser.error("--steps must be comma-separated integers, e.g. '1,2,3,4' or '3,4'")

    invalid = [s for s in steps_to_run if s not in STEPS]
    if invalid:
        parser.error(f"Invalid step numbers: {invalid}. Valid steps: {sorted(STEPS)}")

    logger.info(f"Running pipeline steps: {steps_to_run}")
    run_pipeline(sorted(steps_to_run))
    logger.info("Pipeline complete.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4.2: Verify pipeline imports cleanly (dry-run syntax check)**

```
python -c "import importlib.util, pathlib; spec = importlib.util.spec_from_file_location('pipeline', 'prepare_contacts/pipeline.py'); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); print('OK')"
```

Expected output: `OK`

- [ ] **Step 4.3: Run all existing tests to confirm nothing broken**

```
python -m pytest tests/ -v
```

Expected: all tests PASS (same count as before + new tests from Tasks 1–3).

- [ ] **Step 4.4: Commit**

```
git add prepare_contacts/pipeline.py
git commit -m "feat: add pipeline.py orchestrator for all four data prep steps"
```

---

## Task 5: Final verification

- [ ] **Step 5.1: Run full test suite**

```
python -m pytest tests/ -v --tb=short
```

Expected: all tests PASS. Note the new test count vs. baseline (was 20 tests before this plan).

- [ ] **Step 5.2: Verify pipeline --help works**

```
python prepare_contacts/pipeline.py --help
```

Expected output includes usage line, `--steps` argument description.

- [ ] **Step 5.3: Commit final state if any minor fixes were needed**

```
git add -u
git commit -m "fix: resolve any remaining issues from pipeline integration"
```

Only run this step if Step 5.1 or 5.2 required fixes. Skip if all green.

---

## Self-Review Notes

- **Spec coverage:**
  - ✅ Step 2 (`2__Contact_Geocoding.py`) with caching, fallbacks, tqdm — Task 3
  - ✅ Step 3 (`3__Cleaning_Reviews.py`) — Task 1
  - ✅ Step 4 (`4__Combining_Contacts_Reviews.py`) — Task 2
  - ✅ `pipeline.py` with `--steps` flag — Task 4
  - ✅ Step 1 left unchanged (spec: "no changes needed")

- **Import pattern:** All test files use `importlib.util.spec_from_file_location` to handle digit-prefixed filenames (`2__`, `3__`, `4__`). This pattern is consistent across Tasks 1–3.

- **Type consistency:** `build_address_string` defined in Task 3, used in Task 3 tests ✅. `combine_contacts_reviews` defined and tested in Task 2 ✅. `clean_reviews` defined and tested in Task 1 ✅.

- **No placeholders** — all code blocks are complete and runnable.
