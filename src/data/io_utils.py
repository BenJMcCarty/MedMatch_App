"""
Shared I/O utilities for data loading and file format detection.

This module provides centralized file I/O operations used across the data processing
pipeline, reducing code duplication and ensuring consistent handling of various
data formats (CSV, Excel, Parquet, in-memory buffers).

Key Functions:
- detect_file_format: Determine file format from filename or bytes
- load_dataframe: Universal data loader supporting multiple input types
- looks_like_excel_bytes: Quick heuristic to detect Excel file format

Supported Formats:
- CSV (.csv) - Text-based, fast parsing
- Excel (.xlsx, .xls) - Binary formats with automatic engine selection
- Parquet (.parquet) - Columnar format for efficient storage
- In-memory buffers (BytesIO, bytes, memoryview, bytearray)
- pandas DataFrames (pass-through with column normalization)
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd

logger = logging.getLogger(__name__)


def looks_like_excel_bytes(buffer: BytesIO) -> bool:
    """Quick heuristic: check first bytes to see if data looks like an Excel file.

    Detection logic:
    - XLSX files are ZIP archives and start with PK signature (b'PK\\x03\\x04')
    - Older XLS BIFF files begin with bytes 0xD0 0xCF 0x11 0xE0

    Args:
        buffer: BytesIO buffer containing file data

    Returns:
        True if the buffer appears to contain Excel data, False otherwise
    """
    try:
        buffer.seek(0)
        head = buffer.read(4)
        buffer.seek(0)
    except Exception:
        return False
    if not head:
        return False
    if head.startswith(b"PK"):
        return True
    # BIFF header (xls)
    if head[:4] == b"\xd0\xcf\x11\xe0":
        return True
    return False


def detect_file_format(
    filename: Optional[str] = None, buffer: Optional[BytesIO] = None
) -> tuple[Optional[str], Optional[str]]:
    """Detect file format from filename extension or buffer content.

    Args:
        filename: Optional filename to check for extension
        buffer: Optional BytesIO buffer to inspect for Excel signature

    Returns:
        Tuple of (format_type, engine) where:
        - format_type: 'csv', 'xlsx', 'xls', 'parquet', or None
        - engine: 'openpyxl', 'xlrd', or None (for Excel files)
    """
    engine = None
    format_type = None

    # First try to detect from filename extension
    if filename:
        fname_lower = filename.lower()
        if fname_lower.endswith(".csv"):
            format_type = "csv"
        elif fname_lower.endswith(".xlsx"):
            format_type = "xlsx"
            engine = "openpyxl"
        elif fname_lower.endswith(".xls"):
            format_type = "xls"
            engine = "xlrd"
        elif fname_lower.endswith(".parquet"):
            format_type = "parquet"

    # If no format detected from filename, try to detect from buffer content
    if not format_type and buffer:
        if looks_like_excel_bytes(buffer):
            format_type = "xlsx"  # Default to modern Excel
            engine = "openpyxl"
            buffer.seek(0)

    return format_type, engine


def load_dataframe(
    raw_input: Union[Path, str, BytesIO, bytes, pd.DataFrame, Any],
    *,
    filename: Optional[str] = None,
    sheet_name: Optional[str] = None,
) -> pd.DataFrame:
    """Universal data loader supporting multiple input types and formats.

    This function provides a unified interface for loading data from various sources:
    - File paths (CSV, Excel, Parquet)
    - In-memory buffers (BytesIO, bytes, memoryview, bytearray)
    - pandas DataFrames (normalized and returned)

    Format Detection:
    - Automatic detection based on filename extension
    - Fallback to content inspection for buffers
    - Graceful degradation with multiple format attempts

    Args:
        raw_input: Data source (file path, buffer, or DataFrame)
        filename: Optional filename for logging and format detection
        sheet_name: Optional Excel sheet name (if None, uses default sheet)

    Returns:
        pd.DataFrame with normalized column names (whitespace stripped)

    Raises:
        FileNotFoundError: If file path doesn't exist
        TypeError: If input type is not supported
        ValueError: If file cannot be read in any supported format
    """
    # Handle DataFrame input (pass-through with normalization)
    if isinstance(raw_input, pd.DataFrame):
        logger.info("Processing DataFrame with %d rows (source: %s)", len(raw_input), filename or "unknown")
        df = raw_input.copy()
        df.columns = df.columns.str.strip()
        return df

    # Handle file path input
    elif isinstance(raw_input, (Path, str)):
        raw_path = Path(raw_input)
        if not raw_path.exists():
            raise FileNotFoundError(f"File not found: {raw_path}")

        logger.info("Loading data from %s", raw_path)

        # Detect format and engine
        format_type, engine = detect_file_format(raw_path.name)

        # Load based on format
        if format_type == "csv":
            df = pd.read_csv(raw_path)
        elif format_type == "parquet":
            df = pd.read_parquet(raw_path)
        else:
            # Excel or unknown format - try Excel first with fallback to CSV
            try:
                if engine:
                    if sheet_name:
                        df = pd.read_excel(raw_path, sheet_name=sheet_name, engine=engine)
                    else:
                        df = pd.read_excel(raw_path, engine=engine)
                else:
                    # Try openpyxl first, then xlrd
                    try:
                        if sheet_name:
                            df = pd.read_excel(raw_path, sheet_name=sheet_name, engine="openpyxl")
                        else:
                            df = pd.read_excel(raw_path, engine="openpyxl")
                    except Exception:
                        if sheet_name:
                            df = pd.read_excel(raw_path, sheet_name=sheet_name, engine="xlrd")
                        else:
                            df = pd.read_excel(raw_path, engine="xlrd")
            except Exception:
                # Fallback to CSV
                df = pd.read_csv(raw_path)

        df.columns = df.columns.str.strip()
        return df

    # Handle buffer-like input
    else:
        logger.info("Loading data from memory (source: %s)", filename or "uploaded file")

        # Convert various buffer types to BytesIO
        if isinstance(raw_input, BytesIO):
            buffer = raw_input
        elif isinstance(raw_input, bytes):
            buffer = BytesIO(raw_input)
        elif isinstance(raw_input, (memoryview, bytearray)):
            buffer = BytesIO(bytes(raw_input))
        elif type(raw_input).__name__ == "memoryview":
            # Handle memoryview objects (from Streamlit getbuffer())
            buffer = BytesIO(bytes(raw_input))  # type: ignore
        else:
            # Last resort: try to convert to bytes
            try:
                buffer = BytesIO(bytes(raw_input))  # type: ignore
            except Exception as e:
                raise TypeError(f"Cannot convert {type(raw_input)} to BytesIO: {e}")

        # Detect format
        buffer.seek(0)
        format_type, engine = detect_file_format(filename, buffer)
        buffer.seek(0)

        # Try to load based on detected format
        if format_type == "csv":
            # CSV format (preferred)
            try:
                df = pd.read_csv(buffer)
            except Exception:
                # Fallback to Excel if CSV parsing fails
                buffer.seek(0)
                df = _load_excel_from_buffer(buffer, sheet_name, engine)
        else:
            # Excel format (with CSV fallback)
            try:
                df = _load_excel_from_buffer(buffer, sheet_name, engine)
            except Exception:
                # Final fallback to CSV
                buffer.seek(0)
                try:
                    df = pd.read_csv(buffer)
                except Exception as e:
                    raise ValueError(f"Could not read data as Excel or CSV. " f"Filename hint: {filename}. Error: {e}")

        df.columns = df.columns.str.strip()
        return df


def _load_excel_from_buffer(buffer: BytesIO, sheet_name: Optional[str], engine: Optional[str]) -> pd.DataFrame:
    """Helper to load Excel data from buffer with fallback logic.

    Args:
        buffer: BytesIO buffer containing Excel data
        sheet_name: Optional sheet name to read
        engine: Optional pandas engine ('openpyxl' or 'xlrd')

    Returns:
        pd.DataFrame loaded from Excel

    Raises:
        Exception: If all Excel loading attempts fail
    """
    # Try with sheet name first
    if sheet_name:
        try:
            if engine:
                return pd.read_excel(buffer, sheet_name=sheet_name, engine=engine)
            else:
                try:
                    return pd.read_excel(buffer, sheet_name=sheet_name, engine="openpyxl")
                except Exception:
                    buffer.seek(0)
                    return pd.read_excel(buffer, sheet_name=sheet_name, engine="xlrd")
        except (ValueError, KeyError):
            # Sheet not found, try without sheet name
            buffer.seek(0)

    # Try without sheet name (use default sheet)
    if engine:
        return pd.read_excel(buffer, engine=engine)
    else:
        try:
            return pd.read_excel(buffer, engine="openpyxl")
        except Exception:
            buffer.seek(0)
            return pd.read_excel(buffer, engine="xlrd")


__all__ = [
    "looks_like_excel_bytes",
    "detect_file_format",
    "load_dataframe",
]
