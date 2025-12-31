"""
Data Ingestion Module - Centralized data loading from local parquet files.

This module handles loading data from the Combined_Contacts_and_Reviews.parquet file
and caching with Streamlit's cache system. Data flows from the local parquet file
to processed DataFrames.

Key Features:
- Direct parquet file loading with efficient columnar format
- Streamlit cache integration with file-based invalidation
- Column mapping and transformation from raw to standardized schema
- Centralized error handling and validation
- Optimized for fast data access and processing

Data Source:
- Single source file: Combined_Contacts_and_Reviews.parquet
- Contains provider contact information, specialties, patient counts, and ratings
- Located in: data/processed/Combined_Contacts_and_Reviews.parquet

DESIGN NOTE: Data Caching Strategy
===================================

This module implements a multi-layer caching strategy to optimize data loading
performance while maintaining data freshness.

Caching Layers:
--------------
1. **Streamlit @st.cache_data decorator** (1-hour TTL)
   - Caches processed DataFrames in memory
   - Automatically invalidates on function signature or parameter changes
   - Time-to-live: 3600 seconds (1 hour)
   - Rationale: Balance between performance and data freshness

2. **File modification detection**
   - Tracks last modification time of source parquet files
   - Forces cache invalidation when source data changes
   - Implemented via file hash or mtime checks
   - Rationale: Ensures cache reflects latest data without manual intervention

3. **Daily scheduled refresh** (4 AM)
   - DataIngestionManager.check_and_refresh_daily_cache()
   - Clears all caches once per day at scheduled time
   - Triggered in app.py on startup
   - Rationale: Ensures stale data doesn't persist beyond 24 hours

Cache Invalidation Triggers:
----------------------------
- TTL expiration (1 hour)
- Source file modification
- Daily scheduled refresh (4 AM)
- Explicit cache clear via Streamlit's cache_data.clear()
- App restart

Performance Characteristics:
---------------------------
- First load: ~500ms-2s (depends on dataset size, typically ~10k rows)
- Cached load: <10ms (in-memory DataFrame access)
- Memory footprint: ~5-20MB per cached DataFrame
- Cache warming: Background thread on app startup (auto_update_data in app.py)

Trade-offs and Design Decisions:
--------------------------------
- **1-hour TTL**: Balances fresh data vs. performance. Shorter TTL increases load,
  longer TTL risks stale data during active data updates.
- **In-memory only**: No disk-based cache to avoid stale file artifacts and
  cross-session cache contamination.
- **Background warming**: Prevents first-user-load penalty but adds startup complexity.
- **File-based invalidation**: More complex than pure TTL but essential for data
  update workflows (e.g., 30_🔄_Update_Data.py page).

Integration Points:
------------------
- app.py: auto_update_data() warms cache on startup
- src/app_logic.py: load_application_data() is the primary cache consumer
- pages/30_🔄_Update_Data.py: Triggers cache clear after data updates

For more on the overall data flow architecture, see docs/ARCHITECTURE.md.
"""

import logging
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import pandas as pd
import streamlit as st

from src.data.io_utils import load_dataframe
from src.data.preparation import process_referral_data

logger = logging.getLogger(__name__)

# Flag to ensure preferred providers warnings are logged only once per app session
_preferred_providers_warning_logged = False


class DataSource(Enum):
    """Enumeration of available data sources with clear purpose definitions."""

    # Individual datasets split by referral direction
    INBOUND_REFERRALS = "inbound"  # Referrals TO the law firm
    OUTBOUND_REFERRALS = "outbound"  # Referrals FROM the law firm to providers

    # Combined datasets for comprehensive analysis
    ALL_REFERRALS = "all_referrals"  # Combined inbound + outbound referrals

    # Provider-specific data (aggregated from outbound referrals)
    PROVIDER_DATA = "provider"  # Unique providers with referral counts

    # Preferred providers contact list
    PREFERRED_PROVIDERS = "preferred_providers"  # Firm's preferred provider contacts


