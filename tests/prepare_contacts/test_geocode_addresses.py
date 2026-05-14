import csv
import importlib.util
import pytest
import duckdb
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).parent
SCRIPT_PATH = HERE.parent.parent / "prepare_contacts" / "3__geocode_addresses.py"


def _load():
    spec = importlib.util.spec_from_file_location("geocode_addr", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_db(tmp_path, full_address: str) -> Path:
    """Create a minimal providers-only DuckDB for testing."""
    db_path = tmp_path / "test.duckdb"
    with duckdb.connect(str(db_path)) as con:
        con.execute("""
            CREATE TABLE providers (
                ind_pac_id VARCHAR, last_name VARCHAR, first_name VARCHAR,
                gender VARCHAR, credential VARCHAR, pri_spec VARCHAR,
                sec_spec_all VARCHAR, telehealth VARCHAR, facility_name VARCHAR,
                org_pac_id VARCHAR, telephone VARCHAR,
                full_address VARCHAR, address_id INTEGER, updated_at TIMESTAMP
            )
        """)
        con.execute(
            "INSERT INTO providers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ["1","SMITH","JOHN","M","MD","FAMILY PRACTICE","","Y","CLINIC",
             "1","4105551234", full_address, None, None],
        )
    return db_path


def _zip_centroids(tmp_path, zip_code="21201", lat=39.29, lon=-76.61) -> Path:
    p = tmp_path / "zip_centroids.csv"
    p.write_text(f"zip_code,latitude,longitude\n{zip_code},{lat},{lon}\n")
    return p


# ── _parse_full_address ────────────────────────────────────────────────────────

def test_parse_full_address_standard():
    mod = _load()
    street, city, state, zip_code = mod._parse_full_address(
        "100 N CHARLES ST, BALTIMORE, MD 21201"
    )
    assert street == "100 N CHARLES ST"
    assert city == "BALTIMORE"
    assert state == "MD"
    assert zip_code == "21201"


def test_parse_full_address_street_with_comma():
    mod = _load()
    street, city, state, zip_code = mod._parse_full_address(
        "100 N CHARLES ST STE 200, BALTIMORE, MD 21201"
    )
    assert city == "BALTIMORE"
    assert state == "MD"
    assert zip_code == "21201"


# ── _parse_census_response ────────────────────────────────────────────────────

def test_parse_census_response_exact_match():
    mod = _load()
    text = (
        '"0","100 N Charles St, Baltimore, MD 21201","Match","Exact",'
        '"100 N CHARLES ST, BALTIMORE, MD, 21201","-76.6138,39.2909",110398442,R\n'
    )
    results = mod._parse_census_response(text)
    assert len(results) == 1
    r = results[0]
    assert r["match_status"] == "Match"
    assert r["match_type"] == "Exact"
    assert r["latitude"] == pytest.approx(39.2909)
    assert r["longitude"] == pytest.approx(-76.6138)
    assert r["match_score"] == 100


def test_parse_census_response_non_exact_score_is_50():
    mod = _load()
    text = (
        '"0","100 N Charles St, Baltimore, MD 21201","Match","Non_Exact",'
        '"100 N CHARLES ST, BALTIMORE, MD, 21201","-76.6138,39.2909",110398442,R\n'
    )
    results = mod._parse_census_response(text)
    assert results[0]["match_score"] == 50


def test_parse_census_response_no_match():
    mod = _load()
    text = '"1","bad addr, nowhere, XX 00000","No_Match",,,,,\n'
    results = mod._parse_census_response(text)
    r = results[0]
    assert r["match_status"] == "No_Match"
    assert r["latitude"] is None
    assert r["match_score"] is None


def test_parse_census_response_lon_lat_order():
    """Census returns lon,lat — verify we assign them correctly."""
    mod = _load()
    text = (
        '"0","test","Match","Exact","test addr","-77.0000,39.0000",1,R\n'
    )
    results = mod._parse_census_response(text)
    assert results[0]["longitude"] == pytest.approx(-77.0)
    assert results[0]["latitude"] == pytest.approx(39.0)


# ── cache behaviour ───────────────────────────────────────────────────────────

