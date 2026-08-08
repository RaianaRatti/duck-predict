'''
Overall: This file is project's database helper. It handles putting clean CAISO data into DuckDB and getting it back out when DuckPredict needs it

Note: We are using DuckDB > SQLite because workload (duck-curve heatmap + model's feature table) require group-by aggregations which DuckDB does fast and it reads/writes pandas dataframes natively without converting to SQL formats, etc.
'''

# NOTE: allows python to figure out type annotations in functions later
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

# NOTE: DB must live next to this file (i.e. path = backend/data/duckpredict.db)
DB_PATH = Path(__file__).resolve().parent / "duckpredict.db"

# NOTE: Takes db_path (can be path or str, default = DB_PATH)
# NOTE: duckdb.connect(input) tells DuckDB to open / create the database at this location and give me a connection to it
def get_connection(db_path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path))

''' 
Writes new information (written in df) to permanent DuckDB table (table), where permanent DuckDB table has path db_path

Note: 
    1. mode="replace" recreates table (idemponent re-runs of a backfill)
    2. mode="append" adds rows to existing, permanent table (incremental dialy updates)

Parameters:
    1. df = pandas Dataframe containing new data you want to save
    2. table = name of permanent DuckDB table where all data is to be stored
    3. db_path = location of DuckDB database file
    4. mode = tells function whether to replace existing table or append to it
'''
def write_df(
    df: pd.DataFrame,
    table: str,
    db_path: Path | str = DB_PATH,
    mode: str = "replace",
) -> int:
    
    con = get_connection(db_path)

    try:
        # NOTE: temporarily gives a name to the df, DuckDB can access this df as if it were a table called _incoming
        con.register("_incoming", df)

        # NOTE: Delete and replace existing df (table) with the new dataframe (_incoming (i.e. df))
        if mode == "replace":
            con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM _incoming")

        # NOTE: Keep existing data (in table) and add new dataframe data (in _incoming (i.e. df))
        elif mode == "append":
            con.execute(
                f"CREATE TABLE IF NOT EXISTS {table} AS "
                f"SELECT * FROM _incoming WHERE 1=0"
            )
            con.execute(f"INSERT INTO {table} SELECT * FROM _incoming")
        else:
            raise ValueError(f"unknown mode {mode!r} (use 'replace' or 'append')")

        # NOTE: remove temporary name given to df, so it is no longer equivalent to a table called _incoming
        con.unregister("_incoming")

        # NOTE: Return number of rows currently in permanent df (table)
        (count,) = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        
        return count

    # NOTE: close con (connection to df) after returning count
    finally:
        con.close()

''' Attempts to read entire DuckDB permanent-info table (table) located at db_path '''
def read_table(table: str, db_path: Path | str = DB_PATH) -> pd.DataFrame:
    con = get_connection(db_path)
    try:
        return con.execute(f"SELECT * FROM {table} ORDER BY timestamp").df()
    finally:
        con.close()
