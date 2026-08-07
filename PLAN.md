# PLAN.md — DuckPredict: Clean-Energy Waste Forecasting

**Hackathon:** Hack the Habitat — "Build tech that protects the planet"
**Track:** Clean energy / environmental monitoring
**Team:** Solo
**Target build window:** 3–4 weeks

> **The one-line pitch:** *DuckPredict forecasts where and when the grid will throw away clean energy in the next 48 hours — and tells a battery operator exactly when to charge on it.*

This is not a dashboard project with a forecast bolted on. It is a **forecasting + decision tool** with a dashboard as its surface. That distinction is the difference between a 7.5 and a 9.

---

## Project: DuckPredict

**Locked in.** The duck curve is famous in energy circles and shows insider knowledge. It's memorable, nerd-appeal strong, and perfect for the Devpost branding.

---

## 1. The Problem (niche, quantified, under-served)

When renewable generation exceeds what the grid can absorb or transmit, operators **curtail** — deliberately throttle wind and solar that is already producing free, zero-carbon electricity. That clean energy is thrown away.

- California (CAISO) curtailed **~3.4 million MWh of solar and wind in 2024** — enough to power hundreds of thousands of homes — and it grows every year.
- The waste is **predictable**: it clusters in known transmission bottlenecks and known times (sunny, low-demand spring afternoons — the "duck curve").
- **The gap we fill:** curtailment data is published *after the fact*, scattered across operator portals, and never turned into a *forward-looking, actionable* signal. Nobody says "here is the clean energy about to be wasted tomorrow, why, and what to do about it." That is DuckPredict.

We are **not** "fixing the grid." We are building the **forecasting + decision layer** that curtailment currently lacks.

---

## 2. The Four Pillars (in priority order — build top-down)

Everything is ranked. If we run out of time, we cut from the bottom, never the top.

### Pillar 1 — The Forecast (THE HERO — must be flawless)
A model that predicts **curtailed MWh 12–48h ahead** for CAISO from weather forecast + load + generation features.
- Must **beat a naive baseline** (yesterday-same-hour) on MAE, and we show that comparison openly.
- Presented as a **48h forward curve** with the money-shot callout: *"Tomorrow 1–4pm: ~X MWh of solar will be curtailed."*
- This is the first thing the judge sees and the last thing they remember.

### Pillar 2 — Root-Cause Classification (what makes it look *intelligent*)
Every curtailment event tagged **transmission-constrained** vs **oversupply/local** — CAISO publishes this split, so it's free signal most people never surface.
- Turns a descriptive chart into a diagnosis: *"This waste is a transmission bottleneck in NP15, not statewide oversupply."*
- This single feature is the biggest cheap win for perceived sophistication.

### Pillar 3 — The Action Layer (named user, real decision)
Forecasts are inert until someone acts on them. We attach one concrete user and one concrete action:
- **Primary persona — battery/storage operator:** "Charge your battery 1–4pm tomorrow on curtailed solar that's otherwise free, discharge into the 7pm peak." We show the specific window + estimated free MWh available.
- Secondary framing for judges: grid operators (site demand-response), developers (siting), policymakers (where transmission upgrades pay off).
- **Deliverable:** a small "Recommended action" card driven by the forecast. This is what proves the project *does* something, not just *shows* something.

### Pillar 4 — Historical Context (supporting evidence, not the star)
Hour × day heatmap exposing the chronic duck-curve windows. Grounds the forecast in visible reality and makes the demo self-explanatory. Nice map of covered regions if time allows.

---

## 3. Scope Decision (the honesty that protects our credibility)

**Kill the "global real-time" over-claim.** Real-time curtailment data does not exist openly for most of the world (China: essentially nothing public). Claiming it invites a question we can't answer and tanks credibility with a technical judge.

**Honest framing:** *"A forecasting system designed to scale to any instrumented grid, proven end-to-end on the world's two best-instrumented grids."*

- **Tier 1 (must ship — the whole project stands on this):** **CAISO (California).** Best curtailment data on Earth — actual MWh *with the transmission-vs-oversupply breakdown*, daily. All four pillars run on CAISO alone.
- **Tier 2 (stretch, adds the "scales globally" proof):** **Germany / EU** via ENTSO-E + SMARD. One extra region validates the "designed to scale" claim. It is a bonus, never a dependency.
- **Tier 3 (only if everything else is polished):** a third region for the map.

A polished single-region tool with a working forecast and an action card **beats** a broken three-region dashboard every time. Judges reward focused-and-working over ambitious-and-mocked.

---

## 4. Data Sources

| Data | Source | Notes |
|---|---|---|
| CAISO curtailment (actual MWh, transmission vs oversupply) | CAISO "Managing Oversupply" daily report / OASIS | The single most valuable dataset — powers Pillars 1, 2, 4. Ground this first. |
| CAISO real-time generation + demand | CAISO OASIS via `gridstatus` (Python) | `gridstatus` wraps the API cleanly — big time-saver. |
| Weather actual + forecast (irradiance, wind, cloud, temp) | Open-Meteo (free, no key) | Fastest path; forecast endpoint feeds Pillar 1 directly. |
| EU generation, load, day-ahead (Tier 2) | ENTSO-E Transparency Platform API | Free key, ~1 day to register. |
| German curtailment detail (Tier 2) | SMARD.de / Bundesnetzagentur | Redispatch / Einspeisemanagement figures. |
| Renewable capacity / locations | EIA-860 (US), WRI Global Power Plant DB | Map placement + normalization. |

