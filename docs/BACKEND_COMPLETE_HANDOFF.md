# SETU-DRR — Comprehensive Backend Architecture, Implementation & Team Handoff Guide

**Platform:** SETU-DRR (Hazard Red Zone & Relocation Decision Support Platform)  
**Stakeholder:** Ministry of Home Affairs — National Disaster Response Force (NDRF), Disaster Management Division  
**Document Status:** Day 8 Frozen & Verified (187/187 Automated Tests Passing)  
**Target Audience:** Entire Team (Backend, Machine Learning & Science, Frontend / UI, GIS / Data)

---

## 1. Executive Context & System Purpose

India's disaster-prone regions face recurring landslides, flash floods, riverine flooding, and coastal erosion. Traditional relocation efforts are **reactive**—initiated post-disaster under emergency conditions without a pre-computed inventory of high-risk habitations, and with destination sites chosen solely on land availability rather than utility carrying capacity.

**SETU-DRR** is an evidence-backed GIS screening decision-support engine designed to solve three compounding failures:
1. **No standing inventory of unsafe habitations:** We maintain an automated, ranked triage queue joining hazard intensity, dasymetric vulnerability, and time-decayed loss history.
2. **No utility capacity check on destinations:** We audit candidate relocation sites across four independent infrastructure constraints (land, water, education, healthcare), identify the **binding bottleneck**, and calculate augmented capacity / intervention costs.
3. **Conflation between evacuation and relocation:** We strictly separate chronic permanent risk (**Permanent Red Zones**) from temporary weather emergencies (**Active Alert Zones** and 72-hour **Forecast Alert Zones**).

---

## 2. What We Have Implemented in the Backend (Days 0–7 Complete)

