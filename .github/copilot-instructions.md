# GitHub Copilot Instructions for MedMatch_App

## Project Overview

MedMatch is a **Streamlit healthcare provider recommendation app** that helps users find medical providers based on geographic proximity, specialty, and referral history. The app uses **local parquet files** (no database), caches aggressively with Streamlit's `@st.cache_data`, and scores providers using a weighted multi-criteria algorithm.

**Key Tech Stack:** Streamlit (multi-page app), pandas (data processing), geopy (geocoding), plotly (visualizations), pyarrow (parquet I/O)

## Architecture Essentials

### Data Flow Pattern (Critical to Understand)

1. **Data Source**: Single parquet file at `data/processed/Combined_Contacts_and_Reviews.parquet`
2. **Loading**: `load_application_data()` in [src/app_logic.py](../src/app_logic.py) - cached with 1-hour TTL
3. **Search**: User inputs address → geocoding → coordinates stored in `st.session_state`
4. **Scoring**: `recommend_provider()` in [src/utils/scoring.py](../src/utils/scoring.py) computes weighted scores
5. **Display**: Results ranked by composite score in [pages/2_📄_Results.py](../pages/2_📄_Results.py)

### Multi-Layer Caching Strategy

**All data loading uses `@st.cache_data(ttl=3600)`** with these invalidation triggers:
- TTL expiration (1 hour)
- Source file modification (via file hash/mtime)
- Daily scheduled refresh (4 AM via `check_and_refresh_daily_cache()`)

**When modifying data functions:**
- Keep the `@st.cache_data` decorator
- Don't add side effects in cached functions (use separate functions)
- If you need to force refresh, increment TTL or change function signature

### Session State Usage

Search parameters flow via `st.session_state` between pages:
- **Search page** → Sets: `user_lat`, `user_lon`, `max_radius_miles`, `min_referrals`, `alpha`, `beta`, `selected_specialties`
- **Results page** → Reads these + stores: `last_best`, `last_scored_df`

**Pattern:** Always check for required keys before use:
```python
if "user_lat" not in st.session_state:
    st.switch_page("pages/1_🔎_Search.py")
```

## Code Conventions

### Docstrings (Required for Public Functions)