**Verify every Tier-1 feed in the first 48 hours.** If a feed is broken or gated, cut it immediately.

---

## 5. Tech Stack

- **Data/backend:** Python — `gridstatus`, `pandas`, `requests`.
- **Model:** `XGBoost` / gradient boosting (beats deep learning on tabular, trains in seconds, and is **explainable** — feature importances become demo narration). Features: forecast irradiance, wind, temp, hour-of-day, day-of-week, forecast load, installed capacity. Target: curtailed MWh per interval. Train on 1–2 yrs CAISO history. **Always report MAE vs the naive baseline.**
- **Root-cause:** derive from CAISO's published transmission/oversupply fields; a simple classifier only if needed.
- **API:** FastAPI serving cached forecasts, root-cause tags, and the action recommendation as JSON.
- **Frontend:** React; **Recharts/D3** for the forecast curve + heatmap (the stars); Leaflet/`react-simple-maps` for the region map (supporting).
- **Storage:** SQLite or DuckDB. Don't over-engineer infra.
- **Deploy:** Vercel/Netlify (frontend) + Render/Railway/Fly (API). A **live URL** matters for judging.

> Load the `dataviz` skill before writing any chart code. The forecast curve and heatmap are the visual identity of the project — they must read as one polished system.

---

## 6. Week-by-Week Timeline

**Week 1 — Data & proof of signal (go/no-go)**
- [ ] Confirm CAISO access via `gridstatus`; confirm Open-Meteo forecast pull. (ENTSO-E key in parallel, low priority.)
- [ ] Pull 1–2 yrs CAISO curtailment + generation + demand + the transmission/oversupply split into a local DB.
- [ ] EDA: confirm the duck-curve pattern is visible and the transmission/oversupply split is populated. **GO/NO-GO checkpoint.**

**Week 2 — The hero + the brain (Pillars 1 & 2)**
- [ ] Join weather forecast + load features to curtailment target.
- [ ] Train XGBoost forecaster; lock in naive baseline; report MAE. Iterate until it clearly beats baseline.
- [ ] Implement root-cause tagging from CAISO fields.
- [ ] FastAPI endpoints: 48h forecast + per-interval root-cause.

**Week 3 — The action layer + surface (Pillars 3 & 4)**
- [ ] Battery-operator "Recommended action" card: charge window + free MWh available, derived from the forecast.
- [ ] Forecast curve chart (hero), root-cause labels on events, historical hour×day heatmap.
- [ ] Region map. Add Germany/ENTSO-E **only if** Pillars 1–3 are solid.

**Week 4 — Polish, deploy, demo**
- [ ] Deploy live; responsive/mobile pass.
- [ ] Impact translation ("X MWh = Y homes / Z EVs / N tons CO₂ if stored instead of wasted").
- [ ] Record 2–3 min demo — open on the forecast money-shot, end on the action card.
- [ ] Devpost: problem → data → **forecast accuracy vs baseline** → root-cause → **named user + action** → live demo.

---

## 7. Impact Framing (judges reward measurable impact)

- Convert wasted MWh into felt units: homes powered, EVs charged, CO₂-equivalent if that clean energy had displaced gas.
- Lead with the **action**, not the observation: *"DuckPredict tells a battery operator exactly when to store free clean energy the grid is about to throw away."*
- Path to impact is concrete and one hop away from the forecast — that's what earns the "could genuinely be used" credit.

---

## 8. Risks & Cuts

| Risk | Mitigation |
|---|---|
| Over-claiming "global real-time" | Cut it. Frame as "designed to scale, proven on CAISO + EU." |
| Model underperforms | Baseline comparison still tells a strong story; root-cause + action layer stand on their own. |
| ENTSO-E setup eats time | CAISO-only is a complete, winning project. EU is a bonus, not a dependency. |
| Action card feels hand-wavy | Tie it to specific numbers from the forecast (window + MWh); one solid persona beats three vague ones. |
| Over-scoping the frontend/map | Ship forecast curve + heatmap + action card first; map is nice-to-have. |

**Guiding principle:** Forecast first, diagnosis second, action third, pretty charts fourth. Cut from the bottom.

---

## 9. Definition of Done (the 9/10 bar)

- Live URL, loads on mobile.
- **48h CAISO curtailment forecast that visibly beats a naive baseline (MAE shown).** ← non-negotiable hero.
- **Every event tagged transmission vs oversupply.** ← the "intelligent" differentiator.
- **A battery-operator action card** with a concrete charge window and free-MWh estimate. ← proves it *does* something.
- Historical duck-curve heatmap for context.
- One impact number the audience feels.
- 2–3 min demo video (opens on forecast, closes on action) + Devpost writeup + public repo.
