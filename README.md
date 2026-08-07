# DuckPredict: Clean-Energy Waste Forecasting

> **DuckPredict forecasts where and when the grid will throw away clean energy in the next 48 hours — and tells a battery operator exactly when to charge on it.**

A forecasting system designed to combat grid curtailment: the deliberate throttling of renewable energy when generation exceeds what the grid can absorb. Built for **Hack the Habitat**, this proof-of-concept targets **CAISO (California)** with the goal of scaling globally.

---

## The Problem

Every year, renewable generators across the world curtail clean electricity—deliberately turning down wind and solar that's already producing free, zero-carbon power. In California alone, **~3.4 million MWh** of solar and wind were curtailed in 2024—enough to power hundreds of thousands of homes—and the number grows with each new renewable installation.

### Why It Matters

- **It's predictable.** Curtailment clusters during known times (the "duck curve": sunny, low-demand afternoons) and at known transmission bottlenecks.
- **It's invisible.** Curtailment data is published *after the fact*, scattered across grid operator portals, and never transformed into a *forward-looking, actionable* signal.
- **It could be used.** Battery operators, demand-response aggregators, and grid planners have no decision tool. DuckPredict changes that.

---

## What DuckPredict Does

### 1. **Forecast Clean-Energy Waste (48 hours ahead)**
Predicts how much solar and wind will be curtailed at each hour of the next two days, powered by:
- Historical curtailment patterns (the duck curve)
- Real-time weather forecasts (irradiance, wind, temperature)
- Grid load forecasts
- Installed capacity data

**Result:** A forward-looking 48-hour curve showing exactly when (and how much) the grid will throw away clean energy.

### 2. **Diagnose Why It's Happening**
Automatically tags each curtailment event as:
- **Transmission-constrained** — a specific regional bottleneck (NP15, SP15, etc.)
- **Oversupply/local** — statewide clean-energy glut with nowhere to send it

**Why it matters:** These require different fixes. A transmission bottleneck isn't solved by demand-shifting; oversupply is.

### 3. **Recommend Action**
Translates the forecast into a concrete decision:
- **For battery operators:** "Charge your battery 1–4 PM tomorrow on ~X MWh of curtailed solar (otherwise wasted), discharge into the 7 PM peak."
- **For others:** Frames the opportunity for site demand-response, developer siting decisions, or grid planners (where transmission upgrades pay off).

### 4. **Show Historical Context**
A duck-curve heatmap (hour × day) grounds the forecast in visible, repeating patterns and makes the forecast self-explanatory.

---

## Key Features

- ✅ **48-hour curtailment forecast** with naive-baseline comparison (transparency)
- ✅ **Transmission vs oversupply classification** on every event
- ✅ **Battery-operator action card** with specific charge windows and free-MWh estimates
- ✅ **Historical duck-curve heatmap** for pattern visualization
- ✅ **Live demo** on CAISO (California)
- ✅ **Designed to scale** to EU (ENTSO-E) and beyond
- ✅ **Open-source, transparent** model and data pipeline

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Data/Backend** | Python, `gridstatus`, `pandas`, `requests` |
| **Forecast Model** | XGBoost (gradient boosting on tabular data) |
| **API** | FastAPI with cached forecast/action endpoints |
| **Frontend** | React + Recharts/D3 (forecast curve, heatmap) |
| **Storage** | SQLite / DuckDB |
| **Deploy** | Vercel (frontend) + Render/Railway/Fly (API) |

**Why XGBoost?**
- Beats deep learning on tabular data with small training time (seconds, not hours)
- Feature importances = built-in explainability for demos
- Directly comparable to naive baseline (the honest story)

---

## Data Sources

| Data | Source | Purpose |
|------|--------|---------|
| **CAISO curtailment (MWh, transmission vs oversupply)** | CAISO "Managing Oversupply" daily report / OASIS | Powers Pillars 1–4 (forecast, diagnosis, action, context) |
| **CAISO generation + demand** | CAISO OASIS via `gridstatus` | Real-time features for validation |
| **Weather (actual + forecast)** | Open-Meteo | Irradiance, wind, cloud, temperature inputs to model |
| **EU generation, load, day-ahead** | ENTSO-E Transparency Platform (Tier 2) | Optional: scales proof to second region |
| **German curtailment** | SMARD / Bundesnetzagentur (Tier 2) | Optional: Redispatch / Einspeisemanagement |
| **Renewable capacity** | EIA-860, WRI Global Power Plant DB | Map placement and normalization |

---

## Project Timeline

- **Week 1:** Data access + EDA (go/no-go on CAISO signal)
- **Week 2:** Forecast model + root-cause tagging + API
- **Week 3:** Action card + frontend charts + heatmap
- **Week 4:** Polish, deploy live, record demo, Devpost writeup

For details, see [PLAN.md](PLAN.md).

---

## Getting Started

### Prerequisites
- Python 3.8+
- Node.js 16+ (frontend)
- Git

### Installation

```bash
# Clone the repo
git clone https://github.com/yourusername/duckpredict.git
cd duckpredict

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend setup
cd ../frontend
npm install
```

### Running Locally

**Backend:**
```bash
cd backend
python -m uvicorn app:app --reload
# API available at http://localhost:8000
```

**Frontend:**
```bash
cd frontend
npm start
# App available at http://localhost:3000
```

### Environment Variables

Create a `.env` file in the `backend/` directory:
```
GRIDSTATUS_API_KEY=your_key_here
OPEN_METEO_API_KEY=optional
```

---

## Project Structure

```
duckpredict/
├── backend/
│   ├── app.py                # FastAPI server
│   ├── model/
│   │   ├── train.py          # XGBoost training pipeline
│   │   └── forecast.py       # Inference / 48h forecast
│   ├── data/
│   │   ├── caiso.py          # CAISO data fetching
│   │   ├── weather.py        # Open-Meteo integration
│   │   └── db.py             # SQLite/DuckDB access
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── ForecastChart.tsx     # 48h curve (hero)
│   │   │   ├── HeatmapChart.tsx      # Duck-curve heatmap
│   │   │   ├── ActionCard.tsx        # Battery operator recommendation
│   │   │   └── RegionMap.tsx         # Coverage map (optional)
│   │   └── hooks/
│   │       └── useForecast.ts        # API client
│   └── package.json
├── PLAN.md
└── README.md
```

---

## Impact

DuckPredict translates grid data into human action:

- **~3.4 MWh of curtailment** annually in CAISO = **homes powered for a day**, or **EVs charged**, or **CO₂ offset if stored instead of wasted**
- **One operator, one concrete action** (charge your battery 1–4 PM) = **legitimacy over speculation**
- **Forecast vs baseline comparison** = **no hand-waving, just transparent accuracy**

---

## Demo

[Live link will be added after deployment]

See the project in action:
1. **Open on the 48-hour forecast** — the money-shot curve showing exactly when/how much clean energy gets wasted
2. **Click on a curtailment event** — diagnosis appears (transmission bottleneck in NP15, or statewide oversupply?)
3. **Scroll to the action card** — battery operator gets a specific window to charge
4. **Historical context below** — the duck-curve heatmap proves this is chronic, not a fluke

---

## Credits & Acknowledgments

Built for **Hack the Habitat 2024** — "Build tech that protects the planet."

**Data sources:** CAISO, Open-Meteo, ENTSO-E, EIA, WRI.

---

## License

MIT

---

## Questions?

Open an issue or reach out. We're building transparency into the grid, one forecast at a time.
