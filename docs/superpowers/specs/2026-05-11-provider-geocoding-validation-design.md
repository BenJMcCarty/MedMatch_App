# Provider Geocoding Validation — Design Spec

**Date:** 2026-05-11  
**Status:** Approved

## Context

`data/processed/Combined_Contacts_and_Reviews.parquet` contains 2,469 providers, all with
`latitude`/`longitude` columns sourced from the CMS NPI dataset. CMS coordinates reflect billing
addresses, not necessarily practice locations. This spec covers a one-time (and repeatable)
geocoding validation pass that geocodes each provider's `Full Address` string via Nominatim,
replaces CMS coordinates when a better result is found, and surfaces coverage metrics on the
dashboard.

This is preparation for a Snowflake migration: after this work, `Latitude`, `Longitude`,
`geocode_source`, and `geocode_verified_at` become stable columns that map directly to
Snowflake DDL, and distance calculation can move entirely into SQL (`ST_DISTANCE`).

---

## Approach: Geocode-on-top (Option A)

Keep existing CMS coordinates as the baseline. Geocode each provider's `Full Address` via
Nominatim. When Nominatim returns a result, overwrite `latitude`/`longitude` in-place and mark
the row `geocode_source = 'nominatim'`. When Nominatim fails, keep the CMS value and mark
`geocode_source = 'cms'`. Track timestamps so the dashboard can show staleness.

Rejected alternatives:
- **Full in-place replacement**: loses CMS baseline; no resumability if Nominatim fails mid-run.
- **Separate geocoded parquet**: clean for Snowflake but adds join complexity to the load path.

---

## Schema Changes

Two new columns added to `Combined_Contacts_and_Reviews.parquet`:

| Column | Type | Values |
|---|---|---|
| `geocode_source` | string | `'nominatim'`, `'cms'`, `'failed'` |
| `geocode_verified_at` | ISO-8601 datetime string | timestamp of last geocoding attempt, or `NaT` |

The existing `latitude`/`longitude` columns are updated in-place when Nominatim succeeds.
`ingestion.py:_transform_combined_data` already maps lowercase → title-case at load time;
no load-path changes are needed.

### Conflict resolution

When Nominatim returns a result, it is always preferred over the CMS value. No distance
threshold is applied — any geocodable address replaces the CMS coordinate.

---

## Component 1: CLI Script (`scripts/geocode_providers.py`)

A standalone script with no Streamlit dependency.

**Behavior:**
- Reads `data/processed/Combined_Contacts_and_Reviews.parquet`
- Reuses `src.utils.geocoding._get_rate_limited_geocoder()` (1 req/sec, 3 retries)
- Iterates rows, geocoding each `Full Address`
- **Resumable by default**: skips rows where `geocode_source == 'nominatim'` already
- Accepts `--force` flag to re-geocode all rows regardless of existing source
- Writes progress to stdout: `[1234/2469] Dr. Jane Smith — ✓ nominatim`
- Writes back atomically: temp file → `os.replace()` → original path
- Exits with summary: `2301 nominatim, 142 cms, 26 failed`

**Error handling:**
- `GeocoderTimedOut` / `GeocoderServiceError`: mark `geocode_source = 'failed'`, continue
- Any unhandled exception on a row: log warning, mark `'failed'`, continue
- Script-level exception (e.g., parquet not found): exit with non-zero code and message

**Usage:**
```bash
python scripts/geocode_providers.py           # resumable run
python scripts/geocode_providers.py --force   # re-geocode everything
```

---

## Component 2: UI Button (`pages/30_🔄_Update_Data.py`)

New expander section: **"Validate Provider Coordinates"**

Contents:
- Current geocode coverage breakdown (counts by `geocode_source`)
- **"Validate Unverified Providers"** button (default — skips `geocode_source == 'nominatim'`)
- **"Re-validate All Providers"** button (equivalent to `--force`)
- `st.progress` bar for live feedback during the run
- Warning banner: *"A full validation run takes ~41 minutes for 2,469 providers."*
- On completion: show summary metrics and prompt to refresh dashboard

The UI button calls the same geocoding logic extracted into a shared helper function
`src/utils/geocoding.py:geocode_provider_dataframe(df, force=False) -> pd.DataFrame`.
Both the CLI script and the UI button call this function.

---

## Component 3: Dashboard Metric (`pages/20_📊_Data_Dashboard.py`)

### Quality Metrics table addition

Extend the existing `quality_metrics` list to include geocode source breakdown rows when
`geocode_source` column is present:

| Metric | Complete Records | Total Records | Completeness |
|---|---|---|---|
| Coordinates — Nominatim verified | N | 2469 | X% |
| Coordinates — CMS only | N | 2469 | X% |
| Coordinates — Failed | N | 2469 | X% |

### Donut chart addition

Add a second donut chart next to the existing "Coordinate Completeness" chart titled
**"Coordinate Source"** with three slices: Nominatim / CMS / Failed.

---

## Data Flow (post-implementation)

```
scripts/geocode_providers.py
  └── src/utils/geocoding.py:geocode_provider_dataframe()
        └── _get_rate_limited_geocoder() [Nominatim, 1 req/sec]
              └── Writes latitude, longitude, geocode_source, geocode_verified_at
                    └── data/processed/Combined_Contacts_and_Reviews.parquet

pages/30_Update_Data.py
  └── src/utils/geocoding.py:geocode_provider_dataframe()  [same path]

pages/20_Data_Dashboard.py
  └── Reads geocode_source column → quality metrics + donut chart

src/data/ingestion.py:_transform_combined_data()
  └── Maps latitude→Latitude, longitude→Longitude [unchanged]
  └── Passes geocode_source, geocode_verified_at through [new: no-op passthrough]
```

---

## Files Changed

| File | Change type |
|---|---|
| `scripts/geocode_providers.py` | **New** — CLI script |
| `src/utils/geocoding.py` | **Modified** — add `geocode_provider_dataframe()` |
| `pages/30_🔄_Update_Data.py` | **Modified** — add geocoding expander |
| `pages/20_📊_Data_Dashboard.py` | **Modified** — add geocode source metrics + chart |
| `src/data/ingestion.py` | **Modified** — pass through `geocode_source`/`geocode_verified_at` columns |

---

## Out of Scope

- Google Maps API fallback (separate effort)
- Per-provider geocoding on data upload (address: future enhancement)
- Driving distance calculation (Recommendation 3 from the original proposal)
