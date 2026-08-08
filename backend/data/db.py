"""DuckDB storage helpers for DuckPredict.

A single-file analytical database. DuckDB (not SQLite) because our workload is
analytical — the duck-curve heatmap and the model's feature table are group-by
aggregations, which DuckDB does fast, and it reads/writes pandas DataFrames
natively with no ORM glue.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

# DB lives next to this module: backend/data/duckpredict.db
DB_PATH = Path(__file__).resolve().parent / "duckpredict.db"


def get_connection(db_path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path))


def write_df(
    df: pd.DataFrame,
    table: str,
    db_path: Path | str = DB_PATH,
    mode: str = "replace",
) -> int:
    """Write `df` to `table` and return the table's resulting row count.

    mode="replace" recreates the table (idempotent re-runs of a backfill);
    mode="append" adds rows to an existing table (incremental daily updates).
    """
    con = get_connection(db_path)
    try:
        con.register("_incoming", df)
        if mode == "replace":
            con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM _incoming")
        elif mode == "append":
            con.execute(
                f"CREATE TABLE IF NOT EXISTS {table} AS "
                f"SELECT * FROM _incoming WHERE 1=0"
            )
            con.execute(f"INSERT INTO {table} SELECT * FROM _incoming")
        else:
            raise ValueError(f"unknown mode {mode!r} (use 'replace' or 'append')")
        con.unregister("_incoming")
        (count,) = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return count
    finally:
        con.close()


def read_table(table: str, db_path: Path | str = DB_PATH) -> pd.DataFrame:
    con = get_connection(db_path)
    try:
        return con.execute(f"SELECT * FROM {table} ORDER BY timestamp").df()
    finally:
        con.close()