class DataFormat(Enum):
    """Enumeration of supported data formats with performance characteristics.

    The ingestion system uses parquet files for efficient data storage and loading.
    Parquet is the primary format for local data storage.
    """

    PARQUET = ".parquet"  # Primary format: Columnar, fast parsing, efficient storage
    CSV = ".csv"  # Legacy format: Supported for compatibility
    EXCEL = ".xlsx"  # Legacy format: Supported for compatibility


class DataIngestionManager:
    """
    Centralized data ingestion manager with optimized loading strategies.

    This manager handles the complete data pipeline from local parquet files to
    processed DataFrames, with intelligent caching using Streamlit's cache system.

    Key Features:
    - Direct parquet file loading for fast data access
    - Streamlit cache integration with file-based invalidation
    - Source-specific post-processing for provider aggregation
    - Built-in data validation and quality checks

    Supported Formats:
    - Parquet files (.parquet) - Primary format with columnar storage

    Usage:
        manager = DataIngestionManager()
        df = manager.load_data(DataSource.OUTBOUND_REFERRALS)
        # Automatically loads from local parquet files
    """

    def __init__(self):
        """
        Initialize the data ingestion manager.
        """
        self.cache_ttl = 3600  # 1 hour cache for optimal performance
        self.data_dir = Path("data/processed")  # Local data directory

    def _get_parquet_file_path(self, source: DataSource) -> Optional[Path]:
        """
        Get the parquet file path for a given data source.

        All data sources now use the same Combined_Contacts_and_Reviews.parquet file,
        with different processing applied based on the source type.

        Args:
            source: Data source type

        Returns:
            Path to the parquet file, or None if the file doesn't exist
        """
        # All sources use the same combined file
        parquet_filename = "Combined_Contacts_and_Reviews.parquet"
        parquet_path = self.data_dir / parquet_filename

        if not parquet_path.exists():
            logger.warning(f"Parquet file not found: {parquet_path}")
            return None

        logger.info(f"Found parquet file: {parquet_path}")
        return parquet_path

    @st.cache_data(ttl=3600, show_spinner=False)
    def _load_and_process_data_cached(
        _self, source: DataSource, file_path: str, last_modified: float
    ) -> pd.DataFrame:
        """
        Load and process data from parquet file with Streamlit caching.

        This method is cached based on source, file path, and last modified timestamp.
        The cache automatically invalidates when:
        - The parquet file is updated (detected via last_modified timestamp)
        - The TTL expires (1 hour)
        - Manual cache refresh is triggered

        Args:
            source: Data source to process
            file_path: Path to the parquet file
            last_modified: File modification timestamp for cache invalidation

        Returns:
            Processed DataFrame cached in Streamlit's st.cache_data
        """
        try:
            # Load parquet file
            df = pd.read_parquet(file_path)
            logger.info(f"Loaded {len(df)} records from {file_path}")

            # Transform the combined data to match the expected schema
            df = _self._transform_combined_data(df)

            # Apply source-specific processing
            if source == DataSource.PROVIDER_DATA:
                df = _self._process_provider_data(df)
            # For now, all sources get the same data (all providers)
            # In the future, you could filter by referral_type or other criteria

            return df

        except Exception as e:
            logger.error(f"Failed to load {source.value} from {file_path}: {str(e)}")
            return pd.DataFrame()

    def _transform_combined_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform the Combined_Contacts_and_Reviews data to match the expected schema.

        Maps raw columns to standardized column names used throughout the application.

        Args:
            df: Raw DataFrame from Combined_Contacts_and_Reviews.parquet

        Returns:
            Transformed DataFrame with standardized schema
        """
        df = df.copy()

        # Create Full Name from first and last name
        if 'Provider First Name' in df.columns and 'Provider Last Name' in df.columns:
            df['Full Name'] = (df['Provider First Name'].fillna('') + ' ' + 
                              df['Provider Last Name'].fillna('')).str.strip()
        
        # Map columns to expected schema
        column_mapping = {
            'Telephone Number': 'Work Phone',
            'Full Address': 'Work Address',
            'latitude': 'Latitude',
            'longitude': 'Longitude',
            'pri_spec': 'Specialty',
            'patient_count': 'Referral Count',
            'star_value': 'Rating',
            'gndr': 'Gender',
        }

        for old_col, new_col in column_mapping.items():
            if old_col in df.columns:
                df[new_col] = df[old_col]

        # Ensure Work Phone Number exists (used by other parts of the app)
        if 'Work Phone' in df.columns and 'Work Phone Number' not in df.columns:
            df['Work Phone Number'] = df['Work Phone']

        # Add referral_type for compatibility (all are treated as providers)
        df['referral_type'] = 'provider'

        # Convert numeric columns
        if 'Latitude' in df.columns:
            df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
        if 'Longitude' in df.columns:
            df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')
        if 'Referral Count' in df.columns:
            df['Referral Count'] = pd.to_numeric(df['Referral Count'], errors='coerce').fillna(0).astype(int)
        if 'Rating' in df.columns:
            df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce')

        logger.info(f"Transformed {len(df)} provider records to standard schema")
        return df

    def _load_and_process_data(self, source: DataSource) -> pd.DataFrame:
        """
        Load data from local parquet file and process it into a clean DataFrame.

        This method handles the complete pipeline from parquet file to processed DataFrame,
        cached in Streamlit's cache system.

        Args:
            source: Data source to load and process

        Returns:
            Processed DataFrame or empty DataFrame if processing fails
        """
        try:
            # Get parquet file path
            file_path = self._get_parquet_file_path(source)
            if not file_path:
                logger.error(f"No parquet file available for {source.value}")
                return pd.DataFrame()

            # Get file modification time for cache invalidation
            last_modified = file_path.stat().st_mtime

            # Use the cached processing method with file path and modification time as cache keys
            return self._load_and_process_data_cached(
                source, str(file_path), last_modified
            )

        except Exception as e:
            logger.error(f"Failed to load and process {source.value}: {str(e)}")
            return pd.DataFrame()

    def _post_process_data(self, df: pd.DataFrame, source: DataSource, file_type: str) -> pd.DataFrame:
        """
        Apply source-specific post-processing only when needed.

        Processing Strategy:
        - Skip post-processing for cleaned Parquet files (already processed)
        - Exception: PROVIDER_DATA always needs aggregation processing
        - Apply transformations only to raw Excel data that needs standardization
        - Ensure consistent column names and data types across all sources

        Args:
            df: Raw DataFrame to process
            source: Data source type for source-specific processing
            file_type: File type to determine if processing is needed

        Returns:
            Processed DataFrame with standardized schema
        """
        if df.empty:
            return df

        # Provider data always needs aggregation processing, even from cleaned data
        if source == DataSource.PROVIDER_DATA:
            return self._process_provider_data(df)

        # Skip post-processing if this is already cleaned data (except for provider data)
        if file_type == "cleaned" or self._is_cleaned_data(df):
            return df

        df = df.copy()

        # Apply source-specific transformations for raw data
        if source == DataSource.OUTBOUND_REFERRALS:
            df = self._process_outbound_referrals(df)
        elif source == DataSource.INBOUND_REFERRALS:
            df = self._process_inbound_referrals(df)
        elif source == DataSource.ALL_REFERRALS:
            df = self._process_all_referrals(df)

        return df

    def _is_cleaned_data(self, df: pd.DataFrame) -> bool:
        """
        Check if data appears to be from cleaned parquet files.

        Cleaned data characteristics:
        - Has standardized column names (Full Name, Work Address, etc.)
        - Contains referral_type column for type identification
        - Has proper data types and formatting
        """
        # Key indicators of cleaned data
        cleaned_indicators = {"Full Name", "Work Address", "Work Phone", "Latitude", "Longitude", "referral_type"}
        return len(cleaned_indicators.intersection(set(df.columns))) >= 4

    def _process_outbound_referrals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Process raw outbound referrals data from Excel source.

        Maps raw Excel columns to standardized schema and handles data cleaning.
        """
        # Standard column mapping for raw Excel data
        if "Referred To Full Name" in df.columns:
            column_mapping = {
                "Referred To Full Name": "Full Name",
                "Referred To's Work Phone": "Work Phone",
                "Referred To's Work Address": "Work Address",
                "Referred To's Details: Latitude": "Latitude",
                "Referred To's Details: Longitude": "Longitude",
                "Referred To's Details: Last Verified Date": "Last Verified Date",
            }

            for old_col, new_col in column_mapping.items():
                if old_col in df.columns:
                    df[new_col] = df[old_col]

        # Add referral type identifier
        df["referral_type"] = "outbound"

        # Standardize dates
        df = self._standardize_dates(df)
        return df

    def _process_inbound_referrals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Process raw inbound referrals data from Excel source.

        Maps referral source information to provider format.
        """
        # Map referral source columns for inbound data
        if "Referred From Full Name" in df.columns:
            column_mapping = {
                "Referred From Full Name": "Full Name",
                "Referred From's Work Phone": "Work Phone",
                "Referred From's Work Address": "Work Address",
                "Referred From's Details: Latitude": "Latitude",
                "Referred From's Details: Longitude": "Longitude",
                "Referred From's Details: Last Verified Date": "Last Verified Date",
            }

            for old_col, new_col in column_mapping.items():
                if old_col in df.columns:
                    df[new_col] = df[old_col]

        # Add referral type identifier
        df["referral_type"] = "inbound"

        # Standardize dates
        df = self._standardize_dates(df)
        return df

    def _process_all_referrals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Process combined referrals data from raw Excel source.

        This processes the full dataset and separates inbound/outbound referrals.
        """
        # For all referrals, we need to process both inbound and outbound in one pass
        processed_rows = []

        for _, row in df.iterrows():
            # Process outbound referral if present
            if pd.notna(row.get("Referred To Full Name")):
                outbound_row = row.copy()
                outbound_row["Full Name"] = row.get("Referred To Full Name")
                outbound_row["Work Phone"] = row.get("Referred To's Work Phone")
                outbound_row["Work Address"] = row.get("Referred To's Work Address")
                outbound_row["Latitude"] = row.get("Referred To's Details: Latitude")
                outbound_row["Longitude"] = row.get("Referred To's Details: Longitude")
                outbound_row["Last Verified Date"] = row.get("Referred To's Details: Last Verified Date")
                outbound_row["referral_type"] = "outbound"
                processed_rows.append(outbound_row)

            # Process inbound referral if present
            if pd.notna(row.get("Referred From Full Name")):
                inbound_row = row.copy()
                inbound_row["Full Name"] = row.get("Referred From Full Name")
                inbound_row["Work Phone"] = row.get("Referred From's Work Phone")
                inbound_row["Work Address"] = row.get("Referred From's Work Address")
                inbound_row["Latitude"] = row.get("Referred From's Details: Latitude")
                inbound_row["Longitude"] = row.get("Referred From's Details: Longitude")
                inbound_row["Last Verified Date"] = row.get("Referred From's Details: Last Verified Date")
                inbound_row["referral_type"] = "inbound"
                processed_rows.append(inbound_row)

        if processed_rows:
            df = pd.DataFrame(processed_rows)
            df = self._standardize_dates(df)

        return df

    def _process_provider_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Process provider data by ensuring proper formatting and deduplication.

        For the Combined_Contacts_and_Reviews data, each row already represents a unique provider
        with referral counts, so we just need to ensure proper formatting and handle duplicates.
        """
        if df.empty or "Full Name" not in df.columns:
            return df

        # If Referral Count already exists and each provider is unique, just clean and return
        if "Referral Count" in df.columns:
            # Remove duplicates if any (keep the one with highest referral count)
            if df["Full Name"].duplicated().any():
                df = df.sort_values("Referral Count", ascending=False).drop_duplicates(
                    subset="Full Name", keep="first"
                ).reset_index(drop=True)
                logger.info(f"Deduplicated providers: {len(df)} unique providers")

            # Clean up missing values in text columns
            text_cols = ["Work Address", "Work Phone", "Specialty"]
            for col in text_cols:
                if col in df.columns:
                    df[col] = df[col].astype(str).replace(["nan", "None", "NaN", ""], "").fillna("")

            # Ensure numeric columns are properly typed
            numeric_cols = ["Latitude", "Longitude", "Referral Count", "Rating"]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # Fill NaN referral counts with 0
            if "Referral Count" in df.columns:
                df["Referral Count"] = df["Referral Count"].fillna(0).astype(int)

            return df

        # Fallback: old aggregation logic for legacy data formats
        # This is kept for backward compatibility but won't be used with Combined_Contacts_and_Reviews
        agg_dict = {"Person ID": "count"} if "Person ID" in df.columns else {}

        # Add other columns that exist
        for col in ["Work Address", "Work Phone", "Latitude", "Longitude", "Specialty"]:
            if col in df.columns:
                agg_dict[col] = "first"  # Take first non-null value

        try:
            if agg_dict:
                provider_df = df.groupby("Full Name", as_index=False).agg(agg_dict)
                # Rename count column to Referral Count
                if "Person ID" in provider_df.columns:
                    provider_df = provider_df.rename(columns={"Person ID": "Referral Count"})
                else:
                    provider_df["Referral Count"] = 1
            else:
                provider_df = df.drop_duplicates(subset="Full Name", keep="first")
                provider_df["Referral Count"] = 1

            # Clean up missing values in text columns
            text_cols = ["Work Address", "Work Phone", "Specialty"]
            for col in text_cols:
                if col in provider_df.columns:
                    provider_df[col] = provider_df[col].astype(str).replace(["nan", "None", "NaN", ""], "").fillna("")

            # Ensure numeric columns are properly typed
            numeric_cols = ["Latitude", "Longitude", "Referral Count"]
            for col in numeric_cols:
                if col in provider_df.columns:
                    provider_df[col] = pd.to_numeric(provider_df[col], errors="coerce")

            return provider_df

        except Exception as e:
            logger.error(f"Error processing provider data: {e}")
            return df

    def _standardize_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize date columns across all datasets.

        Handles multiple date column names and creates a unified 'Referral Date' column.
        Validates dates to ensure they fall within reasonable ranges.
        """
        date_columns = ["Create Date", "Date of Intake", "Sign Up Date"]

        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
                # Filter out unrealistic dates (before 1990)
                df.loc[df[col] < pd.Timestamp("1990-01-01"), col] = pd.NaT

        # Standardize Last Verified Date
        if "Last Verified Date" in df.columns:
            df["Last Verified Date"] = pd.to_datetime(df["Last Verified Date"], errors="coerce")
            # Filter out unrealistic dates (before 1990)
            df.loc[df["Last Verified Date"] < pd.Timestamp("1990-01-01"), "Last Verified Date"] = pd.NaT

        # Create unified Referral Date column
        if "Referral Date" not in df.columns:
            # Use first available date column as Referral Date
            for col in date_columns:
                if col in df.columns:
                    df["Referral Date"] = df[col]
                    break

        return df

    def get_data_status(self) -> Dict[str, Dict[str, Union[bool, str]]]:
        """
        Get comprehensive status of all data sources.

        Returns information about file availability and data processing status
        for all configured data sources.

        Returns:
            Dictionary mapping source names to their status information
        """
        status = {}

        for source in DataSource:
            # Check if parquet file exists
            file_path = self._get_parquet_file_path(source)
            available = file_path is not None and file_path.exists()

            status[source.value] = {
                "available": available,
                "file_type": "parquet" if available else "none",
                "filename": file_path.name if available else None,
                "optimized": True,  # Parquet format is optimized
                "performance_tier": "fast",  # Direct parquet loading
            }

        return status

    def load_data(self, source: DataSource, show_status: bool = True) -> pd.DataFrame:
        """
        Public method to load data for a given DataSource.

        This method loads data directly from local parquet files, processes it,
        and caches the result in Streamlit's cache system using st.cache_data.

        File Format Support:
        - Parquet files (.parquet) - Columnar format for optimal performance

        Caching Behavior:
        - Cached with st.cache_data decorator (TTL: 1 hour)
        - Cache key includes: source, file path, last modified timestamp
        - Automatic cache invalidation when parquet file is updated
        - Manual refresh available via refresh_data_cache()

        Data must be available in local parquet files. If files are not found,
        clear error messages are provided.

        Args:
            source: DataSource enum value identifying which dataset to load
            show_status: If True, logs or displays the data source selection

        Returns:
            pd.DataFrame with the requested data cached in st.cache_data (may be empty on failure)
        """
        if show_status:
            logger.debug(f"Loading data for {source.value} from local parquet files")

        # Load data from parquet file
        df = self._load_and_process_data(source)

        # Apply any additional post-processing if needed
        if source == DataSource.PROVIDER_DATA and not df.empty:
            # Ensure provider aggregation is applied
            df = self._process_provider_data(df)

        if df.empty and show_status:
            st.error(
                f"❌ No data available for {source.value}. "
                f"Parquet file not found in `{self.data_dir}/`."
            )

        return df

    def validate_data_integrity(self, source: DataSource) -> Dict[str, Union[bool, str, int, float, list]]:
        """
        Validate data integrity for a specific source.

        Performs basic data quality checks including:
        - Row count validation
        - Required column presence
        - Data type validation
        - Missing value analysis

        Args:
            source: Data source to validate

        Returns:
            Dictionary with validation results
        """
        df = self.load_data(source, show_status=False)

        if df.empty:
            return {
                "valid": False,
                "error": "No data loaded",
                "row_count": 0,
                "column_count": 0,
            }

        # Define required columns based on data source
        if source == DataSource.PROVIDER_DATA:
            required_cols = ["Full Name", "Referral Count"]
        else:
            required_cols = ["Full Name", "Project ID"]

        missing_cols = [col for col in required_cols if col not in df.columns]

        # Coordinate validation for provider data
        coord_issues = 0
        if "Latitude" in df.columns and "Longitude" in df.columns:
            invalid_coords = (
                pd.notna(df["Latitude"])
                & pd.notna(df["Longitude"])
                & ((df["Latitude"] < -90) | (df["Latitude"] > 90) | (df["Longitude"] < -180) | (df["Longitude"] > 180))
            )
            coord_issues = invalid_coords.sum()

        return {
            "valid": len(missing_cols) == 0,
            "row_count": len(df),
            "column_count": len(df.columns),
            "missing_required_columns": missing_cols,
            "duplicate_names": df["Full Name"].duplicated().sum() if "Full Name" in df.columns else 0,
            "invalid_coordinates": coord_issues,
            "missing_values_pct": (
                round((df.isnull().sum().sum() / (len(df) * len(df.columns)) * 100), 2) if not df.empty else 0
            ),
        }

    def preload_data(self) -> None:
        """
        Preload all critical data sources into Streamlit cache on app startup.

        This method loads the most commonly used data sources (referrals and providers)
        from local parquet files to ensure they're cached in st.cache_data and
        ready for immediate use when the app starts.

        Cache Warming Benefits:
        - Reduces first-page-load latency
        - Loads parquet files once
        - Stores in Streamlit cache for fast subsequent access
        """
        logger.info("Preloading data from local parquet files into Streamlit cache...")

        # Load the most critical data sources that are used across the app
        critical_sources = [
            DataSource.ALL_REFERRALS,
            DataSource.PREFERRED_PROVIDERS,
            DataSource.PROVIDER_DATA,
        ]

        loaded_sources = []
        for source in critical_sources:
            try:
                df = self.load_data(source, show_status=False)
                if not df.empty:
                    loaded_sources.append(source.value)
                    logger.info(f"Preloaded {source.value}: {len(df)} records")
                else:
                    logger.warning(f"Failed to preload {source.value}: empty dataset")
            except Exception as e:
                logger.error(f"Failed to preload {source.value}: {e}")

        if loaded_sources:
            logger.info(f"Successfully preloaded data sources: {', '.join(loaded_sources)}")
        else:
            logger.warning("No data sources were successfully preloaded")

    def check_and_refresh_daily_cache(self) -> bool:
        """
        Check if it's time for daily cache refresh (4 AM) and refresh if needed.

        This method checks the current time and compares it to the last refresh time.
        If it's after 4 AM and we haven't refreshed today, it clears the cache
        to force fresh data loading from local parquet files.

        Returns:
            True if cache was refreshed, False otherwise
        """
        from datetime import datetime, time

        # Get current time
        now = datetime.now()
        current_time = now.time()
        today = now.date()

        # Check if it's after 4 AM
        refresh_time = time(4, 0, 0)  # 4:00 AM
        is_after_refresh_time = current_time >= refresh_time

        # Get the last refresh date from session state or cache
        last_refresh_key = "last_daily_refresh_date"
        last_refresh_date = st.session_state.get(last_refresh_key)

        # If no last refresh date or it's a different day and after 4 AM, refresh
        should_refresh = (last_refresh_date is None or last_refresh_date != today) and is_after_refresh_time

        if should_refresh:
            logger.info(f"Performing daily cache refresh at {now.strftime('%Y-%m-%d %H:%M:%S')}")
            try:
                # Clear the cache to force fresh downloads
                refresh_data_cache()

                # Update the last refresh date
                st.session_state[last_refresh_key] = today

                # Preload data again after cache clear
                self.preload_data()

                logger.info("Daily cache refresh completed successfully")
                return True
            except Exception as e:
                logger.error(f"Failed to perform daily cache refresh: {e}")
                return False
        else:
            logger.debug("Daily cache refresh not needed at this time")
            return False


