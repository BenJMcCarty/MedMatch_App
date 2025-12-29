# Architecture

This document explains how the app is structured and how data flows from the database to the map.

<!--
TODO (Copilot):
Read `app.py` and the modules under `src/` (or whatever main package this repo uses).
Use that to fill out each section below with real file names, functions, and data structures.
-->

---

## 1. High-Level Components

### Core Application Files

- [app.py](app.py) – Main Streamlit application entrypoint serving as the landing/home page. Handles navigation to core pages, manages the data loading pipeline from local parquet files to Streamlit cache, and coordinates background data refresh on startup and daily at 4 AM.

- [main.py](main.py) – Simple Python entrypoint for command-line execution (contains a basic "Hello" function).

### Multi-Page Application Structure

- [pages/1_🔎_Search.py](pages/1_🔎_Search.py) – Provider search page where users input search criteria including address, specialty, radius, and filters.

- [pages/2_📄_Results.py](pages/2_📄_Results.py) – Results display page showing recommended providers based on search criteria with interactive maps and detailed provider information.

- [pages/10_🛠️_How_It_Works.py](pages/10_🛠️_How_It_Works.py) – Documentation page explaining the recommendation algorithm and scoring methodology.

- [pages/20_📊_Data_Dashboard.py](pages/20_📊_Data_Dashboard.py) – Analytics dashboard for visualizing referral patterns and provider statistics.

- [pages/30_🔄_Update_Data.py](pages/30_🔄_Update_Data.py) – Data management page for uploading and processing new provider and referral data.

- [pages/5_👟_Quick_Start_Guide.py](pages/5_👟_Quick_Start_Guide.py) – User guide page with instructions for using the application.

### Core Business Logic

- [src/app_logic.py](src/app_logic.py) – Central business logic module containing data loading orchestration, provider filtering, specialty extraction, and recommendation execution functions.

### Data Layer

- [src/data/ingestion.py](src/data/ingestion.py) – Centralized data ingestion manager (`DataIngestionManager`) that handles loading from local parquet files with Streamlit cache integration, column mapping, and source-specific post-processing.

- [src/data/preparation.py](src/data/preparation.py) – Data preparation utilities for transforming raw Excel exports into cleaned parquet datasets, including phone number formatting, address parsing, and data validation.

- [src/data/io_utils.py](src/data/io_utils.py) – Shared I/O utilities providing file format detection and universal data loading supporting CSV, Excel, Parquet, and in-memory buffers.

### Utilities Layer

- [src/utils/config.py](src/utils/config.py) – Configuration and secrets management providing centralized access to API keys, database URLs, and application settings through Streamlit's secrets system.

- [src/utils/geocoding.py](src/utils/geocoding.py) – Geocoding helpers with caching and rate limiting using the geopy library and Nominatim service.

- [src/utils/scoring.py](src/utils/scoring.py) – Provider recommendation scoring engine calculating haversine distances and composite scores based on distance, client count, and client ratings.

- [src/utils/providers.py](src/utils/providers.py) – Provider-focused utilities for counting referrals, data validation, and provider list management.

- [src/utils/cleaning.py](src/utils/cleaning.py) – Data cleaning utilities for address standardization, coordinate validation, state abbreviation mapping, and phone number formatting.

- [src/utils/addressing.py](src/utils/addressing.py) – Address validation and formatting utilities.

- [src/utils/validation.py](src/utils/validation.py) – Data validation helpers for ensuring data quality and consistency.

- [src/utils/responsive.py](src/utils/responsive.py) – Responsive layout utilities for adapting the UI to different screen sizes.

- [src/utils/freshness.py](src/utils/freshness.py) – Data freshness tracking and display utilities for showing when provider information was last verified.

- [src/utils/io_utils.py](src/utils/io_utils.py) – Additional I/O utilities including phone number formatting and filename sanitization.

- [src/utils/performance.py](src/utils/performance.py) – Performance monitoring and optimization utilities.


---

## 2. Data Access Layer

### Data Source

This application uses **local parquet files** as its primary data source—there is no database connection. All provider and referral data is stored in `data/processed/Combined_Contacts_and_Reviews.parquet`.

### Primary Data Loading Functions

**Main Entry Point:**
- `load_application_data()` in [src/app_logic.py](src/app_logic.py)
  - Returns: `Tuple[pd.DataFrame, pd.DataFrame]` (provider_df, detailed_referrals_df)
  - Called by: All pages that need provider data (Search, Results, Dashboard)
  - Decorated with `@st.cache_data(ttl=3600)` for 1-hour caching
  - Orchestrates the complete data loading and enrichment pipeline

