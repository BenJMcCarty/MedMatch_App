# Geocoding Pipeline & DuckDB Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-script pipeline that cleans provider data into DuckDB and geocodes unique addresses via the Census batch API, producing `data/processed/medmatch.duckdb` as the app's primary data store.

**Architecture:** Script 1 (`2__clean_and_build_db.py`) reads raw CSV, reuses existing cleaning logic, and writes the `providers` table with `address_id = NULL`. Script 2 (`3__geocode_addresses.py`) extracts unique addresses, batch-geocodes via Census API with a CSV cache and ZIP centroid fallback, writes the `addresses` table, and back-fills `providers.address_id`. The existing `src/utils/geocoding.py` already implements `geocode_address()` for user-facing Nominatim lookups — no changes needed there.

**Tech Stack:** Python 3, duckdb, requests, pandas, pytest, Census Geocoder Batch API (no key required)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `prepare_contacts/2__clean_and_build_db.py` | Clean raw data → write `providers` table |
| Create | `prepare_contacts/3__geocode_addresses.py` | Census geocode → write `addresses`, update FK |
| Create | `tests/prepare_contacts/__init__.py` | Package marker |
| Create | `tests/prepare_contacts/test_clean_and_build_db.py` | Tests for script 2 |
| Create | `tests/prepare_contacts/test_geocode_addresses.py` | Tests for script 3 |
| Create | `data/processed/zip_centroids.csv` | Static ZIP→lat/lon fallback (downloaded once) |
| No change | `src/utils/geocoding.py` | Already has `geocode_address()` for app use |

---

## Task 0: Prerequisites

**Files:** None created yet

- [ ] **Step 1: Install duckdb and requests**

```bash
pip install duckdb requests
```

Expected output includes: `Successfully installed duckdb-...`

- [ ] **Step 2: Download and process ZIP centroid file**

Run this Python snippet from the project root:

```python
import csv, io, urllib.request, zipfile

url = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2024_Gazetteer/2024_Gaz_zcta_national.zip"
)
print("Downloading ZIP centroids...")
with urllib.request.urlopen(url) as r:
    zf = zipfile.ZipFile(io.BytesIO(r.read()))
    filename = zf.namelist()[0]
    with zf.open(filename) as f:
        reader = csv.DictReader(
            io.TextIOWrapper(f, encoding="utf-8"), delimiter="\t"
        )
        with open("data/processed/zip_centroids.csv", "w", newline="", encoding="utf-8") as out:
            writer = csv.writer(out)
            writer.writerow(["zip_code", "latitude", "longitude"])
            for row in reader:
                writer.writerow([
                    row["GEOID"].strip(),
                    row["INTPTLAT"].strip(),
                    row["INTPTLONG"].strip(),
                ])
print("Done. data/processed/zip_centroids.csv written.")
```

Expected: file created with ~33k rows (one per ZCTA).

- [ ] **Step 3: Create test package directory**

```bash
mkdir tests\prepare_contacts
```

Create `tests/prepare_contacts/__init__.py` (empty file).

- [ ] **Step 4: Commit setup**

```bash
git add data/processed/zip_centroids.csv tests/prepare_contacts/__init__.py
git commit -m "chore: add zip centroids and prepare_contacts test package"
```

---

## Task 1: Failing Tests for `2__clean_and_build_db.py`

**Files:**
- Create: `tests/prepare_contacts/test_clean_and_build_db.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/prepare_contacts/test_clean_and_build_db.py`:

```python
import importlib.util
import pytest
import duckdb
from pathlib import Path

HERE = Path(__file__).parent
SCRIPT_PATH = HERE.parent.parent / "prepare_contacts" / "2__clean_and_build_db.py"

RAW_CSV = (
    "Ind_PAC_ID,Provider Last Name,Provider First Name,gndr,Cred,pri_spec,"
    "sec_spec_1,sec_spec_2,sec_spec_3,sec_spec_4,sec_spec_all,Telehlth,"
    "Facility Name,org_pac_id,adr_ln_1,adr_ln_2,City/Town,State,ZIP Code,Telephone Number\n"
    "7517003643,SMITH,JOHN,M,MD,FAMILY PRACTICE,,,,,,Y,CLINIC A,111,"
    "100 N CHARLES ST,,BALTIMORE,MD,21201,4105551234\n"
    "9931380672,DOE,JANE,F,MD,NEUROLOGY,,,,,,N,CLINIC B,222,"
    "200 S CHARLES ST,,BALTIMORE,MD,21202,4105555678\n"
    "1111111111,TEST,USER,M,MD,CARDIOLOGY,,,,,,N,CLINIC C,333,"
    "300 MAIN ST,,RICHMOND,VA,23220,8045551234\n"
)


def _load():
    spec = importlib.util.spec_from_file_location("clean_db", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def raw_csv(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text(RAW_CSV, encoding="utf-8")
    return p


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.duckdb"


def test_providers_table_created(raw_csv, db_path):
    _load().build_providers_table(raw_path=raw_csv, db_path=db_path)
    with duckdb.connect(str(db_path)) as con:
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    assert "providers" in tables


def test_filters_to_md_and_target_specialties(raw_csv, db_path):
    _load().build_providers_table(raw_path=raw_csv, db_path=db_path)
    with duckdb.connect(str(db_path)) as con:
        count = con.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
    # VA CARDIOLOGY row excluded; 2 MD rows kept
    assert count == 2


def test_address_id_is_null_initially(raw_csv, db_path):
    _load().build_providers_table(raw_path=raw_csv, db_path=db_path)
    with duckdb.connect(str(db_path)) as con:
        nulls = con.execute(
            "SELECT COUNT(*) FROM providers WHERE address_id IS NULL"
        ).fetchone()[0]
    assert nulls == 2


def test_full_address_built_correctly(raw_csv, db_path):
    _load().build_providers_table(raw_path=raw_csv, db_path=db_path)
    with duckdb.connect(str(db_path)) as con:
        addrs = sorted(
            r[0] for r in con.execute("SELECT full_address FROM providers").fetchall()
        )
    assert addrs[0] == "100 N CHARLES ST, BALTIMORE, MD 21201"
    assert addrs[1] == "200 S CHARLES ST, BALTIMORE, MD 21202"


def test_idempotent(raw_csv, db_path):
    mod = _load()
    mod.build_providers_table(raw_path=raw_csv, db_path=db_path)
    mod.build_providers_table(raw_path=raw_csv, db_path=db_path)
    with duckdb.connect(str(db_path)) as con:
        count = con.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
    assert count == 2


def test_updated_at_populated(raw_csv, db_path):
    _load().build_providers_table(raw_path=raw_csv, db_path=db_path)
    with duckdb.connect(str(db_path)) as con:
        nulls = con.execute(
            "SELECT COUNT(*) FROM providers WHERE updated_at IS NULL"
        ).fetchone()[0]
    assert nulls == 0
```

- [ ] **Step 2: Run to confirm all tests fail**

```bash
pytest tests/prepare_contacts/test_clean_and_build_db.py -v
```

Expected: `ERROR` or `ModuleNotFoundError` — script doesn't exist yet.

---

## Task 2: Implement `2__clean_and_build_db.py`

**Files:**
- Create: `prepare_contacts/2__clean_and_build_db.py`

- [ ] **Step 1: Create the script**

Create `prepare_contacts/2__clean_and_build_db.py`:

