"""
Data Ingestion Module - Centralized data loading with S3 integration.

This module handles data downloads from S3, format detection (CSV/Excel/Parquet),
and caching with Streamlit's cache system. Data flows from S3 to processed DataFrames
with automatic cache invalidation based on S3 metadata.

Key Features:
- Direct S3 downloads with automatic format detection
- Streamlit cache integration with metadata-based invalidation
- Support for CSV, Excel, and Parquet formats
- Centralized error handling and validation
"""

import logging
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import pandas as pd
import streamlit as st

from src.data.io_utils import load_dataframe
from src.data.preparation import process_referral_data
from src.utils.s3_client_optimized import S3DataClient

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

    The ingestion system automatically detects and handles both CSV and Excel formats
    from S3. CSV is the preferred format for S3 data exports.
    """

    CSV = ".csv"  # Primary format: Text-based, fast parsing, S3 standard export format
    EXCEL = ".xlsx"  # Legacy format: Slower to parse, but supported with automatic fallback
    PARQUET = ".parquet"  # Internal cache format only (not used for S3 ingestion)


class DataIngestionManager:
    """
    Centralized data ingestion manager with optimized loading strategies.

    This manager handles the complete data pipeline from S3 downloads to
    processed DataFrames, with intelligent caching using Streamlit's cache system.

    Key Features:
    - Direct S3 download and processing without intermediate file storage
    - Automatic CSV and Excel format detection and parsing
    - Streamlit cache integration with S3 metadata-based invalidation
    - Source-specific post-processing for provider aggregation
    - Built-in data validation and quality checks

    Supported Formats:
    - CSV files (.csv) - Primary format with fast parsing
    - Excel files (.xlsx, .xls) - Legacy format with automatic fallback

    Usage:
        manager = DataIngestionManager()
        df = manager.load_data(DataSource.OUTBOUND_REFERRALS)
        # Automatically handles CSV or Excel format from S3
    """

    def __init__(self):
        """
        Initialize the data ingestion manager.
        """
        self.cache_ttl = 3600  # 1 hour cache for optimal performance
        self._s3_client = S3DataClient()

    def _get_s3_data(self, folder_type: str) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
        """
        Download the latest data from S3 for the given folder type.

        Supports both CSV and Excel formats. The S3 client automatically lists
        files with extensions: .csv, .xlsx, .xls

        Args:
            folder_type: Type of data to download ('referrals' or 'preferred_providers')

        Returns:
            Tuple of (data_bytes, filename, last_modified_iso) or (None, None, None) if download fails
            The filename extension determines the parsing method (CSV preferred, Excel fallback)
        """
        try:
            files = self._s3_client.list_files_batch([folder_type]).get(folder_type, [])
            if not files:
                logger.warning(f"No files found in S3 folder '{folder_type}'")
                return None, None, None

            latest_filename, last_modified = files[0]
            logger.info(f"Found latest file '{latest_filename}' from S3 (modified: {last_modified})")

            file_bytes = self._s3_client.download_file(folder_type, latest_filename)
            if file_bytes:
                # Return ISO format string for cache key
                last_modified_iso = last_modified.isoformat() if last_modified else None
                return file_bytes, latest_filename, last_modified_iso
            return None, None, None
        except Exception as e:
            logger.error(f"Failed to download {folder_type} from S3: {str(e)}")
            return None, None, None

    @st.cache_data(ttl=3600, show_spinner=False)
    def _load_and_process_data_cached(
        _self, source: DataSource, last_modified: str, data_bytes: bytes, filename: str
    ) -> pd.DataFrame:
        """
        Process downloaded data into a clean DataFrame with Streamlit caching.

        This method is cached based on source, last_modified timestamp, and data content.
        The cache automatically invalidates when:
        - The S3 file is updated (detected via last_modified timestamp)
        - The TTL expires (1 hour)
        - Manual cache refresh is triggered

        File Format Handling:
        - CSV files: Parsed using pd.read_csv() for optimal performance
        - Excel files: Parsed using pd.read_excel() with automatic fallback
        - Format detection: Based on filename extension from S3

        Args:
            source: Data source to process
            last_modified: Last modified timestamp for cache invalidation
            data_bytes: Raw data bytes from S3 (CSV or Excel format)
            filename: Filename for logging and format detection

        Returns:
            Processed DataFrame cached in Streamlit's st.cache_data
        """
        try:
            # Process the data based on source type
            if source == DataSource.PREFERRED_PROVIDERS:
                # Process preferred providers
                df = _self._process_preferred_providers_data(data_bytes, filename)
            else:
                # Process referral data
                df = _self._process_referral_data(source, data_bytes, filename)

            logger.info(f"Processed {len(df)} records for {source.value}")
            return df

        except Exception as e:
            logger.error(f"Failed to process {source.value}: {str(e)}")
            return pd.DataFrame()

    def _load_and_process_data(self, source: DataSource) -> pd.DataFrame:
        """
        Download data from S3 and process it into a clean DataFrame.

        If S3 is not configured or fails, falls back to local parquet files as cache.

        This method handles the complete pipeline from S3 download to processed DataFrame,
        cached in Streamlit's cache system.

        Args:
            source: Data source to load and process

        Returns:
            Processed DataFrame or empty DataFrame if processing fails
        """
        try:
            # Determine which S3 folder to use
            if source == DataSource.PREFERRED_PROVIDERS:
                folder_type = "preferred_providers"
            else:
                folder_type = "referrals"

            # Download data from S3
            data_bytes, filename, last_modified = self._get_s3_data(folder_type)
            if not data_bytes:
                logger.warning(f"No S3 data available for {source.value}, attempting local fallback")
                # Try to load from local parquet files as fallback
                return self._load_from_local_parquet(source)

            # Use the cached processing method with last_modified as cache key
            return self._load_and_process_data_cached(
                source, last_modified or "unknown", data_bytes, filename or "unknown"
            )

        except Exception as e:
            logger.error(f"Failed to load and process {source.value}: {str(e)}")
            # Try to load from local parquet files as fallback
            logger.info(f"Attempting local parquet fallback for {source.value}")
            return self._load_from_local_parquet(source)

    def _load_from_local_parquet(self, source: DataSource) -> pd.DataFrame:
        """
        Load data from local parquet cache files when S3 is unavailable.

        This serves as a fallback mechanism for development and testing when S3 is not configured.

        Args:
            source: Data source to load

        Returns:
            DataFrame from local parquet file, or empty DataFrame if not found
        """
        # Map data sources to parquet filenames
        parquet_map = {
            DataSource.INBOUND_REFERRALS: "cleaned_inbound_referrals.parquet",
            DataSource.OUTBOUND_REFERRALS: "cleaned_outbound_referrals.parquet",
            DataSource.ALL_REFERRALS: "cleaned_all_referrals.parquet",
            DataSource.PREFERRED_PROVIDERS: "cleaned_preferred_providers.parquet",
            DataSource.PROVIDER_DATA: "cleaned_outbound_referrals.parquet",  # Will be processed
        }

        parquet_filename = parquet_map.get(source)
        if not parquet_filename:
            logger.error(f"No parquet mapping for source: {source.value}")
            return pd.DataFrame()

        parquet_path = Path("data/processed") / parquet_filename

        if not parquet_path.exists():
            logger.warning(f"Local parquet file not found: {parquet_path}")
            return pd.DataFrame()

        try:
            df = pd.read_parquet(parquet_path)
            logger.info(f"Loaded {len(df)} rows from local parquet: {parquet_path}")

            # For provider data, apply aggregation processing
            if source == DataSource.PROVIDER_DATA:
                df = self._process_provider_data(df)

            return df
        except Exception as e:
            logger.error(f"Failed to read local parquet {parquet_path}: {e}")
            return pd.DataFrame()

    def _process_referral_data(self, source: DataSource, data_bytes: bytes, filename: str) -> pd.DataFrame:
        """
        Process referral data from S3 bytes (CSV or Excel format).

        The preparation module automatically detects file format based on filename
        and applies appropriate parsing (pd.read_csv or pd.read_excel).

        Args:
            source: The specific referral data source
            data_bytes: Raw data bytes from S3 (CSV or Excel format)
            filename: Filename for logging and format detection

        Returns:
            Processed DataFrame with standardized schema
        """
        # Use the preparation function to process the data
        # It handles both CSV and Excel formats automatically
        inbound_df, outbound_df, combined_df, _ = process_referral_data(data_bytes, filename=filename)

        # Return the appropriate DataFrame based on source
        if source == DataSource.INBOUND_REFERRALS:
            return inbound_df
        elif source == DataSource.OUTBOUND_REFERRALS:
            return outbound_df
        elif source == DataSource.ALL_REFERRALS:
            return combined_df
        elif source == DataSource.PROVIDER_DATA:
            # For provider data, aggregate from outbound referrals
            return self._process_provider_data(outbound_df)
        else:
            return pd.DataFrame()

    def _process_preferred_providers_data(self, data_bytes: bytes, filename: str) -> pd.DataFrame:
        """
        Process preferred providers data from S3 bytes (CSV or Excel format).

        Uses the shared load_dataframe utility for consistent file loading
        across the application.

        Args:
            data_bytes: Raw data bytes from S3 (CSV or Excel format)
            filename: Filename for logging and format detection

        Returns:
            Processed DataFrame with standardized schema
        """
        # Load the data using shared utility (handles CSV and Excel automatically)
        df = load_dataframe(data_bytes, filename=filename, sheet_name="Referral_App_Preferred_Providers")

        # Process following the notebook logic
        # Deduplicate by Person ID if available, otherwise use generic deduplication
        # Check for the raw column name before renaming
        person_id_col = "Contact's Details: Person ID"
        if person_id_col in df.columns:
            df = df.drop_duplicates(subset=person_id_col, keep="first", ignore_index=True)
            logger.info("Deduplicated preferred providers by Person ID: %d unique providers", len(df))
        else:
            df = df.drop_duplicates(ignore_index=True)
            logger.info("Deduplicated preferred providers (no Person ID column): %d unique providers", len(df))

        # Clean geo data
        lat_col = "Contact's Details: Latitude"
        lon_col = "Contact's Details: Longitude"

        if {lat_col, lon_col}.issubset(df.columns):
            df = df.dropna(subset=[lat_col, lon_col])

        # Rename columns to match expected schema
        column_mapping = {
            "Contact Full Name": "Full Name",
            "Contact's Work Phone": "Work Phone",
            "Contact's Work Address": "Work Address",
            lat_col: "Latitude",
            lon_col: "Longitude",
            "Contact's Details: Specialty": "Specialty",
            "Contact's Details: Last Verified Date": "Last Verified Date",
            "Contact's Details: Person ID": "Person ID",
        }

        for old_col, new_col in column_mapping.items():
            if old_col in df.columns:
                df[new_col] = df[old_col]

        # Standardize dates for preferred providers
        df = self._standardize_dates(df)

        # Log information about the preferred providers data loaded
        if not df.empty and "Full Name" in df.columns:
            unique_providers = df["Full Name"].nunique()
            logger.info(
                f"Loaded preferred providers file '{filename}': " f"{len(df)} rows, {unique_providers} unique providers"
            )

            # Validation: Check if this looks like it might be the wrong file
            # Preferred providers lists are typically smaller than the full provider database
            # If we see more than 100 unique providers, log a warning
            if unique_providers > 100:
                global _preferred_providers_warning_logged

                if not _preferred_providers_warning_logged:
                    logger.warning(
                        f"WARNING: Preferred providers file contains {unique_providers} unique providers. "
                        "This is unusually high. Please verify that the correct file was uploaded to the "
                        "preferred_providers folder in S3. The preferred providers list should contain "
                        "only the firm's preferred provider contacts, not all providers."
                    )
                    _preferred_providers_warning_logged = True  # Set the flag to prevent future warnings

        return df

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
        Process provider data by aggregating referral information.

        Creates unique provider records with referral counts and latest contact info.
        This always aggregates data to create the provider view, even from cleaned data.
        """
        # If this already has aggregated referral counts, return as-is
        if "Referral Count" in df.columns and len(df["Full Name"].unique()) == len(df):
            return df

        # Make sure we have the required columns for aggregation
        if "Full Name" not in df.columns:
            return df

        # Aggregate to create unique providers with referral counts
        agg_dict = {
            "Project ID": "count",  # Count referrals per provider
        }

        # Add other columns that exist
        for col in ["Work Address", "Work Phone", "Latitude", "Longitude", "Referral Source"]:
            if col in df.columns:
                agg_dict[col] = "first"  # Take first non-null value

        # Take most recent Last Verified Date for each provider
        if "Last Verified Date" in df.columns:
            agg_dict["Last Verified Date"] = "max"  # Most recent verification date

        try:
            provider_df = df.groupby("Full Name", as_index=False).agg(agg_dict)

            # Rename count column to Referral Count
            if "Project ID" in provider_df.columns:
                provider_df = provider_df.rename(columns={"Project ID": "Referral Count"})
            else:
                provider_df["Referral Count"] = 1

            # Clean up missing values in text columns
            text_cols = ["Work Address", "Work Phone", "Referral Source"]
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

        Returns information about S3 availability and data processing status
        for all configured data sources.

        Returns:
            Dictionary mapping source names to their status information
        """
        status = {}

        for source in DataSource:
            # Check if S3 data is available
            folder_type = "preferred_providers" if source == DataSource.PREFERRED_PROVIDERS else "referrals"
            data_bytes, filename, last_modified = self._get_s3_data(folder_type)
            available = data_bytes is not None

            status[source.value] = {
                "available": available,
                "file_type": "s3" if available else "none",
                "filename": filename if available else None,
                "optimized": True,  # Always processed fresh from S3
                "performance_tier": "fast",  # Direct processing from S3
            }

        return status

    def load_data(self, source: DataSource, show_status: bool = True) -> pd.DataFrame:
        """
        Public method to load data for a given DataSource.

        This method downloads data directly from S3 (CSV or Excel format), processes it,
        and caches the result in Streamlit's cache system using st.cache_data.

        File Format Support:
        - Automatically detects CSV (.csv) or Excel (.xlsx, .xls) format
        - CSV files are parsed with pd.read_csv() for optimal performance
        - Excel files are parsed with pd.read_excel() with CSV fallback
        - Format detection based on S3 filename extension

        Caching Behavior:
        - Cached with st.cache_data decorator (TTL: 1 hour)
        - Cache key includes: source, last_modified timestamp, data_bytes hash, filename
        - Automatic cache invalidation when S3 file is updated
        - Manual refresh available via refresh_data_cache()

        Data must be available in S3. If S3 is not configured or data is unavailable,
        clear error messages are provided.

        Args:
            source: DataSource enum value identifying which dataset to load
            show_status: If True, logs or displays the data source selection

        Returns:
            pd.DataFrame with the requested data cached in st.cache_data (may be empty on failure)
        """
        # Check if S3 is configured
        from src.utils.config import is_api_enabled

        if not is_api_enabled("s3"):
            error_msg = (
                "⚠️ S3 is not configured — using local cache files as fallback.\n\n"
                "**For production use**, configure S3 credentials in `.streamlit/secrets.toml`:\n"
                "- `s3.aws_access_key_id`\n"
                "- `s3.aws_secret_access_key`\n"
                "- `s3.bucket_name`\n\n"
                "**For development**, local parquet cache files will be used if available.\n"
                "See `docs/S3_MIGRATION_GUIDE.md` for setup instructions."
            )
            logger.warning("S3 not configured, attempting local fallback")
            if show_status:
                st.warning(error_msg)

            # Try to load from local parquet files
            df = self._load_from_local_parquet(source)
            if df.empty and show_status:
                st.error(
                    "❌ No data available. S3 is not configured and local cache files are not found.\n\n"
                    "Please configure S3 or ensure data cache files exist in `data/processed/`."
                )
            return df

        if show_status:
            logger.debug(f"Loading data for {source.value} from S3")

        # Use the cached processing method
        df = self._load_and_process_data(source)

        # Apply any additional post-processing if needed
        if source == DataSource.PROVIDER_DATA and not df.empty:
            # Ensure provider aggregation is applied
            df = self._process_provider_data(df)

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
        from S3 (CSV or Excel format) to ensure they're cached in st.cache_data and
        ready for immediate use when the app starts.

        Cache Warming Benefits:
        - Reduces first-page-load latency
        - Downloads latest CSV/Excel files from S3
        - Processes and transforms data once
        - Stores in Streamlit cache for fast subsequent access
        """
        logger.info("Preloading data from S3 into Streamlit cache...")

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
        to force fresh downloads from S3.

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
    Load detailed referral data (outbound referrals) from S3 into Streamlit cache.

    Downloads the latest CSV or Excel file from S3, processes it, and caches
    the result in st.cache_data for fast subsequent access.

    Maintained for backward compatibility. New code should use:
    data_manager.load_data(DataSource.OUTBOUND_REFERRALS)

    Args:
        filepath: Ignored - automatic file selection from S3 is used

    Returns:
        DataFrame with outbound referral data cached in st.cache_data
    """
    return get_data_manager().load_data(DataSource.OUTBOUND_REFERRALS, show_status=False)


@st.cache_data(ttl=3600, show_spinner=False)
def load_inbound_referrals(filepath: Optional[str] = None) -> pd.DataFrame:
    """
    Load inbound referral data from S3 into Streamlit cache.

    Downloads the latest CSV or Excel file from S3, processes it, and caches
    the result in st.cache_data for fast subsequent access.

    Maintained for backward compatibility. New code should use:
    data_manager.load_data(DataSource.INBOUND_REFERRALS)

    Args:
        filepath: Ignored - automatic file selection from S3 is used

    Returns:
        DataFrame with inbound referral data cached in st.cache_data
    """
    return get_data_manager().load_data(DataSource.INBOUND_REFERRALS, show_status=False)


@st.cache_data(ttl=3600, show_spinner=False)
def load_provider_data(filepath: Optional[str] = None) -> pd.DataFrame:
    """
    Load provider data with referral counts from S3 into Streamlit cache.

    Downloads the latest CSV or Excel file from S3, aggregates provider data,
    and caches the result in st.cache_data for fast subsequent access.

    Maintained for backward compatibility. New code should use:
    data_manager.load_data(DataSource.PROVIDER_DATA)

    Args:
        filepath: Ignored - automatic file selection from S3 is used

    Returns:
        DataFrame with unique providers and referral counts cached in st.cache_data
    """
    return get_data_manager().load_data(DataSource.PROVIDER_DATA, show_status=False)


@st.cache_data(ttl=3600, show_spinner=False)
def load_all_referrals(filepath: Optional[str] = None) -> pd.DataFrame:
    """
    Load combined referral data (inbound + outbound) from S3 into Streamlit cache.

    Downloads the latest CSV or Excel file from S3, processes both inbound and
    outbound referrals, and caches the combined result in st.cache_data.

    New function providing access to the combined dataset.

    Args:
        filepath: Ignored - automatic file selection from S3 is used

    Returns:
        DataFrame with all referral data combined, cached in st.cache_data
    """
    return get_data_manager().load_data(DataSource.ALL_REFERRALS, show_status=False)


@st.cache_data(ttl=3600, show_spinner=False)
def load_preferred_providers(filepath: Optional[str] = None) -> pd.DataFrame:
    """
    Load preferred providers contact data from S3 into Streamlit cache.

    Downloads the latest CSV or Excel file from S3, processes contact information,
    and caches the result in st.cache_data for fast subsequent access.

    Args:
        filepath: Ignored - automatic file selection from S3 is used

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
    Clear Streamlit data cache to force fresh downloads from S3.

    This clears all st.cache_data cached DataFrames, forcing the next load_data()
    call to download fresh CSV/Excel files from S3 and reprocess them.

    Call this after:
    - Uploading new CSV or Excel data to S3
    - Data structure changes
    - When you want to ensure fresh data is loaded
    - Manual cache refresh requested by user

    Cache Clearing Strategy:
    - Clears st.cache_data (DataFrames, processed data)
    - Clears st.cache_resource (S3 client connections, sessions)
    - Next data load will re-download from S3 and rebuild cache
    """
    # Clear cached data (dataframes, downloads) and cached resources
    # (client instances, sessions). This ensures that the app will reload
    # fresh copies of datasets from S3 and recreate any resource objects.
    try:
        st.cache_data.clear()
    except Exception:
        # Best-effort: ignore if Streamlit API changes or clearing fails
        pass
    try:
        st.cache_resource.clear()
    except Exception:
        pass
    logger.info("Data cache cleared - next loads will fetch fresh CSV/Excel data from S3")


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