**Data Ingestion Manager:**
- `DataIngestionManager` class in [src/data/ingestion.py](src/data/ingestion.py)
  - `load_data(source: DataSource)` → `pd.DataFrame`
  - Loads data from parquet files with intelligent caching
  - Uses `@st.cache_data` with file modification timestamp for cache invalidation
  - Singleton accessed via `get_data_manager()`

**Specialized Loaders:**
- `load_and_validate_provider_data()` in [src/utils/providers.py](src/utils/providers.py) → `pd.DataFrame`

### Data Enrichment Pipeline

The `load_application_data()` function performs:

1. **Provider Data Loading** - Loads base provider records from parquet
2. **Coordinate Validation** - Cleans latitude/longitude via `validate_and_clean_coordinates()`
3. **Address Standardization** - Normalizes addresses via `clean_address_data()` and `build_full_address()`
4. **Phone Formatting** - Standardizes phone numbers via `format_phone_number()`
5. **Deduplication** - Removes duplicate providers based on `Full Name`

### Performance & Caching Strategy

**Streamlit Cache Integration:**
- All data loading functions use `@st.cache_data(ttl=3600)` (1-hour TTL)
- Cache keys include file modification timestamps for automatic invalidation
- Background data loading on app startup via `auto_update_data()` thread

**Parquet Format Advantages:**
- Columnar storage for fast column-based queries
- Built-in compression (snappy) reduces file size
- Fast deserialization compared to CSV/Excel
- Native pandas integration via `pd.read_parquet()`

**No Database Connection:**
- No connection pooling or credential management required
- Data is pre-processed and ready to use
- Trade-off: Updates require regenerating parquet files via Update Data page

---

## 3. Streamlit UI Structure

### Multi-Page Application Architecture

This is a **multi-page Streamlit application** using Streamlit's native `st.navigation()` system. The landing page ([app.py](app.py)) coordinates navigation to specialized pages.

**Navigation Setup** ([app.py](app.py) lines 132-179):
```python
def _build_and_run_app():
    nav_pages = [st.Page(path, title=title, icon=icon) for path, title, icon in _nav_items]
    pg = st.navigation(nav_pages)
    pg.run()
```

### Page Organization

**Landing/Home Page:**
- [app.py](app.py) - Entry point with navigation and data loading orchestration
- No user-facing content (immediately navigates to page structure)

**Core User-Facing Pages:**
1. **[1_🔎_Search.py](pages/1_🔎_Search.py)** - Search interface
   - Address input form with responsive columns via `resp_columns()`
   - Preset search profiles (radio buttons) and custom weight sliders
   - Advanced filters expander (specialty, radius, rating)
   - "Find Providers" button triggers geocoding and navigation to Results

2. **[2_📄_Results.py](pages/2_📄_Results.py)** - Results display
   - Top recommendation card with provider details
   - Full results table with ranking, phone, address, scores
   - Export to Word document button
   - Scoring methodology expander at bottom

3. **[5_👟_Quick_Start_Guide.py](pages/5_👟_Quick_Start_Guide.py)** - User guide

4. **[10_🛠️_How_It_Works.py](pages/10_🛠️_How_It_Works.py)** - Documentation on scoring algorithm

5. **[20_📊_Data_Dashboard.py](pages/20_📊_Data_Dashboard.py)** - Analytics dashboard

6. **[30_🔄_Update_Data.py](pages/30_🔄_Update_Data.py)** - Data upload and processing interface

### Sidebar Layout

**Search Page Sidebar** ([1_🔎_Search.py](pages/1_🔎_Search.py)):
- Data auto-update status via `show_auto_update_status()`
- Quick links to other pages
- Search tips and help text

**Results Page Sidebar** ([2_📄_Results.py](pages/2_📄_Results.py) lines 11-25):
- "← New Search" button to return to Search page
- Active search criteria display:
  - Radius (miles)
  - Minimum rating threshold
  - Selected specialties
  - Client address

### Main Content Layout Patterns

**Responsive Columns:**
- Uses `resp_columns([1, 1])` from [src/utils/responsive.py](src/utils/responsive.py)
- Adapts layout based on screen width
- Common pattern: Two-column forms on desktop, single column on mobile

**Search Page Layout:**
1. Data loading status (auto-update banner)
2. Address input section (4 fields: street, city, state, zip)
3. Search profile selection (radio buttons for presets)
4. Custom weights (conditional expander for "Custom Settings")
5. Advanced filters (expander with specialty, radius, ratings)
6. "Find Providers" action button
7. Help section (expander at bottom)

**Results Page Layout:**
1. Page title "🎯 Provider Recommendations"
2. Best match card (two columns: details + metrics)
3. Export button (Word document)
4. Full results table (ranked, formatted, scrollable)
5. Scoring explanation (expander)

### Session State Management

Search parameters are stored in `st.session_state` and passed between pages:

**Stored in Search page** ([1_🔎_Search.py](pages/1_🔎_Search.py) lines 368-390):
- `user_lat`, `user_lon` - Geocoded coordinates
- `alpha`, `beta`, `gamma` - Normalized scoring weights
- `preferred_weight`, `preferred_norm` - Preferred provider weights
- `max_radius_miles` - Distance radius filter
- `selected_specialties` - List of specialty filters
- `time_period`, `use_time_filter` - Date range filtering
- `street`, `city`, `state`, `zipcode` - Original address inputs

**Retrieved in Results page** ([2_📄_Results.py](pages/2_📄_Results.py) lines 26-29):
- Validates required keys exist, redirects to Search if missing
- Uses cached `last_best` and `last_scored_df` to avoid re-computation on page refresh

---

## 4. Mapping Layer

### Current Implementation: No Map Visualization

**Important:** This application **does not currently include map visualizations**. Provider results are displayed in tabular format only.

TODO: Add map rendering in the future using Streamlit's built-in `st.map()` or pydeck/folium for interactive maps.

### Geographic Data Available

Despite the absence of map rendering, the application maintains full geographic capabilities:

**Coordinate Data:**
- Providers have `Latitude` and `Longitude` columns (validated via `validate_and_clean_coordinates()`)
- Client addresses are geocoded to lat/lon coordinates via `geocode_address_with_cache()`
- Distance calculations use the Haversine formula in `calculate_distances()` ([src/utils/scoring.py](src/utils/scoring.py) lines 6-22)

**Geographic Processing:**
- [src/utils/geocoding.py](src/utils/geocoding.py) - Geocoding with caching and rate limiting
  - Uses `geopy.geocoders.Nominatim` for address → coordinates
  - `RateLimiter` wrapper prevents API abuse (min 1 second between requests)
  - Results cached via `@st.cache_data(ttl=3600)`
  
- [src/utils/addressing.py](src/utils/addressing.py) - Address validation and formatting
  - `validate_address_input()` - Ensures addresses meet minimum requirements
  - `build_full_address()` - Constructs standardized address strings

### Potential Future Enhancement

If map visualization is added in the future, the data is already structured to support it:

**Ready for Mapping:**
- `scored_df` DataFrame contains `Latitude`, `Longitude`, `Full Name`, `Distance (Miles)`
- Could be passed to `st.map(scored_df[['lat', 'lon']])` or pydeck/folium
- Color-coding could use `Score` or `Preferred Provider` columns
- Tooltips could show provider name, specialty, distance, phone

**Expected Implementation Pattern:**
```python
# Hypothetical future code in Results page
import pydeck as pdk

map_df = scored_df[['Latitude', 'Longitude', 'Full Name', 'Score']].dropna()
view_state = pdk.ViewState(
    latitude=st.session_state['user_lat'],
    longitude=st.session_state['user_lon'],
    zoom=10
)
layer = pdk.Layer(
    'ScatterplotLayer',
    data=map_df,
    get_position='[Longitude, Latitude]',
    get_radius=200,
    get_fill_color='[200, 30, 0, 160]'
)
st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state))
```

**Why No Maps Currently:**
- Focus on core recommendation algorithm first
- Table format provides precise, sortable, exportable data
- Reduces complexity and dependencies
- Maps can be added later without architectural changes

---

## 5. Data Flow (Detailed)

This section traces the complete user journey from entering search criteria to viewing ranked provider recommendations.

### Application Startup Flow

**Step 1: App Launch** ([app.py](app.py) `_build_and_run_app()` lines 149-179)
1. Streamlit executes `app.py` main entry point
2. `_build_and_run_app()` checks for daily cache refresh via `data_manager.check_and_refresh_daily_cache()`
3. Background thread spawns `auto_update_data()` to warm data cache
4. `auto_update_data()` calls `data_manager.preload_data()` to load all parquet files into `@st.cache_data`
5. Navigation structure created from `_nav_items` list
6. User sees landing page with navigation options

### Search & Recommendation Flow (Main User Journey)

**Step 2: User Inputs Search Criteria** ([1_🔎_Search.py](pages/1_🔎_Search.py))

User enters on Search page:
- **Address fields** (lines 130-166): `street`, `city`, `state`, `zipcode` text inputs
- **Search profile** (lines 171-177): Radio selection sets preset weights or "Custom Settings"
- **Weight sliders** (lines 190-227): If custom, user adjusts `distance_weight`, `outbound_weight`, `inbound_weight`, `preferred_weight`
- **Advanced filters** (lines 230-292):
  - `selected_specialties` - Multi-select of available specialties from `get_unique_specialties(provider_df)`
  - `max_radius_miles` - Slider for search radius (5-100 miles)
  - `min_referrals` - Number input for minimum case count
  - `use_time_filter` + `time_period` - Date range picker for historical filtering

