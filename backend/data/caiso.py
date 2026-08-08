'''
Overall: Used 'gridstatus' library which wraps CAISO's public OASIS (historical data) / outlook feeds (future, predicted data). Each fetch loops day-by-day to to tolerate missing daily report (though slower), then normalizes into tidy, hourly schema that persists to DuckDB
'''

# NOTE: allows python to figure out type annotations in functions later
from __future__ import annotations

import sys
from datetime import date, timedelta

import gridstatus
import pandas as pd

from .db import write_df

_caiso = gridstatus.CAISO()

# NOTE: Converts start and end into dates, keeps returning next date after start till it reaches end date
# NOTE: [start, end] inclusive
def _date_range(start, end):
    start = pd.Timestamp(start).date()
    end = pd.Timestamp(end).date()
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)

# ------------------------------------
# Step 1.1
# ------------------------------------

''' Overall, this function obtains curtailment data for all plants, combines and aggregates data for all plants by time the data was taken in, separates reason (transmission vs oversupply) and returns df'''
def fetch_curtailment(start, end, persist: bool = True) -> pd.DataFrame:

    # NOTE: Loop through all dates [start, end] and obtain curtailment data for each data, adding to list 'frames' in order
    # NOTE: get_curtailment -> ['Interval Start', 'Interval End', 'Curtailment Type', 'Curtailment Reason', 'Fuel Type', 'Curtailment MWH', 'Curtailment MW']
    frames = []
    for d in _date_range(start, end):
        try:
            frames.append(_caiso.get_curtailment(str(d)))

        # NOTE: a missing daily report must not kill the backfill
        except Exception as e:
            print(f"Skipping curtailment data on {d}: {str(e)[:80]}")
            
    if not frames:
        raise RuntimeError("No curtailment data fetched from given range")

    raw = pd.concat(frames, ignore_index=True)

    # NOTE: reason for curtailment made a separate list
    reason = raw["Curtailment Reason"].str.lower()

    # NOTE: new columns added to raw (_transmission + _oversupply) as those are two reasons that get_curtailment combined into one row (Curtailment MWH)
    # # NOTE: Read NOTES.md
    raw["_transmission"] = raw["Curtailment MWH"].where(reason.eq("local"), 0.0)
    raw["_oversupply"] = raw["Curtailment MWH"].where(reason.eq("system"), 0.0)

    # NOTE: currently, a lot of entries start with same "Interval start" because those entries are data for a specific renewable energy plant so we group df by 'Interval start' values and then aggregate them
    # NOTE: Resets new, aggregated row's index to the 'Interval Time' for that group
    # NOTE: Rename 'Interval start' -> 'timestamp'
    out = (
        raw.groupby("Interval Start")
        .agg(
            total_curtailed_mwh=("Curtailment MWH", "sum"),
            transmission_mwh=("_transmission", "sum"),
            oversupply_mwh=("_oversupply", "sum"),
        )
        .reset_index()
        .rename(columns={"Interval Start": "timestamp"})
    )

    # NOTE: Add 'region' column with label CAISO for each as all entries right now are for CA
    out["region"] = "CAISO"

    # NOTE: Sorts rows so they are in chronological order (time-wise, so we organize by timestamp)
    # NOTE: Now df might have index 5 at very top so we do reset_index()
    out = out.sort_values("timestamp").reset_index(drop=True)

    # NOTE: persist = did caller ask to save data
    if persist:
        n = write_df(out, "curtailment")
        print(f"[curtailment] wrote {len(out)} rows ({n} now in table 'curtailment')")
    return out


# ---------------------------------------------------------------------------
# Step 1.2
# ---------------------------------------------------------------------------

''' This function returns the hourly mean of selected columns (sent in cols)'''
def _hourly_mean(df: pd.DataFrame, cols, ts_col: str = "Interval Start") -> pd.DataFrame:

    # NOTE: cols is a list of all the columns we care about keeping (may be ["solar", "wind"])
    # NOTE: Only keep columns we care about, ts_col = 'Interval start' and *cols (just unpacking of cols)
    df = df[[ts_col, *cols]].copy()

    # NOTE: converts values in 'Interval start' to pandas datetime (format in which pd can understand dates)
    df[ts_col] = pd.to_datetime(df[ts_col])
    hourly = (
        # NOTE: Makes timestamp the index -> 1:20 PM = 120 (allows pandas to perform time-based operations)
        df.set_index(ts_col)[cols]

        # NOTE: pulls all operations that happend in same hour together (1:20 and 1:45 are both pulled)
        .resample("1h")

        .mean()

        # NOTE: Turns timestamp back into regular column
        .reset_index()

        .rename(columns={ts_col: "timestamp"})
    )
    return hourly

'''
Pulls hourly solar/wind generation data and total demand for [stard, end]
Columns: timestamp, solar_mwh, wind_mwh, demand_mwh

Note: Capacity_mwh is deliberatly not produced here, CAISO does not publish it, EIA-860 does
'''
def fetch_generation_load(start, end, persist: bool = True) -> pd.DataFrame:

    # NOTE: fuel_frames and load_frames are lists with outputs of get_fuel_mix() and get_load()
    fuel_frames, load_frames = [], []
    for d in _date_range(start, end):
        try:
            fuel_frames.append(_caiso.get_fuel_mix(str(d)))
        except Exception as e:
            print(f"[fuel_mix] skip {d}: {str(e)[:80]}")
        try:
            load_frames.append(_caiso.get_load(str(d)))
        except Exception as e:
            print(f"[load] skip {d}: {str(e)[:80]}")

    # NOTE: If no data generated in either, raise RuntimeError
    if not fuel_frames:
        raise RuntimeError("no generation data fetched for the given range")
    if not load_frames:
        raise RuntimeError("no load data fetched for the given range")

    # NOTE: Returns hourly mean (dataframe with hourly mean of only listed columns) of solar, wind from fuel_frames (CAISO get_fuel_mix() data)
    fuel = _hourly_mean(pd.concat(fuel_frames, ignore_index=True), ["Solar", "Wind"])
    fuel = fuel.rename(columns={"Solar": "solar_mwh", "Wind": "wind_mwh"})

    # NOTE: Returns hourly mean (dataframe with hourly mean of only listed columns) of load from load (CAISO get_load() data)
    load = _hourly_mean(pd.concat(load_frames, ignore_index=True), ["Load"])
    load = load.rename(columns={"Load": "demand_mwh"})

     #NOTE: Merges fuel and load by finding rows where they have same timestamp, creating new df, adding each unique column as a column in the df
    out = (
        fuel.merge(load, on="timestamp", how="inner")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    # NOTE: persist = did caller ask to save data
    if persist:
        n = write_df(out, "generation_load")
        print(f"[generation_load] wrote {len(out)} rows ({n} now in table 'generation_load')")
    return out

'''
Main function

Note: Doing python -m backend.data.caiso will make this function run automatically, but not if we import caiso into another file
'''
if __name__ == "__main__":

    # NOTE: Check whether number was typed (i.e. python -m backend.data.caiso 365), else default = 30
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30

    # NOTE: end = today - 1 day = yesterday (as today's report may be partial)
    end = date.today() - timedelta(days=1)

    start = end - timedelta(days=days)
    print(f"Backfilling CAISO {start} -> {end} ({days} days)")

    fetch_curtailment(start, end)
    fetch_generation_load(start, end)
