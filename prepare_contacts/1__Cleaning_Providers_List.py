"""Provider List Cleaning and Preprocessing Script.

This script loads raw provider data from CSV, applies filtering and cleaning
operations, and outputs a processed parquet file ready for use in the application.

Data Processing Steps:
1. Load raw CSV data with proper type specifications
2. Clean column names (strip whitespace)
3. Remove duplicate records
4. Filter by state and specialty
5. Standardize ZIP codes to 5 digits
6. Build full address field
7. Save to compressed parquet format

Usage:
    python 1__Cleaning_Providers_List.py

Configuration:
    Modify DEFAULT_* constants below to customize filtering and paths.
    For advanced configuration, use command-line arguments or config files.
"""

import logging
from pathlib import Path
from typing import List, Optional

import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Default configuration - modify these for different workflows
DEFAULT_RAW_PATH = Path(__file__).parent.parent / "data" / "raw" / "data.csv"
DEFAULT_CLEANED_PATH = Path(__file__).parent.parent / "data" / "processed" / "cleaned_contacts.parquet"

DEFAULT_STATES = ["MD"]

DEFAULT_SPECIALTIES = [
    "CHIROPRACTIC",
    "EMERGENCY MEDICINE",
    "FAMILY PRACTICE",
    "GENERAL PRACTICE",
    "NEUROLOGY",
    "MENTAL HEALTH COUNSELOR",
    "PAIN MANAGEMENT",
    "PHYSICAL MEDICINE AND REHABILITATION",
]

# Required columns for validation
REQUIRED_COLUMNS = ["pri_spec", "adr_ln_1", "State", "City/Town", "ZIP Code"]