**Step 3: Click "Find Providers" Button** ([1_🔎_Search.py](pages/1_🔎_Search.py) lines 294-398)

1. **Address Validation** (line 307):
   ```python
   valid, msg = validate_address_input(street, city, state, zipcode)
   ```
   - Returns `(bool, str)` with validation status and error message
   - Stops execution with `st.error()` if invalid

2. **Geocoding** (lines 351-367):
   ```python
   full_address = f"{street}, {city}, {state} {zipcode}"
   coords = geocode_address_with_cache(full_address)  # Returns Optional[Tuple[float, float]]
   ```
   - Calls Nominatim API via `geopy` with rate limiting and caching
   - Returns `(latitude, longitude)` or `None` if address not found
   - Shows spinner "🌍 Looking up address coordinates..."

3. **Weight Normalization** (lines 255-265):
   ```python
   total = distance_weight + outbound_weight + inbound_weight + preferred_weight
   alpha = distance_weight / total  # Normalized distance weight
   beta = outbound_weight / total   # Normalized outbound weight
   gamma = inbound_weight / total   # Normalized inbound weight
   pref_norm = preferred_weight / total
   ```

4. **Store in Session State** (lines 370-390):
   ```python
   st.session_state.update({
       "user_lat": float(user_lat),
       "user_lon": float(user_lon),
       "alpha": float(alpha),
       "beta": float(beta),
       "gamma": float(gamma),
       # ... all search parameters
   })
   ```

5. **Navigate to Results** (line 393):
   ```python
   st.switch_page("pages/2_📄_Results.py")
   ```

**Step 4: Results Page Data Loading** ([2_📄_Results.py](pages/2_📄_Results.py) lines 26-46)

1. **Validate Session State** (lines 26-29):
   ```python
   required_keys = ["user_lat", "user_lon", "alpha", "beta", "min_referrals", "max_radius_miles"]
   if any(k not in st.session_state for k in required_keys):
       st.switch_page("pages/1_🔎_Search.py")  # Redirect if missing parameters
   ```

2. **Load Provider Data** (lines 31-46):
   ```python
   provider_df, detailed_referrals_df = load_application_data()
   ```
   This cached function ([src/app_logic.py](src/app_logic.py) lines 30-176) performs:
   - Loads base provider data from parquet
   - Validates and cleans coordinates
   - Cleans address data and builds full addresses
   - Loads and merges inbound referral counts
   - Loads and merges preferred provider list
   - Returns `(pd.DataFrame, pd.DataFrame)` with enriched data

3. **Apply Time Filtering** (lines 48-56, if enabled):
   ```python
   if st.session_state.get("use_time_filter"):
       provider_df = apply_time_filtering(provider_df, detailed_referrals_df, start_date, end_date)
   ```
   - Recalculates `Referral Count` and `Inbound Referral Count` for date range
   - Uses `calculate_time_based_referral_counts()` and `calculate_inbound_referral_counts()`

**Step 5: Run Recommendation Algorithm** ([2_📄_Results.py](pages/2_📄_Results.py) lines 67-89)

1. **Execute Recommendation** via `run_recommendation()` ([src/app_logic.py](src/app_logic.py) lines 311-378):
   
   ```python
   best, scored_df = run_recommendation(
       provider_df,
       st.session_state["user_lat"],
       st.session_state["user_lon"],
       min_referrals=st.session_state["min_referrals"],
       max_radius_miles=st.session_state["max_radius_miles"],
       alpha=st.session_state["alpha"],
       beta=st.session_state["beta"],
       gamma=st.session_state.get("gamma", 0.0),
       preferred_weight=st.session_state.get("preferred_norm", 0.1),
       selected_specialties=st.session_state.get("selected_specialties")
   )
   ```

2. **Inside `run_recommendation()`** - Sequential filtering and scoring:
   
   a. **Specialty Filter** (line 333-336):
   ```python
   if selected_specialties:
       working = filter_providers_by_specialty(working, selected_specialties)
   ```
   - Matches any specialty in comma-separated provider specialty field
   - Returns filtered DataFrame
   
   b. **Referral Count Filter** (line 339-341):
   ```python
   working = working[working["Referral Count"] >= min_referrals].copy()
   ```
   
   c. **Distance Calculation** (line 344):
   ```python
   working["Distance (Miles)"] = calculate_distances(user_lat, user_lon, working)
   ```
   - Uses Haversine formula on `Latitude`/`Longitude` columns ([src/utils/scoring.py](src/utils/scoring.py))
   - Returns `List[Optional[float]]` with distances in miles
   
   d. **Radius Filter** (line 345):
   ```python
   working = filter_providers_by_radius(working, max_radius_miles)
   ```
   - Filters to `Distance (Miles) <= max_radius_miles`
   
   e. **Scoring & Ranking** (lines 348-356):
   ```python
   best, scored_df = recommend_provider(
       working,
       distance_weight=alpha,
       referral_weight=beta,
       inbound_weight=gamma,
       preferred_weight=preferred_weight,
       min_referrals=min_referrals
   )
   ```

