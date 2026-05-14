import importlib.util
import pytest
import duckdb
from pathlib import Path

HERE = Path(__file__).parent
SCRIPT_PATH = HERE.parent.parent / "prepare_contacts" / "2__clean_and_build_db.py"

RAW_CSV = (
    "Ind_PAC_ID,Provider Last Name,Provider First Name,gndr,Cred,pri_spec,"
    "sec_spec_1,sec_spec_2,sec_spec_3,sec_spec_4,sec_spec_all,Telehlth,"
    "Facility Name,org_pac_id,adr_ln_1,adr_ln_2,City/Town,State,ZIP Code,Telephone Number\n"
    "7517003643,SMITH,JOHN,M,MD,FAMILY PRACTICE,,,,,,Y,CLINIC A,111,"
    "100 N CHARLES ST,,BALTIMORE,MD,21201,4105551234\n"
    "9931380672,DOE,JANE,F,MD,NEUROLOGY,,,,,,N,CLINIC B,222,"
    "200 S CHARLES ST,,BALTIMORE,MD,21202,4105555678\n"
    "1111111111,TEST,USER,M,MD,CARDIOLOGY,,,,,,N,CLINIC C,333,"
    "300 MAIN ST,,RICHMOND,VA,23220,8045551234\n"
)


def _load():
    spec = importlib.util.spec_from_file_location("clean_db", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def raw_csv(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text(RAW_CSV, encoding="utf-8")
    return p


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.duckdb"


def test_providers_table_created(raw_csv, db_path):
    _load().build_providers_table(raw_path=raw_csv, db_path=db_path)
    with duckdb.connect(str(db_path)) as con:
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    assert "providers" in tables


def test_filters_to_md_and_target_specialties(raw_csv, db_path):
    _load().build_providers_table(raw_path=raw_csv, db_path=db_path)
    with duckdb.connect(str(db_path)) as con:
        count = con.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
    # VA CARDIOLOGY row excluded; 2 MD rows kept
    assert count == 2


def test_address_id_is_null_initially(raw_csv, db_path):
    _load().build_providers_table(raw_path=raw_csv, db_path=db_path)
    with duckdb.connect(str(db_path)) as con:
        nulls = con.execute(
            "SELECT COUNT(*) FROM providers WHERE address_id IS NULL"
        ).fetchone()[0]
    assert nulls == 2


def test_full_address_built_correctly(raw_csv, db_path):
    _load().build_providers_table(raw_path=raw_csv, db_path=db_path)
    with duckdb.connect(str(db_path)) as con:
        addrs = sorted(
            r[0] for r in con.execute("SELECT full_address FROM providers").fetchall()
        )
    assert addrs[0] == "100 N CHARLES ST, BALTIMORE, MD 21201"
    assert addrs[1] == "200 S CHARLES ST, BALTIMORE, MD 21202"


def test_idempotent(raw_csv, db_path):
    mod = _load()
    mod.build_providers_table(raw_path=raw_csv, db_path=db_path)
    mod.build_providers_table(raw_path=raw_csv, db_path=db_path)
    with duckdb.connect(str(db_path)) as con:
        count = con.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
    assert count == 2


def test_updated_at_populated(raw_csv, db_path):
    _load().build_providers_table(raw_path=raw_csv, db_path=db_path)
    with duckdb.connect(str(db_path)) as con:
        nulls = con.execute(
            "SELECT COUNT(*) FROM providers WHERE updated_at IS NULL"
        ).fetchone()[0]
    assert nulls == 0
