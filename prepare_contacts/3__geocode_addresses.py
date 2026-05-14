"""Step 2: Geocode unique provider addresses via Census batch API and update DuckDB."""
import csv
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
ROOT = HERE.parent
DEFAULT_DB_PATH = ROOT / "data" / "processed" / "medmatch.duckdb"
DEFAULT_CACHE_PATH = ROOT / "data" / "processed" / "geocode_cache.csv"
DEFAULT_ZIP_CENTROIDS_PATH = ROOT / "data" / "processed" / "zip_centroids.csv"

CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
CENSUS_BENCHMARK = "Public_AR_Current"
BATCH_SIZE = 1000

_CACHE_FIELDS = [
    "full_address", "latitude", "longitude", "geocode_source",
    "match_score", "match_type", "matched_address", "geocoded_at",
]


def _parse_full_address(full_address: str) -> Tuple[str, str, str, str]:
    """Parse 'STREET, CITY, STATE ZIP' into (street, city, state, zip_code)."""
    parts = [p.strip() for p in full_address.split(",")]
    if len(parts) < 3:
        return full_address, "", "", ""
    state_zip = parts[-1].split()
    state = state_zip[0] if state_zip else ""
    zip_code = state_zip[1] if len(state_zip) > 1 else ""
    city = parts[-2]
    street = ", ".join(parts[:-2])
    return street, city, state, zip_code


def _parse_census_response(response_text: str) -> List[dict]:
    """Parse Census Geocoder batch CSV response. Returns list of result dicts.

    Census response columns (no header):
      id, input_address, match_status, match_type, matched_address,
      coordinates (lon,lat), tiger_line_id, tiger_line_side
    Coordinates are LON,LAT — note the order.
    """
    results = []
    for row in csv.reader(io.StringIO(response_text)):
        if len(row) < 3:
            continue
        rec_id = row[0].strip()
        match_status = row[2].strip()
        match_type = row[3].strip() if len(row) > 3 else ""
        matched_address = row[4].strip() if len(row) > 4 else ""
        coords = row[5].strip() if len(row) > 5 else ""

        lat: Optional[float] = None
        lon: Optional[float] = None
        if coords and match_status == "Match":
            parts = coords.split(",")
            if len(parts) == 2:
                lon = float(parts[0])  # Census: longitude first
                lat = float(parts[1])

        match_score: Optional[int] = None
        if match_status == "Match":
            match_score = 100 if match_type == "Exact" else 50

        results.append({
            "rec_id": rec_id,
            "match_status": match_status,
            "match_type": match_type,
            "matched_address": matched_address,
            "latitude": lat,
            "longitude": lon,
            "match_score": match_score,
        })
    return results


def _load_cache(cache_path: Path) -> Dict[str, dict]:
    if not cache_path.exists():
        return {}
    with open(cache_path, newline="", encoding="utf-8") as f:
        return {row["full_address"]: row for row in csv.DictReader(f)}


def _append_cache(cache_path: Path, results: List[dict]) -> None:
    write_header = not cache_path.exists()
    with open(cache_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CACHE_FIELDS)
        if write_header:
            writer.writeheader()
        for r in results:
            writer.writerow({k: r.get(k, "") for k in _CACHE_FIELDS})


def _load_zip_centroids(path: Path) -> Dict[str, Tuple[float, float]]:
    with open(path, newline="", encoding="utf-8") as f:
        return {
            row["zip_code"]: (float(row["latitude"]), float(row["longitude"]))
            for row in csv.DictReader(f)
        }


def _batch_geocode_census(batch: List[Tuple[str, str]]) -> List[dict]:
    """POST one batch to Census Geocoder. batch = [(rec_id, full_address), ...]"""
    lines = []
    for rec_id, full_addr in batch:
        street, city, state, zip_code = _parse_full_address(full_addr)
        lines.append(f'"{rec_id}","{street}","{city}","{state}","{zip_code}"')
    csv_content = "\n".join(lines)

    response = requests.post(
        CENSUS_BATCH_URL,
        files={"addressFile": ("addresses.csv", csv_content, "text/csv")},
        data={"benchmark": CENSUS_BENCHMARK},
        timeout=120,
    )
    response.raise_for_status()
    return _parse_census_response(response.text)


