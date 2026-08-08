## Step 1.3

### The Original Assumptions

PLAN.md (step 1.3) assumed, correctly, that a single HTTP request could pull a whole year of history in one shot. This simplified `weather.py` as compared to `caiso.py`.

We also assumed assumed wind speed would come back in *m/s*

**This was wrong**

Open-Meteo returns wind speed in *km/h*

### How We Found Out It was Wrong

**Command 1 - Hit the forecast endpoint directly and look at the raw JSON**

```bash
curl -s "https://api.open-meteo.com/v1/forecast?latitude=38.58&longitude=-121.49&hourly=temperature_2m,shortwave_radiation,wind_speed_10m,cloud_cover&forecast_days=2&timezone=UTC" | python3 -m json.tool | head -40
```

**Output (trimmed)**

```json
{
    "latitude": 38.576817,
    "longitude": -121.485245,
    "hourly_units": {
        "time": "iso8601",
        "temperature_2m": "°C",
        "shortwave_radiation": "W/m²",
        "wind_speed_10m": "km/h",
        "cloud_cover": "%"
    },
    "hourly": {
        "time": ["2026-08-08T00:00", "2026-08-08T01:00", ...],
        ...
    }
}
```

**KEY DISCOVERY: the `hourly_units` block says `"wind_speed_10m": "km/h"` - units are km/h**