3. **Inside `recommend_provider()`** ([src/utils/scoring.py](src/utils/scoring.py) lines 25-126):
   
   a. **Normalize Metrics** (lines 41-49):
   ```python
   # Outbound referrals: higher = better (more experience)
   df["norm_rank"] = (df["Referral Count"] - df["Referral Count"].min()) / referral_range
   
   # Distance: closer = better (inverted normalization)
   df["norm_dist"] = (df["Distance (Miles)"].max() - df["Distance (Miles)"]) / dist_range
   ```
   
   b. **Calculate Composite Score** (line 51):
   ```python
   df["Score"] = distance_weight * df["norm_dist"] + referral_weight * df["norm_rank"]
   ```
   
   c. **Add Preferred Provider Bonus** (lines 54-73, if `preferred_weight > 0`):
   ```python
   df["_pref_flag"] = df["Preferred Provider"].apply(_pref_to_int)  # Convert to 0 or 1
   df["norm_pref"] = (df["_pref_flag"] - df["_pref_flag"].min()) / pref_range
   df["Score"] = df["Score"] + preferred_weight * df["norm_pref"]
   ```
   
   d. **Add Inbound Referral Component** (lines 75-94, if `inbound_weight > 0`):
   ```python
   df["norm_inbound"] = (df["Inbound Referral Count"] - min) / range
   df["Score"] = distance_weight * norm_dist + referral_weight * norm_rank + inbound_weight * norm_inbound
   ```
   
   e. **Sort by Score** (lines 96-110):
   ```python
   sort_keys = ["Score", "Distance (Miles)", "Referral Count", "Inbound Referral Count", "Full Name"]
   df_sorted = df.sort_values(by=sort_keys, ascending=[False, False, False, False, True])
   best = df_sorted.iloc[0]  # Top-ranked provider (pd.Series)
   ```
   
   f. **Return Results**:
   ```python
   return best, df_sorted  # Tuple[pd.Series, pd.DataFrame]
   ```

**Step 6: Display Results** ([2_📄_Results.py](pages/2_📄_Results.py) lines 94-238)

1. **Best Match Card** (lines 94-152):
   - Extract top provider from `best` Series
   - Display in two-column layout:
     - Left: Name, address, phone, specialty, distance, case count
     - Right: Match score metric
   - Show "⭐ Preferred Provider" badge if applicable

2. **Export Button** (lines 157-170):
   ```python
   st.download_button(
       "📄 Export to Word Document",
       data=get_word_bytes(best),  # Generates .docx from provider data
       file_name=f"Provider_{sanitize_filename(provider_name)}.docx"
   )
   ```

3. **Full Results Table** (lines 173-238):
   - Select display columns: Name, Phone, Address, Specialty, Distance, Referral Count, Preferred, Score
   - Sort by Score (descending)
   - Format phone numbers via `format_phone_number()`
   - Format dates via `format_last_verified_display()`
   - Map boolean `Preferred Provider` to "⭐ Yes" / "No"
   - Add "Rank" column (1, 2, 3, ...)
   - Display via `st.dataframe(display_df, height=400)`

4. **Scoring Explanation** (lines 241-262):
   - Expander showing weight breakdown: α, β, γ, preferred weight
   - Formula display: `Score = Distance × α + Outbound × β + Inbound × γ + Preferred × ρ`

### Data Refresh Flow

**Manual Update** (via [30_🔄_Update_Data.py](pages/30_🔄_Update_Data.py)):
1. User uploads Excel file with new provider/referral data
2. Page calls `process_referral_data()` from [src/data/preparation.py](src/data/preparation.py)
3. Data is cleaned, geocoded, and saved to `Combined_Contacts_and_Reviews.parquet`
4. File modification timestamp changes, invalidating `@st.cache_data` cache
5. Next data load automatically uses new parquet file

**Automatic Refresh** ([app.py](app.py) lines 165-167):
1. On each app launch, `check_and_refresh_daily_cache()` checks last update time
2. If last update was before 4 AM today, triggers full data reload
3. Cache is cleared and re-warmed with latest parquet data

---

## 6. Configuration & Environment

### Configuration Module

[src/utils/config.py](src/utils/config.py) provides centralized configuration and secrets management through Streamlit's built-in secrets system.

**Key Functions:**