def test_cache_hit_skips_census_api(tmp_path):
    mod = _load()
    addr = "100 N CHARLES ST, BALTIMORE, MD 21201"

    cache_path = tmp_path / "cache.csv"
    with open(cache_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "full_address","latitude","longitude","geocode_source",
            "match_score","match_type","matched_address","geocoded_at",
        ])
        w.writeheader()
        w.writerow({
            "full_address": addr, "latitude": 39.29, "longitude": -76.61,
            "geocode_source": "census", "match_score": 100,
            "match_type": "Exact", "matched_address": addr,
            "geocoded_at": "2026-05-14T00:00:00+00:00",
        })

    db_path = _make_db(tmp_path, addr)
    zip_path = _zip_centroids(tmp_path)

    with patch("requests.post") as mock_post:
        mod.geocode_addresses(
            db_path=db_path, cache_path=cache_path, zip_centroids_path=zip_path
        )
        mock_post.assert_not_called()


# ── fallback ──────────────────────────────────────────────────────────────────

def test_no_match_falls_back_to_zip_centroid(tmp_path):
    mod = _load()
    addr = "999 UNKNOWN ST, BALTIMORE, MD 21201"
    db_path = _make_db(tmp_path, addr)
    zip_path = _zip_centroids(tmp_path, zip_code="21201", lat=39.29, lon=-76.61)
    cache_path = tmp_path / "cache.csv"

    resp = MagicMock()
    resp.text = f'"0","{addr}","No_Match",,,,,\n'
    resp.raise_for_status = lambda: None

    with patch("requests.post", return_value=resp):
        stats = mod.geocode_addresses(
            db_path=db_path, cache_path=cache_path, zip_centroids_path=zip_path
        )

    assert stats["fallback"] == 1
    with duckdb.connect(str(db_path)) as con:
        row = con.execute(
            "SELECT geocode_source, latitude FROM addresses LIMIT 1"
        ).fetchone()
    assert row[0] == "fallback_zip"
    assert row[1] == pytest.approx(39.29)


def test_no_match_no_centroid_is_failed(tmp_path):
    mod = _load()
    addr = "999 UNKNOWN ST, NOWHERE, XX 99999"
    db_path = _make_db(tmp_path, addr)
    zip_path = tmp_path / "zip_centroids.csv"
    zip_path.write_text("zip_code,latitude,longitude\n")  # empty — no 99999
    cache_path = tmp_path / "cache.csv"

    resp = MagicMock()
    resp.text = f'"0","{addr}","No_Match",,,,,\n'
    resp.raise_for_status = lambda: None

    with patch("requests.post", return_value=resp):
        stats = mod.geocode_addresses(
            db_path=db_path, cache_path=cache_path, zip_centroids_path=zip_path
        )

    assert stats["failed"] == 1


# ── DuckDB FK update ──────────────────────────────────────────────────────────

def test_providers_address_id_fk_set_after_geocoding(tmp_path):
    mod = _load()
    addr = "100 N CHARLES ST, BALTIMORE, MD 21201"
    db_path = _make_db(tmp_path, addr)
    zip_path = _zip_centroids(tmp_path)
    cache_path = tmp_path / "cache.csv"

    resp = MagicMock()
    resp.text = (
        f'"0","{addr}","Match","Exact",'
        f'"100 N CHARLES ST, BALTIMORE, MD, 21201","-76.6138,39.2909",110398442,R\n'
    )
    resp.raise_for_status = lambda: None

    with patch("requests.post", return_value=resp):
        mod.geocode_addresses(
            db_path=db_path, cache_path=cache_path, zip_centroids_path=zip_path
        )

    with duckdb.connect(str(db_path)) as con:
        row = con.execute(
            "SELECT p.address_id, a.geocode_source "
            "FROM providers p JOIN addresses a ON p.address_id = a.address_id"
        ).fetchone()
    assert row is not None
    assert row[1] == "census"


def test_new_results_appended_to_cache(tmp_path):
    mod = _load()
    addr = "100 N CHARLES ST, BALTIMORE, MD 21201"
    db_path = _make_db(tmp_path, addr)
    zip_path = _zip_centroids(tmp_path)
    cache_path = tmp_path / "cache.csv"

    resp = MagicMock()
    resp.text = (
        f'"0","{addr}","Match","Exact",'
        f'"100 N CHARLES ST, BALTIMORE, MD, 21201","-76.6138,39.2909",110398442,R\n'
    )
    resp.raise_for_status = lambda: None

    with patch("requests.post", return_value=resp):
        mod.geocode_addresses(
            db_path=db_path, cache_path=cache_path, zip_centroids_path=zip_path
        )

    assert cache_path.exists()
    with open(cache_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["full_address"] == addr
    assert rows[0]["geocode_source"] == "census"
