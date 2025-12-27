import traceback

import streamlit as st

from src.data import process_referral_data, process_preferred_providers, refresh_data_cache
from src.data.ingestion import DataIngestionManager, DataSource
from src.utils.s3_client_optimized import (
    S3DataClient,
    get_s3_files_optimized,
)

# The optimized client is now the default
OPTIMIZED_S3_AVAILABLE = True

st.set_page_config(page_title="Update Data", page_icon="🗂️", layout="wide")

st.markdown("### 🔄 Update Referral Data")

st.markdown(
    """
**High-Level Overview for Non-Technical Users**

This page shows a summary of your current referral data and provides tools to update it from the S3 bucket.

Data is downloaded from S3, processed, and cached for optimal performance.

"""
)

st.markdown("#### 📊 Current Data Overview")


@st.cache_data
def get_data_summary():
    dim = DataIngestionManager()
    try:
        referrals_df = dim.load_data(DataSource.ALL_REFERRALS)
        providers_df = dim.load_data(DataSource.PREFERRED_PROVIDERS)
        return len(referrals_df), len(providers_df)
    except Exception:
        return None, None


referrals_count, providers_count = get_data_summary()

if referrals_count is not None and providers_count is not None:
    col1, col2 = st.columns(2)
    with col1:
        st.metric("📄 Total Referrals", f"{referrals_count:,}")
    with col2:
        st.metric("👥 Preferred Providers", f"{providers_count:,}")
else:
    st.info("Data not yet loaded or S3 not configured.")

st.markdown("---")

st.markdown("**Technical Details**")

# Check S3 configuration
s3_client = S3DataClient()
s3_enabled = s3_client.is_configured()

# default effective folder map (may be overridden by session state when s3 is enabled)
effective_folder_map = None

if s3_enabled:
    # Validate S3 configuration and display issues if present
    issues = s3_client.validate_configuration()
    if issues:
        # Allow the user to dismiss the warning for the session
        dismissed = st.session_state.get("dismiss_s3_issues", False)

        if not dismissed:
            # Prominent error box with an expander for details and remediation
            with st.container():
                st.error("⚠️ AWS S3 configuration issues detected — some S3 features may not work.")
                with st.expander("View configuration issues and remediation (click to expand)", expanded=True):
                    for k, msg in issues.items():
                        st.write(f"- **{k}**: {msg}")

                    st.markdown("For full setup instructions, see the [API Secrets Guide](docs/API_SECRETS_GUIDE.md).")

                    # Show the resolved S3 config (with secrets masked) to help debugging
                    try:
                        cfg = s3_client.config if hasattr(s3_client, "config") else {}
                        masked = {}
                        for kk, vv in cfg.items() if isinstance(cfg, dict) else []:
                            if "key" in kk.lower() or "secret" in kk.lower():
                                masked[kk] = "****"
                            else:
                                masked[kk] = vv
                        st.write("**Resolved S3 configuration (masked)**")
                        st.json(masked)
                    except Exception:
                        # If anything goes wrong while inspecting config, skip silently
                        pass

                    # Dismiss button so power users can hide the notice after fixing
                    if st.button("Mark as fixed / Dismiss", key="dismiss_s3_issues_button"):
                        st.session_state["dismiss_s3_issues"] = True

                st.info("You can continue with manual uploads or fix the secrets to enable S3 features.")
        else:
            # Provide a small persistent hint and a way to re-show the notice
            cols = st.columns([0.95, 0.05])
            cols[0].warning(
                "⚠️ AWS S3 configuration issues were detected (dismissed). Fix secrets to enable S3 features."
            )
            if cols[1].button("Show", key="show_s3_issues"):
                st.session_state["dismiss_s3_issues"] = False
    else:
        st.success("✅ AWS S3 is configured. You can pull data from S3 or upload files manually.")
    # Allow advanced users to override the S3 folder mapping
    # Persist overrides in session_state so they survive reruns
    effective_folder_map = st.session_state.get("s3_folder_map", None)

    with st.expander("S3 Folder Overrides (advanced)", expanded=False):
        with st.form("s3_folder_form"):
            # defaults come from the currently-initialized client (which reads config)
            ref_default = getattr(s3_client, "folder_map", {}).get("referrals_folder", "")
            prov_default = getattr(s3_client, "folder_map", {}).get("preferred_providers_folder", "")

            referrals_in = st.text_input(
                "Referrals folder/prefix",
                value=ref_default,
                help="Prefix for referrals data (e.g. 990046944 or referrals/)",
            )
            providers_in = st.text_input(
                "Preferred providers folder/prefix",
                value=prov_default,
                help="Prefix for preferred providers data (e.g. 990047553 or preferred_providers/)",
            )

            submitted = st.form_submit_button("Apply folder overrides")
            if submitted:
                # normalize empty strings to None to fall back to defaults/config
                fm = {
                    "referrals_folder": referrals_in.strip() if referrals_in and referrals_in.strip() else "",
                    "preferred_providers_folder": providers_in.strip() if providers_in and providers_in.strip() else "",
                }
                st.session_state["s3_folder_map"] = fm
                effective_folder_map = fm
                st.success("Folder overrides applied — these will be used for subsequent S3 operations on this page")

        # Option to clear overrides
        if st.button("Clear folder overrides"):
            if "s3_folder_map" in st.session_state:
                del st.session_state["s3_folder_map"]
            effective_folder_map = None
            st.info("Folder overrides cleared — defaults/config will be used")