# ============================================================================
# Global Instance and Compatibility Functions
# ============================================================================

# Lazy-initialized global instance for use throughout the application
_data_manager: Optional[DataIngestionManager] = None


def get_data_manager() -> DataIngestionManager:
    """
    Return a singleton DataIngestionManager, creating it on first use.

    This laziness avoids import-time side-effects and makes module
    imports safer for long-running processes (like Streamlit) that
    may reload modules during development.
    """
    global _data_manager
    if _data_manager is None:
        _data_manager = DataIngestionManager()
    return _data_manager


# Backwards-compatible module-level symbol for older imports. This proxy
# delegates attribute access to the lazily-created DataIngestionManager
# instance so 'from src.data.ingestion import data_manager' continues to work
# without reintroducing eager instantiation side-effects.
class _DataManagerProxy:
    def __getattr__(self, name: str):
        manager = get_data_manager()
        return getattr(manager, name)


# Exported symbol (keeps older import paths working)
data_manager = _DataManagerProxy()


# ============================================================================
# Backward Compatibility Functions
#
# These functions maintain compatibility with existing code while providing
# the benefits of the new optimized ingestion system.
# ============================================================================


@st.cache_data(ttl=3600, show_spinner=False)
def load_detailed_referrals(filepath: Optional[str] = None) -> pd.DataFrame:
    """
    Load detailed referral data (outbound referrals) from local parquet files into Streamlit cache.

    Loads from local parquet file, processes it, and caches
    the result in st.cache_data for fast subsequent access.

    Maintained for backward compatibility. New code should use:
    data_manager.load_data(DataSource.OUTBOUND_REFERRALS)

    Args:
        filepath: Ignored - automatic file selection from local parquet is used

    Returns:
        DataFrame with outbound referral data cached in st.cache_data
    """
    return get_data_manager().load_data(DataSource.OUTBOUND_REFERRALS, show_status=False)


