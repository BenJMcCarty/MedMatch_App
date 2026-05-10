# MedMatch Provider Recommender

_A Streamlit app for finding and evaluating healthcare providers based on location, specialty, and experience._

For a deeper technical breakdown, see:

- `docs/ARCHITECTURE.md` – how the code is structured and how data flows.
- `docs/AI_ASSISTANTS_GUIDE.md` – how to use Copilot/AI helpers without creating mystery code.

---

## 1. Overview

**MedMatch** is a Streamlit-based provider recommendation app that helps users find and evaluate medical providers based on geographic proximity, specialty, gender preferences, and experience level. Users can search by address or location, filter by specialty and gender, and view ranked provider recommendations with detailed contact information and client statistics.

The app uses a dataset of provider contacts (names, addresses, phone numbers, specialties, gender) enriched with patient volume metrics and user ratings. Data is loaded from local parquet files and cached for fast access. The recommendation algorithm scores providers using a weighted combination of distance from the user's location and client count (experience level).

### Data Source

Provider data is sourced from the **Centers for Medicare & Medicaid Services (CMS) Physician & Other Practitioners dataset**, available at:

[https://data.cms.gov/provider-data/dataset/mj5m-pzi6](https://data.cms.gov/provider-data/dataset/mj5m-pzi6)

This dataset includes Medicare-enrolled providers with specialty, practice address, and claims data. The app processes and enriches this data locally for search and recommendation.

This project showcases data-driven decision support, interactive geospatial visualization, and real-time data exploration for healthcare provider networks.

---

## 2. Architecture (High-Level)

A short version of the architecture is summarized here. Full details live in `docs/ARCHITECTURE.md`.

**Core Application:**
- [app.py](app.py) – Landing page and ETL orchestration. Handles navigation, data loading pipeline from local parquet files to Streamlit cache, and background data refresh on startup.
- [pages/1_🔎_Search.py](pages/1_🔎_Search.py) – Search interface where users enter address, select specialty, set search radius, and configure scoring weights.
- [pages/2_📄_Results.py](pages/2_📄_Results.py) – Results display with ranked provider list, detailed provider info cards, and export functionality.
- [pages/5_👟_Quick_Start_Guide.py](pages/5_👟_Quick_Start_Guide.py) – Onboarding walkthrough explaining how to use the app step by step.
- [pages/10_🛠️_How_It_Works.py](pages/10_🛠️_How_It_Works.py) – Explanation of the recommendation algorithm and scoring methodology.
- [pages/20_📊_Data_Dashboard.py](pages/20_📊_Data_Dashboard.py) – Analytics dashboard showing referral statistics and data quality metrics.
- [pages/30_🔄_Update_Data.py](pages/30_🔄_Update_Data.py) – Data refresh interface for reloading provider and referral data.

**Data Layer (`src/data/`):**
- [ingestion.py](src/data/ingestion.py) – Centralized data loading from local parquet files with Streamlit cache integration and file-based invalidation.
- [preparation.py](src/data/preparation.py) – Data cleaning and transformation from raw Excel exports to processed parquet files.
- [io_utils.py](src/data/io_utils.py) – File I/O utilities for loading DataFrames from multiple formats (parquet, CSV, Excel).

**Business Logic (`src/`):**
- [app_logic.py](src/app_logic.py) – Core application logic including `load_application_data()`, specialty/gender filtering, radius filtering, and recommendation orchestration.

**Utilities (`src/utils/`):**
- [scoring.py](src/utils/scoring.py) – Distance calculation (haversine formula) and weighted recommendation scoring algorithm using distance and client count.
- [geocoding.py](src/utils/geocoding.py) – Address-to-coordinates conversion using Nominatim with rate limiting and caching.
- [providers.py](src/utils/providers.py) – Provider data validation, client count aggregation, and time-based filtering.
- [config.py](src/utils/config.py) – Configuration management for API keys, database URLs, and application settings via Streamlit secrets.
- [cleaning.py](src/utils/cleaning.py) – Data validation and cleaning functions for coordinates, addresses, and provider records.
- [addressing.py](src/utils/addressing.py) – Address validation and formatting utilities.
- [responsive.py](src/utils/responsive.py) – Responsive layout utilities for adapting the UI to different screen sizes.
- [freshness.py](src/utils/freshness.py) – Data freshness tracking and display utilities for showing when provider information was last verified.
- [validation.py](src/utils/validation.py) – Input validation helpers for addresses, coordinates, and phone numbers.
- [performance.py](src/utils/performance.py) – Decorators and helpers for monitoring function execution time and logging slow operations.
- [io_utils.py](src/utils/io_utils.py) – Additional I/O utilities including phone number formatting and filename sanitization.

**Key Design Notes:**
- Configuration is defined in [src/utils/config.py](src/utils/config.py) and reads from Streamlit secrets.
- Data is stored in local parquet files (`data/processed/Combined_Contacts_and_Reviews.parquet`) – no database required.
- Map visualization using pydeck displays provider locations and user location with color-coded rankings.

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
   - User selects specialty filters, gender filters, search radius, minimum client count, and scoring weights (distance vs. experience)
   - Search parameters stored in `st.session_state`

3. **Data Loading ([src/app_logic.py](src/app_logic.py))**:
   - `load_application_data()` retrieves cached provider and referral data
   - Validates coordinates and cleans address fields
   - Returns provider data with client counts and contact information

4. **Recommendation Scoring ([src/utils/scoring.py](src/utils/scoring.py))**:
   - `calculate_distances()` computes haversine distance from user location to each provider
   - `recommend_provider()` scores providers using weighted formula:
     - Distance (closer is better)
     - Client Count (more clients indicates more experience)
   - Normalizes each factor to 0-1 scale using min-max normalization
   - Combines normalized values with user-specified weights (distance_weight and client_weight)

5. **Results Display ([pages/2_📄_Results.py](pages/2_📄_Results.py))**:
   - Displays top-ranked provider in a detailed info card
   - Shows full ranked list of all matching providers in a sortable table
   - Provides Word document export for best match provider
   - Includes interactive map visualization (if pydeck available)
   - Includes scoring explanation and search criteria sidebar showing active filters

---

## 4. Setup & Installation

### Requirements

- Python 3.11+ (as specified in `pyproject.toml`)
- pip for package management
- Local parquet files for data storage (no database required)

**Key Dependencies:**

- **streamlit** (>=1.18.0) – Web application framework for interactive UI
- **pandas** (>=1.5.0) – Data manipulation and analysis
- **geopy** (>=2.3.0) – Geocoding via Nominatim (OpenStreetMap)
- **pydeck** (>=0.9.1) – Interactive map visualization for provider locations
- **python-docx** (>=0.8.11) – Word document export functionality
- **pyarrow** (>=8.0.0) – Fast parquet file reading/writing
- **plotly** (>=5.0.0) – Interactive data visualizations
- **openpyxl** (>=3.0.10) – Excel file processing
- **numpy** (>=1.23.0) – Numerical computing support
- **cachetools** (>=5.0.7) – Advanced caching utilities
- **tqdm** (>=4.67.1) – Progress bars for data processing operations
- **watchdog** (>=6.0.0) – File system monitoring for automatic data refresh
- **boto3** (>=1.28.0) – AWS S3 integration for data uploads

### Install

```bash
git clone https://github.com/BenJMcCarty/MedMatch_App.git
cd MedMatch_App

# Create and activate virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Alternatively, use uv for faster installation (if available)
uv pip install -r requirements.txt
```

### Run the app

```bash
streamlit run app.py
```

The app will open in your default browser at `http://localhost:8501`.

**Alternative methods:**

```bash
# Using the provided shell script (Windows)
./start_app.sh

# With custom port
streamlit run app.py --server.port 8502

# With custom configuration
streamlit run app.py --server.headless true
```

---

## 5. Configuration

The app uses **Streamlit's secrets management** for all configuration. No environment variables or `.env` files are needed.

### Configuration Files

**`.streamlit/config.toml`** - Streamlit app settings (already configured):
- Theme settings (dark mode)
- Server configuration (port, CORS, XSRF)
- Performance settings (caching, fast reruns)
- Logging configuration

**`.streamlit/secrets.toml`** - Sensitive credentials and API keys (gitignored):
This file is optional. Create it only if you need to configure external services.

Example structure:
```toml
[geocoding]
# Google Maps API (optional - app uses free Nominatim by default)
google_maps_api_key = "YOUR_API_KEY"
google_maps_enabled = false

[s3]
# AWS S3 for data uploads (optional)
aws_access_key_id = "YOUR_ACCESS_KEY"
aws_secret_access_key = "YOUR_SECRET_KEY"
bucket_name = "your-bucket-name"
region_name = "us-east-1"

[app]
# Application settings
environment = "development"  # or "production"
debug_mode = false
log_level = "INFO"
```

### Configuration Module

The app provides centralized configuration access via [src/utils/config.py](src/utils/config.py):

```python
from src.utils.config import get_api_config, get_app_config

# Get geocoding configuration
geocoding_config = get_api_config('geocoding')
api_key = geocoding_config.get('google_maps_api_key')

# Get app settings
app_config = get_app_config()
debug_mode = app_config['debug_mode']
```

### Default Configurations

**Geocoding:**
- Service: Nominatim (OpenStreetMap) - **no API key required**
- Rate limit: 1 request per second
- Cache TTL: 1 hour
- Timeout: 10 seconds

**Data Loading:**
- Cache TTL: 1 hour (3600 seconds)
- Data directory: `data/processed/`
- Primary file: `Combined_Contacts_and_Reviews.parquet`
- Daily refresh: 4:00 AM

**Search Defaults:**
- Radius: 25 miles (range: 1-200)
- Minimum clients: 0 (range: 0-100)
- Default weights: Balanced (Distance: 0.5, Experience: 0.5)
- Preset profiles:
  - **Prioritize Proximity (Recommended)**: Distance: 1.0, Experience: 0.0
  - **Balanced**: Distance: 0.5, Experience: 0.5
  - **Prioritize Experience**: Distance: 0.3, Experience: 0.7
  - **Custom Settings**: User-defined sliders

### Deployment to Streamlit Cloud

When deploying to Streamlit Cloud:
1. Go to your app settings in the Streamlit Cloud dashboard
2. Navigate to "Secrets" section
3. Paste your secrets in TOML format
4. Secrets are encrypted and not visible in your repository

---

## 6. Code Style & Documentation

This project is intentionally **human-readable** and portfolio-friendly. Code quality is maintained through clear documentation and consistent style.

### Documentation Standards

**Docstrings:**
- All public functions and classes have docstrings explaining behavior, parameters, and returns
- Format: Google-style docstrings with Args, Returns, and Examples sections
- Example from [src/app_logic.py](src/app_logic.py):
  ```python
  def filter_providers_by_radius(df: pd.DataFrame, max_radius_miles: float) -> pd.DataFrame:
      """Filter providers by maximum radius distance.

      Args:
          df: Provider DataFrame with "Distance (Miles)" column
          max_radius_miles: Maximum distance threshold in miles

      Returns:
          pd.DataFrame: Filtered DataFrame with only providers within radius
      """
  ```

**Comments:**
- Comments explain *why*, not *what* (the code shows what)
- Non-obvious logic includes short comments about intent or assumptions
- Example from [pages/2_📄_Results.py](pages/2_📄_Results.py):
  ```python
  # Round distance to 1 decimal place for cleaner display
  if "Distance (Miles)" in display_df.columns:
      display_df["Distance (Miles)"] = display_df["Distance (Miles)"].round(1)
  ```

### Code Style

**Formatting:**
- Black code formatter with 120-character line length
- isort for import sorting (Black-compatible profile)
- Enforced via pre-commit hooks (see `.pre-commit-config.yaml`)

**Type Hints:**
- Type hints on function signatures where practical
- Helps with IDE autocomplete and code clarity

**Running Linters:**
```bash
# Auto-format code
black --line-length=120 .

# Sort imports
isort --profile=black --line-length=120 .

# Or use pre-commit to run all checks
pre-commit run --all-files
```

### When to Update Documentation

Update documentation when:
- Adding new search filters or scoring weights
- Changing data flow or architecture
- Adding new pages or UI components
- Modifying configuration options

Files to update:
- `README.md` – User-facing features and setup instructions
- `docs/ARCHITECTURE.md` – Technical architecture and data flow
- `docs/AI_ASSISTANTS_GUIDE.md` – AI usage guidelines and examples

For detailed AI assistance guidelines, see [docs/AI_ASSISTANTS_GUIDE.md](docs/AI_ASSISTANTS_GUIDE.md).

---

## 7. Development Workflow

### Standard Development Cycle

1. **Make a focused change**
   - Keep changes small and focused on a single feature or fix
   - Follow existing code patterns and style

2. **Run the app locally**
   ```bash
   streamlit run app.py
   ```
   - Test your changes in the browser
   - Verify all affected pages work correctly

3. **Format and lint your code**
   ```bash
   # Auto-format with Black
   black --line-length=120 .
   
   # Sort imports
   isort --profile=black --line-length=120 .
   
   # Or use pre-commit hooks
   pre-commit run --all-files
   ```

4. **Update documentation**
   - Add/update docstrings for new/modified functions
   - Add comments for non-obvious logic
   - Update README.md if user-facing behavior changed
   - Update ARCHITECTURE.md if data flow or structure changed

5. **If using AI assistance (Copilot, ChatGPT, etc.)**
   - Read through generated code carefully
   - Add or refine docstrings to match project style
   - Add comments explaining "why" for complex logic
   - See [docs/AI_ASSISTANTS_GUIDE.md](docs/AI_ASSISTANTS_GUIDE.md) for detailed guidelines

6. **Commit with a clear message**
   ```bash
   git add .
   git commit -m "Add specialty filter to provider search"
   git push
   ```

### Working with Data

**Adding new data:**
1. Download updated data from the [CMS Provider dataset](https://data.cms.gov/provider-data/dataset/mj5m-pzi6)
2. Go to "🔄 Update Data" page in the app
3. Upload the file with provider data
4. App processes and saves to parquet format; cache automatically refreshes

**Data location:**
- Raw data: `data/raw/`
- Processed data: `data/processed/` (parquet files)
- Primary file: `Combined_Contacts_and_Reviews.parquet`

### Pre-commit Hooks

The project uses pre-commit hooks for code quality:

**Install hooks:**
```bash
pip install pre-commit
pre-commit install
```

**What gets checked:**
- Black formatting (120 char line length)
- isort import sorting
- Trailing whitespace removal
- YAML file validation
- Large file detection
- Merge conflict markers

**Skip hooks temporarily:**
```bash
git commit --no-verify -m "Quick fix"
```

### Common Development Tasks

**Add a new page:**
1. Create file in `pages/` with format `N_🔬_Page_Name.py` (N = order number)
2. Add to navigation in `app.py` in the `_nav_items` list
3. Use `load_application_data()` for accessing provider data
4. Follow responsive layout patterns from existing pages

**Add a new filter:**
1. Add UI controls in `pages/1_🔎_Search.py`
2. Store filter values in `st.session_state`
3. Apply filter in `run_recommendation()` in `src/app_logic.py`
4. Update Results page to display active filters

**Modify scoring algorithm:**
1. Update `recommend_provider()` in `src/utils/scoring.py`
2. Document changes in `pages/10_🛠️_How_It_Works.py`
3. Add explanation in Results page scoring expander
4. Update weight controls in Search page if needed

---

## 8. Future Improvements

Some possible next steps:

- Add multi-select specialty and gender filters.
- Add clustering or heatmap map visualizations.
- Add CSV/Excel export for full filtered results.
- Add unit and integration tests for core data and scoring functions.
- Surface additional CMS data fields (e.g., Medicare acceptance, languages spoken).