else:
    st.warning(
        "⚠️ AWS S3 is not configured. Configure S3 credentials in secrets to enable data updates from the bucket."
    )

    # S3 Data Management Section
if s3_enabled:
    st.markdown("#### 📥 S3 Data Management")
    performance_note = "⚡ Optimized performance mode" if OPTIMIZED_S3_AVAILABLE else "Standard mode"
    st.markdown(f"Download and process the latest files from your S3 bucket. *{performance_note}*")
    st.markdown("Data is downloaded from S3, processed, and cached for fast access.")
    # Get file information for both types using optimized client
    try:
        # Use optimized batch file listing for better performance
        files_data = get_s3_files_optimized(
            ["referrals", "preferred_providers"], "s3_folder_map" if effective_folder_map else None
        )
        referrals_files = files_data.get("referrals", [])
        providers_files = files_data.get("preferred_providers", [])
    except Exception as e:
        st.error(f"Failed to list S3 files: {e}")
        referrals_files = []
        providers_files = []

    # Display file information
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**📄 Referrals Data**")
        if referrals_files:
            latest_referral_file, latest_referral_date = referrals_files[0]
            st.caption(f"📁 Latest: `{latest_referral_file}`")
            st.caption(f"📅 Modified: {latest_referral_date.strftime('%Y-%m-%d %H:%M:%S')}")
            st.caption(f"📊 Total files: {len(referrals_files)}")
        else:
            st.caption("❌ No files found")

    with col2:
        st.markdown("**👥 Preferred Providers**")
        if providers_files:
            latest_provider_file, latest_provider_date = providers_files[0]
            st.caption(f"📁 Latest: `{latest_provider_file}`")
            st.caption(f"📅 Modified: {latest_provider_date.strftime('%Y-%m-%d %H:%M:%S')}")
            st.caption(f"📊 Total files: {len(providers_files)}")
        else:
            st.caption("❌ No files found")

    st.markdown("---")

    # Action buttons in a clean layout
    col1, col2, col3 = st.columns([2.5, 1.5, 1.5])

    with col1:
        # Primary action: Refresh both files
        if st.button(
            "🔄 **Refresh Both Files**",
            key="s3_refresh_both",
            type="primary",
            width="stretch",
            help="Download and process the latest referrals and providers files",
        ):
            if not referrals_files and not providers_files:
                st.error("❌ No files found in S3 to refresh.")
            else:
                try:
                    with st.spinner("🔄 Refreshing data from S3..."):
                        # Clear cache to force fresh downloads
                        refresh_data_cache()

                        # Use DataIngestionManager to load fresh data
                        dim = DataIngestionManager()
                        processed_files = []

                        referrals_df = None
                        inbound_df = None
                        outbound_df = None
                        providers_df = None

                        # Load referrals data
                        if referrals_files:
                            referrals_df = dim.load_data(DataSource.ALL_REFERRALS, show_status=False)
                            inbound_df = dim.load_data(DataSource.INBOUND_REFERRALS, show_status=False)
                            outbound_df = dim.load_data(DataSource.OUTBOUND_REFERRALS, show_status=False)
                            processed_files.append("referrals")

                        # Load providers data
                        if providers_files:
                            providers_df = dim.load_data(DataSource.PREFERRED_PROVIDERS, show_status=False)
                            processed_files.append("providers")

                    # Show results
                    if processed_files:
                        st.success(f"✅ Successfully updated: {', '.join(processed_files)}")

                        # Compact metrics display
                        if (referrals_df is not None and providers_df is not None and
                                not referrals_df.empty and not providers_df.empty):
                            metrics_col1, metrics_col2 = st.columns(2)
                            with metrics_col1:
                                inbound_count = len(inbound_df) if inbound_df is not None else 0
                                outbound_count = len(outbound_df) if outbound_df is not None else 0
                                st.metric(
                                    "📄 Referrals",
                                    f"{len(referrals_df):,}",
                                    delta=f"In: {inbound_count:,}, Out: {outbound_count:,}",
                                )
                            with metrics_col2:
                                st.metric(
                                    "👥 Providers",
                                    f"{len(providers_df):,}",
                                )
                        elif referrals_df is not None and not referrals_df.empty:
                            st.metric("📄 Referrals Processed", f"{len(referrals_df):,}")
                        elif providers_df is not None and not providers_df.empty:
                            st.metric("👥 Providers Processed", f"{len(providers_df):,}")
                    else:
                        st.warning("⚠️ No files were successfully processed.")

                except Exception as e:
                    st.error(f"❌ Failed to refresh S3 data: {e}")
                    st.code(traceback.format_exc())

    with col2:
        # Referrals only
        if st.button("📄 Referrals Only", key="s3_referrals_only", disabled=not referrals_files, width="stretch"):
            if referrals_files:
                try:
                    with st.spinner("Processing referrals..."):
                        s3_client = S3DataClient(folder_map=effective_folder_map)
                        file_bytes = s3_client.download_file("referrals", referrals_files[0][0])
                        if file_bytes:
                            inbound_df, outbound_df, combined_df, summary = process_referral_data(
                                file_bytes, filename=referrals_files[0][0]
                            )
                            refresh_data_cache()
                            st.success(f"✅ Referrals: {summary.all_count:,} records")
                        else:
                            st.error("❌ Failed to download file")
                except Exception as e:
                    st.error(f"❌ Failed: {e}")

    with col3:
        # Providers only
        if st.button("👥 Providers Only", key="s3_providers_only", disabled=not providers_files, width="stretch"):
            if providers_files:
                try:
                    with st.spinner("Processing providers..."):
                        s3_client = S3DataClient(folder_map=effective_folder_map)
                        file_bytes = s3_client.download_file("preferred_providers", providers_files[0][0])
                        if file_bytes:
                            df_cleaned, summary = process_preferred_providers(
                                file_bytes, filename=providers_files[0][0]
                            )
                            refresh_data_cache()
                            st.success(f"✅ Providers: {summary.cleaned_count:,} records")
                        else:
                            st.error("❌ Failed to download file")
                except Exception as e:
                    st.error(f"❌ Failed: {e}")

    # Collapsible test connection section
    with st.expander("🧪 Test S3 Connection", expanded=False):
        if st.button("Test Connection", key="test_s3_connection", width="stretch"):
            try:
                with st.spinner("Testing S3 connection..."):
                    if referrals_files or providers_files:
                        st.success("✅ S3 connection successful!")
                        if referrals_files:
                            st.info(f"📄 Found {len(referrals_files)} referral file(s)")
                            if len(referrals_files) <= 5:
                                for filename, modified in referrals_files:
                                    st.caption(f"  • {filename} ({modified.strftime('%Y-%m-%d %H:%M')})")
                        if providers_files:
                            st.info(f"👥 Found {len(providers_files)} provider file(s)")
                            if len(providers_files) <= 5:
                                for filename, modified in providers_files:
                                    st.caption(f"  • {filename} ({modified.strftime('%Y-%m-%d %H:%M')})")
                    else:
                        st.warning("⚠️ S3 connection works, but no files found in configured folders")
            except Exception as e:
                st.error(f"❌ S3 connection test failed: {e}")

st.markdown("---")

st.markdown("#### Clear Cached Data")
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

# st.markdown("---")
# st.markdown(
#     "Need analytics? Launch the separate dashboard with: `streamlit run data_dashboard.py`"
# )
