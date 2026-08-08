# NOTES.md — DuckPredict Implementation Notes

Technical deep-dive on the choices, discoveries, and trade-offs made during steps 1.1 and 1.2.

---

## Part 1: What We Originally Thought (and Why It Was Wrong)

### The Original Assumption (from PLAN.md)

PLAN.md step 1.1 said we'd fetch curtailment data with a field called `transmission_vs_oversupply` showing us the split directly. Step 1.2 said we'd also fetch `capacity_mwh` directly from CAISO. **This was wrong.** The real CAISO feeds don't export either of these exactly as we assumed.

### How We Found Out It Was Wrong

We didn't guess. We probed the live API first, using the `gridstatus` library (explained below), and ran real requests to see what columns actually come back.

**Command 1 — Check gridstatus version and available CAISO methods:**
```bash
source .venv/bin/activate
python -c "import gridstatus; print('gridstatus', gridstatus.__version__)"
python -c "import gridstatus; print([m for m in dir(gridstatus.CAISO) if any(k in m.lower() for k in ['curtail','fuel','load','demand'])])"
```

**Output:**
```
gridstatus 0.36.0
['_add_load_forecast_publish_time', '_get_historical_fuel_mix', ..., 'get_curtailment', 'get_curtailment_legacy', 'get_fuel_mix', 'get_load', ...]
```

✓ Found: `get_curtailment`, `get_fuel_mix`, `get_load` methods exist. Good start.

**Command 2 — Probe what columns `get_curtailment` actually returns (May 2024 — this failed!):**
```bash
python -c "
import gridstatus
c=gridstatus.CAISO()
df=c.get_curtailment('2024-05-01')
print('shape', df.shape)
print('cols', list(df.columns))
print(df.head(6).to_string())
"
```

**Output (failed):**
```
ValueError: Failed to fetch renewables report for 2024-05-01: HTTP 404
```

❌ Old dates don't work. Why? CAISO changed their report URL format over time. The `get_curtailment` method hits a specific URL pattern that works for recent data but not 2024.

**Command 3 — Try recent date (July 2026):**
```bash
python -c "
import gridstatus
c=gridstatus.CAISO()
df=c.get_curtailment('2026-07-15')
print('shape', df.shape, 'cols', list(df.columns))
print(df.head(6).to_string())
"
```

**Output (success):**
```
shape (288, 7) cols ['Interval Start', 'Interval End', 'Curtailment Type', 'Curtailment Reason', 'Fuel Type', 'Curtailment MWH', 'Curtailment MW']
             Interval Start              Interval End Curtailment Type Curtailment Reason Fuel Type  Curtailment MWH  Curtailment MW
0 2026-07-15 00:00:00-07:00 2026-07-15 01:00:00-07:00         Economic              Local     Solar              0.0             0.0
1 2026-07-15 00:00:00-07:00 2026-07-15 01:00:00-07:00         Economic              Local      Wind              0.0             0.0
2 2026-07-15 00:00:00-07:00 2026-07-15 01:00:00-07:00         Economic             System     Solar              0.0             0.0
3 2026-07-15 00:00:00-07:00 2026-07-15 01:00:00-07:00         Economic             System      Wind              0.0             0.0
```

✓ Recent data works. **KEY DISCOVERY: The transmission-vs-oversupply split is NOT a separate column. It's encoded in `Curtailment Reason` as `"Local"` (transmission-constrained) or `"System"` (systemwide oversupply).** We need to pivot this.

**Command 4 — Check how far back history goes:**
```bash
for d in 2026-06-01 2026-03-01 2026-01-01 2025-11-01; do
    python -c "
import gridstatus
c=gridstatus.CAISO()
try:
    df=c.get_curtailment('$d'); print('$d OK rows',df.shape[0])
except Exception as e:
    print('$d ERR',repr(e)[:80])
"
done
```

**Output:**
```
2026-06-01 OK rows 288
2026-03-01 OK rows 288
2026-01-01 OK rows 288
2025-11-01 OK rows 288
```

✓ History goes back to at least Nov 2025. Older dates need `get_curtailment_legacy()` which scrapes PDFs (slow/fragile).

**Command 5 — What do `get_load` and `get_fuel_mix` return?**
```bash
python -c "
import gridstatus
c=gridstatus.CAISO()
df=c.get_load('2026-07-15')
print('load cols',list(df.columns)); print(df.head(2).to_string())
"
python -c "
import gridstatus
c=gridstatus.CAISO()
df=c.get_fuel_mix('2026-07-15')
print('fuel cols',list(df.columns)); print(df.head(2).to_string())
"
```