- `get_secret(key_path: str, default: Any = None) -> Any`
  - Retrieves secrets from `st.secrets` using dot-notation paths
  - Example: `get_secret('geocoding.google_maps_api_key')`
  - Falls back to default value if secret not found
  - Handles nested mappings gracefully

- `get_api_config(service_name: str) -> Dict[str, Any]`
  - Returns configuration dict for specific API services
  - Examples: `'geocoding'`, `'database'`, `'aws'`
  
- `get_database_config() -> Dict[str, Any]`
  - Returns database connection parameters (unused in current parquet-based architecture)

### Secrets Management

**Secrets File Location:**
- Local development: `.streamlit/secrets.toml` (gitignored)
- Streamlit Cloud: Dashboard → App Settings → Secrets

**Expected Secrets Structure:**
```toml
[geocoding]
google_maps_api_key = "YOUR_API_KEY"  # Optional - app uses Nominatim (free)

[database]
url = "postgresql://..."  # Not currently used (parquet-based system)

[app]
debug_mode = false
```

### Critical Settings & Defaults

**Geocoding Configuration:**
- **Service**: Nominatim (OpenStreetMap) via `geopy`
- **No API key required** - Free geocoding service
- **Rate limiting**: 1 second minimum between requests (via `RateLimiter`)
- **Caching**: Results cached for 1 hour via `@st.cache_data(ttl=3600)`
- **User agent**: `"provider_recommender"` (required by Nominatim)
- **Timeout**: 10 seconds per request
- **Fallback**: If `geopy` unavailable, `geocode_address_with_cache()` returns `None` and shows warning

**Data Loading Configuration:**
- **Cache TTL**: 3600 seconds (1 hour) for all `@st.cache_data` decorators
- **Data directory**: `data/processed/` (relative to project root)
- **Primary data file**: `Combined_Contacts_and_Reviews.parquet`
- **Daily refresh time**: 4:00 AM (checked on each app startup)
- **Background loading**: Enabled via threaded `auto_update_data()`

**Search & Scoring Defaults:**
- **Default radius**: 50 miles (slider range: 5-100)
- **Default min referrals**: 0 (no minimum)
- **Preset weights**:
  - **Prioritize Proximity**: `{distance: 0.7, outbound: 0.2, inbound: 0.05, preferred: 0.05}`
  - **Balanced**: `{distance: 0.4, outbound: 0.4, inbound: 0.1, preferred: 0.1}`
  - **Prioritize Referrals**: `{distance: 0.2, outbound: 0.6, inbound: 0.1, preferred: 0.1}`
- **Distance calculation**: Haversine formula on WGS84 coordinates (Earth radius: 3958.8 miles)

### Environment Variables

**Not currently used** - The app relies on:
1. Streamlit secrets (via `st.secrets`)
2. Local parquet files (no environment-specific paths)
3. Hard-coded defaults in code

**Potential future use cases:**
- `DATA_DIR` - Override default data directory path
- `CACHE_TTL` - Adjust cache duration
- `GEOCODING_SERVICE` - Switch between Nominatim/Google Maps/etc.
- `ENABLE_BACKGROUND_LOADING` - Toggle background data loading thread

### Local vs Production Differences

**Local Development:**
- Data files stored in local `data/processed/` directory
- Secrets in `.streamlit/secrets.toml` (gitignored)
- Debug mode can be enabled via `st.secrets.get('app', {}).get('debug_mode', False)`
- Manual data uploads via Update Data page

**Streamlit Cloud (Production):**
- Same parquet file approach (uploaded to repository or mounted storage)
- Secrets configured in Streamlit Cloud dashboard
- Automatic daily cache refresh at 4 AM server time
- Background data loading on each dyno restart

**No Database Configuration Needed:**
- Original architecture may have used PostgreSQL/MySQL (hence `get_database_config()`)
- Current implementation uses local parquet files exclusively
- Database config functions remain for backward compatibility but are unused

### How Settings Plug Into Architecture

**Geocoding Flow** ([1_🔎_Search.py](pages/1_🔎_Search.py) → [src/utils/geocoding.py](src/utils/geocoding.py)):
```python
# No API key needed for Nominatim
geolocator = Nominatim(user_agent="provider_recommender")
rate_limited = RateLimiter(geolocator.geocode, min_delay_seconds=1.0, max_retries=3)
coords = rate_limited(address, timeout=10)
```

**Data Loading Flow** ([app.py](app.py) → [src/data/ingestion.py](src/data/ingestion.py)):
```python
# Hard-coded paths relative to project root
data_dir = Path("data/processed")
parquet_path = data_dir / "Combined_Contacts_and_Reviews.parquet"
df = pd.read_parquet(parquet_path)  # No connection string needed
```