@st.cache_data(ttl=3600, show_spinner=False)
def load_inbound_referrals(filepath: Optional[str] = None) -> pd.DataFrame:
    """
    Load inbound referral data from local parquet files into Streamlit cache.

    Loads from local parquet file, processes it, and caches
    the result in st.cache_data for fast subsequent access.

    Maintained for backward compatibility. New code should use:
    data_manager.load_data(DataSource.INBOUND_REFERRALS)

    Args:
        filepath: Ignored - automatic file selection from local parquet is used

    Returns:
        DataFrame with inbound referral data cached in st.cache_data
    """
    return get_data_manager().load_data(DataSource.INBOUND_REFERRALS, show_status=False)


@st.cache_data(ttl=3600, show_spinner=False)
def load_provider_data(filepath: Optional[str] = None) -> pd.DataFrame:
    """
    Load provider data with referral counts from local parquet files into Streamlit cache.

    Loads from local parquet file, aggregates provider data,
    and caches the result in st.cache_data for fast subsequent access.

    Maintained for backward compatibility. New code should use:
    data_manager.load_data(DataSource.PROVIDER_DATA)

    Args:
        filepath: Ignored - automatic file selection from local parquet is used

    Returns:
        DataFrame with unique providers and referral counts cached in st.cache_data
    """
    return get_data_manager().load_data(DataSource.PROVIDER_DATA, show_status=False)


