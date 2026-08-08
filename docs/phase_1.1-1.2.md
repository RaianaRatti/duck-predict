## Step 1.1 + Step 1.2

### The Original Assumption

PLAN.md (step 1.1) said we'd fetch curtailment data with a field called `transmission_vs_oversupply` showing us the split directly

**This was wrong**

The real CAISO feeds don't export `transmission` and `oversupply` as two different fields (columns). Instead, these two entries are written as `Local` and `System` in same column `Curtailment Reason`

### How We Found Out It Was Wrong

We probed the live API using `gridstatus` library and ran requests to see what columns actually came back

**Command ` - Check gridstatus version and available CAISO methods:**

```bash
source .venv/bin/activate
python -c "import gridstatus; print('gridstatus', gridstatus.__version__)"
python -c "
    import gridstatus
    print(
        [m
        for m in dir(gridstatus.CAISO) 
        if any(k in m.lower() for k in ['curtail', 'fuel', 'load', 'demand'])]
    )
```

**Output:**
```
gridstatus 0.36.0
['_add_load_forecast_publish_time',
'__get_historical_fuel_mix', ...,
'get_curtailment', 'get_curtailment_legacy',
'get_fuel_mix', 'get_load', ...]
```

✓ Found: `get_curtailment`, `get_fuel_mix`, `get_load` methods

**Command 2 - See what columns `get_curtailment` actually returns (fail!)**

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

**Output**
```
ValueError: Failed to fetch renewables report for 2024-05-01: HTTP 404
```

✗ Old dates don't work. Why? CAISO changed their report URL format over time. The `get_curtailment` method hits a specific URL patter that works for recent data but not 2024.

**Command 3 - Try recent date (July 2026) (success)**
```bash
python -c "
import gridstatus
c=gridstatus.CAISO()
df=c.get_curtailment('2026-07-15')
print('shape', df.shape, 'cols', list(df.columns))
print(df.head(6).to_string())
"
```

**Output**

```
shape (288, 7) cols ['Interval Start', 'Interval End', 'Curtailment Type', 'Curtailment Reason', 'Fuel Type', 'Curtailment MWH', 'Curtailment MW']
             Interval Start              Interval End Curtailment Type Curtailment Reason Fuel Type  Curtailment MWH  Curtailment MW
0 2026-07-15 00:00:00-07:00 2026-07-15 01:00:00-07:00         Economic              Local     Solar              0.0             0.0
1 2026-07-15 00:00:00-07:00 2026-07-15 01:00:00-07:00         Economic              Local      Wind              0.0             0.0
2 2026-07-15 00:00:00-07:00 2026-07-15 01:00:00-07:00         Economic             System     Solar              0.0             0.0
3 2026-07-15 00:00:00-07:00 2026-07-15 01:00:00-07:00         Economic             System      Wind              0.0             0.0
```

✓ Recent data works. 

**KEY DISCOVERY: The transmission-vs-oversupply split is NOT a separate column. It's encoded in `Curtailment Reason` as `Local` or `System`**

**Command 4 - Check how far back history goes**
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

✓ History goes back to at least Nov 2025. That is all we need.

**Command 5 - What do `get_load` and `get_fuel_mix` return**

```bash
python -c "
import gridstatus
c=gridstatus.CAISO()
df=c.get_load('2026-07-15')
print('load cols',list(df.columns)); print(df.head(2).to_string())
print("\n")
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

**KEY DISCOVERY: Neither feed has `capacity_mwh`. CAISO does not publish installed capacity in real-time feeds. It will have to come from EIA-860 (step 4)**

### Technical Terminology

**gridstatus**

*Simple* A python library that fetches electricity grid dat
a from public APIs

