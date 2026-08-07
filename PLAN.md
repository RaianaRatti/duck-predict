# PLAN.md — DuckPredict Implementation Roadmap

Ordered build steps. Each step names the file to write, the libraries/APIs it uses, and what the code must do. Complete steps top to bottom. If time runs short, cut from the bottom — the forecast (Phase 2–3) is the hero and ships first.

> **Fun fact / where the name comes from:** The "duck curve" is grid-operator slang for the shape of net electricity demand on a high-solar day — it sags in the middle (solar floods the grid) and ramps up steeply at sunset (the duck's neck). Curtailment lives in the belly of that duck. DuckPredict forecasts the belly.

**Scope note for this build:** Tier 1 = **CAISO (California)** only — it is a complete, winning project on its own. Germany/EU (ENTSO-E, SMARD) and a region map are **stretch goals**; only start them once Phases 1–4 are solid. Do not let stretch work block the core.

---

## Phase 0 — Repo & Environment (Day 1)

### Step 0.1 — Backend project skeleton
- **File:** `backend/requirements.txt`
- **Do:** List Python deps: `gridstatus`, `pandas`, `requests`, `xgboost`, `scikit-learn`, `fastapi`, `uvicorn`, `python-dotenv`, `duckdb` (or `sqlite3` stdlib), `matplotlib` (EDA only).
- **Done when:** `pip install -r requirements.txt` succeeds in a fresh venv.

### Step 0.2 — Config & secrets
- **File:** `backend/.env` (git-ignored) + `backend/config.py`
- **Do:** `config.py` reads env vars via `python-dotenv`: DB path, CAISO settings, California lat/lon for weather, optional ENTSO-E key. Provide sane defaults so the app runs with no `.env`.
- **Done when:** `from config import settings` works and prints the DB path.

---

## Phase 1 — Data Ingestion & Validation (Days 1–3)

### Step 1.1 — CAISO curtailment history
- **File:** `backend/data/caiso.py`
- **Library/API:** `gridstatus` (`gridstatus.CAISO`) hitting CAISO OASIS / the "Managing Oversupply" daily report.
- **Do:** Function `fetch_curtailment(start, end)` pulls 1–2 years of curtailment with the transmission-vs-oversupply split. Normalize to columns: `timestamp, total_curtailed_mwh, transmission_mwh, oversupply_mwh, region`. Write to the DB (DuckDB/SQLite) table `curtailment`.
- **Done when:** Table has continuous hourly rows across the window with the split populated.

### Step 1.2 — CAISO generation + demand history
- **File:** `backend/data/caiso.py` (extend)
- **Library/API:** `gridstatus` fuel-mix + load endpoints (OASIS).
- **Do:** Function `fetch_generation_load(start, end)` pulls hourly solar MWh, wind MWh, total demand, installed capacity. Write to table `generation_load`: `timestamp, solar_mwh, wind_mwh, demand_mwh, capacity_mwh`.
- **Done when:** Rows align on `timestamp` with the curtailment table.

### Step 1.3 — Weather history (actual) + forecast fetcher
- **File:** `backend/data/weather.py`
- **Library/API:** Open-Meteo (free, no key). Historical archive endpoint for training; forecast endpoint for serving.
- **Do:**
  - `fetch_weather_history(start, end)` → table `weather`: `timestamp, irradiance_w_m2, wind_speed_ms, temp_c, cloud_cover_pct` for California coords from config.
  - `fetch_weather_forecast()` → returns next-48h weather as a DataFrame (used later by the forecast endpoint; no DB write needed).
- **Done when:** History table is populated; `fetch_weather_forecast()` returns 48 rows.

### Step 1.4 — EDA & GO/NO-GO checkpoint
- **File:** `backend/analysis/eda.py`
- **Library:** `pandas`, `matplotlib`.
- **Do:** Load all three tables, join on `timestamp`, and produce plots saved to `backend/analysis/plots/`: (a) hour × day heatmap of curtailment (confirm the duck curve is visible), (b) time series of transmission vs oversupply split (confirm it's populated, not all-zero), (c) scatter of curtailment vs irradiance (confirm signal exists).
- **Done when:** Plots visibly show the mid-day duck-curve pattern and a populated split. **If a feed is broken or the split is empty, stop and fix the data source before continuing.**

---

## Phase 2 — Forecast Model (Days 4–10)

### Step 2.1 — Build the training table
- **File:** `backend/model/features.py`
- **Library:** `pandas`.
- **Do:** Function `build_training_frame()` joins curtailment (target) + weather + generation/load on `timestamp` and engineers features:
  - Time: `hour_of_day`, `day_of_week`, `is_weekend`, `month` (encode hour/month cyclically with sin/cos).
  - Weather: irradiance, wind speed, temp, cloud cover.
  - Grid: `demand_mwh`, `capacity_mwh`, `solar_mwh`, `wind_mwh`.
  - Lags: `curtailed_lag_24h` (yesterday same hour), `curtailed_roll_7d` (7-day rolling mean).
  - Target column: `target_curtailed_mwh`.
- **Done when:** Returns a clean DataFrame with no NaNs in feature columns (drop or impute warm-up rows).

### Step 2.2 — Naive baseline
- **File:** `backend/model/baseline.py`
- **Do:** Implement "yesterday-same-hour" predictor = `curtailed_lag_24h`. Compute MAE on the held-out test split. Save the number to `backend/model/metrics_baseline.json`.
- **Done when:** Baseline MAE is recorded. This is the bar to beat.

### Step 2.3 — Train XGBoost forecaster
- **File:** `backend/model/train.py`
- **Library:** `xgboost` (`XGBRegressor`), `scikit-learn` for the split/metrics.
- **Do:** Chronological train/test split (e.g., last ~2 months as test — never shuffle time series). Train `XGBRegressor` (start `n_estimators=300, max_depth=6, learning_rate=0.05`; tune if it doesn't beat baseline). Report test MAE and MAE-vs-baseline improvement. Save model to `backend/model/model.pkl` (joblib) and metrics to `backend/model/metrics_model.json`.
- **Done when:** Model test MAE is clearly below baseline MAE, and both are written to disk.

### Step 2.4 — Feature importance (for demo narration)
- **File:** `backend/model/train.py` (extend)
- **Do:** After training, dump `model.feature_importances_` mapped to feature names, sorted, to `backend/model/feature_importance.json`.
- **Done when:** JSON lists top features (expect irradiance/hour/demand near the top).

### Step 2.5 — Root-cause tagging
- **File:** `backend/model/root_cause.py`
- **Do:** Function `classify(timestamp) -> {"type": "transmission" | "oversupply", "region": str}`. Prefer CAISO's published transmission/oversupply fields directly; fall back to a rule (if `transmission_mwh / total_curtailed_mwh > 0.5` → transmission, else oversupply). Region from CAISO fields if present (NP15/SP15/ZP26), else `"CAISO"`.
- **Done when:** Given a historical timestamp, returns the correct tag consistent with the source split.

---

## Phase 3 — API (Days 11–14)

### Step 3.1 — FastAPI skeleton
- **File:** `backend/app.py`
- **Library:** `fastapi`, `uvicorn`, CORS middleware.
- **Do:** Create the app, enable CORS for the frontend origin, add `GET /health` returning `{"status": "ok"}`.
- **Done when:** `uvicorn app:app --reload` serves and `/docs` loads.

### Step 3.2 — `GET /api/forecast`
- **File:** `backend/app.py` (extend)
- **Do:** Call `weather.fetch_weather_forecast()`, build the same feature vector as training (reuse `features.py`), load `model.pkl`, predict each of the next 48 hours. Also compute the baseline prediction per hour so the frontend can overlay it. Return JSON list: `[{"timestamp", "forecast_mwh", "baseline_mwh"}]`. Cache the response ~1 hour (simple in-memory TTL).
- **Done when:** Endpoint returns 48 hourly points with both series.

### Step 3.3 — `GET /api/root-cause`
- **File:** `backend/app.py` (extend)
- **Do:** Query param `timestamp`; return `root_cause.classify(timestamp)` as JSON `{"timestamp", "type", "region"}`.
- **Done when:** Returns a valid tag for any forecast hour.

### Step 3.4 — `GET /api/action`
- **File:** `backend/model/action.py` + wire into `backend/app.py`
- **Do:** From the 48h forecast, find the contiguous window of highest curtailment (e.g., peak ± surrounding hours above a threshold). Sum forecast MWh in that window = free energy available. Return `{"headline", "window_start", "window_end", "free_mwh", "next_step", "impact"}` where `impact` converts `free_mwh` to homes-powered / EVs-charged / tons CO₂ avoided (constants in `action.py`).
- **Done when:** Returns a concrete charge window + free-MWh + one impact number.

### Step 3.5 — `GET /api/history/heatmap`
- **File:** `backend/app.py` (extend)
- **Do:** Return past ~90 days of curtailment aggregated as hour × day for the heatmap: `[{"day", "hour", "curtailed_mwh"}]`.
- **Done when:** Endpoint returns a dense grid the frontend can render.

### Step 3.6 — Smoke-test endpoints
- **File:** `backend/tests/test_api.py`
- **Library:** `pytest`, FastAPI `TestClient`.
- **Do:** One test per endpoint asserting 200 + expected JSON shape.
- **Done when:** `pytest` passes for all endpoints.

---

## Phase 4 — Frontend (Days 15–21)

> Load the `dataviz` skill before writing any chart code. The forecast curve and heatmap are the visual identity — they must read as one polished system.

### Step 4.1 — React app skeleton
- **File:** `frontend/` (Vite + React + TypeScript)
- **Library:** `react`, `recharts`, `axios`.
- **Do:** Scaffold the app; add `VITE_API_URL` env var for the backend base URL.
- **Done when:** `npm run dev` serves on `localhost:5173`.

### Step 4.2 — API client hook
- **File:** `frontend/src/hooks/useDuckData.ts`
- **Do:** Hook that fetches `/api/forecast`, `/api/action`, `/api/history/heatmap` (and `/api/root-cause` on demand) via `axios`; exposes `{ forecast, action, heatmap, loading, error }`.
- **Done when:** A test component logs live data from the backend.

### Step 4.3 — Forecast chart (HERO)
- **File:** `frontend/src/components/ForecastChart.tsx`
- **Library:** Recharts (`LineChart`).
- **Do:** Plot 48h `forecast_mwh` as the primary line and `baseline_mwh` as a muted reference line (proves we beat naive). X = time, Y = MWh. Shade the peak curtailment window. Show a callout: "Tomorrow 1–4 PM: ~X MWh of solar will be curtailed."
- **Done when:** Both series render, peak window is highlighted, callout reflects live data.

### Step 4.4 — Root-cause labels
- **File:** `frontend/src/components/RootCauseBadge.tsx`
- **Do:** For selected/peak events, call `/api/root-cause` and show a badge: "Transmission · NP15" or "Oversupply". Distinct colors per type.
- **Done when:** Badge reflects the correct tag for the hovered/peak event.

### Step 4.5 — Action card
- **File:** `frontend/src/components/ActionCard.tsx`
- **Do:** Prominent card from `/api/action`: headline ("Charge 1–4 PM tomorrow"), window, free MWh, next step ("discharge into the 7 PM peak"), and the impact number. Mobile-friendly.
- **Done when:** Card shows a complete, specific recommendation from live data.

### Step 4.6 — Duck-curve heatmap
- **File:** `frontend/src/components/Heatmap.tsx`
- **Do:** Render `/api/history/heatmap` as hour (Y) × day (X), color = MWh curtailed (sequential palette from `dataviz`). Makes the chronic mid-day pattern obvious.
- **Done when:** Heatmap clearly shows the recurring mid-day band.

### Step 4.7 — App layout
- **File:** `frontend/src/App.tsx`
- **Do:** Compose: header → ForecastChart (hero) → ActionCard → Heatmap. Responsive (1-col mobile, wider on desktop). Loading + error states.
- **Done when:** Full page loads end to end against the live API.

### Step 4.8 — (Stretch) Region map
- **File:** `frontend/src/components/RegionMap.tsx`
- **Library:** `react-simple-maps` or Leaflet.
- **Do:** Show CAISO zones (NP15/SP15/ZP26) with hover labels. Skip if time is tight.

---

## Phase 5 — Deploy, Polish, Submit (Days 22–28)

### Step 5.1 — Backend deploy
- **Target:** Render / Railway / Fly.io.
- **Do:** Add a start command (`uvicorn app:app --host 0.0.0.0 --port $PORT`); push and deploy. Confirm `/api/forecast` returns on the live URL.
- **Done when:** Public API URL responds.

### Step 5.2 — Frontend deploy
- **Target:** Vercel / Netlify.
- **Do:** Set `VITE_API_URL` to the live backend URL; deploy.
- **Done when:** Public demo URL loads and pulls live data.

### Step 5.3 — Mobile pass
- **Do:** Test 320–768px: charts scale, action card readable, no horizontal scroll.
- **Done when:** Clean on a phone-sized viewport.

### Step 5.4 — Demo video (2–3 min)
- **Do:** Screen-record: open on the forecast curve (beats baseline) → click a spike, root-cause appears → heatmap shows the pattern is chronic → close on the action card. Narrate the one-line pitch.
- **Done when:** Uploaded, link ready for Devpost.

### Step 5.5 — Devpost submission
- **Do:** Write up in order — problem → data → forecast accuracy vs baseline → root-cause → named user + action → impact. Attach live demo URL, GitHub repo, and video.
- **Done when:** Submission is live with all links.

---

## Definition of Done (the 9/10 bar)

- [ ] Live URL, loads on mobile.
- [ ] 48h CAISO curtailment forecast that visibly beats the naive baseline (MAE shown).
- [ ] Every curtailment event tagged transmission vs oversupply.
- [ ] Battery-operator action card with a concrete charge window + free-MWh estimate.
- [ ] Historical duck-curve heatmap for context.
- [ ] One impact number the audience feels.
- [ ] 2–3 min demo video + Devpost writeup + public repo.