@st.cache_data(ttl=3600, show_spinner=False)
def load_all_referrals(filepath: Optional[str] = None) -> pd.DataFrame:
    """
    Load combined referral data (inbound + outbound) from local parquet files into Streamlit cache.

    Loads from local parquet file, processes both inbound and
    outbound referrals, and caches the combined result in st.cache_data.

    New function providing access to the combined dataset.

    Args:
        filepath: Ignored - automatic file selection from local parquet is used

    Returns:
        DataFrame with all referral data combined, cached in st.cache_data
    """
    return get_data_manager().load_data(DataSource.ALL_REFERRALS, show_status=False)


@st.cache_data(ttl=3600, show_spinner=False)
def load_preferred_providers(filepath: Optional[str] = None) -> pd.DataFrame:
    """
    Load preferred providers contact data from local parquet files into Streamlit cache.

    Loads from local parquet file, processes contact information,
    and caches the result in st.cache_data for fast subsequent access.

    Args:
        filepath: Ignored - automatic file selection from local parquet is used

    Returns:
        DataFrame with preferred provider contact information cached in st.cache_data
    """
    return get_data_manager().load_data(DataSource.PREFERRED_PROVIDERS, show_status=False)


# ============================================================================
# System Management Functions
# ============================================================================


def get_data_ingestion_status() -> Dict[str, Dict[str, Union[bool, str]]]:
    """
    Get comprehensive status of all data ingestion sources.

    Returns:
        Status dictionary with availability and optimization info for each source
    """
    return get_data_manager().get_data_status()


