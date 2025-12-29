# Project Title

_A Streamlit app for searching a dataset and visualizing results on a map._

> <!--
> TODO (Copilot + human):
> - Replace this paragraph with a 2–3 sentence summary of what this specific app does,
>   based on `app.py` and the modules in `src/` (or wherever the main logic lives).
> - Mention the real data domain (e.g. real estate, incidents, stores, etc.).
> -->

This project is a Streamlit-based portfolio app that lets users search a dataset and see the results plotted on an interactive map.

For a deeper technical breakdown, see:

- `docs/ARCHITECTURE.md` – how the code is structured and how data flows.
- `docs/AI_ASSISTANTS_GUIDE.md` – how to use Copilot/AI helpers without creating mystery code.

---

## 1. Overview

**MedMatch** is a Streamlit-based provider recommendation app that helps users find and evaluate medical providers based on geographic proximity, specialty, and referral history. Users can search by address or location, filter by specialty, and view ranked provider recommendations with detailed contact information and referral statistics.

The app uses a dataset of provider contacts (names, addresses, phone numbers, specialties) enriched with patient volume metrics and user ratings. Data is loaded from local parquet files and cached for fast access. The recommendation algorithm scores providers using a weighted combination of distance from the user's location, patient volume, and user ratings.

This project showcases data-driven decision support, interactive geospatial visualization, and real-time data exploration for healthcare provider networks.

---

## 2. Architecture (High-Level)

A short version of the architecture is summarized here. Full details live in `docs/ARCHITECTURE.md`.

**Core Application:**
- [app.py](app.py) – Landing page and ETL orchestration. Handles navigation, data loading pipeline from local parquet files to Streamlit cache, and background data refresh on startup.
- [pages/1_🔎_Search.py](pages/1_🔎_Search.py) – Search interface where users enter address, select specialty, set search radius, and configure scoring weights.
- [pages/2_📄_Results.py](pages/2_📄_Results.py) – Results display with ranked provider list, detailed provider info cards, and export functionality.
- [pages/20_📊_Data_Dashboard.py](pages/20_📊_Data_Dashboard.py) – Analytics dashboard showing referral statistics and data quality metrics.
- [pages/30_🔄_Update_Data.py](pages/30_🔄_Update_Data.py) – Data refresh interface for reloading provider and referral data.

**Data Layer (`src/data/`):**
- [ingestion.py](src/data/ingestion.py) – Centralized data loading from local parquet files with Streamlit cache integration and file-based invalidation.
- [preparation.py](src/data/preparation.py) – Data cleaning and transformation from raw Excel exports to processed parquet files.
- [io_utils.py](src/data/io_utils.py) – File I/O utilities for loading DataFrames from multiple formats (parquet, CSV, Excel).

**Business Logic (`src/`):**
- [app_logic.py](src/app_logic.py) – Core application logic including `load_application_data()`, radius filtering, and recommendation orchestration.

**Utilities (`src/utils/`):**
- [scoring.py](src/utils/scoring.py) – Distance calculation (haversine formula) and weighted recommendation scoring algorithm.
- [geocoding.py](src/utils/geocoding.py) – Address-to-coordinates conversion using Nominatim with rate limiting and caching.
- [providers.py](src/utils/providers.py) – Provider data validation, referral count aggregation, and time-based filtering.
- [config.py](src/utils/config.py) – Configuration management for API keys, database URLs, and application settings via Streamlit secrets.
- [cleaning.py](src/utils/cleaning.py) – Data validation and cleaning functions for coordinates, addresses, and provider records.
- [addressing.py](src/utils/addressing.py) – Address validation and formatting utilities.

**Key Design Notes:**
- Configuration is defined in [src/utils/config.py](src/utils/config.py) and reads from Streamlit secrets.
- Data is stored in local parquet files (`data/processed/Combined_Contacts_and_Reviews.parquet`) – no database required.
- No map visualization currently – results are displayed in tabular format with distance calculations.

---

## 3. Data Flow (High-Level)

How data moves through the app from user input to ranked provider recommendations.

1. **App Initialization ([app.py](app.py))**:
   - On startup, `auto_update_data()` runs in a background thread to load data from `data/processed/Combined_Contacts_and_Reviews.parquet`
   - `DataIngestionManager` loads parquet files and caches them in Streamlit cache with 1-hour TTL
   - Daily refresh at 4 AM invalidates cache and reloads data