### Day 0 & 1 — Database Foundation, Geospatial Schema & Indexing
* **Database Engine:** PostgreSQL 16 + PostGIS 3.4 + PostGIS Raster + native H3 4.2 hosted on Neon (using direct non-pooled connections for prepared statements and GIS queries).
* **Migrations Framework:** Numbered sequential SQL migrations ([`infra/migrations/001_` through `006_`](file:///d:/the-dead-zone/infra/migrations)) applied idempotently via [`infra/apply_migrations.py`](file:///d:/the-dead-zone/infra/apply_migrations.py) and tracked in `schema_migrations`.
* **Spatial & Temporal Indexing:**
  * Spatial GiST indexes on administrative boundaries, habitations, candidate sites, disaster events, and H3 hexagonal polygons/centroids.
  * Temporal BRIN indexes on dynamic hazard observations (`hazard_dynamic.valid_at`) and MHI snapshots (`mhi_snapshot.valid_at`).
  * Partial optimization indexes for Active Alert Zones (`mhi_live >= 0.75`) and Forecast Alert Zones (`mhi_fcst >= 0.75`).
* **Spatial Grid Generation:** Multi-resolution Uber H3 grid generation (Resolution 6 overview, Resolution 7 national, Resolution 8 pilot/district, Resolution 9 site).

### Day 2 — Covariates, Demographics & Offline Mode
* **DEM Derivatives:** Zonal statistics from Copernicus GLO-30 DEM (slope, aspect, profile curvature, plan curvature, Topographic Wetness Index, Height Above Nearest Drainage).
* **Dasymetric Population:** Population downscaling using building footprint counts and land use masks.
* **Deterministic Seed Pipeline:** Fully idempotent database seeding ([`pipeline/src/pipeline/jobs/seed_pilot_data.py`](file:///d:/the-dead-zone/pipeline/src/pipeline/jobs/seed_pilot_data.py)) covering pilot districts (Wayanad LGD 555, Kodagu LGD 540) with fixed random seeds for reproducible testing.
* **Offline Execution Gate:** Full `DEMO_MODE=true` enforcement ensuring zero external network calls during runtime.

### Day 3 — Sentinel-1 SAR Flood Pipeline & ML Protocol Boundaries
* **STAC Querying:** Microsoft Planetary Computer STAC integration querying Sentinel-1 Radiometrically Terrain Corrected (RTC) dual-pol scenes.
* **Permanent Water Removal:** JRC Global Surface Water integration to isolate ephemeral flood water from permanent water bodies.
* **Multi-Temporal Frequency Stack:** Pixel-wise inundation frequency stacking combined with HAND thresholding to produce empirical flood susceptibility.
* **Protocol Interfaces:** Defined strict structural subtyping protocols ([`core/src/core/ml/protocols.py`](file:///d:/the-dead-zone/core/src/core/ml/protocols.py)) for Landslide, Flood, Vulnerability, and Dynamic Triggers.

### Day 4 — Habitation Risk Profiling, Vulnerability & Triage Engine
* **Social Vulnerability Index (SoVI):** Principal Component Analysis (PCA) across 4 dimensions:
  * $V_{\text{demographic}}$: Elderly, children, female-headed households.
  * $V_{\text{structural}}$: Kucha / non-permanent housing.
  * $V_{\text{access}}$: Road distance, emergency response travel time.
  * $V_{\text{economic}}$: Below-poverty-line, agricultural labor ratio.
* **Time-Decayed Disaster Loss History:**
  $$\hat{L}_j = \sum_{i} e^{-\lambda (t_{\text{now}} - t_i)} \cdot \text{severity}_i \quad \text{with } \lambda = \frac{\ln(2)}{10\text{ years}}$$
* **Priority Urgency & Caseload Scores:**
  $$PS_j = (\hat{h}_j \cdot \hat{f}_j \cdot \hat{V}_j) \cdot (1 + \gamma \cdot \hat{L}_j) \quad (\gamma \approx 0.5)$$
  $$\text{Caseload}_j = PS_j \times \text{Population}_j$$
* **Four-Tier Triage Classification:**
  * **Tier 1 (Immediate, 0–6 mo):** Extreme PRZ overlap + active ground deformation or fatal recurrence in last 3 monsoons.
  * **Tier 2 (Short-term, 6–24 mo):** High priority score ($PS_j \ge 0.30$) or significant PRZ overlap.
  * **Tier 3 (Medium-term, 2–5 yr):** Caution Zone with adverse trends or moderate exposure.
  * **Tier 4 (Mitigate in-situ):** Low PRZ fraction ($< 30\%$) where structural engineering / catchment protection is more cost-effective than relocation.
* **Habitations APIs:** `GET /habitations` (paginated, sorted by urgency or caseload, filtered by tier and admin unit) and `GET /habitations/{id}/risk` (full risk dossier).

### Day 5 — Candidate Relocation Site Assessment & Carrying Capacity
* **Candidate Site Eligibility Mask:** Strict screening requiring static $MHI \le 0.25$, slope $\le 15^\circ$, usable area $\ge 2.0\text{ ha}$, and non-protected land tenure.
* **Four-Resource Carrying Capacity:**
  $$CC(s) = \min(CC_{\text{land}}, CC_{\text{water}}, CC_{\text{school}}, CC_{\text{health}}) \times \mu_{\text{livelihood}}$$
  * *Land:* $90\text{ m}^2$ plot norm $+ 40\%$ infrastructure overhead ($126\text{ m}^2/\text{hh}$).
  * *Water:* CPHEEO norms ($55\text{ LPCD}$ rural, $135\text{ LPCD}$ urban) evaluated against aquifer recharge and pipeline headroom.
  * *Education:* UDISE+ sanctioned school capacity minus current local enrollment.
  * *Healthcare:* Indian Public Health Standards (1 PHC per 20,000 in hilly/tribal, 30,000 in plains).
* **Binding Constraint & Augmentation:** Automatically isolates the single resource capping capacity, computes augmented capacity if relieved, and estimates capital expenditure costs.
* **Candidate Sites APIs:** `GET /sites/{id}`, `GET /habitations/{id}/sites` (search radius query), and `POST /sites/{id}/capacity` (policy norm override simulator).

### Day 6 — Dynamic Weather Triggers, Alerts & Google OR-Tools Allocation
* **Dynamic Trigger Feeds:** NASA GPM IMERG observed precipitation and ECMWF Open Data numerical weather forecasts.
* **Threshold Models:** Antecedent Rainfall Index (ARI, 15-day window, decay $k=0.9$) and Intensity–Duration (I-D) power-law threshold curves ($I = \alpha D^{-\beta}$).
* **Active & Forecast Alert Zones:**
  * `GET /alerts/active`: Cells where $MHI_{\text{live}} \ge 0.75$ and $MHI_{\text{static}} < 0.75$ (emergency evacuation).
  * `GET /alerts/forecast`: Cells predicted to cross threshold within 72 hours with issuing model and cycle attribution.
* **Google OR-Tools Allocation Solver:**
  * Formulated as a constrained bipartite min-cost flow / MIP optimization.
  * Maximizes total risk reduction while penalizing geographic displacement and preventing community fragmentation (group splits).
  * Endpoint: `POST /plan/allocate`.

### Day 7 — Stateless Scenario Simulation, Formula Governance & Hardening
* **Stateless Scenario Simulation (`POST /scenario`):** Allows decision-makers to evaluate hypothetical hazard weights ($w_h$), loss weight ($\gamma$), and search radii without persisting to or mutating the baseline database. Computes rank deltas ($\Delta \text{Rank} = \text{Rank}_{\text{orig}} - \text{Rank}_{\text{scen}}$) and tier shifts.
* **Formula Governance:** Strict 4-tier separation in [`core/src/core/governance.py`](file:///d:/the-dead-zone/core/src/core/governance.py) separating non-negotiable scientific definitions from policy parameters and operational settings.
* **7-State Data Quality Preservation:** `DataQuality` enum (`observed`, `nowcast`, `forecast_72h`, `proxy`, `interpolated`, `stale`, `synthetic`) tracking data fidelity across all API responses.
* **Security & Validation Hardening:** Rejection of non-finite floats (`NaN`/`Inf`), bounding box area caps ($\le 5.0\text{ deg}^2$), strict H3 format validation, and OpenAPI 3.1 synchronization ([`openapi.json`](file:///d:/the-dead-zone/openapi.json)).

### Day 8 — Stabilization & Freeze Audit
* **187 / 187 automated tests passing** (100% pass rate across contract, integration, unit, and performance suites).
* Zero hardcoded credentials or committed secrets.
* Performance: PostgreSQL internal query planner $< 10\text{ ms}$; API p95 $< 350\text{ ms}$.
* Officially marked **DAY 8 FROZEN — READY**.

---

## 3. What is Left to Do in the Backend (Post-Freeze / Future Scope)

These items are deliberately scheduled for post-demo evolution and do not block the core presentation:

1. **Automated PDF Briefing Pack Generation (`GET /export/{admin}/briefing.pdf`):**
   * *Status:* Intentionally deferred during Day 7 to focus on stateless scenario simulation and data quality hardening.
   * *Implementation Path:* Use `reportlab` or `weasyprint` to compile the habitation risk dossier, candidate site maps, and OR-Tools allocation table into an official SDMA briefing document.
2. **Background Ingestion Scheduler:**
   * *Status:* Dynamic triggers currently run from pre-ingested snapshots in `DEMO_MODE=true`.
   * *Implementation Path:* Wire an `APScheduler` or Celery cron worker to pull daily IMERG GPM files and ECMWF 00Z/12Z cycles in production.
3. **National-Scale Partitioning:**
   * *Status:* Pilot districts run in unpartitioned tables with BRIN temporal indexes.
   * *Implementation Path:* When expanding from pilot districts to pan-India, enable `pg_partman` on `hazard_dynamic` to drop partitions older than 90 days.
4. **Ground-Truth Survey Feedback Ingestion:**
   * *Status:* Current habitations and sites originate from GIS layers.
   * *Implementation Path:* Build a mobile survey sync endpoint for field geologists to upload soil bore and slope inclinometer ground-truth verifications.

---

## 4. Specifically Left Vague / Decoupled for the ML & Science Team

The backend was purposefully built with clean adapter boundaries so the ML and science team can refine models without touching backend routing or database schemas:

### A. Upstream Model Drops & Protocols ([`core/src/core/ml/protocols.py`](file:///d:/the-dead-zone/core/src/core/ml/protocols.py))
* **How to plug in:** Implement the `predict(features)` method defined in `LandslideModelProtocol` or `FloodSurfaceProtocol`.
* **Current status:** The backend provides clean heuristic baseline implementations in [`core/src/core/ml/registry.py`](file:///d:/the-dead-zone/core/src/core/ml/registry.py).
* **ML action:** When the trained XGBoost model (with spatial block cross-validation) or Random Forest checkpoint is ready, wrap it in a class conforming to the protocol and register it in `ModelRegistry`. The backend will consume it automatically.

### B. Empirical Hazard Weights & Amplification Beta
* **Locations:** [`core/src/core/constants.py`](file:///d:/the-dead-zone/core/src/core/constants.py) and [`core/src/core/governance.py`](file:///d:/the-dead-zone/core/src/core/governance.py).
* **Current defaults:**
  * Landslide: $1.0$
  * Flash Flood: $1.0$
  * Storm Surge: $0.9$
  * Riverine Flood: $0.8$
  * Coastal Erosion: $0.7$
  * Dynamic Trigger Amplification: $\beta = 1.0$ in $H = \text{clamp}(S \cdot (1 + \beta T), 0, 1)$
* **ML action:** The ML team can refine these weights based on empirical validation against historical event catalogues (e.g. Wayanad 2024, Barpeta 2023) or calibration curves.

### C. TreeSHAP Explanation Payloads
* **Location:** [`core/src/core/schemas/explanation.py`](file:///d:/the-dead-zone/core/src/core/schemas/explanation.py) and `Explanation` table in DB.
* **Payload structure:**
  ```json
  [
    {"name": "Slope Angle", "contribution": 0.42, "type": "hazard"},
    {"name": "Curvature", "contribution": 0.28, "type": "hazard"},
    {"name": "Permanent Red Zone Overlap", "contribution": 0.85, "type": "exposure"},
    {"name": "Kucha Housing Ratio", "contribution": 0.65, "type": "vulnerability"}
  ]
  ```
* **ML action:** Precompute TreeSHAP values for pilot H3 cells and write them to the `explanation` table. The backend routes (`/zones/{h3}` and `/habitations/{id}/risk`) will immediately render them.

### D. INDOFLOODS Event Catalogue & I-D Curve Fitting
* **Open question (PRD Q-7):** Licensing terms of the INDOFLOODS Zenodo dataset (14584655).
* **Science action:** Verify if INDOFLOODS allows CC BY redistribution. If so, fit regional power-law parameters ($\alpha, \beta$) for $I = \alpha D^{-\beta}$ and supply the fitted thresholds to `pipeline/src/pipeline/adapters/trigger_adapter.py`.

---

## 5. Specifically Left Vague / Decoupled for the Frontend Team

The frontend workspace is located in [`web/`](file:///d:/the-dead-zone/web) (Next.js 16, React 19, Tailwind CSS v4). The backend has completely exposed and stabilized the API contract in [`openapi.json`](file:///d:/the-dead-zone/openapi.json).

### A. Generating Strong TypeScript Types
In the `web/` directory, run:
```bash
pnpm generate:types
```
This reads [`openapi.json`](file:///d:/the-dead-zone/openapi.json) and outputs strict TypeScript interfaces in `lib/api-types.ts` for every request payload and response envelope.

### B. Core UI Architecture & Recommended Three-Panel Layout
The PRD prescribes an SDMA Decision Cockpit consisting of three panels:

```text
+------------------------+------------------------------------+--------------------------+
|  LEFT PANEL            |  CENTER PANEL                      |  RIGHT PANEL             |
|  Habitations Triage    |  Interactive MapLibre GL           |  Detailed Dossier &      |
|  Queue & Ranking       |  Hexagonal Choropleth              |  Site Recommendations    |
|                        |                                    |                          |
|  - Urgency vs Caseload |  - H3 Res 8 Hexagons               |  - SoVI breakdown chart  |
|  - Tier Filter Chips   |  - PRZ (Red), Caution (Yellow)     |  - Loss history timeline |
|  - Search & LGD filter |  - Active Alert (Flashing/Hatched) |  - SHAP Factor Bar Chart |
|  - Habitation Card     |  - 72h Forecast (Blue dashed)      |  - Candidate Site Cards  |
|                        |  - Time Slider (-7d to +3d)        |  - Capacity Bars (Bottl.)|
+------------------------+------------------------------------+--------------------------+
|  BOTTOM / DRAWER: Scenario Sensitivity Simulation (Sliders: Landslide, Flood, Gamma)   |
+----------------------------------------------------------------------------------------+
```

### C. Specific Frontend Interactions to Implement
1. **Selection Synchronization:**
   * Clicking a habitation in the Left Panel centers the Map and opens its Risk Dossier and Candidate Sites in the Right Panel.
   * Clicking an H3 cell on the map opens the Cell Dossier (`/zones/{h3}`) showing TreeSHAP feature importances.
2. **Carrying Capacity Bars with Bottleneck Highlighting:**
   * For each site from `GET /habitations/{id}/sites` or `GET /sites/{id}`, render stacked or grouped capacity bars for Land, Water, School, and Health.
   * **Visual indicator:** The binding constraint (e.g. "Water-limited: 218 HH") must be styled with an amber/red warning badge.
   * Show the **Augmented Capacity** toggle: "If water pipeline expanded (+₹18.5L), capacity increases to 540 HH".
3. **Scenario Simulation Drawer:**
   * Provide sliders for:
     * Landslide Weight (0.0 – 2.0, default 1.0)
     * Flood Weight (0.0 – 2.0, default 1.0)
     * Loss Gamma $\gamma$ (0.0 – 2.0, default 0.5)
     * Search Radius (5 km – 50 km, default 15 km)
   * On slider change (or "Simulate" click), call `POST /scenario`.
   * Render the delta badge on habitation cards (e.g., `+4 Rank`, `Tier changed: Medium -> Immediate`).
4. **Mandatory Screening-Grade Label & Disclaimers:**
   * Every view and exported summary **must display the persistent label**:
     > *"Screening Grade: Cell-level screening and prioritisation tool. Geotechnical investigation, hydraulic study, and community consultation required before executing relocation orders."*
   * Forecast Alert Zones must state: *"Meteorological threshold crossing based on ECMWF Open Data. The system does not predict disasters."*

---

## 6. End-to-End API Quick Reference

All endpoints are served from `http://localhost:8000`:

| Method | Endpoint | Primary Use Case |
|---|---|---|
| `GET` | `/health/ready` | Readiness check & database probe. |
| `GET` | `/zones?bbox=minx,miny,maxx,maxy&res=8` | Fetch H3 grid cells for map viewport rendering. |
| `GET` | `/zones/{h3}` | Hexagon cell dossier with SHAP factor breakdown. |
| `GET` | `/habitations?admin=555&sort=urgency` | Paginated ranked habitations queue with tier filters. |
| `GET` | `/habitations/{id}/risk` | Deep habitation risk dossier (SoVI, loss timeline, priority). |
| `GET` | `/habitations/{id}/sites?radius_km=15` | Ranked candidate destination relocation sites for habitation. |
| `GET` | `/sites/{id}` | Detailed site capacity breakdown, binding bottleneck & augmentation. |
| `POST` | `/sites/{id}/capacity` | Recompute site capacity with custom LPCD or plot norms. |
| `GET` | `/alerts/active` | Active Alert Zones ($MHI_{\text{live}} \ge 0.75$) from observed rain. |
| `GET` | `/alerts/forecast?horizon=72` | 72-hour Forecast Alert Zones from NWP models. |
| `POST` | `/plan/allocate` | Execute Google OR-Tools bipartite relocation matching. |
| `POST` | `/scenario` | Stateless what-if sensitivity analysis with rank deltas. |

---

## 7. How to Run & Verify

```bash
# 1. Activate Python virtual environment and run full test suite
uv run pytest -v

# 2. Run API server locally
uv run uvicorn api.main:app --reload --port 8000

# 3. View interactive Swagger UI documentation
# Open browser to: http://localhost:8000/docs

# 4. In frontend workspace (web/)
cd web
pnpm install
pnpm generate:types   # Syncs TypeScript types with backend
pnpm dev              # Starts Next.js development server at http://localhost:3000
```

---

*This document serves as the canonical handoff reference for all team members.*