def _write_to_duckdb(db_path: Path, results_by_addr: Dict[str, dict]) -> None:
    """Write addresses table and update providers.address_id FK."""
    import pandas as pd

    now = datetime.now(timezone.utc)
    rows = []
    for i, (full_address, r) in enumerate(results_by_addr.items(), start=1):
        street, city, state, zip_code = _parse_full_address(full_address)
        lat = r.get("latitude")
        lon = r.get("longitude")
        score = r.get("match_score")
        rows.append({
            "address_id": i,
            "full_address": full_address,
            "adr_ln_1": street,
            "adr_ln_2": None,
            "city": city,
            "state": state,
            "zip_code": zip_code,
            "latitude": float(lat) if lat not in (None, "") else None,
            "longitude": float(lon) if lon not in (None, "") else None,
            "geocode_source": r.get("geocode_source"),
            "match_score": float(score) if score not in (None, "") else None,
            "match_type": r.get("match_type"),
            "matched_address": r.get("matched_address"),
            "geocoded_at": r.get("geocoded_at"),
            "updated_at": now,
        })

    df_addr = pd.DataFrame(rows)

    with duckdb.connect(str(db_path)) as con:
        con.execute("DROP TABLE IF EXISTS addresses")
        con.execute("""
            CREATE TABLE addresses (
                address_id      INTEGER PRIMARY KEY,
                full_address    VARCHAR NOT NULL UNIQUE,
                adr_ln_1        VARCHAR,
                adr_ln_2        VARCHAR,
                city            VARCHAR,
                state           VARCHAR,
                zip_code        VARCHAR,
                latitude        DOUBLE,
                longitude       DOUBLE,
                geocode_source  VARCHAR,
                match_score     DOUBLE,
                match_type      VARCHAR,
                matched_address VARCHAR,
                geocoded_at     TIMESTAMP,
                updated_at      TIMESTAMP
            )
        """)
        con.register("addr_view", df_addr)
        con.execute("""
            INSERT INTO addresses (
                address_id, full_address, adr_ln_1, adr_ln_2, city, state,
                zip_code, latitude, longitude, geocode_source, match_score,
                match_type, matched_address, geocoded_at, updated_at
            )
            SELECT * FROM addr_view
        """)

        con.execute("""
            UPDATE providers
            SET address_id = (
                SELECT address_id FROM addresses
                WHERE addresses.full_address = providers.full_address
            )
        """)
        updated = con.execute(
            "SELECT COUNT(*) FROM providers WHERE address_id IS NOT NULL"
        ).fetchone()[0]
        logger.info(f"Set address_id FK for {updated} providers")


def geocode_addresses(
    db_path: Path = DEFAULT_DB_PATH,
    cache_path: Path = DEFAULT_CACHE_PATH,
    zip_centroids_path: Path = DEFAULT_ZIP_CENTROIDS_PATH,
    batch_size: int = BATCH_SIZE,
) -> dict:
    """Geocode unique addresses and update DuckDB. Returns stats dict."""
    with duckdb.connect(str(db_path)) as con:
        unique_addresses: List[str] = [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT full_address FROM providers "
                "WHERE full_address IS NOT NULL"
            ).fetchall()
        ]

    cache = _load_cache(cache_path)
    uncached = [
        (str(i), addr)
        for i, addr in enumerate(unique_addresses)
        if addr not in cache
    ]

    zip_centroids = _load_zip_centroids(zip_centroids_path)
    now = datetime.now(timezone.utc).isoformat()
    new_results: List[dict] = []

    for i in range(0, len(uncached), batch_size):
        batch = uncached[i : i + batch_size]
        logger.info(f"Batch {i // batch_size + 1}: geocoding {len(batch)} addresses")
        addr_by_id = {rec_id: addr for rec_id, addr in batch}

        try:
            api_results = _batch_geocode_census(batch)
        except Exception as exc:
            logger.error(f"Census API error: {exc}")
            for _, addr in batch:
                new_results.append({
                    "full_address": addr, "latitude": None, "longitude": None,
                    "geocode_source": "failed", "match_score": None,
                    "match_type": "No_Match", "matched_address": "", "geocoded_at": now,
                })
            continue

        for result in api_results:
            addr = addr_by_id.get(result["rec_id"], "")
            if result["match_status"] == "Match":
                new_results.append({
                    "full_address": addr,
                    "latitude": result["latitude"],
                    "longitude": result["longitude"],
                    "geocode_source": "census",
                    "match_score": result["match_score"],
                    "match_type": result["match_type"],
                    "matched_address": result["matched_address"],
                    "geocoded_at": now,
                })
            else:
                _, _, _, zip_code = _parse_full_address(addr)
                centroid = zip_centroids.get(zip_code)
                if centroid:
                    new_results.append({
                        "full_address": addr,
                        "latitude": centroid[0], "longitude": centroid[1],
                        "geocode_source": "fallback_zip",
                        "match_score": None, "match_type": "No_Match",
                        "matched_address": "", "geocoded_at": now,
                    })
                else:
                    new_results.append({
                        "full_address": addr,
                        "latitude": None, "longitude": None,
                        "geocode_source": "failed",
                        "match_score": None, "match_type": "No_Match",
                        "matched_address": "", "geocoded_at": now,
                    })

    if new_results:
        _append_cache(cache_path, new_results)

    all_results: Dict[str, dict] = {r["full_address"]: r for r in cache.values()}
    all_results.update({r["full_address"]: r for r in new_results})

    _write_to_duckdb(db_path, all_results)

    stats = {
        "total": len(all_results),
        "matched": sum(1 for r in all_results.values() if r.get("geocode_source") == "census"),
        "fallback": sum(1 for r in all_results.values() if r.get("geocode_source") == "fallback_zip"),
        "failed": sum(1 for r in all_results.values() if r.get("geocode_source") == "failed"),
    }
    logger.info(
        f"Complete: {stats['total']} addresses | "
        f"{stats['matched']} matched | {stats['fallback']} fallback | {stats['failed']} failed"
    )
    return stats


def main():
    geocode_addresses()


if __name__ == "__main__":
    main()
