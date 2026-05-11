# Provider Geocoding Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Geocode every provider's `Full Address` via Nominatim, overwrite CMS coordinates when a better result is found, persist `geocode_source` and `geocode_verified_at` to the parquet, and surface coverage metrics on the dashboard.

**Architecture:** A new `geocode_provider_dataframe()` helper in `src/utils/geocoding.py` contains all logic; a CLI script (`scripts/geocode_providers.py`) and a UI expander in the Update Data page both call it. The parquet gains two new columns (`geocode_source`, `geocode_verified_at`) that pass through the ingestion pipeline automatically — no changes to `ingestion.py` are required.

**Tech Stack:** Python 3.11, pandas, geopy (Nominatim), Streamlit, pytest

---

## File Map

| File | Action |
|---|---|
| `src/utils/geocoding.py` | Add `geocode_provider_dataframe(df, force, progress_callback)` |
| `tests/utils/test_geocoding.py` | Add 6 tests for `geocode_provider_dataframe` |
| `scripts/geocode_providers.py` | New — CLI entry point |
| `pages/20_📊_Data_Dashboard.py` | Add geocode source rows to quality metrics table + donut chart |
| `pages/30_🔄_Update_Data.py` | Add "Validate Provider Coordinates" expander |

---

## Task 1: Add `geocode_provider_dataframe()` to `src/utils/geocoding.py`

**Files:**
- Modify: `src/utils/geocoding.py`
- Test: `tests/utils/test_geocoding.py`

- [ ] **Step 1.1: Write failing tests**

Add to `tests/utils/test_geocoding.py` (keep existing tests, append these):

```python
import pandas as pd
from src.utils.geocoding import geocode_provider_dataframe


def _provider_df(**overrides):
    """Minimal provider DataFrame for geocoding tests."""
    defaults = {
        "Full Address": ["100 N Charles St, Baltimore, MD 21201"],
        "Full Name": ["Dr. Test"],
        "latitude": [39.29],
        "longitude": [-76.61],
        "geocode_source": ["cms"],
        "geocode_verified_at": [None],
    }
    defaults.update(overrides)
    return pd.DataFrame(defaults)


def test_geocode_provider_dataframe_skips_nominatim_rows():
    """Rows already marked nominatim are not re-geocoded when force=False."""
    df = _provider_df(geocode_source=["nominatim"])
    call_count = [0]

    def fake_geocoder():
        def geocode(addr, timeout=10):
            call_count[0] += 1
            loc = MagicMock()
            loc.latitude = 99.0
            loc.longitude = 99.0
            return loc
        return geocode

    with patch("src.utils.geocoding._get_rate_limited_geocoder", fake_geocoder):
        result = geocode_provider_dataframe(df, force=False)

    assert call_count[0] == 0
    assert result.loc[0, "latitude"] == pytest.approx(39.29)


def test_geocode_provider_dataframe_force_regeocodesall():
    """force=True re-geocodes rows already marked nominatim."""
    df = _provider_df(geocode_source=["nominatim"])
    call_count = [0]

    def fake_geocoder():
        def geocode(addr, timeout=10):
            call_count[0] += 1
            loc = MagicMock()
            loc.latitude = 40.0
            loc.longitude = -77.0
            return loc
        return geocode

    with patch("src.utils.geocoding._get_rate_limited_geocoder", fake_geocoder):
        result = geocode_provider_dataframe(df, force=True)

    assert call_count[0] == 1
    assert result.loc[0, "latitude"] == pytest.approx(40.0)
    assert result.loc[0, "geocode_source"] == "nominatim"


def test_geocode_provider_dataframe_updates_coords_on_success():
    """Successful geocode overwrites lat/lon and sets source to nominatim."""
    df = _provider_df(latitude=[0.0], longitude=[0.0])

    def fake_geocoder():
        def geocode(addr, timeout=10):
            loc = MagicMock()
            loc.latitude = 39.29
            loc.longitude = -76.61
            return loc
        return geocode

    with patch("src.utils.geocoding._get_rate_limited_geocoder", fake_geocoder):
        result = geocode_provider_dataframe(df)

    assert result.loc[0, "latitude"] == pytest.approx(39.29)
    assert result.loc[0, "longitude"] == pytest.approx(-76.61)
    assert result.loc[0, "geocode_source"] == "nominatim"
    assert result.loc[0, "geocode_verified_at"] is not None


def test_geocode_provider_dataframe_sets_cms_on_none():
    """Geocoder returning None sets source to cms and preserves existing coords."""
    df = _provider_df()

    with patch("src.utils.geocoding._get_rate_limited_geocoder", lambda: (lambda addr, timeout=10: None)):
        result = geocode_provider_dataframe(df)

    assert result.loc[0, "geocode_source"] == "cms"
    assert result.loc[0, "latitude"] == pytest.approx(39.29)


def test_geocode_provider_dataframe_sets_failed_on_exception():
    """Geocoder exception sets source to failed and preserves existing coords."""
    df = _provider_df()

    def fake_geocoder():
        def raise_timeout(addr, timeout=10):
            raise GeocoderTimedOut("timeout")
        return raise_timeout

    with patch("src.utils.geocoding._get_rate_limited_geocoder", fake_geocoder):
        result = geocode_provider_dataframe(df)

    assert result.loc[0, "geocode_source"] == "failed"
    assert result.loc[0, "latitude"] == pytest.approx(39.29)


def test_geocode_provider_dataframe_initializes_missing_columns():
    """DataFrames without geocode columns get them added."""
    df = pd.DataFrame({
        "Full Address": ["100 N Charles St, Baltimore, MD 21201"],
        "Full Name": ["Dr. Test"],
        "latitude": [39.29],
        "longitude": [-76.61],
    })

    with patch("src.utils.geocoding._get_rate_limited_geocoder", lambda: (lambda addr, timeout=10: None)):
        result = geocode_provider_dataframe(df)

    assert "geocode_source" in result.columns
    assert "geocode_verified_at" in result.columns
```

