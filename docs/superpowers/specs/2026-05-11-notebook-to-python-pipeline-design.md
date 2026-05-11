# Design: Convert prepare_contacts Notebooks to Python Pipeline

**Date:** 2026-05-11  
**Status:** Approved

---

## Goal

Convert the numbered Jupyter notebooks in `prepare_contacts/` (notebooks 2–4) into standalone Python scripts, and add a `pipeline.py` orchestrator that runs all four steps in sequence. This streamlines the data cleaning process from a notebook-by-notebook workflow into a single runnable pipeline.

Notebook 1 (`1__Cleaning_Providers_List.py`) already exists as a well-structured script and requires no changes.

---

## File Structure

```
prepare_contacts/
  1__Cleaning_Providers_List.py    ← existing (unchanged)
  2__Contact_Geocoding.py          ← new, from 2__Contact_Geocoding_New.ipynb
  3__Cleaning_Reviews.py           ← new, from 3__Cleaning_Reviews.ipynb
  4__Combining_Contacts_Reviews.py ← new, from 4__Combining_Contacts_and_Reviews.ipynb
  pipeline.py                      ← new, orchestrates steps 1–4
```

---

## Data Flow

```
data/raw/data.csv
  → [step 1] 1__Cleaning_Providers_List.py
  → data/processed/cleaned_contacts.parquet

data/processed/cleaned_contacts.parquet
  → [step 2] 2__Contact_Geocoding.py
  → data/processed/Geocoded_Contacts.parquet
  (side output) data/processed/geocode_cache.json

data/raw/grp_public_reporting.csv
  → [step 3] 3__Cleaning_Reviews.py
  → data/processed/cleaned_reviews.parquet

data/processed/Geocoded_Contacts.parquet + data/processed/cleaned_reviews.parquet
  → [step 4] 4__Combining_Contacts_Reviews.py
  → data/processed/Combined_Contacts_and_Reviews.parquet
```

---

## Script Conventions

All scripts follow the same pattern established by `1__Cleaning_Providers_List.py`:

- **Constants** at module top: `DEFAULT_INPUT_PATH`, `DEFAULT_OUTPUT_PATH`, etc.
- **Named functions** with single responsibilities (load, process, save)
- **`main()` function** with optional parameters (defaulting to constants)
- **`if __name__ == "__main__": main()`** entry point
- **`logging`** for all progress/status output (no print statements)
- **Type annotations** on all function signatures

---

## Step 2: `2__Contact_Geocoding.py`

Most complex step. Converts `2__Contact_Geocoding_New.ipynb` to a CLI-compatible script.

**Key changes from notebook:**
- Replace `tqdm.notebook` → standard `tqdm` for CLI use
- All logic extracted into named functions:
  - `load_cleaned_contacts(path)` → DataFrame
  - `build_full_address(row, fallback_level)` → str
  - `geocode_unique_addresses(df, cache, geolocator)` → dict mapping address→(lat, lon)
  - `apply_geocodes_to_df(df, address_coords)` → DataFrame
  - `save_geocoded_contacts(df, path)` → None

**Preserved from notebook:**
- MD5 hash-based address cache (`geocode_cache.json`)
- Three-level fallback strategy (full address → no adr_ln_2 → ZIP+State only)
- Retry logic with extended sleep on 403 responses
- Cache save every 50 addresses (survive interruptions)
- Summary statistics logging at completion

**Constants:**
- `DEFAULT_INPUT_PATH` → `data/processed/cleaned_contacts.parquet`
- `DEFAULT_OUTPUT_PATH` → `data/processed/Geocoded_Contacts.parquet`
- `CACHE_FILE` → `data/processed/geocode_cache.json`
- `NOMINATIM_DELAY` = 1.5 seconds
- `MAX_RETRIES` = 3

---

## Step 3: `3__Cleaning_Reviews.py`

Simple script. Converts `3__Cleaning_Reviews.ipynb`.

**Logic:**
1. Load `grp_public_reporting.csv` with `low_memory=False`
2. Strip column name whitespace
3. Drop rows where `star_value` is null
4. Deduplicate on `org_PAC_ID` (keep first)
5. Save to `cleaned_reviews.parquet`

**Constants:**
- `DEFAULT_INPUT_PATH` → `data/raw/grp_public_reporting.csv`
- `DEFAULT_OUTPUT_PATH` → `data/processed/cleaned_reviews.parquet`

---

## Step 4: `4__Combining_Contacts_Reviews.py`

Simple script. Converts `4__Combining_Contacts_and_Reviews.ipynb`.

**Logic:**
1. Load `Geocoded_Contacts.parquet`
2. Load `cleaned_reviews.parquet` (columns: `org_PAC_ID`, `patient_count`, `star_value`)
3. Inner merge on `org_pac_id` (contacts) == `org_PAC_ID` (reviews)
4. Reset index
5. Save to `Combined_Contacts_and_Reviews.parquet`

**Constants:**
- `DEFAULT_CONTACTS_PATH` → `data/processed/Geocoded_Contacts.parquet`
- `DEFAULT_REVIEWS_PATH` → `data/processed/cleaned_reviews.parquet`
- `DEFAULT_OUTPUT_PATH` → `data/processed/Combined_Contacts_and_Reviews.parquet`

---

## `pipeline.py` — Orchestrator

Imports `main()` from each of the four step scripts and runs them in sequence.

**Features:**
- `--steps` flag: comma-separated list of step numbers to run (e.g., `--steps 3,4` to re-run only reviews and combine). Default: all steps (1,2,3,4).
- Clear logging before/after each step with elapsed time
- Failures propagate naturally — a failed step stops the pipeline

**Usage:**
```bash
python prepare_contacts/pipeline.py              # run all steps
python prepare_contacts/pipeline.py --steps 3,4 # re-run reviews + combine only
```

---

## Out of Scope

- `Cleaning_Preferred_Providers.ipynb` and `contact_cleaning.ipynb` are not converted (exploratory/scratch notebooks)
- No changes to `scripts/geocode_providers.py` (separate post-pipeline validation step)
- No changes to `1__Cleaning_Providers_List.py`