def refresh_data_cache():
    """
    Clear Streamlit data cache to force fresh data loading from local parquet files.

    This clears all st.cache_data cached DataFrames, forcing the next load_data()
    call to reload fresh parquet files from disk and reprocess them.

    Call this after:
    - Updating local parquet data files
    - Data structure changes
    - When you want to ensure fresh data is loaded
    - Manual cache refresh requested by user

    Cache Clearing Strategy:
    - Clears st.cache_data (DataFrames, processed data)
    - Clears st.cache_resource (resource objects, sessions)
    - Next data load will re-read parquet files and rebuild cache
    """
    # Clear cached data (dataframes) and cached resources
    # (resource objects). This ensures that the app will reload
    # fresh copies of datasets from local parquet files.
    try:
        st.cache_data.clear()
    except Exception:
        # Best-effort: ignore if Streamlit API changes or clearing fails
        pass
    try:
        st.cache_resource.clear()
    except Exception:
        pass
    logger.info("Data cache cleared - next loads will fetch fresh data from local parquet files")


def validate_all_data_sources() -> Dict[str, Dict[str, Union[bool, str, int, float, list]]]:
    """
    Validate data integrity for all available sources.

    Returns:
        Validation results for each data source
    """
    results = {}
    for source in DataSource:
        try:
            results[source.value] = get_data_manager().validate_data_integrity(source)
        except Exception as e:
            results[source.value] = {
                "valid": False,
                "error": str(e),
                "row_count": 0,
                "column_count": 0,
            }
    return results