- [ ] **Step 1.2: Run tests to verify they fail**

```
pytest tests/utils/test_geocoding.py -k "geocode_provider_dataframe" -v
```

Expected: `ImportError` or `AttributeError` — `geocode_provider_dataframe` does not exist yet.

- [ ] **Step 1.3: Implement `geocode_provider_dataframe` in `src/utils/geocoding.py`**

Append this function before the `__all__` line at the bottom of `src/utils/geocoding.py`:

```python
def geocode_provider_dataframe(
    df: pd.DataFrame,
    force: bool = False,
    progress_callback=None,
) -> pd.DataFrame:
    """Geocode provider Full Address values and annotate with source/timestamp.

    For each row (skipping geocode_source=='nominatim' rows unless force=True):
      - Nominatim returns location → update latitude/longitude, source='nominatim'
      - Nominatim returns None     → keep existing coords, source='cms'
      - Nominatim raises exception → keep existing coords, source='failed'
    geocode_verified_at is set to the current UTC timestamp in all processed rows.

    Args:
        df: DataFrame with 'Full Address', 'latitude', 'longitude' columns.
        force: Re-geocode rows already marked 'nominatim' when True.
        progress_callback: Optional callable(current, total, name, source).

    Returns:
        Copy of df with updated latitude, longitude, geocode_source, geocode_verified_at.
    """
    import pandas as pd
    from datetime import datetime, timezone

    result = df.copy()
    if "geocode_source" not in result.columns:
        result["geocode_source"] = "cms"
    if "geocode_verified_at" not in result.columns:
        result["geocode_verified_at"] = None

    geocode_fn = _get_rate_limited_geocoder()
    total = len(result)

    for i, (idx, row) in enumerate(result.iterrows()):
        if not force and row.get("geocode_source") == "nominatim":
            if progress_callback:
                progress_callback(i + 1, total, str(row.get("Full Name", "")), "nominatim")
            continue

        address = str(row.get("Full Address", "")).strip()
        now = datetime.now(timezone.utc).isoformat()

        if not address:
            result.at[idx, "geocode_source"] = "failed"
            result.at[idx, "geocode_verified_at"] = now
            if progress_callback:
                progress_callback(i + 1, total, str(row.get("Full Name", "")), "failed")
            continue

        try:
            location = geocode_fn(_normalize_address(address))
            if location:
                result.at[idx, "latitude"] = location.latitude
                result.at[idx, "longitude"] = location.longitude
                source = "nominatim"
            else:
                source = "cms"
        except Exception:
            source = "failed"

        result.at[idx, "geocode_source"] = source
        result.at[idx, "geocode_verified_at"] = now

        if progress_callback:
            progress_callback(i + 1, total, str(row.get("Full Name", "")), source)

    return result
```