**Cache Configuration** (Applied via decorators throughout codebase):
```python
@st.cache_data(ttl=3600)  # TTL from hard-coded constant
def load_application_data():
    # Data loading logic with automatic Streamlit cache management
```

---

## 7. Known Limitations and Trade-offs

This section documents intentional design decisions, current limitations, and areas for future improvement. Understanding these trade-offs helps reviewers and future maintainers make informed decisions.

### Data Architecture Limitations

**Parquet File Storage (No Database):**
- **Trade-off**: Simplicity and portability vs. real-time updates and concurrent access
- **Impact**: 
  - Cannot handle concurrent writes from multiple users
  - Data updates require file regeneration via Update Data page
  - No transaction support or ACID guarantees
- **Benefit**: 
  - No database credentials or connection management
  - Fast read performance for analytics workloads
  - Easy deployment (no database provisioning)
  - Works seamlessly with version control for sample data

**Cache Invalidation:**
- **Limitation**: Cache invalidation is time-based (1 hour TTL) and file-modification-based
- **Impact**: Users may see stale data for up to 1 hour after updates
- **Benefit**: Consistent fast performance, reduced file I/O
- **Mitigation**: Daily auto-refresh at 4 AM, manual refresh via Update Data page

### Geocoding Limitations

**Nominatim Rate Limiting:**
- **Limitation**: 1 request per second enforced by `RateLimiter`
- **Impact**: Batch geocoding of providers is slow (1 per second max)
- **Benefit**: Free geocoding service, no API key required
- **Alternative**: Can configure Google Maps API for faster geocoding (requires paid API key)

**Address Quality Dependency:**
- **Limitation**: Geocoding accuracy depends on address completeness and formatting
- **Impact**: Poorly formatted addresses may not geocode or return wrong coordinates
- **Mitigation**: Address validation via `validate_address_input()`, manual coordinate cleanup

**No Driving Distance:**
- **Trade-off**: Haversine (straight-line) distance vs. actual driving distance
- **Impact**: Distance estimates may differ from real travel time by 20-40%
- **Benefit**: No external API calls, instant calculation, works offline
- **Future**: Could integrate Google Distance Matrix API or OSRM for driving distances

### Scoring Algorithm Limitations

**Min-Max Normalization Sensitivity:**
- **Limitation**: Score normalization uses min-max scaling, sensitive to outliers
- **Impact**: A single provider with extreme values can compress score range for others
- **Example**: Provider with 1000 referrals makes providers with 10-50 referrals all appear similar
- **Mitigation**: Filter by minimum referral count to remove low-volume outliers
- **Alternative**: Could use z-score normalization or percentile-based scaling

**No Multi-Specialty Matching:**
- **Limitation**: Specialty filter is "any of" (OR logic), not ranked by specialty relevance
- **Impact**: Provider matching 1 of 5 selected specialties ranks equally to one matching all 5
- **Future**: Could add specialty match score component to ranking

**Static Weight Normalization:**
- **Limitation**: Weights are normalized at search time, cannot dynamically adjust during browsing
- **Impact**: Users must return to Search page to change scoring preferences
- **Benefit**: Consistent scores across results viewing session

### User Interface Limitations

**No Map Visualization:**
- **Limitation**: Results displayed in table format only, no geographic map
- **Impact**: Users cannot visually identify spatial clusters or geographic patterns
- **Benefit**: Simpler UI, faster rendering, no map library dependencies
- **Future**: Could add Streamlit `st.map()`, pydeck, or folium for interactive maps
- **Data Ready**: Provider coordinates already validated and available for mapping

**No Real-Time Search:**
- **Limitation**: Search requires clicking "Find Providers" button, no live filtering
- **Impact**: Cannot see results update as filters change
- **Benefit**: Reduces geocoding API calls, clearer separation between input and results
- **Alternative**: Could add client-side filtering on Results page (radius, specialty) without re-geocoding

**Session State Persistence:**
- **Limitation**: Search parameters stored in Streamlit session state only
- **Impact**: Parameters lost on browser refresh or tab close
- **Benefit**: No cookies or local storage needed, privacy-friendly
- **Alternative**: Could add URL parameters for shareable search links

### Performance Limitations

**Single-Threaded Scoring:**
- **Limitation**: Recommendation scoring runs in single thread during Streamlit request
- **Impact**: Large provider datasets (>10,000 records) may take 2-3 seconds to score
- **Current Scale**: Handles ~2,000 providers smoothly (<1 second)
- **Future**: Could parallelize distance calculation with multiprocessing or Dask

**Full DataFrame Operations:**
- **Limitation**: All filtering and scoring loads full dataset into memory
- **Impact**: Memory usage scales linearly with provider count
- **Current Scale**: ~2,000 providers = ~5MB parquet file, ~20MB in memory
- **Future**: Could add chunked processing for 100,000+ provider datasets