Use Google-style with Args/Returns. See [filter_providers_by_radius](../src/app_logic.py#L226) for example:
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

### Design Notes for Complex Logic

Add `DESIGN NOTE:` comments at module/function level for non-obvious patterns. Examples:
- [src/utils/scoring.py](../src/utils/scoring.py#L3-L65) - Explains scoring algorithm, normalization strategy, trade-offs
- [src/data/ingestion.py](../src/data/ingestion.py#L20-L48) - Documents multi-layer caching strategy
- [src/app_logic.py](../src/app_logic.py#L6-L48) - Describes preferred provider integration and merge logic

### Comments Should Explain "Why"

Bad: `i = i + 1  # increment i`  
Good: `# Round distance to 1 decimal place for cleaner display`

See [docs/AI_ASSISTANTS_GUIDE.md](../docs/AI_ASSISTANTS_GUIDE.md) for full guidelines.

## Common Development Patterns

### Refactoring Applied

Based on analysis of the codebase, the following refactoring was completed:

- **src/app_logic.py**: Extracted helper functions from `load_application_data()` (originally 155 lines):
  - `_clean_provider_addresses()` - Address and phone number standardization
  - `_enrich_inbound_referrals()` - Inbound referral count calculation
  - `_integrate_preferred_providers()` - Preferred provider list merging and validation
  - `_ensure_referral_counts()` - Referral count data validation
  - Main function reduced to ~50 lines with clear orchestration logic

These helper functions improve testability and make the data loading pipeline easier to understand and maintain.

### Adding a New Filter

1. **UI controls** in [pages/1_🔎_Search.py](../pages/1_🔎_Search.py)
2. **Store in session state**: `st.session_state["filter_name"] = value`
3. **Apply in** `run_recommendation()` in [src/app_logic.py](../src/app_logic.py) or create new filter function (e.g., `filter_providers_by_specialty`)
4. **Display active filter** in Results sidebar

### Responsive Layout

Use `resp_columns()` from [src/utils/responsive.py](../src/utils/responsive.py) instead of `st.columns()`:
```python
from src.utils.responsive import resp_columns
col1, col2 = resp_columns([1, 1])  # Adapts to mobile
```

### Phone Number Formatting

Always use `format_phone_number()` from [src/utils/io_utils.py](../src/utils/io_utils.py):
```python
from src.utils.io_utils import format_phone_number
display_df["Work Phone Number"] = display_df["Work Phone Number"].apply(format_phone_number)
```

### Configuration Access

Use centralized config instead of hardcoded values:
```python
from src.utils.config import get_api_config
geocoding_config = get_api_config('geocoding')
```

## Development Workflow

### Running the App
```bash
streamlit run app.py
# Or using the provided script (Windows):
./start_app.sh
```

### Code Formatting (Before Commit)
```bash
black --line-length=120 .
isort --profile=black --line-length=120 .
```

### Debugging & Logging
All modules use standard Python logging:
```python
import logging
logger = logging.getLogger(__name__)
logger.info("Loaded X records from file")  # Info for normal operations
logger.warning("Data quality issue detected")  # Warnings for degraded state
logger.error("Failed to process X")  # Errors for failures
```
Check console/terminal for log output when debugging.

### No Tests Yet
The `tests/` directory is empty. When adding tests:
- Focus on core functions: `calculate_distances()`, `recommend_provider()`, `filter_providers_by_radius()`
- Use pytest (not in requirements.txt yet - add if needed)

## Key Files to Reference

- **[src/app_logic.py](../src/app_logic.py)** - Central orchestration, see `load_application_data()` and `run_recommendation()`
- **[src/utils/scoring.py](../src/utils/scoring.py)** - Scoring algorithm with extensive design notes
- **[src/data/ingestion.py](../src/data/ingestion.py)** - Data loading patterns and caching strategy
- **[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)** - Complete architecture reference
- **[docs/AI_ASSISTANTS_GUIDE.md](../docs/AI_ASSISTANTS_GUIDE.md)** - Code quality and documentation standards

## Project-Specific Gotchas

1. **No Database** - All data is in parquet files. Don't add database connection code without discussion.
2. **Geocoding Rate Limits** - Uses free Nominatim with 1 req/sec limit. Cache is in `data/processed/geocode_cache.json`.
3. **Preferred Provider Warning** - If >80% providers are preferred, one-time warning logs (see `_preferred_pct_warning_logged` flag).
4. **Column Name Variations** - Phone fields: `["Work Phone Number", "Work Phone", "Phone Number", "Phone 1"]`. Use first available.
5. **Portfolio Project** - Code must be human-readable for reviewers. Avoid "clever" code; prefer clarity.
6. **Optional S3 Integration** - `src/utils/s3_client_optimized.py` provides AWS S3 upload capability (boto3 required). Disabled by default - check `is_api_enabled("s3")` before use.
7. **Background Data Loading** - `auto_update_data()` in `app.py` runs in a thread at startup. Don't use `st.*` calls inside - write status to `data/processed/data_auto_update_status.txt` instead.

## When Modifying Scoring Algorithm

1. Update `recommend_provider()` in [src/utils/scoring.py](../src/utils/scoring.py)
2. Update the DESIGN NOTE at top of that file
3. Update explanation in [pages/2_📄_Results.py](../pages/2_📄_Results.py) scoring expander
4. Update [pages/10_🛠️_How_It_Works.py](../pages/10_🛠️_How_It_Works.py) documentation

## Documentation Requirements

**Always update when changing:**
- User-facing features → [README.md](../README.md) section 1-3
- Architecture/data flow → [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- AI coding patterns → [docs/AI_ASSISTANTS_GUIDE.md](../docs/AI_ASSISTANTS_GUIDE.md)

Keep examples concrete and project-specific. See existing docs for style.