Also update the `__all__` list at the bottom:

```python
__all__ = ["geocode_address", "geocode_provider_dataframe", "handle_geocoding_error"]
```

- [ ] **Step 1.4: Run tests to verify they pass**

```
pytest tests/utils/test_geocoding.py -v
```

Expected: All 16 tests pass (10 existing + 6 new).

- [ ] **Step 1.5: Commit**

```bash
git add src/utils/geocoding.py tests/utils/test_geocoding.py
git commit -m "feat: add geocode_provider_dataframe helper with source/timestamp tracking"
```

---

## Task 2: Create CLI script `scripts/geocode_providers.py`

**Files:**
- Create: `scripts/geocode_providers.py`
- Create: `scripts/__init__.py` (empty, makes scripts importable)

- [ ] **Step 2.1: Create the `scripts/` directory and `__init__.py`**

```bash
mkdir scripts
```

Create `scripts/__init__.py` as an empty file.

- [ ] **Step 2.2: Create `scripts/geocode_providers.py`**

```python
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

    # Atomic write: write to temp, then replace original
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
```

- [ ] **Step 2.3: Smoke-test the script (dry run with `--help`)**

```
python scripts/geocode_providers.py --help
```

Expected output:
```
usage: geocode_providers.py [-h] [--force]

Validate and update provider geocoordinates from Full Address strings.

options:
  -h, --help  show this help message and exit
  --force     Re-geocode rows already marked nominatim (default: skip them)
```

- [ ] **Step 2.4: Commit**

```bash
git add scripts/__init__.py scripts/geocode_providers.py
git commit -m "feat: add geocode_providers CLI script with resumable run and atomic write"
```

---

## Task 3: Add geocode source metrics to the Data Dashboard

**Files:**
- Modify: `pages/20_📊_Data_Dashboard.py`

The dashboard loads provider data via `data_manager.load_data(DataSource.PROVIDER_DATA)`. After the ingestion pipeline runs, this DataFrame has `geocode_source` (lowercase, passed through from parquet) and `Latitude`/`Longitude` (title-case, from the column mapping in `_transform_combined_data`).

- [ ] **Step 3.1: Add geocode source rows to the quality metrics table**

In `pages/20_📊_Data_Dashboard.py`, find the block that builds `quality_metrics` (around line 185). After the existing "Geographic Coordinates" entry (the `if "Latitude" in provider_df.columns` block), add this block:

```python
            # Geocode source breakdown (only when geocode_source column exists)
            if "geocode_source" in provider_df.columns:
                source_counts = provider_df["geocode_source"].value_counts()
                for source_label, col_key in [
                    ("Coordinates — Nominatim verified", "nominatim"),
                    ("Coordinates — CMS only", "cms"),
                    ("Coordinates — Failed", "failed"),
                ]:
                    count = int(source_counts.get(col_key, 0))
                    pct = (count / total_records * 100) if total_records > 0 else 0
                    quality_metrics.append({
                        "Metric": source_label,
                        "Complete Records": count,
                        "Total Records": total_records,
                        "Completeness": f"{pct:.1f}%",
                    })
```

- [ ] **Step 3.2: Add the "Coordinate Source" donut chart**