```python
"""Step 1: Clean raw provider data and write the initial providers table to DuckDB."""
import importlib.util
import logging
from datetime import datetime, timezone
from pathlib import Path

import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
ROOT = HERE.parent
DEFAULT_RAW_PATH = ROOT / "data" / "raw" / "data.csv"
DEFAULT_DB_PATH = ROOT / "data" / "processed" / "medmatch.duckdb"


def _load_cleaning_module():
    script = HERE / "1__Cleaning_Providers_List.py"
    spec = importlib.util.spec_from_file_location("cleaning", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_providers_table(
    raw_path: Path = DEFAULT_RAW_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    """Clean raw data and write providers table to DuckDB. Returns row count."""
    cleaning = _load_cleaning_module()
    df = cleaning.load_raw_provider_data(raw_path)
    df = cleaning.clean_provider_data(
        df,
        states=cleaning.DEFAULT_STATES,
        specialties=cleaning.DEFAULT_SPECIALTIES,
    )

    db_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    with duckdb.connect(str(db_path)) as con:
        con.execute("DROP TABLE IF EXISTS providers")
        con.execute("""
            CREATE TABLE providers (
                ind_pac_id    VARCHAR,
                last_name     VARCHAR,
                first_name    VARCHAR,
                gender        VARCHAR,
                credential    VARCHAR,
                pri_spec      VARCHAR,
                sec_spec_all  VARCHAR,
                telehealth    VARCHAR,
                facility_name VARCHAR,
                org_pac_id    VARCHAR,
                telephone     VARCHAR,
                full_address  VARCHAR,
                address_id    INTEGER,
                updated_at    TIMESTAMP
            )
        """)
        con.register("df_view", df)
        con.execute("""
            INSERT INTO providers
            SELECT
                CAST("Ind_PAC_ID"       AS VARCHAR),
                "Provider Last Name",
                "Provider First Name",
                gndr,
                "Cred",
                pri_spec,
                sec_spec_all,
                "Telehlth",
                "Facility Name",
                CAST(org_pac_id         AS VARCHAR),
                "Telephone Number",
                "Full Address",
                NULL,
                ?
            FROM df_view
        """, [now])
        row_count = con.execute("SELECT COUNT(*) FROM providers").fetchone()[0]

    logger.info(f"Wrote {row_count} providers to {db_path}")
    return row_count


def main():
    count = build_providers_table()
    logger.info(f"Done. {count} providers written to medmatch.duckdb.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run tests to confirm they pass**

```bash
pytest tests/prepare_contacts/test_clean_and_build_db.py -v
```

Expected: 6 PASSED.

- [ ] **Step 3: Commit**

```bash
git add prepare_contacts/2__clean_and_build_db.py tests/prepare_contacts/test_clean_and_build_db.py
git commit -m "feat: add clean_and_build_db script with providers table"
```

---

## Task 3: Failing Tests for `3__geocode_addresses.py`

**Files:**
- Create: `tests/prepare_contacts/test_geocode_addresses.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/prepare_contacts/test_geocode_addresses.py`:

```python
import csv
import importlib.util
import pytest
import duckdb
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).parent
SCRIPT_PATH = HERE.parent.parent / "prepare_contacts" / "3__geocode_addresses.py"


def _load():
    spec = importlib.util.spec_from_file_location("geocode_addr", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_db(tmp_path, full_address: str) -> Path:
    """Create a minimal providers-only DuckDB for testing."""
    db_path = tmp_path / "test.duckdb"
    with duckdb.connect(str(db_path)) as con:
        con.execute("""
            CREATE TABLE providers (
                ind_pac_id VARCHAR, last_name VARCHAR, first_name VARCHAR,
                gender VARCHAR, credential VARCHAR, pri_spec VARCHAR,
                sec_spec_all VARCHAR, telehealth VARCHAR, facility_name VARCHAR,
                org_pac_id VARCHAR, telephone VARCHAR,
                full_address VARCHAR, address_id INTEGER, updated_at TIMESTAMP
            )
        """)
        con.execute(
            "INSERT INTO providers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ["1","SMITH","JOHN","M","MD","FAMILY PRACTICE","","Y","CLINIC",
             "1","4105551234", full_address, None, None],
        )
    return db_path


def _zip_centroids(tmp_path, zip_code="21201", lat=39.29, lon=-76.61) -> Path:
    p = tmp_path / "zip_centroids.csv"
    p.write_text(f"zip_code,latitude,longitude\n{zip_code},{lat},{lon}\n")
    return p


# ── _parse_full_address ────────────────────────────────────────────────────────

def test_parse_full_address_standard():
    mod = _load()
    street, city, state, zip_code = mod._parse_full_address(
        "100 N CHARLES ST, BALTIMORE, MD 21201"
    )
    assert street == "100 N CHARLES ST"
    assert city == "BALTIMORE"
    assert state == "MD"
    assert zip_code == "21201"


def test_parse_full_address_street_with_comma():
    mod = _load()
    street, city, state, zip_code = mod._parse_full_address(
        "100 N CHARLES ST STE 200, BALTIMORE, MD 21201"
    )
    assert city == "BALTIMORE"
    assert state == "MD"
    assert zip_code == "21201"


# ── _parse_census_response ────────────────────────────────────────────────────

