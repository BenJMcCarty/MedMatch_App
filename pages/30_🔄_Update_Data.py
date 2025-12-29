import traceback
from pathlib import Path

import streamlit as st

from src.data.ingestion import DataIngestionManager, DataSource, refresh_data_cache

st.set_page_config(page_title="Update Data", page_icon="🗂️", layout="wide")

st.markdown("### 🔄 Data Status and Cache Management")

st.markdown(
    """
**High-Level Overview for Non-Technical Users**

This page shows a summary of your current referral data loaded from local parquet files
and provides tools to refresh the cached data.

Data is loaded from local parquet files and cached for optimal performance.

"""
)

st.markdown("#### 📊 Current Data Overview")


@st.cache_data
def get_data_summary():
    dim = DataIngestionManager()
    try:
        referrals_df = dim.load_data(DataSource.ALL_REFERRALS, show_status=False)
        providers_df = dim.load_data(DataSource.PREFERRED_PROVIDERS, show_status=False)
        inbound_df = dim.load_data(DataSource.INBOUND_REFERRALS, show_status=False)
        outbound_df = dim.load_data(DataSource.OUTBOUND_REFERRALS, show_status=False)
        return len(referrals_df), len(providers_df), len(inbound_df), len(outbound_df)
    except Exception:
        return None, None, None, None


referrals_count, providers_count, inbound_count, outbound_count = get_data_summary()

if referrals_count is not None and providers_count is not None:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📄 Total Referrals", f"{referrals_count:,}")
    with col2:
        st.metric("📥 Inbound", f"{inbound_count:,}")
    with col3:
        st.metric("📤 Outbound", f"{outbound_count:,}")
    with col4:
        st.metric("👥 Preferred Providers", f"{providers_count:,}")
else:
    st.info("Data not yet loaded from local parquet files.")

st.markdown("---")

st.markdown("#### 📁 Local Data File")

# Check for parquet file status
dim = DataIngestionManager()
data_dir = Path("data/processed")
combined_file = data_dir / "Combined_Contacts_and_Reviews.parquet"

if combined_file.exists():
    file_size = combined_file.stat().st_size / (1024 * 1024)  # Convert to MB
    last_modified = combined_file.stat().st_mtime
    import datetime
    mod_time = datetime.datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')
    
    st.success(f"✅ Data file found: `Combined_Contacts_and_Reviews.parquet`")
    col1, col2 = st.columns(2)
    with col1:
        st.caption(f"📊 File size: {file_size:.2f} MB")
    with col2:
        st.caption(f"📅 Last modified: {mod_time}")
else:
    st.error(f"❌ Data file not found: `Combined_Contacts_and_Reviews.parquet`")
    st.info("Please ensure the file exists in `data/processed/` directory.")

st.markdown("---")

st.markdown("#### 🔄 Reload Data from Files")
st.markdown("Click the button below to clear the cache and reload data from local parquet files.")

if st.button("🔄 **Reload Data**", key="reload_data", type="primary", help="Clear cache and reload data from local parquet files"):
    try:
        with st.spinner("🔄 Reloading data from parquet files..."):
            # Clear cache to force fresh data loading
            refresh_data_cache()

            # Use DataIngestionManager to load fresh data
            dim = DataIngestionManager()

            referrals_df = dim.load_data(DataSource.ALL_REFERRALS, show_status=False)
            inbound_df = dim.load_data(DataSource.INBOUND_REFERRALS, show_status=False)
            outbound_df = dim.load_data(DataSource.OUTBOUND_REFERRALS, show_status=False)
            providers_df = dim.load_data(DataSource.PREFERRED_PROVIDERS, show_status=False)

        # Show results
        st.success("✅ Successfully reloaded data from local parquet files")

        # Compact metrics display
        if not referrals_df.empty and not providers_df.empty:
            metrics_col1, metrics_col2, metrics_col3 = st.columns(3)
            with metrics_col1:
                st.metric(
                    "📄 Referrals",
                    f"{len(referrals_df):,}",
                    delta=f"In: {len(inbound_df):,}, Out: {len(outbound_df):,}",
                )
            with metrics_col2:
                st.metric(
                    "👥 Providers",
                    f"{len(providers_df):,}",
                )
            with metrics_col3:
                st.metric(
                    "📊 Total Records",
                    f"{len(referrals_df) + len(providers_df):,}",
                )
        elif not referrals_df.empty:
            st.metric("📄 Referrals Loaded", f"{len(referrals_df):,}")
        elif not providers_df.empty:
            st.metric("👥 Providers Loaded", f"{len(providers_df):,}")
        else:
            st.warning("⚠️ No data was loaded. Please ensure parquet files exist in `data/processed/`.")

    except Exception as e:
        st.error(f"❌ Failed to reload data: {e}")
        st.code(traceback.format_exc())

st.markdown("---")

st.markdown("#### 🗑️ Clear Cached Data")
st.markdown("Clear the application cache to force reloading data from parquet files on next access.")

if st.button("🔄 Clear cache and reload data"):
    try:
        refresh_data_cache()
        # Clear any time filter info flags to avoid stale notices
        keys_to_remove = [
            key for key in list(st.session_state.keys()) if isinstance(key, str) and key.startswith("time_filter_msg_")
        ]
        for key in keys_to_remove:
            del st.session_state[key]
        st.success("Cache cleared. The app will reload data on next access.")
        st.rerun()
    except Exception:
        st.error("Could not clear cache.")
        st.code(traceback.format_exc())
