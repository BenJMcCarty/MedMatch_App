#!/usr/bin/env python
"""Geocoding validation pass for provider addresses.

Reads data/processed/Combined_Contacts_and_Reviews.parquet, geocodes each
provider's Full Address via Nominatim, updates latitude/longitude when a
result is found, and writes back atomically.

Usage:
    python scripts/geocode_providers.py           # resumable (skips nominatim rows)
    python scripts/geocode_providers.py --force   # re-geocode all rows
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.geocoding import geocode_provider_dataframe

PARQUET_PATH = PROJECT_ROOT / "data" / "processed" / "Combined_Contacts_and_Reviews.parquet"


def _progress(current: int, total: int, name: str, source: str) -> None:
    symbol = "✓" if source == "nominatim" else ("~" if source == "cms" else "✗")
    print(f"[{current}/{total}] {name} — {symbol} {source}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and update provider geocoordinates from Full Address strings."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-geocode rows already marked nominatim (default: skip them)",
    )
    args = parser.parse_args()

    if not PARQUET_PATH.exists():
        print(f"ERROR: Parquet file not found: {PARQUET_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {PARQUET_PATH} ...")
    df = pd.read_parquet(PARQUET_PATH)
    total = len(df)
    print(f"Loaded {total} providers.")

    if "geocode_source" in df.columns and not args.force:
        already = (df["geocode_source"] == "nominatim").sum()
        print(f"Skipping {already} already-verified rows (--force to re-geocode).")

    mode = "all" if args.force else "unverified"
    print(f"\nGeocoding {mode} providers ...\n")

    result_df = geocode_provider_dataframe(df, force=args.force, progress_callback=_progress)

    # Atomic write: write to temp file, then replace original
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".parquet", dir=PARQUET_PATH.parent)
    try:
        os.close(tmp_fd)
        result_df.to_parquet(tmp_path, index=False)
        os.replace(tmp_path, PARQUET_PATH)
    except Exception as exc:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        print(f"ERROR: Failed to write parquet: {exc}", file=sys.stderr)
        sys.exit(1)

    counts = result_df["geocode_source"].value_counts()
    nominatim = counts.get("nominatim", 0)
    cms = counts.get("cms", 0)
    failed = counts.get("failed", 0)
    print(f"\nDone. {nominatim} nominatim, {cms} cms, {failed} failed.")


if __name__ == "__main__":
    main()