def test_parse_census_response_exact_match():
    mod = _load()
    text = (
        '"0","100 N Charles St, Baltimore, MD 21201","Match","Exact",'
        '"100 N CHARLES ST, BALTIMORE, MD, 21201","-76.6138,39.2909",110398442,R\n'
    )
    results = mod._parse_census_response(text)
    assert len(results) == 1
    r = results[0]
    assert r["match_status"] == "Match"
    assert r["match_type"] == "Exact"
    assert r["latitude"] == pytest.approx(39.2909)
    assert r["longitude"] == pytest.approx(-76.6138)
    assert r["match_score"] == 100


def test_parse_census_response_non_exact_score_is_50():
    mod = _load()
    text = (
        '"0","100 N Charles St, Baltimore, MD 21201","Match","Non_Exact",'
        '"100 N CHARLES ST, BALTIMORE, MD, 21201","-76.6138,39.2909",110398442,R\n'
    )
    results = mod._parse_census_response(text)
    assert results[0]["match_score"] == 50


def test_parse_census_response_no_match():
    mod = _load()
    text = '"1","bad addr, nowhere, XX 00000","No_Match",,,,,\n'
    results = mod._parse_census_response(text)
    r = results[0]
    assert r["match_status"] == "No_Match"
    assert r["latitude"] is None
    assert r["match_score"] is None


def test_parse_census_response_lon_lat_order():
    """Census returns lon,lat — verify we assign them correctly."""
    mod = _load()
    text = (
        '"0","test","Match","Exact","test addr","-77.0000,39.0000",1,R\n'
    )
    results = mod._parse_census_response(text)
    assert results[0]["longitude"] == pytest.approx(-77.0)
    assert results[0]["latitude"] == pytest.approx(39.0)


# ── cache behaviour ───────────────────────────────────────────────────────────

def test_cache_hit_skips_census_api(tmp_path):
    mod = _load()
    addr = "100 N CHARLES ST, BALTIMORE, MD 21201"

    cache_path = tmp_path / "cache.csv"
    with open(cache_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "full_address","latitude","longitude","geocode_source",
            "match_score","match_type","matched_address","geocoded_at",
        ])
        w.writeheader()
        w.writerow({
            "full_address": addr, "latitude": 39.29, "longitude": -76.61,
            "geocode_source": "census", "match_score": 100,
            "match_type": "Exact", "matched_address": addr,
            "geocoded_at": "2026-05-14T00:00:00+00:00",
        })

    db_path = _make_db(tmp_path, addr)
    zip_path = _zip_centroids(tmp_path)

    with patch("requests.post") as mock_post:
        mod.geocode_addresses(
            db_path=db_path, cache_path=cache_path, zip_centroids_path=zip_path
        )
        mock_post.assert_not_called()


# ── fallback ──────────────────────────────────────────────────────────────────

def test_no_match_falls_back_to_zip_centroid(tmp_path):
    mod = _load()
    addr = "999 UNKNOWN ST, BALTIMORE, MD 21201"
    db_path = _make_db(tmp_path, addr)
    zip_path = _zip_centroids(tmp_path, zip_code="21201", lat=39.29, lon=-76.61)
    cache_path = tmp_path / "cache.csv"

    resp = MagicMock()
    resp.text = f'"0","{addr}","No_Match",,,,,\n'
    resp.raise_for_status = lambda: None

    with patch("requests.post", return_value=resp):
        stats = mod.geocode_addresses(
            db_path=db_path, cache_path=cache_path, zip_centroids_path=zip_path
        )

    assert stats["fallback"] == 1
    with duckdb.connect(str(db_path)) as con:
        row = con.execute(
            "SELECT geocode_source, latitude FROM addresses LIMIT 1"
        ).fetchone()
    assert row[0] == "fallback_zip"
    assert row[1] == pytest.approx(39.29)


def test_no_match_no_centroid_is_failed(tmp_path):
    mod = _load()
    addr = "999 UNKNOWN ST, NOWHERE, XX 99999"
    db_path = _make_db(tmp_path, addr)
    zip_path = tmp_path / "zip_centroids.csv"
    zip_path.write_text("zip_code,latitude,longitude\n")  # empty — no 99999
    cache_path = tmp_path / "cache.csv"

    resp = MagicMock()
    resp.text = f'"0","{addr}","No_Match",,,,,\n'
    resp.raise_for_status = lambda: None

    with patch("requests.post", return_value=resp):
        stats = mod.geocode_addresses(
            db_path=db_path, cache_path=cache_path, zip_centroids_path=zip_path
        )

    assert stats["failed"] == 1