**Output:**
```
load cols ['Time', 'Interval Start', 'Interval End', 'Load']
fuel cols ['Time', 'Interval Start', 'Interval End', 'Solar', 'Wind', 'Geothermal', 'Biomass', 'Biogas', 'Small Hydro', 'Coal', 'Nuclear', 'Natural Gas', 'Large Hydro', 'Batteries', 'Imports', 'Other']
```

✓ `get_load()` returns hourly Load in MW. 
✓ `get_fuel_mix()` returns Solar, Wind, and all other fuel types in MW.
❌ **Neither feed has `capacity_mwh`.** CAISO doesn't publish installed capacity in real-time feeds. It comes from EIA-860 (a separate historical dataset, step 4+).

---

## Part 2: The Technical Concepts Explained Simply

### What is `gridstatus`?

**Simple:** A Python library that fetches electricity grid data from public APIs.

**More detailed:** `gridstatus` is a wrapper around CAISO's OASIS (Open Access Same-time Information System) and Outlook feeds. Rather than you figuring out URLs, HTTP requests, CSV parsing, and timezone handling, `gridstatus` does all that — you call `gridstatus.CAISO().get_curtailment('2026-07-15')` and get back a pandas DataFrame.

**Why we use it:** Building URLs, parsing CSVs, and handling CAISO's timezone quirks would take hours. `gridstatus` is maintained by open-source energy-data folks; we trust it more than home-rolled HTTP.


### What is `DuckDB`?

**Simple:** A SQL database that lives in a single file on disk, optimized for reading/writing Python pandas DataFrames.

**More detailed:** 
- **SQLite** (the other option) is a traditional SQL database: row-oriented, good for transactional (INSERT/UPDATE/DELETE) workloads.
- **DuckDB** is columnar: it stores data column-by-column, which makes analytical queries (GROUP BY, aggregations, filtering) incredibly fast. It reads/writes pandas DataFrames natively with zero glue code.
- Both are single-file, serverless (no separate database server process).

**Why DuckDB over SQLite for this project:** Our main queries are analytical—"sum curtailment by hour," "group by day," "compute 7-day rolling mean." DuckDB crushes these queries because it's columnar. When step 4 builds the training dataset, it's mostly GROUP BYs and aggregations, not INSERT/UPDATE loops.

**Why not PostgreSQL or MySQL:** Those need a running server; we'd need Docker or a hosted database. For a hackathon with one machine, a single-file database keeps it simple.


### Database Format: What's Actually on Disk?

**DuckDB file format:** Binary, proprietary. If you `hexdump backend/data/duckpredict.db`, you'll see gibberish — it's optimized for speed, not human readability.

**Backup/portability:** You can copy `duckpredict.db` to another machine and query it with any DuckDB client. Or export to CSV: `SELECT * FROM curtailment` -> CSV.

**Size:** DuckDB compresses well. 1–2 years of CAISO hourly data (~10k rows) is <5 MB.

### Timezone Handling: The Gotcha

CAISO data is in Pacific Time (UTC-7 or UTC-8 depending on DST). Pandas and DuckDB internally store everything as UTC. When you print a timestamp, it renders in your machine's local timezone:

```python
# Data from CAISO is "2026-07-15 01:00 Pacific" but stored as UTC
# On a machine in Eastern time (UTC-4), it displays as "2026-07-15 04:00-04:00"
# This is correct; both refer to the same instant. Join operations work fine because both tables are in UTC.
```

**Why we didn't hardcode Pacific:** Hardcoding `tz="US/Pacific"` would break if the code runs on a machine in Europe. Storing UTC and letting the display timezone be the system's is the safe, portable approach.

---

## Part 3: The Options We Considered (and Why We Picked What We Did)

### Choice 1: Fetch Strategy — All at Once vs. Day-by-Day?

**Option A: One big request**
```python
df = gridstatus.CAISO().get_curtailment(start="2025-11-01", end="2026-08-06")
```
- ✓ Fast.
- ✗ If the API times out or one date is missing, the whole backfill dies.

