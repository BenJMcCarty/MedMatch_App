"""
Optimized AWS S3 client utilities for improved performance.

This module provides performance-optimized utilities for accessing S3 with:
- Connection pooling and reuse
- Parallel operations
- Better caching strategies
- Reduced API calls
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import streamlit as st

logger = logging.getLogger(__name__)


class OptimizedS3DataClient:
    """Performance-optimized client for accessing data files from AWS S3."""

    def __init__(self, folder_map: Optional[Dict[str, str]] = None):
        """Initialize the optimized S3 client with connection pooling."""
        from src.utils.config import get_api_config, is_api_enabled

        self.config = get_api_config("s3")
        self.enabled = is_api_enabled("s3")
        self._client = None
        self._session = None

        # Default folder configuration
        defaults = {
            "referrals_folder": "990046944",
            "preferred_providers_folder": "990047553",
        }

        # Merge configurations
        merged = defaults.copy()
        if isinstance(self.config, dict):
            cfg_ref = self.config.get("referrals_folder")
            cfg_pref = self.config.get("preferred_providers_folder")
            if cfg_ref:
                merged["referrals_folder"] = cfg_ref
            if cfg_pref:
                merged["preferred_providers_folder"] = cfg_pref

        # Apply caller overrides
        if folder_map:
            for k, v in folder_map.items():
                if k in merged and v:
                    merged[k] = v

        self.folder_map = merged

    def is_configured(self) -> bool:
        """Check if S3 is properly configured."""
        return self.enabled and isinstance(self.config, dict) and bool(self.config.get("bucket_name"))

    def validate_configuration(self) -> Dict[str, str]:
        """Return configuration issues found for S3 as a dict of field->message.

        This is a lightweight helper intended for UI surfaces to show helpful
        guidance when S3 is partially configured.
        """
        issues: Dict[str, str] = {}
        # Ensure config is a mapping and has required keys
        if not isinstance(self.config, dict):
            issues["config"] = "S3 configuration is missing or invalid."
            return issues

        if not self.config.get("bucket_name"):
            issues["bucket_name"] = "S3 bucket_name is not configured."

        if not self.config.get("aws_access_key_id"):
            issues["aws_access_key_id"] = "AWS access key id is not configured."

        if not self.config.get("aws_secret_access_key"):
            issues["aws_secret_access_key"] = "AWS secret access key is not configured."

        return issues

    def _get_session(self):
        """Get cached boto3 session for connection reuse."""
        if self._session is None and self.enabled:
            try:
                import boto3

                session_kwargs = {}
                if isinstance(self.config, dict):
                    access_key = self.config.get("aws_access_key_id")
                    secret_key = self.config.get("aws_secret_access_key")
                    region = self.config.get("region_name")
                    if access_key and secret_key:
                        session_kwargs.update({"aws_access_key_id": access_key, "aws_secret_access_key": secret_key})
                    if region:
                        session_kwargs["region_name"] = region

                self._session = boto3.Session(**session_kwargs)
            except Exception as e:
                logger.error(f"Failed to initialize S3 session: {e}")
                self.enabled = False
        return self._session

    def _get_client(self):
        """Get S3 client from cached session."""
        if self._client is None:
            session = self._get_session()
            if session:
                try:
                    from botocore.config import Config

                    # Optimize connection pooling
                    config = Config(
                        retries={"max_attempts": 3, "mode": "adaptive"},
                        max_pool_connections=10,
                    )

                    self._client = session.client("s3", config=config)
                except Exception as e:
                    logger.error(f"Failed to create S3 client: {e}")
                    self.enabled = False
        return self._client

    def _resolve_folder(self, folder_type: str) -> Optional[str]:
        """Resolve S3 folder prefix for the given folder type."""
        if folder_type == "referrals":
            sub = self.folder_map.get("referrals_folder")
        elif folder_type == "preferred_providers":
            sub = self.folder_map.get("preferred_providers_folder")
        else:
            logger.error(f"Unknown folder type: {folder_type}")
            return None

        if not sub:
            return None

        # Normalize folder path
        folder = sub.rstrip("/")
        if not folder.endswith("/"):
            folder += "/"

        # Remove any leading bucket name if accidentally included
        if isinstance(self.config, dict):
            bucket = self.config.get("bucket_name")
            if bucket and folder.startswith(f"{bucket}/"):
                folder = folder[len(bucket) + 1:]

        return folder.lstrip("/")

    def list_files_batch(self, folder_types: List[str]) -> Dict[str, List[Tuple[str, datetime]]]:
        """List files for multiple folder types in parallel."""
        client = self._get_client()
        if not client or not isinstance(self.config, dict):
            return {ft: [] for ft in folder_types}

        bucket_name = self.config["bucket_name"]
        results = {}

        # Prepare operations for parallel execution
        operations = []
        for folder_type in folder_types:
            folder = self._resolve_folder(folder_type)
            if folder:
                operations.append((folder_type, folder))

        # Execute in parallel
        with ThreadPoolExecutor(max_workers=min(len(operations), 4)) as executor:
            future_to_folder = {
                executor.submit(self._list_folder_files, client, bucket_name, folder): folder_type
                for folder_type, folder in operations
            }

            for future in as_completed(future_to_folder):
                folder_type = future_to_folder[future]
                try:
                    results[folder_type] = future.result()
                except Exception as e:
                    logger.error(f"Failed to list files for {folder_type}: {e}")
                    results[folder_type] = []

        # Ensure all requested folder types have entries
        for folder_type in folder_types:
            if folder_type not in results:
                results[folder_type] = []

        return results

    def _list_folder_files(self, client, bucket_name: str, folder: str) -> List[Tuple[str, datetime]]:
        """List files in a single folder."""
        try:
            paginator = client.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=folder, PaginationConfig={"PageSize": 100})

            files = []
            for page in page_iterator:
                if "Contents" in page:
                    for obj in page["Contents"]:
                        # Skip the folder itself
                        if obj["Key"] == folder:
                            continue
                        # Include Excel and CSV files
                        if obj["Key"].lower().endswith((".xlsx", ".xls", ".csv")):
                            filename = obj["Key"].split("/")[-1]
                            files.append((filename, obj["LastModified"]))

            return sorted(files, key=lambda x: x[1], reverse=True)

        except Exception as e:
            logger.error(f"Failed to list files in folder '{folder}': {e}")
            return []

    def download_files_batch(self, downloads: List[Tuple[str, str]]) -> Dict[str, Optional[bytes]]:
        """Download multiple files in parallel.

        Args:
            downloads: List of (folder_type, filename) tuples

        Returns:
            Dict mapping "{folder_type}:{filename}" to file bytes or None
        """
        client = self._get_client()
        if not client or not isinstance(self.config, dict):
            return {f"{ft}:{fn}": None for ft, fn in downloads}

        bucket_name = self.config["bucket_name"]
        results = {}

        # Prepare download operations
        operations = []
        for folder_type, filename in downloads:
            folder = self._resolve_folder(folder_type)
            if folder:
                s3_key = f"{folder}{filename}"
                key = f"{folder_type}:{filename}"
                operations.append((key, s3_key))

        # Execute downloads in parallel
        with ThreadPoolExecutor(max_workers=min(len(operations), 3)) as executor:
            future_to_key = {
                executor.submit(self._download_single_file, client, bucket_name, s3_key): key
                for key, s3_key in operations
            }

            for future in as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    results[key] = future.result()
                except Exception as e:
                    logger.error(f"Failed to download {key}: {e}")
                    results[key] = None

        return results

    def _download_single_file(self, client, bucket_name: str, s3_key: str) -> Optional[bytes]:
        """Download a single file from S3."""
        try:
            buffer = BytesIO()
            client.download_fileobj(bucket_name, s3_key, buffer)
            buffer.seek(0)
            return buffer.getvalue()
        except Exception as e:
            logger.error(f"Failed to download file '{s3_key}': {e}")
            return None

    def download_file(self, folder_type: str, filename: str) -> Optional[bytes]:
        """Download a specific file from S3."""
        client = self._get_client()
        if not client or not isinstance(self.config, dict):
            return None

        folder = self._resolve_folder(folder_type)
        if not folder:
            return None

        s3_key = f"{folder}{filename}"
        return self._download_single_file(client, self.config["bucket_name"], s3_key)

    def list_files_in_folder(self, folder_type: str) -> List[Tuple[str, datetime]]:
        """
        List all files in a specific S3 folder.

        Args:
            folder_type: Either 'referrals' or 'preferred_providers'

        Returns:
            List of tuples (filename, last_modified_datetime)
        """
        files_data = self.list_files_batch([folder_type])
        return files_data.get(folder_type, [])

    def download_latest_file(self, folder_type: str) -> Optional[Tuple[bytes, str]]:
        """
        Download the most recently modified file from an S3 folder.

        Args:
            folder_type: Either 'referrals' or 'preferred_providers'

        Returns:
            Tuple of (file_bytes, filename) or None if no files found
        """
        files = self.list_files_batch([folder_type]).get(folder_type, [])
        if not files:
            logger.warning(f"No files found in S3 folder '{folder_type}'")
            return None

        latest_filename, last_modified = files[0]
        logger.info(f"Downloading latest file '{latest_filename}' from S3 (modified: {last_modified})")

        file_bytes = self.download_file(folder_type, latest_filename)
        if file_bytes:
            return file_bytes, latest_filename
        return None

    def download_latest_files_batch(self, folder_types: List[str]) -> Dict[str, Optional[Tuple[bytes, str]]]:
        """Download the latest file from multiple folders in parallel."""
        # First get file listings
        file_listings = self.list_files_batch(folder_types)

        # Prepare downloads for latest files
        downloads = []
        for folder_type in folder_types:
            files = file_listings.get(folder_type, [])
            if files:
                latest_filename = files[0][0]  # Files are already sorted by date desc
                downloads.append((folder_type, latest_filename))

        if not downloads:
            return {ft: None for ft in folder_types}

        # Download files
        download_results = self.download_files_batch(downloads)

        # Format results
        results = {}
        for folder_type, filename in downloads:
            key = f"{folder_type}:{filename}"
            file_bytes = download_results.get(key)
            if file_bytes:
                results[folder_type] = (file_bytes, filename)
            else:
                results[folder_type] = None

        # Ensure all requested folder types have entries
        for folder_type in folder_types:
            if folder_type not in results:
                results[folder_type] = None

        return results


# Cached instances and functions for Streamlit
@st.cache_resource
def get_optimized_s3_client(folder_map_key: Optional[str] = None) -> OptimizedS3DataClient:
    """Get cached optimized S3 client instance."""
    folder_map = None
    if folder_map_key and folder_map_key in st.session_state:
        folder_map = st.session_state[folder_map_key]
    return OptimizedS3DataClient(folder_map=folder_map)


@st.cache_data(ttl=86400, show_spinner=False)
def get_s3_files_optimized(
    folder_types: List[str], folder_map_key: Optional[str] = None
) -> Dict[str, List[Tuple[str, datetime]]]:
    """Cached function to get file listings for multiple folder types.

    Note: TTL is set to 86400 seconds (1 day) to keep listings available
    across user sessions while still allowing a daily refresh. The cache
    is cleared immediately when new data is processed via
    ``refresh_data_cache()`` which calls ``st.cache_data.clear()``.
    """
    client = get_optimized_s3_client(folder_map_key)
    if not client.is_configured():
        return {ft: [] for ft in folder_types}

    return client.list_files_batch(folder_types)


@st.cache_data(ttl=86400, show_spinner=False)
def get_latest_s3_files_optimized(
    folder_types: List[str], folder_map_key: Optional[str] = None
) -> Dict[str, Optional[Tuple[bytes, str]]]:
    """Cached function to download latest files from multiple folders.

    TTL is 1 day to align with the upstream daily sync cadence. If an
    immediate refresh is required after processing new data, call
    ``refresh_data_cache()`` which clears Streamlit caches.
    """
    # Strategy: compute a lightweight signature from the S3 listing (filenames
    # and LastModified timestamps) and use that as the cache key for the
    # heavy download operation. This allows automatic invalidation when the
    # remote files change while still caching downloaded bytes for a day.
    client = get_optimized_s3_client(folder_map_key)
    if not client.is_configured():
        return {ft: None for ft in folder_types}

    # Obtain the current listing (fresh) to compute a signature. We call the
    # client's listing method directly (not the cached wrapper) so the
    # signature reflects the true remote state.
    try:
        listings = client.list_files_batch(folder_types)
    except Exception as e:
        logger.error(f"Failed to compute S3 listing signature: {e}")
        listings = {ft: [] for ft in folder_types}

    # Build a compact signature string from the most relevant metadata. Use
    # the most-recent file's name and last-modified time per folder.
    sig_parts: List[str] = []
    for ft in folder_types:
        files = listings.get(ft, [])
        if files:
            filename, lm = files[0]
            try:
                ts = int(lm.timestamp())
            except Exception:
                ts = 0
            sig_parts.append(f"{ft}:{filename}:{ts}")
        else:
            sig_parts.append(f"{ft}::0")

    signature = "|".join(sig_parts)

    # Delegate to the cached downloader keyed by signature
    return _download_latest_files_cached(folder_types, folder_map_key, signature)


@st.cache_data(ttl=86400, show_spinner=False)
def _download_latest_files_cached(
    folder_types: List[str], folder_map_key: Optional[str], signature: str
) -> Dict[str, Optional[Tuple[bytes, str]]]:
    """Cached heavy download operation keyed by a signature string.

    The `signature` parameter should be derived from S3 last-modified
    timestamps and filenames so that when remote files change the cache key
    changes and the downloads are refreshed automatically.
    """
    client = get_optimized_s3_client(folder_map_key)
    if not client.is_configured():
        return {ft: None for ft in folder_types}

    return client.download_latest_files_batch(folder_types)


# Compatibility functions to match the old s3_client interface
def list_s3_files(folder_type: str, folder_map: Optional[Dict[str, str]] = None) -> List[Tuple[str, datetime]]:
    """List files in an S3 folder - compatibility wrapper for old interface."""
    client = OptimizedS3DataClient(folder_map=folder_map)
    if not client.is_configured():
        return []

    files_data = client.list_files_batch([folder_type])
    return files_data.get(folder_type, [])


@st.cache_data(ttl=86400, show_spinner=False)
def get_latest_s3_file(folder_type: str, folder_map: Optional[Dict[str, str]] = None) -> Optional[Tuple[bytes, str]]:
    """
    Cached function to get the latest file from S3 - compatibility wrapper for old interface.

    Args:
        folder_type: Either 'referrals' or 'preferred_providers'
        folder_map: Optional folder mapping overrides

    Returns:
        Tuple of (file_bytes, filename) or None if download fails
    """
    client = OptimizedS3DataClient(folder_map=folder_map)
    if not client.is_configured():
        return None

    # Compute signature from latest file metadata to allow automatic
    # cache invalidation when remote files change.
    try:
        files = client.list_files_in_folder(folder_type)
    except Exception as e:
        logger.error(f"Failed to list files for signature: {e}")
        files = []

    if files:
        latest_filename, latest_lm = files[0]
        try:
            ts = int(latest_lm.timestamp())
        except Exception:
            ts = 0
        signature = f"{folder_type}:{latest_filename}:{ts}"
    else:
        signature = f"{folder_type}::0"

    # If a caller supplied a folder_map dict (backwards-compatible), we need
    # to provide a stable folder_map_key to the cached downloader. Streamlit's
    # cache keys require hashable args, so we store the dict in
    # ``st.session_state`` under a generated key and pass that key through.
    folder_map_key = None
    if isinstance(folder_map, dict):
        try:
            # Create a deterministic key from the sorted items
            items = tuple(sorted((k, str(v)) for k, v in folder_map.items()))
            key_name = "__s3_folder_map_" + str(abs(hash(items)))
            # Store in session_state so get_optimized_s3_client can read it
            if key_name not in st.session_state:
                st.session_state[key_name] = folder_map
            folder_map_key = key_name
        except Exception:
            folder_map_key = None
    elif isinstance(folder_map, str):
        folder_map_key = folder_map

    result = _download_latest_files_cached([folder_type], folder_map_key, signature)
    return result.get(folder_type)


# Alias for backward compatibility
S3DataClient = OptimizedS3DataClient