# ── DuckDB FK update ──────────────────────────────────────────────────────────

def test_providers_address_id_fk_set_after_geocoding(tmp_path):
    mod = _load()
    addr = "100 N CHARLES ST, BALTIMORE, MD 21201"
    db_path = _make_db(tmp_path, addr)
    zip_path = _zip_centroids(tmp_path)
    cache_path = tmp_path / "cache.csv"

    resp = MagicMock()
    resp.text = (
        f'"0","{addr}","Match","Exact",'
        f'"100 N CHARLES ST, BALTIMORE, MD, 21201","-76.6138,39.2909",110398442,R\n'
    )
    resp.raise_for_status = lambda: None

    with patch("requests.post", return_value=resp):
        mod.geocode_addresses(
            db_path=db_path, cache_path=cache_path, zip_centroids_path=zip_path
        )

    with duckdb.connect(str(db_path)) as con:
        row = con.execute(
            "SELECT p.address_id, a.geocode_source "
            "FROM providers p JOIN addresses a ON p.address_id = a.address_id"
        ).fetchone()
    assert row is not None
    assert row[1] == "census"


def test_new_results_appended_to_cache(tmp_path):
    mod = _load()
    addr = "100 N CHARLES ST, BALTIMORE, MD 21201"
    db_path = _make_db(tmp_path, addr)
    zip_path = _zip_centroids(tmp_path)
    cache_path = tmp_path / "cache.csv"

    resp = MagicMock()
    resp.text = (
        f'"0","{addr}","Match","Exact",'
        f'"100 N CHARLES ST, BALTIMORE, MD, 21201","-76.6138,39.2909",110398442,R\n'
    )
    resp.raise_for_status = lambda: None

    with patch("requests.post", return_value=resp):
        mod.geocode_addresses(
            db_path=db_path, cache_path=cache_path, zip_centroids_path=zip_path
        )

    assert cache_path.exists()
    with open(cache_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["full_address"] == addr
    assert rows[0]["geocode_source"] == "census"
```

- [ ] **Step 2: Run to confirm all tests fail**

```bash
pytest tests/prepare_contacts/test_geocode_addresses.py -v
```

Expected: `ERROR` — script doesn't exist yet.

---

## Task 4: Implement `3__geocode_addresses.py`

**Files:**
- Create: `prepare_contacts/3__geocode_addresses.py`

- [ ] **Step 1: Create the script**

Create `prepare_contacts/3__geocode_addresses.py`:

```python
"""Step 2: Geocode unique provider addresses via Census batch API and update DuckDB."""
import csv
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
ROOT = HERE.parent
DEFAULT_DB_PATH = ROOT / "data" / "processed" / "medmatch.duckdb"
DEFAULT_CACHE_PATH = ROOT / "data" / "processed" / "geocode_cache.csv"
DEFAULT_ZIP_CENTROIDS_PATH = ROOT / "data" / "processed" / "zip_centroids.csv"

CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
CENSUS_BENCHMARK = "Public_AR_Current"
BATCH_SIZE = 1000

_CACHE_FIELDS = [
    "full_address", "latitude", "longitude", "geocode_source",
    "match_score", "match_type", "matched_address", "geocoded_at",
]


def _parse_full_address(full_address: str) -> Tuple[str, str, str, str]:
    """Parse 'STREET, CITY, STATE ZIP' into (street, city, state, zip_code)."""
    parts = [p.strip() for p in full_address.split(",")]
    if len(parts) < 3:
        return full_address, "", "", ""
    state_zip = parts[-1].split()
    state = state_zip[0] if state_zip else ""
    zip_code = state_zip[1] if len(state_zip) > 1 else ""
    city = parts[-2]
    street = ", ".join(parts[:-2])
    return street, city, state, zip_code


def _parse_census_response(response_text: str) -> List[dict]:
    """Parse Census Geocoder batch CSV response. Returns list of result dicts.

    Census response columns (no header):
      id, input_address, match_status, match_type, matched_address,
      coordinates (lon,lat), tiger_line_id, tiger_line_side
    Coordinates are LON,LAT — note the order.
    """
    results = []
    for row in csv.reader(io.StringIO(response_text)):
        if len(row) < 3:
            continue
        rec_id = row[0].strip()
        match_status = row[2].strip()
        match_type = row[3].strip() if len(row) > 3 else ""
        matched_address = row[4].strip() if len(row) > 4 else ""
        coords = row[5].strip() if len(row) > 5 else ""

        lat: Optional[float] = None
        lon: Optional[float] = None
        if coords and match_status == "Match":
            parts = coords.split(",")
            if len(parts) == 2:
                lon = float(parts[0])  # Census: longitude first
                lat = float(parts[1])

        match_score: Optional[int] = None
        if match_status == "Match":
            match_score = 100 if match_type == "Exact" else 50

        results.append({
            "rec_id": rec_id,
            "match_status": match_status,
            "match_type": match_type,
            "matched_address": matched_address,
            "latitude": lat,
            "longitude": lon,
            "match_score": match_score,
        })
    return results


def _load_cache(cache_path: Path) -> Dict[str, dict]:
    if not cache_path.exists():
        return {}
    with open(cache_path, newline="", encoding="utf-8") as f:
        return {row["full_address"]: row for row in csv.DictReader(f)}


def _append_cache(cache_path: Path, results: List[dict]) -> None:
    write_header = not cache_path.exists()
    with open(cache_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CACHE_FIELDS)
        if write_header:
            writer.writeheader()
        for r in results:
            writer.writerow({k: r.get(k, "") for k in _CACHE_FIELDS})


def _load_zip_centroids(path: Path) -> Dict[str, Tuple[float, float]]:
    with open(path, newline="", encoding="utf-8") as f:
        return {
            row["zip_code"]: (float(row["latitude"]), float(row["longitude"]))
            for row in csv.DictReader(f)
        }


def _batch_geocode_census(batch: List[Tuple[str, str]]) -> List[dict]:
    """POST one batch to Census Geocoder. batch = [(rec_id, full_address), ...]"""
    lines = []
    for rec_id, full_addr in batch:
        street, city, state, zip_code = _parse_full_address(full_addr)
        lines.append(f'"{rec_id}","{street}","{city}","{state}","{zip_code}"')
    csv_content = "\n".join(lines)

    response = requests.post(
        CENSUS_BATCH_URL,
        files={"addressFile": ("addresses.csv", csv_content, "text/csv")},
        data={"benchmark": CENSUS_BENCHMARK},
        timeout=120,
    )
    response.raise_for_status()
    return _parse_census_response(response.text)


def _write_to_duckdb(db_path: Path, results_by_addr: Dict[str, dict]) -> None:
    """Write addresses table and update providers.address_id FK."""
    import pandas as pd

    now = datetime.now(timezone.utc)
    rows = []
    for i, (full_address, r) in enumerate(results_by_addr.items(), start=1):
        street, city, state, zip_code = _parse_full_address(full_address)
        lat = r.get("latitude")
        lon = r.get("longitude")
        score = r.get("match_score")
        rows.append({
            "address_id": i,
            "full_address": full_address,
            "adr_ln_1": street,
            "adr_ln_2": None,
            "city": city,
            "state": state,
            "zip_code": zip_code,
            "latitude": float(lat) if lat not in (None, "") else None,
            "longitude": float(lon) if lon not in (None, "") else None,
            "geocode_source": r.get("geocode_source"),
            "match_score": float(score) if score not in (None, "") else None,
            "match_type": r.get("match_type"),
            "matched_address": r.get("matched_address"),
            "geocoded_at": r.get("geocoded_at"),
            "updated_at": now,
        })

    df_addr = pd.DataFrame(rows)

    with duckdb.connect(str(db_path)) as con:
        con.execute("DROP TABLE IF EXISTS addresses")
        con.execute("""
            CREATE TABLE addresses (
                address_id      INTEGER PRIMARY KEY,
                full_address    VARCHAR NOT NULL UNIQUE,
                adr_ln_1        VARCHAR,
                adr_ln_2        VARCHAR,
                city            VARCHAR,
                state           VARCHAR,
                zip_code        VARCHAR,
                latitude        DOUBLE,
                longitude       DOUBLE,
                geocode_source  VARCHAR,
                match_score     DOUBLE,
                match_type      VARCHAR,
                matched_address VARCHAR,
                geocoded_at     TIMESTAMP,
                updated_at      TIMESTAMP
            )
        """)
        con.register("addr_view", df_addr)
        con.execute("INSERT INTO addresses SELECT * FROM addr_view")

        con.execute("""
            UPDATE providers
            SET address_id = (
                SELECT address_id FROM addresses
                WHERE addresses.full_address = providers.full_address
            )
        """)
        updated = con.execute(
            "SELECT COUNT(*) FROM providers WHERE address_id IS NOT NULL"
        ).fetchone()[0]
        logger.info(f"Set address_id FK for {updated} of {len(rows)} providers")


def geocode_addresses(
    db_path: Path = DEFAULT_DB_PATH,
    cache_path: Path = DEFAULT_CACHE_PATH,
    zip_centroids_path: Path = DEFAULT_ZIP_CENTROIDS_PATH,
    batch_size: int = BATCH_SIZE,
) -> dict:
    """Geocode unique addresses and update DuckDB. Returns stats dict."""
    with duckdb.connect(str(db_path)) as con:
        unique_addresses: List[str] = [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT full_address FROM providers "
                "WHERE full_address IS NOT NULL"
            ).fetchall()
        ]

    cache = _load_cache(cache_path)
    uncached = [
        (str(i), addr)
        for i, addr in enumerate(unique_addresses)
        if addr not in cache
    ]

    zip_centroids = _load_zip_centroids(zip_centroids_path)
    now = datetime.now(timezone.utc).isoformat()
    new_results: List[dict] = []

    for i in range(0, len(uncached), batch_size):
        batch = uncached[i : i + batch_size]
        logger.info(f"Batch {i // batch_size + 1}: geocoding {len(batch)} addresses")
        addr_by_id = {rec_id: addr for rec_id, addr in batch}

        try:
            api_results = _batch_geocode_census(batch)
        except Exception as exc:
            logger.error(f"Census API error: {exc}")
            for _, addr in batch:
                new_results.append({
                    "full_address": addr, "latitude": None, "longitude": None,
                    "geocode_source": "failed", "match_score": None,
                    "match_type": "No_Match", "matched_address": "", "geocoded_at": now,
                })
            continue

        for result in api_results:
            addr = addr_by_id.get(result["rec_id"], "")
            if result["match_status"] == "Match":
                new_results.append({
                    "full_address": addr,
                    "latitude": result["latitude"],
                    "longitude": result["longitude"],
                    "geocode_source": "census",
                    "match_score": result["match_score"],
                    "match_type": result["match_type"],
                    "matched_address": result["matched_address"],
                    "geocoded_at": now,
                })
            else:
                _, _, _, zip_code = _parse_full_address(addr)
                centroid = zip_centroids.get(zip_code)
                if centroid:
                    new_results.append({
                        "full_address": addr,
                        "latitude": centroid[0], "longitude": centroid[1],
                        "geocode_source": "fallback_zip",
                        "match_score": None, "match_type": "No_Match",
                        "matched_address": "", "geocoded_at": now,
                    })
                else:
                    new_results.append({
                        "full_address": addr,
                        "latitude": None, "longitude": None,
                        "geocode_source": "failed",
                        "match_score": None, "match_type": "No_Match",
                        "matched_address": "", "geocoded_at": now,
                    })

    if new_results:
        _append_cache(cache_path, new_results)

    all_results: Dict[str, dict] = {r["full_address"]: r for r in cache.values()}
    all_results.update({r["full_address"]: r for r in new_results})

    _write_to_duckdb(db_path, all_results)

    stats = {
        "total": len(all_results),
        "matched": sum(1 for r in all_results.values() if r.get("geocode_source") == "census"),
        "fallback": sum(1 for r in all_results.values() if r.get("geocode_source") == "fallback_zip"),
        "failed": sum(1 for r in all_results.values() if r.get("geocode_source") == "failed"),
    }
    logger.info(
        f"Complete: {stats['total']} addresses | "
        f"{stats['matched']} matched | {stats['fallback']} fallback | {stats['failed']} failed"
    )
    return stats