*In-depth* `gridstatus` is a wrapper around CAISO's OASIS (Open Access Same-time Information System) and Outlook feeds. Rather than you figuring out URLs, HTTP requests, CSV parsing, and timezone handling, `gridstatus` does all that - you just call `gridstatus.CAISO().get_curtailment('2026-07-15)` and get back a Pandas dataframe

**DuckDB**

*Simple* An SQL database that lives in a single file on disk, optimized for reading/writing Python Pandas DataFrames

*In-depth*
- SQLite (other option) is a traditional SQL database: row-oriented, good for transactional workloads (INSERT/UPDATE/DELETE)

- DuckDB is columnar, stores data column-by-column which makes analytical queries (GROUP BY, aggregations, filtering) fast. Reads/writes Pandas Dataframes natively.

*Choice* DuckDB chosen. More analytical queries will be made in this project than transactional workloads. PostgreSQL or MySQL not chosen as they need a running server; we'd need Docker or a hosted database.

**Database Format: What's Actually On Disk**

*DuckDB file format* Binary, proprietary. If you use `hexdump backend/data/duckpredict.db` you'll see gibberish - optimized for speed, not human readability

*Backup/Portability* Can copy `duckpredict.db` to another machine and query it with any DuckDB client. Or export to CSV: `SELECT * FROM curtailment` -> CSV

*Size* DuckDB compresses well. 1-2 years of CAISO hourly data (~10k rows) is <5 MB

**Timezone Handling**

CAISO data is in Pacific time (UTC-7 or UTC-8). Pandas and DuckDB internally store everything as UTC. but when you print a timestamp, it renders in your machine's local timezone.

So no issue.

### Choices

*Choice 1: Fetch Strategy - all-at-once vs. day-by-day*

```python
df = gridstatus.CAISO().get_curtailment(start="2025-11-01", end="2026-08-06")
```

```python
for d in _date_range(start, end):
    try:
        frames.append(gridstatus.CAISO().get_curtailment(str(d)))
    except Exception as e:
        print(f"skip {d}: {e}")
```

Chose Option B. Slower but will not crash whole backfill due to one missing daily report. Backfill runs once so robustness matters more than speed.

*Choice 2: Schema Normalization - when and how?*

```python
# Store raw CAISO output, normalize later in model code
# Example: Curtailment Reason = "Local", Curtailment Type = ...
```

```python
# Normalize at ingest, store tidy schema
```

Chose Option B. Decouples model from CAISO's schema (doesn't care where data comes from)

*Choice 3: Handling missing `capacity_mwh`*

```python
# capacity = peak generation we ever saw
```

```python
# EIA-860 has every power planet's nameplace capacity
# Aggregate by date; join onto generation_load table later
```

Chose Option B.

### Tables

**Curtailment**

| Column | Type | Source | Why |
|---|---|---|---|
| `timestamp` | timestamp | `Interval Start` from CAISO curtailment report | Hourly UTC instant. Primary key for joins. |
| `total_curtailed_mwh` | float | Sum of `Curtailment MWH` across all reasons/fuels for that hour | Total wasted solar+wind. The target we predict. |
| `transmission_mwh` | float | Sum of `Curtailment MWH` where `Curtailment Reason = "Local"` | Transmission-constrained curtailment (Pillar 2 signal). "Local" = local congestion. |
| `oversupply_mwh` | float | Sum of `Curtailment MWH` where `Curtailment Reason = "System"` | Systemwide oversupply curtailment. "System" = too much generation for the entire grid. |
| `region` | string | Hardcoded to `"CAISO"` | Future: when we add sub-zones (NP15, SP15), this becomes a grouping column. For now, everything is system-level. |

**Generation_load**

| Column | Type | Source | Why |
|---|---|---|---|
| `timestamp` | timestamp | `Interval Start` from CAISO load/fuel-mix reports | Hourly UTC. Matches `curtailment.timestamp` for joins. |
| `solar_mwh` | float | `get_fuel_mix()["Solar"]`, averaged to hourly | Renewable generation to predict. Negative at night (inverter draw). |
| `wind_mwh` | float | `get_fuel_mix()["Wind"]`, averaged to hourly | Renewable generation to predict. |
| `demand_mwh` | float | `get_load()["Load"]`, averaged to hourly | Total demand. Feature for the model. |

### Running Code (End-to-End Verificiation)

```bash
source .venv/bin/activate
python -m backend.data.caiso 3 # Backfills last 3 days
```

Output:

```
Backfilling CAISO 2026-08-03 -> 2026-08-06 (3 days)
[curtailment] wrote 96 rows (96 now in table 'curtailment')
[generation_load] wrote 96 rows (96 now in table 'generation_load')
```