**Option B: Loop day-by-day with `try/except` around each day**
```python
for d in _date_range(start, end):
    try:
        frames.append(gridstatus.CAISO().get_curtailment(str(d)))
    except Exception as e:
        print(f"skip {d}: {e}")
```
- ✓ Tolerates missing daily reports (doesn't crash the whole backfill).
- ✗ Slower (network overhead per day).

**We picked Option B** because a hackathon backfill runs *once*, and robustness matters more than speed. If CAISO's API has a hiccup on one day, we log it and move on, not lose the whole month of data.

### Choice 2: Database — DuckDB vs. SQLite?

(Already explained above, but summarized:)

**SQLite:** Row-oriented, good for transactional workloads. Simpler for small projects.

**DuckDB:** Columnar, great for analytical workloads (GROUP BY, aggregations). Native pandas support.

**We picked DuckDB** because step 2 (model features) is mostly GROUP BYs and rolling aggregations — DuckDB's sweet spot. Plus the native pandas integration means less boilerplate code.

### Choice 3: Schema Normalization — When and How?

**Option A: Store raw CAISO output, normalize later in the model code**
```python
# Store raw: Curtailment Reason = "Local", "System", ...
# Pivot this in the model training code.
```
- ✓ Minimal code in the ingest step.
- ✗ Downstream code couples to CAISO's schema; harder to add a second data source (EU later).

**Option B: Normalize at ingest, store a tidy schema**
```python
# Pivot transmission/oversupply here.
# Store: transmission_mwh, oversupply_mwh columns.
# Model code is decoupled from raw CAISO schema.
```

**We picked Option B** because it decouples the model from CAISO's schema. When step 3+ adds EU data (ENTSO-E, SMARD), they'll have different raw schemas but we'll normalize both to the same tidy schema. The model doesn't care where the data came from.

### Choice 4: Handling the Missing `capacity_mwh`

**Option A: Fabricate installed capacity from average generation**
```python
# capacity ≈ peak generation we ever saw
```
- ✓ Have a number.
- ✗ Wrong. Capacity is engineering fact; generation varies with weather. Confusing them breaks the model.

**Option B: Pull capacity from EIA-860 (a separate, authoritative dataset)**
```python
# EIA-860 has every power plant's nameplate capacity.
# Aggregate by date; join onto generation_load table later.
```

**We picked Option B** and deliberately omit capacity from this step's output. Better to have an honestly-incomplete schema than a wrong one. Step 4 (features) joins EIA-860 data later.

---

## Part 4: The Final Schema and Why It's Designed This Way

### Table: `curtailment`

| Column | Type | Source | Why |
|---|---|---|---|
| `timestamp` | timestamp | `Interval Start` from CAISO curtailment report | Hourly UTC instant. Primary key for joins. |
| `total_curtailed_mwh` | float | Sum of `Curtailment MWH` across all reasons/fuels for that hour | Total wasted solar+wind. The target we predict. |
| `transmission_mwh` | float | Sum of `Curtailment MWH` where `Curtailment Reason = "Local"` | Transmission-constrained curtailment (Pillar 2 signal). "Local" = local congestion. |
| `oversupply_mwh` | float | Sum of `Curtailment MWH` where `Curtailment Reason = "System"` | Systemwide oversupply curtailment. "System" = too much generation for the entire grid. |
| `region` | string | Hardcoded to `"CAISO"` | Future: when we add sub-zones (NP15, SP15), this becomes a grouping column. For now, everything is system-level. |

**Why this schema:** Summarizes CAISO's 5-min resolution, multi-row-per-interval data into clean hourly rows. The transmission/oversupply split is the single most valuable signal (judges notice sophistication). Normalizing it here means every downstream code gets it for free.

### Table: `generation_load`

| Column | Type | Source | Why |
|---|---|---|---|
| `timestamp` | timestamp | `Interval Start` from CAISO load/fuel-mix reports | Hourly UTC. Matches `curtailment.timestamp` for joins. |
| `solar_mwh` | float | `get_fuel_mix()["Solar"]`, averaged to hourly | Renewable generation to predict. Negative at night (inverter draw). |
| `wind_mwh` | float | `get_fuel_mix()["Wind"]`, averaged to hourly | Renewable generation to predict. |
| `demand_mwh` | float | `get_load()["Load"]`, averaged to hourly | Total demand. Feature for the model. |

**Deliberately NOT included:**
- `capacity_mwh` — pull from EIA-860 later (step 4).
- Other fuel types (coal, gas, nuclear) — not needed for a solar/wind curtailment forecast.

---

## Part 5: The Libraries We're Using and When

| Library | What It Does | Used In | Import |
|---|---|---|---|
| `gridstatus` | Fetches grid data from CAISO OASIS / Outlook feeds | `backend/data/caiso.py` | `import gridstatus` → `gridstatus.CAISO().get_curtailment(date)` |
| `pandas` | Table (DataFrame) manipulation: filter, group, aggregate, merge | `backend/data/caiso.py` (aggregations), `backend/model/features.py` (joins), `backend/model/train.py` (feature engineering) | `import pandas as pd` → `pd.concat()`, `df.groupby()`, `df.merge()` |
| `duckdb` | Single-file SQL database optimized for analytics | `backend/data/db.py` (persist tables), `backend/model/features.py` (query training table) | `import duckdb` → `duckdb.connect()`, `con.execute("SELECT ...")` |
| `xgboost` | Gradient-boosted decision trees for forecasting | `backend/model/train.py` | `from xgboost import XGBRegressor` → `XGBRegressor().fit()` |
| `scikit-learn` | Train/test split, metrics (MAE, etc.) | `backend/model/train.py` | `from sklearn.model_selection import train_test_split` |
| `fastapi` | Web framework for building the API | `backend/app.py` | `from fastapi import FastAPI` → `@app.get("/api/forecast")` |
| `uvicorn` | ASGI server to run the FastAPI app | `backend/app.py` (via `uvicorn app:app`) | Imported implicitly when you run `uvicorn` CLI |
| `requests` | HTTP client for fetching data from APIs | (potential use in weather/EIA; not yet written) | `import requests` → `requests.get(url)` |
| `python-dotenv` | Load `.env` file variables into `os.environ` | `backend/config.py` | `from dotenv import load_dotenv` → `load_dotenv()` |

---

## Part 6: Running the Code (End-to-End Verification)

We ran steps 1.1 and 1.2 and verified the output:

```bash
source .venv/bin/activate
python -m backend.data.caiso 3   # Backfill 3 days (2026-08-03 to 2026-08-06)
```

**Output:**
```
Backfilling CAISO 2026-08-03 -> 2026-08-06 (3 days)
[curtailment] wrote 96 rows (96 now in table 'curtailment')
[generation_load] wrote 96 rows (96 now in table 'generation_load')
```

**Verification — read back:**
```bash
python -c "
from backend.data.db import read_table
df_c = read_table('curtailment')
df_g = read_table('generation_load')
print('curtailment:', len(df_c), 'rows', list(df_c.columns))
print('generation_load:', len(df_g), 'rows', list(df_g.columns))
print(df_c.head(3))
print(df_g.head(3))
"
```

**Output:**
```
curtailment: 96 rows ['timestamp', 'total_curtailed_mwh', 'transmission_mwh', 'oversupply_mwh', 'region']
generation_load: 96 rows ['timestamp', 'solar_mwh', 'wind_mwh', 'demand_mwh']

                timestamp  total_curtailed_mwh  transmission_mwh  oversupply_mwh region
2026-08-03 03:00:00-04:00             0.000083               0.0        0.000083  CAISO
2026-08-03 04:00:00-04:00             0.000128               0.0        0.000128  CAISO
...

                timestamp  solar_mwh    wind_mwh   demand_mwh
2026-08-03 03:00:00-04:00 -61.333333 5382.500000 29845.666667
2026-08-03 04:00:00-04:00 -60.083333 5885.500000 27929.416667
```

**✓ Both tables created, columns correct, data populated.** The negative solar at night and positive wind confirm we're getting real CAISO data.

---

## Part 7: Known Limitations and Next Steps

### Limitation 1: August Is Low Curtailment Season
The 3-day test pull is early August. Curtailment peaks in spring (March–May). When you run the real backfill with `python -m backend.data.caiso 365`, you'll see strong signals then.

### Limitation 2: History Doesn't Go Back to 2024
The current CAISO report format works back to ~Nov 2025. Older data needs `get_curtailment_legacy()` which scrapes PDFs. For the model, recent data is enough (it'll be well-trained on 9 months of 2025–2026), but FYI if you see a gap.

### Limitation 3: No Capacity Field
Installed capacity comes from EIA-860 (step 4). This table is intentionally incomplete.

### Next: Step 1.3 (Weather Fetching)
Weather forecast data comes from Open-Meteo (free, no API key). Step 1.3 will fetch 1–2 years of actual weather and set up the forecast fetcher.

### Next: Step 1.4 (EDA)
Exploratory Data Analysis: plot the duck curve, verify the transmission/oversupply split, confirm the signals are strong. Go/no-go checkpoint.

---

## Summary Table: What Got Written

| File | Purpose | Key Classes/Functions | Libraries Used |
|---|---|---|---|
| `backend/data/db.py` | Storage helpers | `get_connection()`, `write_df()`, `read_table()` | `duckdb`, `pandas`, `pathlib` |
| `backend/data/caiso.py` | Steps 1.1 + 1.2 data fetching | `fetch_curtailment()`, `fetch_generation_load()`, `_date_range()`, `_hourly_mean()` | `gridstatus`, `pandas`, `duckdb` (via `db.py`) |

**Database:**
- File: `backend/data/duckpredict.db` (single-file, binary)
- Tables: `curtailment` (96 rows in test), `generation_load` (96 rows in test)
- Indexes: None yet (added when needed for performance)