def main():
    geocode_addresses()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run tests to confirm they pass**

```bash
pytest tests/prepare_contacts/test_geocode_addresses.py -v
```

Expected: 12 PASSED.

- [ ] **Step 3: Run full test suite to check for regressions**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add prepare_contacts/3__geocode_addresses.py tests/prepare_contacts/test_geocode_addresses.py
git commit -m "feat: add census geocoder pipeline with cache and ZIP centroid fallback"
```

---

## Task 5: Integration Smoke Test

**Files:** None created

- [ ] **Step 1: Run script 2 against real data**

```bash
python prepare_contacts/2__clean_and_build_db.py
```

Expected log output:
```
INFO - Loaded 402680 records from raw data
INFO - Removed N duplicate records
INFO - Retained N records after dropping missing values
INFO - Filtered to states ['MD']: N records remaining
INFO - Filtered to 8 specialties: ~7180 records remaining
INFO - Wrote ~7180 providers to ...medmatch.duckdb
INFO - Done. ~7180 providers written to medmatch.duckdb.
```

- [ ] **Step 2: Verify providers table in DuckDB**

```python
import duckdb
con = duckdb.connect("data/processed/medmatch.duckdb")
print(con.execute("SELECT COUNT(*) FROM providers").fetchone())
print(con.execute("SELECT COUNT(DISTINCT full_address) FROM providers").fetchone())
print(con.execute("SELECT COUNT(*) FROM providers WHERE address_id IS NOT NULL").fetchone())
con.close()
```

Expected: ~7180 providers, ~2168 unique addresses, 0 with address_id set.

- [ ] **Step 3: Run script 3 against real data**

```bash
python prepare_contacts/3__geocode_addresses.py
```

Expected log output (runs ~3 batches, ~1-2 min total):
```
INFO - Batch 1: geocoding 1000 addresses
INFO - Batch 2: geocoding 1000 addresses
INFO - Batch 3: geocoding ~168 addresses
INFO - Set address_id FK for ~7180 of ~2168 providers
INFO - Complete: ~2168 addresses | N matched | N fallback | N failed
```

- [ ] **Step 4: Verify final DuckDB state**

```python
import duckdb
con = duckdb.connect("data/processed/medmatch.duckdb")
print("Providers with geocode:", con.execute(
    "SELECT COUNT(*) FROM providers p JOIN addresses a ON p.address_id = a.address_id"
).fetchone())
print("Source breakdown:", con.execute(
    "SELECT geocode_source, COUNT(*) FROM addresses GROUP BY 1 ORDER BY 2 DESC"
).fetchall())
print("Sample proximity query:")
print(con.execute("""
    WITH nearby AS (
        SELECT p.first_name, p.last_name, p.pri_spec,
            3958.8 * acos(LEAST(1.0,
                sin(radians(39.2904)) * sin(radians(a.latitude)) +
                cos(radians(39.2904)) * cos(radians(a.latitude)) *
                cos(radians(a.longitude) - radians(-76.6122))
            )) AS distance_miles
        FROM providers p
        JOIN addresses a ON p.address_id = a.address_id
        WHERE a.latitude BETWEEN 39.2904 - (10/69.0) AND 39.2904 + (10/69.0)
          AND a.longitude BETWEEN -76.6122 - (10/(69.0*cos(radians(39.2904))))
                              AND -76.6122 + (10/(69.0*cos(radians(39.2904))))
    )
    SELECT * FROM nearby WHERE distance_miles <= 10 ORDER BY distance_miles LIMIT 5
""").fetchall())
con.close()
```

- [ ] **Step 5: Commit smoke test results**

```bash
git add data/processed/geocode_cache.csv
git commit -m "feat: run geocoding pipeline; add geocode cache"
```

---

## Self-Review Notes

- `address_id` on providers is set via SQL `UPDATE ... SET address_id = (SELECT ...)` — standard SQL, confirmed DuckDB-compatible.
- Census coordinates are `lon,lat` — handled in `_parse_census_response` with comment.
- `match_score` derived (100/50/NULL) since Census batch API has no numeric score — noted in spec.
- `provider_id` is not used as PK on providers — `ind_pac_id` is not guaranteed unique after cleaning (a provider can practice at two locations). Using full_address as the join key avoids PK conflicts.
- `src/utils/geocoding.py` unchanged — it already implements `geocode_address()` using Nominatim for user-facing address resolution.
