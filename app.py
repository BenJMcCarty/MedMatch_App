"""
Streamlit app entrypoint - Landing page and ETL orchestration.

This module serves as the home/landing page and handles:
- Navigation to core pages (Search, Dashboard, Update Data)
- Data loading pipeline: local parquet files → Streamlit cache
- Background data refresh on startup and daily at 4 AM

The data pipeline uses DataIngestionManager to load data from local parquet files
and cache it in Streamlit's cache with 1-hour TTL.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

import streamlit as st

st.set_page_config(page_title="Provider Recommender", page_icon=":hospital:", layout="wide")

logger = logging.getLogger(__name__)

from src.app_logic import filter_providers_by_radius  # noqa: E402 - must import after set_page_config

# Try to import the real geocoding helper. Tests expect a fallback
# `geocode_address_with_cache` to exist when `geopy` is not installed.
try:
    import geopy  # noqa: F401 - optional dependency

    GEOPY_AVAILABLE = True

    # Real implementation provided by the utils package
    from src.utils.geocoding import geocode_address_with_cache  # type: ignore
except Exception:  # pragma: no cover - environment dependent
    GEOPY_AVAILABLE = False

    def geocode_address_with_cache(address: str) -> Optional[Tuple[float, float]]:  # type: ignore[override]
        """Fallback geocode function used when geopy isn't available.

        The function intentionally returns None to signal that geocoding
        is unavailable in the current environment. Tests rely on this
        fallback behavior.
        """
        # We use Streamlit to surface a friendly message in the UI.
        st.warning(
            "geopy package not available. Geocoding disabled (returns None). "
            "Install with: pip install geopy"
        )
        return None


# Symbols exported when this module is imported elsewhere (tests)
__all__ = ["filter_providers_by_radius", "geocode_address_with_cache", "GEOPY_AVAILABLE", "show_auto_update_status"]


def show_auto_update_status():
    """
    Display the auto-update status message if available.

    This function can be called from any page to show the result
    of the automatic data loading that occurs on app launch.
    """
    # Prefer a status file written by the background updater (safer than
    # accessing session state from background threads). If the file exists,
    # show its content once and then remove it.
    status_file = Path("data/processed/data_auto_update_status.txt")
    try:
        if status_file.exists():
            text = status_file.read_text(encoding="utf-8").strip()
            if text.startswith("✅"):
                st.success(text)
            elif text.startswith("❌"):
                st.error(text)
            else:
                st.info(text)
            try:
                status_file.unlink()
            except Exception:
                # If deletion fails, ignore — it's just a convenience file
                pass
            return
    except Exception:
        # If anything goes wrong reading the file, fall back silently
        return


def auto_update_data():
    """
    Trigger data loading pipeline on app launch.

    Loads data from local parquet files and warms Streamlit's cache.
    Runs in background thread.
    Writes status to data/processed/data_auto_update_status.txt for UI display.
    """
    # Background worker: avoid Streamlit APIs (no st.* calls)
    # Write status file for main thread to read
    status_file = Path("data/processed/data_auto_update_status.txt")
    try:
        from src.data.ingestion import get_data_manager

        data_manager = get_data_manager()

        logger.info("Starting data loading: Load from local parquet files → Cache...")
        try:
            data_manager.preload_data()
            msg = "✅ Data loading complete: Loaded from local parquet files and cached"
            logger.info(msg)
            try:
                status_file.parent.mkdir(parents=True, exist_ok=True)
                status_file.write_text(msg, encoding="utf-8")
            except Exception:
                logger.exception("Failed to write status file")
        except Exception as e:
            logger.exception(f"Data loading process failed: {e}")
            try:
                status_file.parent.mkdir(parents=True, exist_ok=True)
                status_file.write_text(f"❌ Data loading process failed: {e}", encoding="utf-8")
            except Exception:
                pass

    except ImportError as e:
        logger.info(f"Data ingestion module not available - skipping data loading: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error during data loading: {e}")
        try:
            status_file.parent.mkdir(parents=True, exist_ok=True)
            status_file.write_text(f"❌ Data loading process failed: {e}", encoding="utf-8")
        except Exception:
            pass


# Exclude this module from navigation to avoid import recursion
_current_file = Path(__file__).name
_nav_items = [
    ("pages/1_🔎_Search.py", "Search", "🔎"),
    ("pages/2_📄_Results.py", "Results", "📄"),
    ("pages/5_👟_Quick_Start_Guide.py", "Quick Start Guide", "👟"),
    ("pages/10_🛠️_How_It_Works.py", "How It Works", "🛠️"),
    ("pages/20_📊_Data_Dashboard.py", "Data Dashboard", "📊"),
    ("pages/30_🔄_Update_Data.py", "Update Data", "🔄"),
]


def _build_and_run_app():
    """Build navigation and trigger data loading processes.

    Orchestrates daily cache refresh (synchronous) and background data loading on app launch.
    Intentionally encapsulated to prevent duplicate rendering when pages import app.
    """

    # Check for daily refresh (may trigger full data reload if after 4 AM)
    try:
        from src.data.ingestion import get_data_manager
        data_manager = get_data_manager()
        refreshed = data_manager.check_and_refresh_daily_cache()
        if refreshed:
            logger.info("Daily cache refresh triggered full data reload")
    except Exception as e:
        logger.warning(f"Could not check daily refresh on app load: {e}")

    nav_pages = [st.Page(path, title=title, icon=icon) for path, title, icon in _nav_items if path != _current_file]

    import threading

    # Run data loading in background thread to avoid blocking app startup
    try:
        thread = threading.Thread(target=auto_update_data, daemon=True)
        thread.start()
    except Exception:
        auto_update_data()  # Fallback to synchronous

    pg = st.navigation(nav_pages)
    pg.run()


if __name__ == "__main__":
    _build_and_run_app()