def load_raw_provider_data(file_path: Path) -> pd.DataFrame:
    """Load raw provider data from CSV with appropriate type specifications.

    Args:
        file_path: Path to raw CSV file

    Returns:
        pd.DataFrame: Raw provider data with proper types

    Raises:
        FileNotFoundError: If the CSV file doesn't exist
        pd.errors.EmptyDataError: If the CSV file is empty
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Raw data file not found: {file_path}")

    logger.info(f"Loading raw data from {file_path}")

    # Specify dtypes to ensure consistent data types
    dtype_spec = {
        "sec_spec_1": str,
        "sec_spec_2": str,
        "sec_spec_3": str,
        "sec_spec_4": str,
        "ZIP Code": str,
    }

    try:
        df = pd.read_csv(file_path, dtype=dtype_spec)
        logger.info(f"Loaded {len(df)} records from raw data")
        return df
    except pd.errors.EmptyDataError:
        logger.error("CSV file is empty")
        raise
    except Exception as e:
        logger.error(f"Failed to load CSV: {e}")
        raise


def validate_required_columns(df: pd.DataFrame, required_cols: List[str]) -> None:
    """Validate that required columns exist in the DataFrame.

    Args:
        df: DataFrame to validate
        required_cols: List of required column names

    Raises:
        ValueError: If any required columns are missing
    """
    missing_cols = set(required_cols) - set(df.columns)
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")


def clean_provider_data(
    df: pd.DataFrame, states: Optional[List[str]] = None, specialties: Optional[List[str]] = None
) -> pd.DataFrame:
    """Clean and filter provider data.

    Processing Steps:
    1. Strip whitespace from column names
    2. Remove duplicate records
    3. Drop rows with missing critical fields
    4. Filter by state (if specified)
    5. Filter by specialty (if specified)
    6. Standardize ZIP codes to 5 digits
    7. Build full address field

    Args:
        df: Raw provider DataFrame
        states: List of state codes to filter by (e.g., ['MD', 'VA'])
        specialties: List of specialty names to filter by

    Returns:
        pd.DataFrame: Cleaned and filtered provider data
    """
    # Clean column names (strip leading/trailing whitespace)
    df = df.rename(columns=lambda x: x.strip())
    logger.info("Cleaned column names")

    # Validate required columns exist
    validate_required_columns(df, REQUIRED_COLUMNS)

    # Remove duplicate records
    initial_count = len(df)
    df = df.drop_duplicates(ignore_index=True)
    duplicates_removed = initial_count - len(df)
    if duplicates_removed > 0:
        logger.info(f"Removed {duplicates_removed} duplicate records")

    # Drop rows with missing critical fields
    df = df.dropna(subset=["pri_spec", "adr_ln_1"], how="any", ignore_index=True)
    logger.info(f"Retained {len(df)} records after dropping missing values")

    # Filter by state if specified
    if states:
        df = df[df["State"].isin(states)].reset_index(drop=True)
        logger.info(f"Filtered to states {states}: {len(df)} records remaining")

    # Filter by specialty if specified
    if specialties:
        df = df[df["pri_spec"].isin(specialties)].reset_index(drop=True)
        logger.info(f"Filtered to {len(specialties)} specialties: {len(df)} records remaining")

    # Standardize ZIP codes to 5 digits
    df["ZIP Code"] = df["ZIP Code"].map(lambda x: str(x)[:5])
    logger.info("Standardized ZIP codes to 5 digits")

    # Build full address field using vectorized string ops to ensure proper types
    addr1 = df["adr_ln_1"].fillna("").astype(str).str.strip()
    city = df["City/Town"].fillna("").astype(str).str.strip()
    state = df["State"].fillna("").astype(str).str.strip()
    zipc = df["ZIP Code"].fillna("").astype(str).str.strip()

    # Concatenate components safely: "adr_ln_1, City/Town, State ZIP"
    df["Full Address"] = addr1.str.cat([city, state], sep=", ").str.cat(zipc, sep=" ")
    df["Full Address"] = df["Full Address"].str.strip()
    logger.info("Created Full Address field")

    return df


def save_cleaned_data(df: pd.DataFrame, output_path: Path) -> None:
    """Save cleaned provider data to compressed parquet format.

    Args:
        df: Cleaned provider DataFrame
        output_path: Path for output parquet file

    Raises:
        OSError: If unable to write to output path
    """
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Saving {len(df)} cleaned records to {output_path}")

    try:
        df.to_parquet(output_path, index=False, compression="zstd")
        logger.info(f"Successfully saved cleaned data to {output_path}")
    except Exception as e:
        logger.error(f"Failed to save parquet file: {e}")
        raise


def main(
    raw_path: Optional[Path] = None,
    cleaned_path: Optional[Path] = None,
    states: Optional[List[str]] = None,
    specialties: Optional[List[str]] = None,
) -> None:
    """Main workflow for cleaning provider data.

    Args:
        raw_path: Path to raw CSV file (defaults to DEFAULT_RAW_PATH)
        cleaned_path: Path for output parquet file (defaults to DEFAULT_CLEANED_PATH)
        states: List of state codes to filter by (defaults to DEFAULT_STATES)
        specialties: List of specialties to filter by (defaults to DEFAULT_SPECIALTIES)
    """
    # Use defaults if not specified
    raw_path = raw_path or DEFAULT_RAW_PATH
    cleaned_path = cleaned_path or DEFAULT_CLEANED_PATH
    states = states or DEFAULT_STATES
    specialties = specialties or DEFAULT_SPECIALTIES

    logger.info("Starting provider data cleaning workflow")
    logger.info(f"Configuration: States={states}, Specialties={len(specialties)} types")

    try:
        # Load raw data
        df = load_raw_provider_data(raw_path)

        # Clean and filter data
        df_cleaned = clean_provider_data(df, states=states, specialties=specialties)

        # Save cleaned data
        save_cleaned_data(df_cleaned, cleaned_path)

        logger.info("Provider data cleaning workflow completed successfully")

    except Exception as e:
        logger.error(f"Workflow failed: {e}")
        raise


if __name__ == "__main__":
    # Run with default configuration
    # To customize, modify the DEFAULT_* constants at the top of this file
    # or call main() with custom parameters
    main()