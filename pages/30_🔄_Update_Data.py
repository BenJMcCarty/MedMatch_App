import traceback
from pathlib import Path

import streamlit as st

from src.data.ingestion import DataIngestionManager, DataSource, refresh_data_cache

st.set_page_config(page_title="Update Data", page_icon="🗂️", layout="wide")

st.markdown("### 🔄 Data Status and Cache Management")

st.markdown(
    """
**High-Level Overview**

Provider data is loaded from `data/processed/medmatch.duckdb` — a DuckDB database built
from CMS provider data and geocoded via the Census Geocoder batch API.

To update data with a fresh CMS export, run the two pipeline scripts from the project root
(see **Re-run Pipeline** section below).
"""
)

st.markdown("#### 📊 Current Data Overview")

DB_PATH = Path("data/processed/medmatch.duckdb")


@st.cache_data
def get_db_summary():
    if not DB_PATH.exists():
        return None, None, None
    try:
        import duckdb
        with duckdb.connect(str(DB_PATH), read_only=True) as con:
            provider_count = con.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
            address_count = con.execute("SELECT COUNT(*) FROM addresses").fetchone()[0]
            geocode_counts = con.execute(
                "SELECT geocode_source, COUNT(*) AS n FROM addresses GROUP BY geocode_source"
            ).df()
        return provider_count, address_count, geocode_counts
    except Exception:
        return None, None, None


provider_count, address_count, geocode_counts = get_db_summary()

if provider_count is not None:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("👥 Providers", f"{provider_count:,}")
    with col2:
        st.metric("📍 Unique Addresses", f"{address_count:,}")
    with col3:
        if geocode_counts is not None and not geocode_counts.empty:
            census_n = int(geocode_counts.loc[geocode_counts["geocode_source"] == "census", "n"].sum())
            st.metric("✅ Census Geocoded", f"{census_n:,}")
else:
    st.info("Database not yet loaded.")

st.markdown("---")

st.markdown("#### 📁 Database File")

if DB_PATH.exists():
    import datetime
    file_size = DB_PATH.stat().st_size / (1024 * 1024)
    mod_time = datetime.datetime.fromtimestamp(DB_PATH.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    st.success(f"✅ Database found: `{DB_PATH}`")
    col1, col2 = st.columns(2)
    with col1:
        st.caption(f"📊 File size: {file_size:.2f} MB")
    with col2:
        st.caption(f"📅 Last modified: {mod_time}")

    if geocode_counts is not None and not geocode_counts.empty:
        gcol1, gcol2, gcol3 = st.columns(3)
        counts = dict(zip(geocode_counts["geocode_source"], geocode_counts["n"]))
        with gcol1:
            st.metric("✅ Census geocoded", int(counts.get("census", 0)))
        with gcol2:
            st.metric("🔵 ZIP centroid fallback", int(counts.get("fallback_zip", 0)))
        with gcol3:
            st.metric("❌ Failed", int(counts.get("failed", 0)))
else:
    st.error(f"❌ Database not found: `{DB_PATH}`")
    st.info("Run the pipeline scripts to build the database (see below).")

st.markdown("---")

st.markdown("#### 🔄 Reload Cached Data")
st.markdown("Clear the Streamlit cache to force the app to re-read the database on next access.")

if st.button("🔄 **Reload Data**", key="reload_data", type="primary"):
    try:
        with st.spinner("Clearing cache..."):
            refresh_data_cache()
        st.success("✅ Cache cleared — the app will reload from the database on next access.")
        st.rerun()
    except Exception as e:
        st.error(f"❌ Failed to clear cache: {e}")
        st.code(traceback.format_exc())

if st.button("🗑️ Clear cache and reload data"):
    try:
        refresh_data_cache()
        keys_to_remove = [
            key for key in list(st.session_state.keys())
            if isinstance(key, str) and key.startswith("time_filter_msg_")
        ]
        for key in keys_to_remove:
            del st.session_state[key]
        st.success("Cache cleared. The app will reload data on next access.")
        st.rerun()
    except Exception:
        st.error("Could not clear cache.")
        st.code(traceback.format_exc())

st.markdown("---")

st.markdown("#### 🔧 Re-run Pipeline (Fresh CMS Data)")
st.markdown(
    "To rebuild the database from a new CMS provider export, run these two scripts "
    "in order from the project root. Both scripts are idempotent — re-running always "
    "produces a clean, consistent database."
)

st.code(
    """\
# Step 1 — Clean raw CMS data and write providers table
python prepare_contacts/2__clean_and_build_db.py

# Step 2 — Geocode unique addresses via Census API and update the database
python prepare_contacts/3__geocode_addresses.py
""",
    language="bash",
)

st.info(
    "**Step 2 uses a geocode cache** (`data/processed/geocode_cache.csv`) to avoid "
    "re-hitting the Census API for already-geocoded addresses. For ~2,000 addresses "
    "the first run takes about 1–2 minutes; subsequent runs are nearly instant for "
    "previously cached addresses."
)

with st.expander("📋 Database Schema"):
    st.markdown(
        """
**`providers`** — one row per provider record

| Column | Description |
|--------|-------------|
| `ind_pac_id` | CMS Individual PAC ID (primary key) |
| `last_name`, `first_name` | Provider name |
| `gender` | M / F |
| `credential` | Credential / degree |
| `pri_spec` | Primary specialty |
| `sec_spec_all` | Secondary specialties |
| `telehealth` | Telehealth indicator |
| `facility_name` | Facility / practice name |
| `telephone` | Provider phone number |
| `full_address` | Full address string |
| `address_id` | FK → `addresses.address_id` |

**`addresses`** — one row per unique address

| Column | Description |
|--------|-------------|
| `address_id` | Integer primary key |
| `full_address` | Full address string (unique) |
| `latitude`, `longitude` | Geocoded coordinates |
| `geocode_source` | `census` / `fallback_zip` / `failed` |
| `match_type` | Census match type (Exact / Non_Exact / Tie) |
| `geocoded_at` | Timestamp when geocoded |
"""
    )
