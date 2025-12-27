"""Self-contained Streamlit sub-page: Data Quality Dashboard.

This page uses the repository's centralized ingestion API (DataIngestionManager
via the compatibility `data_manager` and `DataSource` enums) instead of
direct helper functions. That follows project conventions:
`DataIngestionManager.load_data(DataSource.X)`.
"""

from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.data.ingestion import DataSource, data_manager
from src.utils.cleaning import validate_provider_data

# Centralized Plotly configuration used by Streamlit plotly charts in this page.
# Using a single variable instead of repeating inline config dicts improves
# maintainability and makes it easier to adjust display options in one place.
PLOTLY_CONFIG = {"displayModeBar": True}


def calculate_referral_counts(provider_df: pd.DataFrame, detailed_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate referral counts if missing from provider data."""
    if not detailed_df.empty and "Full Name" in detailed_df.columns:
        referral_counts = detailed_df.groupby("Full Name").size().reset_index(name="Referral Count")
        provider_df = provider_df.merge(referral_counts, on="Full Name", how="left")
        provider_df["Referral Count"] = provider_df["Referral Count"].fillna(0)
    else:
        provider_df["Referral Count"] = 0

    return provider_df


def display_data_quality_dashboard() -> None:
    """Render the dashboard in the multipage app using the ingestion manager.

    This function attempts to import Streamlit and render the interactive
    dashboard. If Streamlit is not available (for example the module is used
    in a non-UI context), it falls back to a minimal text summary so the file
    can safely replace the legacy `data_dashboard.py` shim.
    """

    # Try to import Streamlit lazily so this module can be imported in
    # non-Streamlit contexts (tests, CLI tools, or removal of the old shim).
    try:
        import streamlit as st  # type: ignore
    except Exception:
        # Non-Streamlit fallback: print a compact summary using the
        # centralized ingestion manager and return.
        try:
            provider_df = data_manager.load_data(DataSource.PROVIDER_DATA, show_status=False)
            detailed_df = data_manager.load_data(DataSource.OUTBOUND_REFERRALS, show_status=False)
        except Exception as e:
            summary = f"Failed to load data: {e}"
            print(summary)
            return

        total_providers = len(provider_df)
        total_referrals = len(detailed_df) if detailed_df is not None else "N/A"
        summary = f"Providers: {total_providers} | Referrals: {total_referrals}"
        print(summary)
        return

    # Streamlit is available; render the interactive dashboard.
    st.set_page_config(page_title="Data Quality Dashboard", page_icon="📊", layout="wide")
    # Import responsive columns for layout. Import inside function so non-Streamlit
    # imports (tests/CLI) remain lightweight.
    try:
        from src.utils.responsive import resp_columns
    except Exception:
        resp_columns = None
    st.title("📊 Data Quality Dashboard")
    st.markdown("Monitor provider data quality and system health.")

    # Load data via the centralized data manager
    try:
        provider_df = data_manager.load_data(DataSource.PROVIDER_DATA, show_status=False)
        detailed_df = data_manager.load_data(DataSource.OUTBOUND_REFERRALS, show_status=False)
    except Exception as e:
        st.error("❌ Failed to load data for the dashboard.")
        st.info("💡 Please ensure data files are available. Use the 'Update Data' page to refresh from S3.")
        st.info(f"Technical details: {str(e)}")
        return

    # Validate data is available
    if provider_df.empty:
        st.error("❌ No provider data available.")
        st.info("💡 Please upload data using the 'Update Data' page or contact support.")
        return

    # Add referral counts if missing
    if "Referral Count" not in provider_df.columns:
        st.info("📊 Calculating referral counts from detailed referral data...")
        provider_df = calculate_referral_counts(provider_df, detailed_df)

    # Overview metrics
    st.markdown("## 🎯 Overview Metrics")

    if resp_columns:
        col1, col2, col3, col4 = resp_columns([1, 1, 1, 1])
    else:
        col1, col2, col3, col4 = st.columns(4)

    with col1:
        total_providers = len(provider_df)
        st.metric("Total Providers", total_providers)

    with col2:
        if not detailed_df.empty:
            total_referrals = len(detailed_df)
            st.metric("Total Referrals", total_referrals)
        else:
            st.metric("Total Referrals", "N/A")

    with col3:
        if "Referral Count" in provider_df.columns:
            avg_referrals = provider_df["Referral Count"].mean()
            st.metric("Avg Referrals/Provider", f"{avg_referrals:.1f}")
        else:
            st.metric("Avg Referrals/Provider", "N/A")

    with col4:
        if not detailed_df.empty and "Referral Date" in detailed_df.columns:
            latest_referral = detailed_df["Referral Date"].max()
            days_since = (datetime.now() - latest_referral).days
            st.metric("Days Since Last Referral", days_since)
        else:
            st.metric("Days Since Last Referral", "N/A")

    # Data Quality Assessment
    st.markdown("## ✅ Data Quality Assessment")

    data_valid, data_message = validate_provider_data(provider_df)

    if data_valid:
        st.success("✅ **Data Quality: GOOD**")
    else:
        st.warning("⚠️ **Data Quality: NEEDS ATTENTION**")

    st.markdown(data_message)

    # Data Source and Processing Status
    st.markdown("## 📋 Data Source and Processing Status")

    # Show information about data sources and cleaning status
    try:
        # Try to load raw data to compare with cleaned data
        from pathlib import Path

        processed_dir = Path("data/processed")

        # Check for parquet files and their metadata
        parquet_files = {
            "Cleaned Referrals": processed_dir / "cleaned_all_referrals.parquet",
            "Cleaned Providers": processed_dir / "cleaned_outbound_referrals.parquet",
            "Preferred Providers": processed_dir / "cleaned_preferred_providers.parquet",
        }

        file_info = []
        for name, path in parquet_files.items():
            if path.exists():
                import os

                size_mb = os.path.getsize(path) / (1024 * 1024)
                modified = datetime.fromtimestamp(os.path.getmtime(path))
                file_info.append(
                    {
                        "Dataset": name,
                        "Size (MB)": f"{size_mb:.2f}",
                        "Last Updated": modified.strftime("%Y-%m-%d %H:%M:%S"),
                        "Status": "✅ Available",
                    }
                )
            else:
                file_info.append({"Dataset": name, "Size (MB)": "N/A", "Last Updated": "N/A", "Status": "❌ Not Found"})

        if file_info:
            st.dataframe(pd.DataFrame(file_info), width="stretch", hide_index=True)

        # Show data quality comparison if we have both cleaned and provider data
        st.markdown("### Data Quality Metrics")

        quality_metrics = []

        # Provider data quality
        if not provider_df.empty:
            total_records = len(provider_df)

            # Check for missing coordinates
            if "Latitude" in provider_df.columns and "Longitude" in provider_df.columns:
                valid_coords = provider_df.dropna(subset=["Latitude", "Longitude"])
                coord_completeness = (len(valid_coords) / total_records * 100) if total_records > 0 else 0
                quality_metrics.append(
                    {
                        "Metric": "Geographic Coordinates",
                        "Complete Records": len(valid_coords),
                        "Total Records": total_records,
                        "Completeness": f"{coord_completeness:.1f}%",
                    }
                )

            # Check for phone numbers
            if "Phone Number" in provider_df.columns:
                valid_phones = provider_df[provider_df["Phone Number"].notna() & (provider_df["Phone Number"] != "")]
                phone_completeness = (len(valid_phones) / total_records * 100) if total_records > 0 else 0
                quality_metrics.append(
                    {
                        "Metric": "Phone Numbers",
                        "Complete Records": len(valid_phones),
                        "Total Records": total_records,
                        "Completeness": f"{phone_completeness:.1f}%",
                    }
                )

            # Check for addresses
            if "Full Address" in provider_df.columns:
                valid_addresses = provider_df[provider_df["Full Address"].notna() & (provider_df["Full Address"] != "")]
                address_completeness = (len(valid_addresses) / total_records * 100) if total_records > 0 else 0
                quality_metrics.append(
                    {
                        "Metric": "Addresses",
                        "Complete Records": len(valid_addresses),
                        "Total Records": total_records,
                        "Completeness": f"{address_completeness:.1f}%",
                    }
                )

            # Check for Last Verified Date
            if "Last Verified Date" in provider_df.columns:
                valid_verified = provider_df[provider_df["Last Verified Date"].notna()]
                verified_completeness = (len(valid_verified) / total_records * 100) if total_records > 0 else 0
                quality_metrics.append(
                    {
                        "Metric": "Last Verified Date",
                        "Complete Records": len(valid_verified),
                        "Total Records": total_records,
                        "Completeness": f"{verified_completeness:.1f}%",
                    }
                )

        if quality_metrics:
            st.dataframe(pd.DataFrame(quality_metrics), width="stretch", hide_index=True)

        # Data Freshness Analysis
        if "Last Verified Date" in provider_df.columns and not provider_df.empty:
            st.markdown("### 📅 Data Freshness Analysis")

            from src.utils.freshness import get_freshness_indicator, calculate_data_age_days

            # Calculate freshness statistics
            verified_df = provider_df[provider_df["Last Verified Date"].notna()].copy()

            if not verified_df.empty:
                verified_df["Age (Days)"] = verified_df["Last Verified Date"].apply(calculate_data_age_days)
                verified_df["Indicator"], verified_df["Status"] = zip(
                    *verified_df["Last Verified Date"].apply(get_freshness_indicator)
                )

                # Count by status
                status_counts = verified_df["Status"].value_counts()

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    fresh_count = status_counts.get("Fresh", 0)
                    st.metric("✅ Fresh", fresh_count, help="Verified within 90 days")
                with col2:
                    stale_count = status_counts.get("Stale", 0)
                    st.metric("⚠️ Stale", stale_count, help="Verified 90-180 days ago")
                with col3:
                    very_stale_count = status_counts.get("Very Stale", 0)
                    st.metric("❌ Very Stale", very_stale_count, help="Verified over 180 days ago")
                with col4:
                    unverified = len(provider_df) - len(verified_df)
                    st.metric("❓ Unverified", unverified, help="No verification date available")

                # Show recommendation if there are stale or very stale records
                total_stale = stale_count + very_stale_count
                if total_stale > 0:
                    st.warning(
                        f"⚠️ **{total_stale} provider(s) have stale verification data.** "
                        "Consider updating provider information to ensure accuracy."
                    )

        # Show S3 sync status if configured
        from src.utils.s3_client_optimized import S3DataClient

        s3_client = S3DataClient()
        if s3_client.is_configured():
            st.markdown("### 📥 S3 Sync Status")
            st.success("✅ AWS S3 is configured and available for data pulls")

            # Show latest S3 file info
            from src.utils.s3_client_optimized import list_s3_files

            referrals_files = list_s3_files("referrals")
            providers_files = list_s3_files("preferred_providers")

            col1, col2 = st.columns(2)
            with col1:
                if referrals_files:
                    latest_file, latest_date = referrals_files[0]
                    st.caption("**Latest Referrals in S3:**")
                    st.caption(f"📄 {latest_file}")
                    st.caption(f"🕐 {latest_date.strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    st.caption("No referrals files in S3")

            with col2:
                if providers_files:
                    latest_file, latest_date = providers_files[0]
                    st.caption("**Latest Providers in S3:**")
                    st.caption(f"📄 {latest_file}")
                    st.caption(f"🕐 {latest_date.strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    st.caption("No provider files in S3")
        else:
            st.info("ℹ️ AWS S3 is not configured. Using local data files only.")

    except Exception as e:
        st.warning(f"Could not load data source information: {e}")

    # Geographic Coverage
    st.markdown("## 🗺️ Geographic Coverage")

    if "Latitude" in provider_df.columns and "Longitude" in provider_df.columns:
        valid_coords = provider_df.dropna(subset=["Latitude", "Longitude"])

        if not valid_coords.empty:
            # Only include hover_data columns that actually exist to avoid plotly errors
            hover_cols = [c for c in ("City", "State", "Referral Count") if c in valid_coords.columns]
            # Always include Full Name as hover_name; hover_data may be empty
            fig = px.scatter_map(
                valid_coords,
                lat="Latitude",
                lon="Longitude",
                hover_name="Full Name",
                hover_data=hover_cols,
                color="Referral Count" if "Referral Count" in valid_coords.columns else None,
                size="Referral Count" if "Referral Count" in valid_coords.columns else None,
                color_continuous_scale="Viridis",
                map_style="open-street-map",
                title="Provider Geographic Distribution",
                height=500,
            )
            fig.update_layout(mapbox=dict(center=dict(lat=39.2904, lon=-76.6122), zoom=8))
            st.plotly_chart(fig, config=PLOTLY_CONFIG)

            if resp_columns:
                col1, col2 = resp_columns([1, 1])
            else:
                col1, col2 = st.columns(2)
            with col1:
                st.markdown("### Coverage Statistics")
                if "State" in provider_df.columns:
                    state_counts = provider_df["State"].value_counts()
                    st.write("**Providers by State:**")
                    for state, count in state_counts.items():
                        st.write(f"- {state}: {count} providers")

            with col2:
                st.markdown("### Coordinate Quality")
                total_providers = len(provider_df)
                valid_coords_count = len(valid_coords)
                missing_coords = total_providers - valid_coords_count

                coord_quality_fig = go.Figure(
                    data=[
                        go.Pie(
                            labels=["Valid Coordinates", "Missing Coordinates"],
                            values=[valid_coords_count, missing_coords],
                            hole=0.4,
                        )
                    ]
                )
                coord_quality_fig.update_layout(title="Coordinate Completeness")
                st.plotly_chart(coord_quality_fig, use_container_width=True, config=PLOTLY_CONFIG)
        else:
            st.warning("No valid coordinates found in provider data.")

    # Referral Distribution Analysis
    st.markdown("## 📈 Referral Distribution Analysis")

    if "Referral Count" in provider_df.columns:
        if resp_columns:
            col1, col2 = resp_columns([1, 1])
        else:
            col1, col2 = st.columns(2)

        with col1:
            fig = px.histogram(
                provider_df,
                x="Referral Count",
                nbins=20,
                title="Distribution of Referral Counts",
                labels={"count": "Number of Providers", "Referral Count": "Referral Count"},
            )
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

        with col2:
            top_providers = provider_df.nlargest(10, "Referral Count")[["Full Name", "Referral Count"]]
            fig = px.bar(
                top_providers,
                x="Referral Count",
                y="Full Name",
                orientation="h",
                title="Top 10 Providers by Referral Count",
            )
            fig.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

    # Time-based Analysis
    if not detailed_df.empty and "Referral Date" in detailed_df.columns:
        st.markdown("## ⏰ Referral Trends Over Time")

        detailed_df["Referral Date"] = pd.to_datetime(detailed_df["Referral Date"])
        detailed_df["Month"] = detailed_df["Referral Date"].dt.to_period("M")

        monthly_referrals = detailed_df.groupby("Month").size().reset_index(name="Referral Count")
        monthly_referrals["Month"] = monthly_referrals["Month"].astype(str)

        if len(monthly_referrals) > 1:
            fig = px.line(
                monthly_referrals, x="Month", y="Referral Count", title="Monthly Referral Trends", markers=True
            )
            fig.update_xaxes(tickangle=45)
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

        st.markdown("### Recent Activity")
        recent_cutoff = datetime.now() - timedelta(days=30)
        recent_referrals = detailed_df[detailed_df["Referral Date"] >= recent_cutoff]

        if resp_columns:
            col1, col2 = resp_columns([1, 1])
        else:
            col1, col2 = st.columns(2)
        with col1:
            st.metric("Referrals (Last 30 Days)", len(recent_referrals))

        with col2:
            if len(recent_referrals) > 0:
                unique_providers = recent_referrals["Full Name"].nunique()
                st.metric("Active Providers (Last 30 Days)", unique_providers)

    # Data Issues and Recommendations
    st.markdown("## 🔧 Data Issues and Recommendations")

    issues = []
    recommendations = []

    if "Latitude" in provider_df.columns and "Longitude" in provider_df.columns:
        missing_coords = provider_df[provider_df["Latitude"].isna() | provider_df["Longitude"].isna()]
        if not missing_coords.empty:
            issues.append(f"{len(missing_coords)} providers missing geographic coordinates")
            recommendations.append("Update provider geocoding to ensure all providers have valid coordinates")

    if "Referral Count" in provider_df.columns:
        zero_referrals = provider_df[provider_df["Referral Count"] == 0]
        if not zero_referrals.empty:
            issues.append(f"{len(zero_referrals)} providers have zero referrals")
            recommendations.append("Review providers with zero referrals - consider removing inactive providers")

    if "Phone Number" in provider_df.columns:
        missing_phone = provider_df[provider_df["Phone Number"].isna() | (provider_df["Phone Number"] == "")]
        if not missing_phone.empty:
            issues.append(f"{len(missing_phone)} providers missing phone numbers")
            recommendations.append("Update provider contact information to ensure completeness")

    if not detailed_df.empty and "Referral Date" in detailed_df.columns:
        latest_referral = detailed_df["Referral Date"].max()
        days_since = (datetime.now() - latest_referral).days
        if days_since > 7:
            issues.append(f"No referrals recorded in the last {days_since} days")
            recommendations.append("Verify data pipeline is updating regularly")

    if issues:
        st.warning("**Issues Found:**")
        for issue in issues:
            st.write(f"- {issue}")

        st.info("**Recommendations:**")
        for rec in recommendations:
            st.write(f"- {rec}")
    else:
        st.success("No major data quality issues detected!")

    with st.expander("🔍 Raw Data Preview", expanded=False):
        st.markdown("### Provider Data Sample")
        if not provider_df.empty:
            preview_df = provider_df.head(10).copy()
            # Format boolean Preferred Provider column for better display
            if "Preferred Provider" in preview_df.columns:
                preview_df["Preferred Provider"] = preview_df["Preferred Provider"].map({True: "Yes", False: "No"})
            st.dataframe(preview_df)

        if not detailed_df.empty:
            st.markdown("### Detailed Referrals Sample")
            st.dataframe(detailed_df.head(10))


# Render the page when Streamlit imports it
display_data_quality_dashboard()