**Command 2 - Check whether "historical" archive endpoint has a lag near today (does it refuse to serve yesterday's data)?**

```bash
curl -s "https://archive-api.open-meteo.com/v1/archive?latitude=38.58&longitude=-121.49&start_date=2026-08-06&end_date=2026-08-08&hourly=temperature_2m&timezone=UTC" | 

python3 -c "
import json,sys
d=json.load(sys.stdin)
times = d['hourly']['time']
print('first:', times[0], 'last:', times[-1], 'count:', len(times))
vals = d['hourly']['temperature_2m']
print('last 5 temp values (None = missing):', vals[-5:])
"
```

**Output**
```
first: 2026-08-06T00:00 last: 2026-08-08T23:00 count: 72
last 5 temp values (None = missing): [28.6, 31.6, 34.3, 36.4, 37.9]
```

✓ Safe. There are no `None` values, even for "today". Some weather archives have a multi-day publishing lag but this one does not

**Command 3 - Does a full year come back in ONE request, or does the API cap / paginate large ranges?**

```bash
curl -s "https://archive-api.open-meteo.com/v1/archive?latitude=38.58&longitude=-121.49&start_date=2025-08-08&end_date=2026-08-08&hourly=temperature_2m&timezone=UTC" | python3 -c "
import json,sys
d=json.load(sys.stdin)
t=d['hourly']['time']
print('rows:', len(t), 'first:', t[0], 'last:', t[-1])
print('expected ~ 365*24 =', 365*24)
"
```

**Output**
```
rows: 8784 first: 2025-08-08T00:00 last: 2026-08-08T23:00
expected ~ 365*24 = 8760
```

✓ Safe. 8784 rows returned (365 days x 24h = 8760, 2026 is a leap year so about right)

### Some Background

CAISO territory is split into 3 zones. CAISO treats them as separate in their dataset because they are separate "power-flow regions". They are not interconnected. There could be a trasmission bottleneck in one region and oversupply in the other.

Essentially, the state of one does not dictate the state of the other, so they are treated as separate.

- NP15 = "Northern Path 15"
- SP15 = "Southern Path 15"
- ZP26 - another zone between them

Currently, program is just fetching CAISO-wide data (so we are not differentiating by region). 

Since this report converns `weather.py`, talking about that, we should be taking weather in 3 cities, one from each one of these representative regions. But right now, we are just taking weather in Sacramento and applying it to all the 3 regions.

### Technical Terminology

**curl**

*Simple* CLI tool that sends a request to a web address (a URL) and prints back whatever server sends.

**requests**

*Simple* Python library for asking a website or API for data (code equivalent of typing a URL into a browser and reading what comes back

*In-depth* `requests.get(url, params = {...})` builds URL with query parameters, sends HTTP GET request, and gives back `Response` object. Calling `.json()` on that parses response body as JSON into Python dictionary

**REST API / HTTP GET / query parameters**

*Simple* A REST API is a web service that responds to plain URLs. An HTTP GET request is "please send me this data" (as opposed to POST, which is "here, take this data"). Query aparameters are the `?key=value&key2=value2` part of a URL, they are named settings you pass to the API to tell it what kind of data you want

*Why it matters* Open-Meteo does not use API keys (and thus no authentication, sessions, or POST bodies). It only requires a URL with the right query parameters to provide data

**ISO8601**

*Simple* A standard way to write dates and times as text so computers everywhere parse them the same way, e.g. `2026-08-08T00:00`

*Why it matters* Open-Meteo's `time` field comes back as ISO8061 strings, not native datetime objects (becsuse JSON has no datetime type - just strings). `pd.to_datetime(..., utc=True)` converts those strings into real, timezone-aware pandas timestamps that can be compared and joined in CAISO tables

**"Archive" vs. "Forecast" endpoint**

*Question* Why do we have two URLs for one library

*Simple* One endpoint answers "what already happened" (archive / history). The other answers "what's predicted to happen next" (forecast)

Both endpoints return identical JSON shape, one shared function (`_parse_hourly_response`) parses both

*Why it matters* Step 1.3 needs both - the model is trained on 1-2 years of `fetch_weather_history()` (what actually happened, paired with what curtailment actually happened)

But oonce deployed, the live forecast API calls `fetch_weather_forecast()` (step 3.2) to get the next 48 hours.

### Choices

*Choice 1 - data obtainment loop*

- Option A: Day-by-day loop like in `caiso.py`
- Option B: One request for whole data range, `try/except` around single call

Chose Option B. Since this API did not fail for older data, using one request was more efficient.

*Choice 2 - Where to do km/h -> m/s conversion*

- Option A: Leave raw km/h in database, convert in model-training code
- Option B: Convert at ingest, store m/s in database

Chose Option B. Matches "normalize at ingest" principle already established in CAISO transmission/oversupply split. Keeps database clean with what model actually uses, in case someone uses `weather` to train their own model and ends up using incorrect units

*Choice 3: - how many representative lat/lon points to span CAISO's territory*

- Option A: Average weather across several representative points (e.g. Central Valley solar belt + Tehachapi/Solano wind corridors)
- Option B: One representative point (Sacramento)

Chose Option B: CAISO spans a huge territory with many microclimates, but Option A would lead to more API calls and no immediate payoff until we implement region-specific attribution (NP15 / SP14 breakdowns). Sacramento sits in Central Valley solar corridor near NP15, one of the zones CAISO's own curtailment reports reference and it is simpler and faster to do.

### Tables

**Weather**

| Column | Type | Source | Why |
|---|---|---|---|
| `timestamp` | timestamp (UTC) | `hourly.time` (ISO8601 strings), parsed via `pd.to_datetime(..., utc=True)` | Joins against `curtailment.timestamp` and `generation_load.timestamp` from Part 4. |
| `irradiance_w_m2` | float | `hourly.shortwave_radiation` (already W/m², no conversion needed) | Solar irradiance — the single strongest predictor of solar generation and therefore solar curtailment. |
| `wind_speed_ms` | float | `hourly.wind_speed_10m` (km/h), **divided by 3.6** | Wind generation predictor, converted to standard m/s at ingest (see Choice 2 above). |
| `temp_c` | float | `hourly.temperature_2m` (already °C) | Secondary feature — affects both demand (AC load) and generation efficiency. |
| `cloud_cover_pct` | float | `hourly.cloud_cover` (already %) | Redundant-but-useful alongside irradiance; cloud cover is what a human weather forecast narrates, irradiance is what the panel actually sees. |

### Running Code (End-to-End Verification)

```bash
source .venv/bin/activate
python -m backend.data.weather 5   # Fetch 5 days of weather history
```

Output:
```
Fetching weather history 2026-08-02 -> 2026-08-07 (5 days)
[weather] wrote 144 rows (144 now in table 'weather')
```