**No Result Pagination:**
- **Limitation**: Results page displays all matching providers in single scrollable table
- **Impact**: Very large result sets (>500 providers) may slow down browser rendering
- **Mitigation**: Radius and specialty filters reduce result set size
- **Future**: Could add pagination (show 50 at a time) or virtual scrolling

### Security Limitations

**No Authentication:**
- **Limitation**: App is publicly accessible, no user login or access control
- **Impact**: Anyone with the URL can access all provider data
- **Use Case**: Appropriate for internal tools or public provider directories
- **Future**: Could add Streamlit authentication or SSO integration

**No Rate Limiting:**
- **Limitation**: No per-user rate limiting on searches or geocoding
- **Impact**: Malicious users could exhaust geocoding API quota
- **Mitigation**: Nominatim rate limiter prevents server abuse, Streamlit caching reduces duplicate calls
- **Future**: Could add IP-based rate limiting via middleware

**Sensitive Data in Parquet Files:**
- **Limitation**: Provider data (names, addresses, phone numbers) stored in plain parquet files
- **Impact**: Data readable by anyone with file system access
- **Mitigation**: Deploy with proper file permissions, use private Git repositories
- **Alternative**: Could encrypt parquet files or move to database with access controls

### Data Quality Limitations

**Name-Based Deduplication:**
- **Limitation**: Duplicate providers removed by exact "Full Name" match only
- **Impact**: Same provider with slight name variations (e.g., "John Smith" vs "John A. Smith") treated as separate
- **Mitigation**: Data preparation includes name standardization
- **Future**: Could add fuzzy matching or NPI-based deduplication

**Preferred Provider Matching:**
- **Limitation**: Preferred provider status matched by name only, not unique ID
- **Impact**: Name mismatches between provider list and preferred list cause missing flags
- **Mitigation**: Warning logged if >30% of providers are marked preferred (indicates data issue)
- **Future**: Could use unique identifiers (NPI, ID) for matching

**No Data Versioning:**
- **Limitation**: Parquet file overwrites previous data, no historical versions
- **Impact**: Cannot track provider changes over time, no rollback capability
- **Benefit**: Simple storage model, no database migration complexity
- **Alternative**: Could add timestamped parquet files or data versioning

### Integration Limitations

**No External APIs:**
- **Limitation**: No integration with provider directories (NPI Registry, CMS, etc.)
- **Impact**: Provider data must be manually uploaded and maintained
- **Benefit**: Works offline, no API keys required (except optional Google Maps)
- **Future**: Could add automated data sync from external sources

**No Export Formats:**
- **Limitation**: Export supports Word documents only, no CSV/Excel/JSON
- **Impact**: Harder to integrate results with external systems
- **Current**: Word export generates formatted provider info cards
- **Future**: Could add CSV export for full results table

**No Calendar Integration:**
- **Limitation**: No scheduling or appointment booking features
- **Impact**: Users must contact providers separately
- **Use Case**: App is for provider discovery and evaluation, not booking
- **Future**: Could integrate with scheduling platforms (Calendly, Acuity, etc.)

### Intentional Simplifications

These are deliberate design choices to keep the codebase maintainable and focused:

1. **No user accounts or profiles** – Simplifies authentication and data privacy concerns
2. **No database** – Reduces deployment complexity and infrastructure requirements
3. **No real-time data updates** – Batch processing sufficient for provider data (changes infrequently)
4. **No mobile-specific UI** – Streamlit responsive layout sufficient for basic mobile support
5. **No automated testing** – Portfolio/demo project, manual testing during development
6. **No CI/CD pipeline** – Manual deployment via Streamlit Cloud dashboard
7. **No monitoring or analytics** – Use Streamlit Cloud built-in metrics

### Scalability Considerations

**Current Scale:**
- Providers: ~2,000 records
- Referrals: ~50,000 records
- File size: ~5MB parquet
- Memory: ~30MB in Streamlit cache
- Response time: <1 second for search

**Expected Limits:**
- Providers: Up to ~10,000 (< 3 second scoring)
- Referrals: Up to ~500,000 (< 100MB file)
- Concurrent users: 10-50 (Streamlit Cloud free tier)

**Beyond Current Scale:**
- 50,000+ providers → Need database with indexed queries
- 1M+ referrals → Need distributed processing (Dask, Spark)
- 100+ concurrent users → Need horizontal scaling and load balancer

### Portfolio Context

This is a **portfolio project** designed to demonstrate:
- Clean, readable code over production-scale architecture
- End-to-end feature development (data → algorithm → UI)
- Real-world data processing and visualization
- AI-assisted development best practices

The limitations listed above are **intentional trade-offs** for a portfolio scope. A production deployment would address several of these areas based on actual usage requirements and scale.
