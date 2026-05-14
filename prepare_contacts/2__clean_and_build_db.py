"""Step 2: Clean raw provider data and write the initial providers table to DuckDB."""
import importlib.util
import logging
from datetime import datetime, timezone
from pathlib import Path

import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
ROOT = HERE.parent
DEFAULT_RAW_PATH = ROOT / "data" / "raw" / "data.csv"
DEFAULT_DB_PATH = ROOT / "data" / "processed" / "medmatch.duckdb"


_cleaning_module = None

def _load_cleaning_module():
    global _cleaning_module
    if _cleaning_module is None:
        script = HERE / "1__Cleaning_Providers_List.py"
        spec = importlib.util.spec_from_file_location("cleaning", script)
        _cleaning_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_cleaning_module)
    return _cleaning_module


def build_providers_table(
    raw_path: Path = DEFAULT_RAW_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    """Clean raw data and write providers table to DuckDB. Returns row count."""
    cleaning = _load_cleaning_module()
    df = cleaning.load_raw_provider_data(raw_path)
    df = cleaning.clean_provider_data(
        df,
        states=cleaning.DEFAULT_STATES,
        specialties=cleaning.DEFAULT_SPECIALTIES,
    )

    db_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    with duckdb.connect(str(db_path)) as con:
        con.execute("DROP TABLE IF EXISTS providers")
        con.execute("""
            CREATE TABLE providers (
                ind_pac_id    VARCHAR,
                last_name     VARCHAR,
                first_name    VARCHAR,
                gender        VARCHAR,
                credential    VARCHAR,
                pri_spec      VARCHAR,
                sec_spec_all  VARCHAR,
                telehealth    VARCHAR,
                facility_name VARCHAR,
                org_pac_id    VARCHAR,
                telephone     VARCHAR,
                full_address  VARCHAR,
                address_id    INTEGER,
                updated_at    TIMESTAMP
            )
        """)
        con.register("df_view", df)
        con.execute("""
            INSERT INTO providers (
                ind_pac_id, last_name, first_name, gender, credential,
                pri_spec, sec_spec_all, telehealth, facility_name, org_pac_id,
                telephone, full_address, address_id, updated_at
            )
            SELECT
                CAST("Ind_PAC_ID"       AS VARCHAR),
                "Provider Last Name",
                "Provider First Name",
                gndr,
                "Cred",
                pri_spec,
                sec_spec_all,
                "Telehlth",
                "Facility Name",
                CAST(org_pac_id         AS VARCHAR),
                "Telephone Number",
                "Full Address",
                NULL,
                ?
            FROM df_view
        """, [now])
        row_count = con.execute("SELECT COUNT(*) FROM providers").fetchone()[0]

    logger.info(f"Wrote {row_count} providers to {db_path}")
    return row_count


def main():
    count = build_providers_table()
    logger.info(f"Done. {count} providers written to medmatch.duckdb.")


if __name__ == "__main__":
    main()
