# Geocoding Pipeline & DuckDB Design

**Date:** 2026-05-14
**Status:** Approved
**Next step:** Reviews table integration (next sprint)

## Overview

Replace the existing Nominatim-based geocoding notebook with a two-script pipeline that:
1. Cleans fresh provider data and writes an initial DuckDB database
2. Geocodes unique addresses via the Census Geocoder batch API and completes the database

Output: `data/processed/medmatch.duckdb` — the primary data store for the MedMatch Streamlit app.

---

## Pipeline Architecture

```
data/raw/data.csv
        │
        ▼
┌─────────────────────────────────────┐
│  Step 1: Clean + Build initial DB   │
│  prepare_contacts/                  │
│  2__clean_and_build_db.py           │
│                                     │
│  - Filter MD + 8 specialties        │
│  - Dedup, build Full Address        │
│  - Write providers table to DuckDB  │
│    (address_id NULL at this stage)  │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  Step 2: Geocode + Update DB        │
│  prepare_contacts/                  │
│  3__geocode_addresses.py            │
│                                     │
│  - Extract unique Full Addresses    │
│  - Check geocode_cache.csv          │
│  - Batch POST to Census Geocoder    │
│    (1,000 addresses/request, ~3     │
│     batches, ~1-2 min total)        │
│  - Fallback: ZIP+State centroid     │
│  - Write addresses table to DuckDB  │
│  - Update providers.address_id FK   │
│  - Append results to cache CSV      │
└────────────────┬────────────────────┘
                 │
                 ▼
       data/processed/medmatch.duckdb
       data/processed/geocode_cache.csv
```

Both scripts are idempotent — re-running always produces a clean, consistent database. Step 2 uses the cache to avoid re-hitting the Census API for already-geocoded addresses.

---

## DuckDB Schema

### `addresses` — one row per unique Full Address

```sql
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
    geocode_source  VARCHAR,   -- 'census', 'fallback_zip', 'failed'
    match_score     DOUBLE,    -- Census confidence 0–100
    match_type      VARCHAR,   -- 'Exact', 'Non_Exact', 'Tie', 'No_Match'
    matched_address VARCHAR,   -- standardized address returned by Census
    geocoded_at     TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT now()
);
```

### `providers` — one row per provider record

```sql
CREATE TABLE providers (
    ind_pac_id    VARCHAR PRIMARY KEY,
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
    address_id    INTEGER REFERENCES addresses(address_id),
    updated_at    TIMESTAMP DEFAULT now()
);
```

**`geocode_source` values:**
- `'census'` — matched by Census Geocoder (Exact or Non_Exact)
- `'fallback_zip'` — Census failed; ZIP+State centroid used
- `'failed'` — no geocode available

**`updated_at`** on both tables supports future Snowflake incremental loads via `MERGE`.

---

## Geocoding: Census Geocoder Batch API

**Endpoint:** `https://geocoding.geo.census.gov/geocoder/locations/addressbatch`

**Request format:** CSV with columns `id, street, city, state, zip`

**Batch size:** 1,000 addresses per request (API limit: 10,000; using 1,000 for reliability)

**Fallback strategy:**
1. Census Geocoder (primary) — returns lat/lon, match score, match type, standardized address
2. ZIP+State centroid lookup (static CSV, no API call) — used when Census returns no match
3. `geocode_source = 'failed'` — recorded when both fail; provider retains `address_id` pointing to an address row with NULL lat/lon

**Cache:** `data/processed/geocode_cache.csv` stores all previously geocoded addresses. Columns: `full_address, latitude, longitude, geocode_source, match_score, match_type, matched_address, geocoded_at`. Step 2 skips cached addresses and only sends uncached ones to the API.

**ZIP centroid fallback source:** `data/processed/zip_centroids.csv` — a static file derived from the Census ZIP Code Tabulation Area (ZCTA) centroid dataset. Columns: `zip_code, latitude, longitude`. Downloaded once and committed to the repo.

---

## App Integration

### Proximity Search

```sql
WITH nearby AS (
    SELECT
        p.*,
        a.latitude,
        a.longitude,
        3958.8 * acos(LEAST(1.0,
            sin(radians($lat)) * sin(radians(a.latitude)) +
            cos(radians($lat)) * cos(radians(a.latitude)) *
            cos(radians(a.longitude) - radians($lon))
        )) AS distance_miles
    FROM providers p
    JOIN addresses a ON p.address_id = a.address_id
    WHERE p.pri_spec = $specialty
      AND a.latitude  BETWEEN $lat - ($radius / 69.0)
                          AND $lat + ($radius / 69.0)
      AND a.longitude BETWEEN $lon - ($radius / (69.0 * cos(radians($lat))))
                          AND $lon + ($radius / (69.0 * cos(radians($lat))))
)
SELECT * FROM nearby
WHERE distance_miles <= $radius
ORDER BY distance_miles
```

**Formula:** Spherical law of cosines — accurate to <0.3% error for distances under a few hundred miles.

**Performance:** Bounding box pre-filter on lat/lon eliminates most rows before the expensive `acos` calculation. `LEAST(1.0, ...)` prevents `NaN` from floating-point precision errors when two points are nearly identical. CTE required because SQL cannot reference column aliases in `WHERE`.

**Bounding box constants:**
- Latitude: 69.0 miles/degree (actual: 69.17 — using 69.0 makes the box slightly larger, safe for a pre-filter)
- Longitude: adjusted by `cos(latitude)` to account for meridian convergence

### Map Display

Provider lat/lon from the query result is passed directly to `st.map()`, Folium, or Pydeck. No additional geocoding call needed at render time.

### Nominatim / Google Maps Integration

User address resolution (converting a user-supplied address to lat/lon for the search) is isolated in `src/geocoding.py`:

```python
def geocode_address(address: str) -> tuple[float, float]:
    ...
```

Currently implemented with Nominatim (free, no key). Swapping to Google Maps Geocoding API requires changing only this function — no changes to the query layer or app.

---

## Scope

**In scope (this sprint):**
- `2__clean_and_build_db.py` — cleaning + initial DuckDB write
- `3__geocode_addresses.py` — Census Geocoder batch + DuckDB update
- `src/geocoding.py` — user address resolution abstraction
- Maryland data only (PoC scope)

**Next sprint:**
- `reviews` table — integrate notebook 3 (review cleaning) and notebook 4 (combining) into DuckDB
- Expand to additional states if needed

**Out of scope:**
- Google Maps API integration (currently Nominatim; swap is a one-function change when ready)
- Snowflake migration (schema designed for compatibility; migration not implemented here)