Find the existing `coord_quality_fig` donut chart block (the one titled "Coordinate Completeness", around line 367). Replace the `with col2:` block that contains it with this expanded version showing both charts side by side:

```python
            with col2:
                st.markdown("### Coordinate Quality")
                total_providers_map = len(provider_df)
                valid_coords_map = len(valid_coords)
                missing_coords_map = total_providers_map - valid_coords_map

                coord_quality_fig = go.Figure(
                    data=[
                        go.Pie(
                            labels=["Valid Coordinates", "Missing Coordinates"],
                            values=[valid_coords_map, missing_coords_map],
                            hole=0.4,
                        )
                    ]
                )
                coord_quality_fig.update_layout(title="Coordinate Completeness")
                st.plotly_chart(coord_quality_fig, use_container_width=True, config=PLOTLY_CONFIG)

                if "geocode_source" in provider_df.columns:
                    source_counts = provider_df["geocode_source"].value_counts()
                    source_fig = go.Figure(
                        data=[
                            go.Pie(
                                labels=["Nominatim", "CMS", "Failed"],
                                values=[
                                    int(source_counts.get("nominatim", 0)),
                                    int(source_counts.get("cms", 0)),
                                    int(source_counts.get("failed", 0)),
                                ],
                                hole=0.4,
                                marker_colors=["#2ecc71", "#3498db", "#e74c3c"],
                            )
                        ]
                    )
                    source_fig.update_layout(title="Coordinate Source")
                    st.plotly_chart(source_fig, use_container_width=True, config=PLOTLY_CONFIG)
```

- [ ] **Step 3.3: Verify the dashboard renders without error**

Start the app and navigate to the Data Dashboard page:

```
streamlit run app.py
```

Before running the geocoding script, `geocode_source` won't exist in the parquet, so the new blocks should silently be skipped (the `if "geocode_source" in provider_df.columns` guards protect them). Confirm no errors appear.

- [ ] **Step 3.4: Commit**

```bash
git add "pages/20_📊_Data_Dashboard.py"
git commit -m "feat: add geocode source breakdown metrics and donut chart to dashboard"
```

---

## Task 4: Add "Validate Provider Coordinates" expander to Update Data page

**Files:**
- Modify: `pages/30_🔄_Update_Data.py`

- [ ] **Step 4.1: Add the geocoding expander**

At the bottom of `pages/30_🔄_Update_Data.py`, append:

```python
st.markdown("---")

st.markdown("#### 🌐 Validate Provider Coordinates")
st.markdown(
    "Geocode each provider's address via Nominatim and compare against CMS coordinates. "
    "Results are saved back to the parquet file and the cache is refreshed automatically."
)
st.warning(
    "⏱️ A full validation run takes approximately 41 minutes for 2,469 providers "
    "(Nominatim rate limit: 1 request/second). Use **Validate Unverified Only** for fast incremental updates."
)

with st.expander("📍 Validate Provider Coordinates", expanded=False):
    # Show current geocode coverage
    try:
        from pathlib import Path as _Path
        import pandas as _pd

        _parquet = _Path("data/processed/Combined_Contacts_and_Reviews.parquet")
        if _parquet.exists():
            _df_preview = _pd.read_parquet(_parquet)
            if "geocode_source" in _df_preview.columns:
                _counts = _df_preview["geocode_source"].value_counts()
                st.markdown("**Current geocode coverage:**")
                gcol1, gcol2, gcol3 = st.columns(3)
                with gcol1:
                    st.metric("✅ Nominatim verified", int(_counts.get("nominatim", 0)))
                with gcol2:
                    st.metric("🔵 CMS only", int(_counts.get("cms", 0)))
                with gcol3:
                    st.metric("❌ Failed", int(_counts.get("failed", 0)))
            else:
                st.info("No geocode data yet. Run validation to populate.")
    except Exception:
        st.info("Could not read current geocode status.")

    col_a, col_b = st.columns(2)

    with col_a:
        run_incremental = st.button(
            "🔍 Validate Unverified Providers",
            key="geocode_incremental",
            help="Skip rows already marked as Nominatim-verified. Fast for incremental updates.",
        )

    with col_b:
        run_full = st.button(
            "🔄 Re-validate All Providers",
            key="geocode_full",
            help="Re-geocode every provider regardless of existing source. Takes ~41 minutes.",
        )

    if run_incremental or run_full:
        force = run_full
        import os
        import tempfile
        import pandas as pd
        from pathlib import Path
        from src.utils.geocoding import geocode_provider_dataframe
        from src.data.ingestion import refresh_data_cache

        parquet_path = Path("data/processed/Combined_Contacts_and_Reviews.parquet")

        if not parquet_path.exists():
            st.error("❌ Parquet file not found. Please upload data first.")
        else:
            df = pd.read_parquet(parquet_path)
            total = len(df)
            progress_bar = st.progress(0.0, text="Starting geocoding...")

            def _ui_progress(current, total_count, name, source):
                pct = current / total_count
                symbol = "✓" if source == "nominatim" else ("~" if source == "cms" else "✗")
                progress_bar.progress(pct, text=f"[{current}/{total_count}] {name} — {symbol} {source}")

            with st.spinner("Geocoding providers..."):
                result_df = geocode_provider_dataframe(df, force=force, progress_callback=_ui_progress)

            # Atomic write
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".parquet", dir=parquet_path.parent)
            try:
                os.close(tmp_fd)
                result_df.to_parquet(tmp_path, index=False)
                os.replace(tmp_path, parquet_path)
            except Exception as exc:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                st.error(f"❌ Failed to save results: {exc}")
                st.stop()

            refresh_data_cache()
            progress_bar.progress(1.0, text="Done!")

            final_counts = result_df["geocode_source"].value_counts()
            nominatim_n = int(final_counts.get("nominatim", 0))
            cms_n = int(final_counts.get("cms", 0))
            failed_n = int(final_counts.get("failed", 0))

            st.success(
                f"✅ Geocoding complete: **{nominatim_n} Nominatim**, "
                f"**{cms_n} CMS fallback**, **{failed_n} failed**"
            )
            st.info("💡 Navigate to the Data Dashboard to see updated coordinate source metrics.")
```

- [ ] **Step 4.2: Verify the Update Data page renders without error**

Navigate to the Update Data page in the running app. The expander should appear and show either the coverage metrics (if `geocode_source` exists in the parquet) or the "No geocode data yet" message.

- [ ] **Step 4.3: Commit**

```bash
git add "pages/30_🔄_Update_Data.py"
git commit -m "feat: add Validate Provider Coordinates expander to Update Data page"
```



---

## Task 5: End-to-end verification

- [ ] **Step 5.1: Run the full test suite**

```
pytest tests/ -v
```

Expected: All tests pass. No regressions in existing geocoding or scoring tests.

- [ ] **Step 5.2: Run the CLI script in resumable mode**

```
python scripts/geocode_providers.py
```

Expected: Script prints progress lines and a final summary. Parquet file is updated with `geocode_source` and `geocode_verified_at` columns.

- [ ] **Step 5.3: Verify parquet columns were written**

```python
python -c "
import pandas as pd
df = pd.read_parquet('data/processed/Combined_Contacts_and_Reviews.parquet')
print(df[['Full Address','latitude','longitude','geocode_source','geocode_verified_at']].head(5).to_string())
print(df['geocode_source'].value_counts())
"
```

Expected: `geocode_source` column present with values `nominatim`, `cms`, or `failed`. `geocode_verified_at` populated with ISO timestamps.

- [ ] **Step 5.4: Verify dashboard geocode metrics appear**

Reload the Data Dashboard page. The quality metrics table should now include the three geocode source rows, and the "Coordinate Source" donut chart should appear next to the existing completeness chart.

- [ ] **Step 5.5: Final commit**

```bash
git add -A
git commit -m "test: verify geocoding validation end-to-end"
```