2. **Search Input ([pages/1_🔎_Search.py](pages/1_🔎_Search.py))**:
   - User enters address (street, city, state, zip)
   - `geocode_address_with_cache()` converts address to latitude/longitude coordinates
   - User selects specialty, search radius, minimum referrals, and scoring weights
   - Search parameters stored in `st.session_state`

3. **Data Loading ([src/app_logic.py](src/app_logic.py))**:
   - `load_application_data()` retrieves cached provider and referral data
   - Enriches provider data with inbound referral counts and preferred provider status
   - Validates coordinates and cleans address fields
   - Optionally applies time-based filtering via `apply_time_filtering()`

4. **Recommendation Scoring ([src/utils/scoring.py](src/utils/scoring.py))**:
   - `calculate_distances()` computes haversine distance from user location to each provider
   - `recommend_provider()` scores providers using weighted formula:
     - Distance (closer is better)
     - Outbound referral count (more experience is better)
     - Inbound referral count (optional)
     - Preferred provider status (optional boost)
   - Normalizes each factor to 0-1 scale and combines with user-specified weights

5. **Results Display ([pages/2_📄_Results.py](pages/2_📄_Results.py))**:
   - Displays top-ranked provider in a detailed info card
   - Shows full ranked list of all matching providers in a sortable table
   - Provides Word document export for selected provider
   - Includes scoring explanation and search criteria sidebar

---

## 4. Setup & Installation

### Requirements

- Python 3.10+ (adjust as needed)
- pip or conda
- A supported database or local data file

<!--
TODO (Copilot):
Inspect the existing `requirements.txt`, `pyproject.toml`, or `environment.yml` and list the real key dependencies here (Streamlit, DB drivers, mapping libs, etc.).
-->

### Install

```bash
git clone https://github.com/<username>/<repo>.git
cd <repo>

# Option A: pip
pip install -r requirements.txt

# Option B: conda
conda env create -f environment.yml
conda activate <env-name>
```

<!--
TODO (Copilot):
Adjust the commands above to match this project's actual setup (requirements file name, environment name, etc.).
-->

### Run the app

```bash
streamlit run app.py
```

<!--
TODO (Copilot):
If the real entrypoint is different (e.g. `src/app.py` or a specific page), update this command accordingly.
-->

---

## 5. Configuration

The app reads configuration from code and/or environment variables.

<!--
TODO (Copilot):
Search the codebase for configuration patterns:
- `os.environ[...]`
- `.env` files
- constants in a `config` module
Document here:
- Which settings exist (e.g. DATABASE_URL, map defaults, API keys).
- Where they are defined.
- Reasonable defaults or examples.
-->

Typical examples (replace with real ones):

- `DATABASE_URL` – database connection string or path to local file.
- `MAP_DEFAULT_LAT`, `MAP_DEFAULT_LON` – default map center.
- `MAP_DEFAULT_ZOOM` – default zoom level.

---

## 6. Code Style & Documentation

This project is intentionally **human-readable** and portfolio-friendly.

<!--
TODO (Copilot):
Review the existing code and, if needed, add/adjust docstrings and comments so that:
- Public functions and classes explain what they do and their parameters/returns.
- Non-obvious logic has short comments explaining why it's implemented that way.
Then, summarize those expectations here in your own words, keeping it consistent with the codebase.
-->

Guidelines:

- Public functions/classes should have docstrings describing behavior, inputs, and outputs.
- Non-trivial logic should include a short comment explaining the intent or assumption.
- When behavior changes, docstrings and this README should be updated together.

---

## 7. Development Workflow

A simple workflow for working on this app:

<!--
TODO (Copilot):
Based on any existing dev scripts, Makefiles, or docs, describe the realistic workflow here.
If none exist, keep this generic but accurate.
-->

1. Make a small, focused change (e.g. new filter, new map behavior).
2. Run the app locally with `streamlit run app.py`.
3. If you used GitHub Copilot or another AI assistant:
   - Read through the generated code.
   - Add or refine docstrings.
   - Add comments for any non-trivial logic.
4. Update this README if the user-facing behavior changed.
5. Commit with a clear message.

---

## 8. Future Improvements

<!--
TODO (Copilot + human):
Propose realistic improvements based on the current app:
- Better filters?
- More map visualizations?
- Performance improvements?
- Tests?
Replace the placeholder list below with project-specific ideas.
-->

Some possible next steps:

- Add more advanced filters (geographic radius, multi-select categories).
- Add clustering or heatmap visualizations.
- Add download/export options for filtered results.
- Add tests for core data and mapping functions.
