# Product Requirements Document
## Hazard Red Zone & Relocation Decision Support Platform

**Working name:** SETU-DRR
**Problem statement:** Intelligent Identification of Hazard-Based Red Zones, Carrying Capacity Assessment, and Immediate Relocation Needs for Vulnerable Habitations
**Organisation:** Ministry of Home Affairs — National Disaster Response Force (NDRF), DM Division
**Document version:** 1.3 · August 2026
**Status:** Approved for build

> **v1.1 revision — authenticated access permitted.** The "no API keys" selection rule
> is replaced by a three-tier access policy (§8.1). Licence rules are unchanged, so the
> exclusion list and the train/infer pilot split survive intact. Three decisions follow:
> Microsoft Planetary Computer as a STAC catalogue for Sentinel-1 RTC (§8.2a); Forecast
> Alert Zones in scope at a 72-hour horizon (FR-3.12–3.15); and vulnerability downscaled
> within district rather than scraped or flattened (FR-5.5–5.8, closing Q-1).

> **v1.2 revision — database host and repository layout.** The Postgres host is now named:
> **Neon** (§9.7). Supabase was evaluated first and rejected — it does not ship `h3` or
> `h3_postgis`, which FR-2.5 requires, and §2.2 rules out authentication, so every Supabase
> differentiator is out of scope. Recorded in `docs/adr/0001-neon-as-database-host.md`.
> The repository layout (§9.8) is flattened: `apps/` and `packages/` collapse to top-level
> `web/`, `api/`, `pipeline/`, and `packages/schemas` becomes `core/`. Alembic is dropped in
> favour of numbered SQL under `infra/migrate.sh`. Frontend is Next.js 16, not 15.

> **v1.3 revision — flood layer verified, pilot build order inverted.** Three changes, each
> forced by a measurement rather than an argument. First, the MSPC `sentinel-1-rtc`
> collection was probed and **cleared** (§8.2a): live, CC BY 4.0, anonymous SAS token, 632
> scenes over Wayanad and 1,697 over Barpeta, all dual-pol. The CDSE fallback and its day of
> pyroSAR terrain correction leave the critical path. Second, the empirical flood pipeline is
> **built on Barpeta and then run over Wayanad**, not the reverse (§9.4, §11) — Barpeta
> yields ~55 acquisitions coinciding with a flood day against Wayanad's ~8, because Wayanad's
> floods last a median 1.5 days and S1 cannot see them (§8.6). Third, that pipeline writes
> `riverine_flood`, never `flash_flood` (FR-3.16); flash flood is carried by the I–D
> threshold path (FR-4.2), now anchored on the INDOFLOODS event catalogue (§8.2b).

**Companion documents**
- Technical architecture — https://claude.ai/code/artifact/1249cb1b-e3f8-4dcc-b599-35ae920b69bf
- Data sources audit — https://claude.ai/code/artifact/84c39bcc-e814-42ac-85b6-230198dd6e71
- Team onboarding guide — `TEAM-GUIDE.md`
- Data toolkit — `sih-data-toolkit.tar.gz`

---

## 1. Overview

### 1.1 The problem

India's disaster-prone regions face recurring landslides, floods, coastal erosion and
cloudbursts. Vulnerable habitations remain inside unsafe zones, producing repeated loss of
life and property. Relocation today is **reactive** — it begins after a disaster, under
emergency conditions, with no pre-computed assessment of where people should go or whether
the destination can absorb them.

Three failures compound:

1. **No standing inventory of unsafe habitation.** Hazard maps exist but are not joined to
   population, vulnerability and loss history, so nobody has a ranked list of which
   settlements need to move first.
2. **No capacity check on destinations.** Relocation sites are chosen for land availability
   alone. Sites with adequate land but no water supply or school capacity fail within two
   years, and families return.
3. **No separation between "move permanently" and "evacuate tonight."** These are different
   decisions with different budgets and timescales, and conflating them means neither is
   made well.

### 1.2 What we are building

A GIS decision-support platform that:

- Maintains a continuously updated **multi-hazard Red Zone** map at 30–750 m resolution
- Distinguishes **Permanent Red Zones** (unsuitable for habitation) from **Active Alert
  Zones** (temporarily unsafe right now) and **Forecast Alert Zones** (predicted to
  cross threshold within 72 hours) — the difference between an evacuation notification
  and an evacuation order
- Generates and scores **candidate relocation sites**, reporting the specific constraint
  that limits each site's capacity
- Produces a **prioritised, triaged queue** of habitations for immediate, short-term and
  medium-term relocation
- Explains every score, so a District Magistrate can defend a relocation order

### 1.3 What this is not

A screening and prioritisation tool, **not** a substitute for site-specific geotechnical
investigation. Cell-level scores identify where scarce survey capacity should be spent
first. Any actual relocation order requires ground verification, a detailed slope-stability
or hydraulic study, and community consultation. This constraint must be surfaced in the
interface as a persistent label on every output, not buried in documentation.

---

## 2. Goals and non-goals

### 2.1 Goals

| ID | Goal |
|---|---|
| G-1 | Give an SDMA officer a ranked, evidence-backed list of habitations to relocate, updated automatically |
| G-2 | Separate permanent relocation decisions from immediate evacuation decisions in both the model and the interface |
| G-3 | Report the *binding constraint* on every candidate site, so investment can be targeted |
| G-4 | Make every score inspectable — no unexplained numbers reach a decision-maker |
| G-5 | Run on permissively licensed data that a state government could productionise without a licensing surprise. Authentication is permitted at acquisition time; every keyed source has a declared fallback and verified quota headroom |
| G-6 | Demonstrate credibly within an 8-day build window |

### 2.2 Non-goals (v1)

- Hydrodynamic flood modelling or slope-stability engineering
- Land acquisition workflow, compensation calculation, or beneficiary management
- Mobile field-survey application
- Real-time sensor integration (IoT tilt meters, piezometers)
- Multi-lingual interface beyond English
- Authentication, RBAC, or audit logging beyond a demo stub

---

## 3. Users

| Persona | Context | Primary need |
|---|---|---|
| **SDMA planning officer** | State Disaster Management Authority. Prepares annual relocation proposals against a fixed budget. | A defensible ranked list, with cost implications and destination options |
| **District Magistrate / Collector** | Signs relocation orders. Personally accountable. | Evidence for *why this village* that survives a legal or political challenge |
| **NDRF sector commander** | Pre-positions teams before and during monsoon events. | Which populated areas are unsafe *this week*, and how many people are in them |
| **State planning department** | Approves new construction and infrastructure. | Where new building should be restricted; where it is already encroaching |

### 3.1 Primary user journey

1. Officer opens the district view. The map shows hazard intensity; the left panel shows a
   ranked queue of habitations.
2. Officer selects the top-ranked habitation. The right panel shows why it ranks there:
   hazard breakdown, exposed population, vulnerability, past losses.
3. Officer opens candidate relocation sites. Each shows a household capacity and the
   constraint that caps it ("218 households, water-limited").
4. Officer sees the augmented capacity: what the site becomes if the constraint is
   relieved, and the indicative cost.
5. Officer runs the allocation solver for the district and exports a briefing pack.

---

## 4. Success metrics

### 4.1 Product metrics (post-deployment, not measurable in 8 days)

| Metric | Target |
|---|---|
| Habitations screened without manual survey | 100% of pilot districts |
| Time from "which villages need relocation?" to a ranked list | Under 5 minutes (from weeks) |
| Candidate sites rejected before survey due to capacity constraint | Measurable reduction in failed resettlements |

### 4.2 Build metrics (measurable in 8 days)

| ID | Metric | Target |
|---|---|---|
| M-1 | Landslide susceptibility model AUC under **spatial block cross-validation** | ≥ 0.75 |
| M-2 | Agreement with IIT Delhi's published India Landslide Susceptibility Map on held-out Uttarakhand | Qualitative comparison, documented |
| M-3 | Map render time, 500k H3 cells | < 2 s to first paint |
| M-4 | API p95 latency, `/habitations` and `/zones/{h3}` | < 300 ms |
| M-5 | Full pipeline rerun for one pilot district | < 45 min |
| M-6 | Demo runs end-to-end with zero live external API calls | Pass/fail |
| M-7 | SAR water-detection rule scored against Sen1Floods11 hand-labelled India chips | Precision and recall reported, not visually asserted |

> **Note on M-1:** an AUC above 0.90 under *random* k-fold cross-validation is a red flag,
> not a success. Spatial autocorrelation leaks between folds and inflates the score. See §7.2.

---

## 5. Scope

### 5.1 In scope for v1 (8 days)

- Multi-hazard index across 6 hazard types, pan-India at H3 resolution 7
- Four pilot districts at H3 resolution 8/9
- Permanent Red Zone / Caution Zone / Active Alert Zone classification
- **Forecast Alert Zones** — 72-hour horizon, pilot districts only
- Vulnerability index from Census demographics, housing type and service access,
  **downscaled within district** using building, access and nightlight covariates
- Habitation-level priority scoring and four-tier triage
- Candidate site generation with binding-constraint carrying capacity
- Min-cost-flow allocation of habitations to sites
- SHAP-based per-cell explanation
- Live trigger ingestion from IMERG, IMD and CWC with recorded-snapshot fallback
- Forecast trigger ingestion from ECMWF open-data
- Scenario endpoint for adjustable hazard weights
- Web interface: map, prioritised queue, dossier panel, time slider, scenario drawer

### 5.2 Explicit cut-line

If behind at the end of Day 5, drop **in this order**:

1. Forecast Alert Zone **UI** (keep the endpoint — it is nearly free once the
   observed-trigger code exists)
2. PDF briefing export
3. Scenario weight sliders (keep the endpoint, drop the UI)
4. Encroachment change detection
5. Allocation arcs on the map (keep the solver, show results in the table)

**Never cut:** the multi-hazard map, the cell dossier with its explanation, the prioritised
queue, and one working carrying-capacity comparison. Those four *are* the demo.

### 5.3 Deferred to v2

Land acquisition workflow · beneficiary tracking · mobile field app · IoT sensors ·
in-situ mitigation cost engineering · multi-state deployment · Hindi and regional languages

---

## 6. Functional requirements

### 6.1 Data ingestion

| ID | Requirement |
|---|---|
| FR-1.1 | Every external data source is accessed through a single adapter class with a uniform interface |
| FR-1.2 | Every adapter caches its raw response to object storage before parsing |
| FR-1.3 | The application layer reads **only** from PostgreSQL. No UI request ever calls an external API |
| FR-1.4 | The system ships a recorded snapshot of a real monsoon week, replayable via a `DEMO_MODE` flag |
| FR-1.5 | Every dataset carries its licence and required attribution string in the manifest |
| FR-1.6 | Dynamic feeds are polled on a schedule; a failed poll logs and retains the last good value rather than nulling |
| FR-1.7 | Credentials are read from environment variables only. No key appears in source, in the manifest, or in the demo snapshot. `.env.example` documents variable names with no values |
| FR-1.8 | Every Tier B/C source declares in `sources.yaml` a named fallback source and a quota record (limit, window, calls needed). Quota headroom is verified before Day 1; target 5–10×, below 2× the source is demoted to enrichment-only |
| FR-1.9 | An adapter that exhausts its quota falls back to its declared fallback source and logs the substitution. It never fails silently and never nulls the layer |

### 6.2 Gridding

| ID | Requirement |
|---|---|
| FR-2.1 | All spatial data is resampled onto a single H3 hexagonal index |
| FR-2.2 | Working resolution: H3 res 7 nationally (~637,000 cells), res 8/9 in pilot districts |
| FR-2.3 | The pipeline is parameterised by area of interest and resolution; a national run and a district run share the same code path |
| FR-2.4 | H3 indices are stored as `BIGINT`, never as text |
| FR-2.5 | Coarser resolutions are materialised views built with `h3_cell_to_parent()`, refreshed after each scoring run |
| FR-2.6 | Population is distributed dasymetrically — redistributed onto built-up footprints rather than spread evenly across a polygon |

### 6.3 Red Zone engine

| ID | Requirement |
|---|---|
| FR-3.1 | Static susceptibility `S_h` and dynamic trigger `T_h` are stored as separate quantities and composed at read time |
| FR-3.2 | Per-hazard score: `H_h(c,t) = clamp(S_h(c) · (1 + β_h · T_h(c,t)), 0, 1)` with `β_h ≈ 1.0` |
| FR-3.3 | A cell with `S_h = 0` must remain 0 regardless of trigger value |
| FR-3.4 | Multi-hazard combination uses probabilistic union: `MHI = 1 − Π_h (1 − w_h · H_h)` |
| FR-3.5 | Hazard weights `w_h`: landslide 1.0, flash flood 1.0, storm surge 0.9, riverine flood 0.8, coastal erosion 0.7 |
| FR-3.6 | Both `MHI_static` (all triggers zero) and `MHI_live` (current triggers) are computed and stored |
| FR-3.7 | `dominant_hazard = argmax_h (w_h · H_h)` is stored per cell |
| FR-3.8 | Permanent Red Zone: `MHI_static ≥ 0.75`, OR any `S_h ≥ 0.85`, OR a fatal event in the cell within 25 years with `MHI_static ≥ 0.60` |
| FR-3.9 | Caution Zone: `0.45 ≤ MHI_static < 0.75` |
| FR-3.10 | Active Alert Zone: `MHI_live ≥ 0.75` while `MHI_static < 0.75`; time-boxed, expires as the trigger decays |
| FR-3.11 | Active Alert Zone status must never influence a relocation tier assignment |
| FR-3.12 | Forecast Alert Zone: `MHI_fcst ≥ 0.75` within a **72-hour** horizon, computed for pilot districts only. `MHI_fcst` is the same composition applied to forecast triggers |
| FR-3.13 | Forecast Alert Zones render as a visually distinct state — a different treatment, not a darker shade of the observed ramp — and always display the issuing model, cycle time and horizon |
| FR-3.14 | FR-3.11 applies doubly to Forecast Alert Zones. They never influence tier assignment |
| FR-3.15 | Forecast output is attributed to the meteorological agency. The system's claim is the threshold crossing, never the weather. No interface string may state or imply that the system predicts disasters |
| FR-3.16 | The empirical Sentinel-1 inundation-frequency layer is stored as `hazard_type = 'riverine_flood'`. It measures standing water at satellite overpass and is **never** written as `flash_flood`. Mislabelling it applies the wrong FR-3.5 weight (1.0 instead of 0.8) and corrupts `dominant_hazard` in FR-3.7 |
| FR-3.17 | Flood susceptibility is hard-zeroed where `HAND > 30 m` **or** `slope > 15°`, applied before any normalisation. Min–max normalised HAND otherwise gives every ridge top a non-zero flood score which FR-3.2 then amplifies by the trigger. FR-3.3 protects zeros; this requirement is what creates them |

### 6.4 Trigger computation

| ID | Requirement |
|---|---|
| FR-4.1 | Antecedent Rainfall Index: `API_t = Σ kⁱ · P_(t−i)` with `k ≈ 0.9` over a 15-day window |
| FR-4.2 | Intensity–duration threshold `I = α · D^(−β)` fitted per physiographic zone from historical event dates against gridded rainfall |
| FR-4.3 | `T = 1` when the current rolling window crosses the threshold curve, ramped continuously below it |
| FR-4.4 | Trigger values are recomputed at least hourly during monsoon season |
| FR-4.5 | Rainfall sources are split by role: **CHIRPS v3** for climatology and I–D threshold fitting; **GPM IMERG Early** (half-hourly, 0.1°, ~4 h latency) for operational ARI and live trigger; **ECMWF open-data** for forecast trigger. CHIRPS is daily with multi-day latency and cannot satisfy FR-4.4 |
| FR-4.6 | Fallback chain: IMERG → CHIRPS at degraded cadence (FR-4.4 relaxes to daily, and the degradation is surfaced in the UI). ECMWF → IMD basin QPF → Open-Meteo. Open-Meteo is Tier C: its free tier is non-commercial, permitted for the build window only and flagged for replacement before any deployment |
| FR-4.7 | Observed and forecast trigger values are stored as separate quantities and never merged into a single displayed number |
| FR-4.8 | I–D thresholds are fitted on INDOFLOODS event dates (§8.2b) against **CHIRPS v3**, the source FR-4.5 assigns to threshold fitting. The `T1d`–`T10d` columns shipped inside INDOFLOODS are derived from **EM-Earth 0.1°**, a different rainfall climatology; they may be used for cross-checking but must not be substituted for a CHIRPS fit without a documented bias comparison. A curve fitted on one product and served against another fires on the wrong days |

### 6.5 Exposure and vulnerability

| ID | Requirement |
|---|---|
| FR-5.1 | Vulnerability index combines four normalised dimensions: demographic, structural, access/coping, economic |
| FR-5.2 | Dimension weights are derived by PCA (the SoVI method), not hand-picked |
| FR-5.3 | Census 2011 is used for **ratios only** (vulnerability shares, housing type); absolute population counts come from WorldPop |
| FR-5.4 | Cell-level values aggregate to habitation level via LGD code |
| FR-5.5 | District-level Census PCA ratios are **downscaled dasymetrically within the district** using covariates already in the stack: Open Buildings 2.5D height and footprint density (structural), OSM distance to road / school / health facility (access), VIIRS annual nightlight composite (economic). The demographic dimension remains district-level — no observable proxy exists for age structure |
| FR-5.6 | Each district's population-weighted mean of every downscaled dimension must reproduce its Census district value. The SoVI PCA (FR-5.2) runs on the combined feature set after this constraint is applied |
| FR-5.7 | A flat district-level vulnerability index is **not acceptable** as the working design. If V̂ is constant across a district, within-district ranking reduces to `ĥ · f̂` and vulnerability contributes nothing to the ordering a District Magistrate actually sees. Flat V̂ is a last-resort failure state and must be labelled as such in the interface |
| FR-5.8 | A village-level Census PCA obtained via data.gov.in, if reachable, refines the anchor. It is an enhancement, never a dependency |

### 6.6 Prioritisation

| ID | Requirement |
|---|---|
| FR-6.1 | Priority score: `PS_j = (ĥ_j · f̂_j · V̂_j) × (1 + γ · L̂_j)` with `γ ≈ 0.5` |
| FR-6.2 | `L̂_j` is time-decayed loss history: `Σ e^(−λ(t_now − t_i)) · severity_i`, 10-year half-life |
| FR-6.3 | The system exposes **two rankings**: per-capita urgency (`PS_j`) and caseload-weighted (`PS_j × population`). The toggle is a first-class UI control |
| FR-6.4 | Triage tiers are assigned by rule, not by score threshold — see §6.7 |

### 6.7 Triage tiers

| Tier | Rule |
|---|---|
| **Immediate** (0–6 mo) | PRZ overlap AND any of: active ground deformation detected; fatal event in last three monsoons; `f_j > 0.6` with `ĥ_j > 0.85` |
| **Short-term** (6–24 mo) | Significant PRZ overlap, high priority score, no active trigger |
| **Medium-term** (2–5 yr) | Caution Zone with adverse trend — built-up area growing inside hazard footprint, or loss frequency rising |
| **Mitigate in situ** | Small PRZ fraction where slope stabilisation, embankment or drainage retrofit costs less than relocation |

> **FR-6.5:** The *Mitigate in situ* tier is not requested by the problem statement and is
> mandatory. A tool that cannot recommend against relocation will not be trusted by the
> officials who fund relocation.

### 6.8 Carrying capacity

| ID | Requirement |
|---|---|
| FR-7.1 | Candidate sites are generated within a configurable radius (default 15 km) of the source habitation |
| FR-7.2 | Site eligibility mask: `MHI_static < 0.25`, slope < 15°, not forest / protected area / CRZ-I or II / water body, contiguous area ≥ 2 ha |
| FR-7.3 | Land tenure is reported as government/revenue, private, or **tenure unverified** — never guessed |
| FR-7.4 | Capacity is the **minimum** of independent constraints, never an average: `CC(s) = min(CC_land, CC_water, CC_school, CC_health) × μ_livelihood` |
| FR-7.5 | `binding_constraint = argmin(...)` is stored and displayed |
| FR-7.6 | Augmented capacity is computed: capacity after relieving the binding constraint, with the intervention named and an indicative cost |
| FR-7.7 | Suitability (0–100) is stored and displayed **separately** from capacity |

**Capacity norms**

| Constraint | Formula | Norm |
|---|---|---|
| Land | `A_developable / a_hh` | ~90 m² plot + 40% infrastructure overhead ≈ 126 m²/household |
| Water | `Y_sustainable / (LPCD × HH_size)` | CPHEEO: 55 LPCD rural, 135 LPCD urban with sewerage |
| Schooling | `spare_seats / children_per_HH` | UDISE+ enrolment vs sanctioned capacity within 1 km |
| Health | `(PHC_norm_pop − catchment_pop) / HH_size` | IPHS: 1 PHC per 30,000 plains / 20,000 hilly and tribal |
| Livelihood | multiplier `μ ∈ [0.6, 1.0]` | Jobs, market and cultivable land within commute distance |

### 6.9 Allocation

| ID | Requirement |
|---|---|
| FR-8.1 | Habitation-to-site assignment is solved as a min-cost flow: maximise `Σ x_js · (PS_j · suit_s) − c_js · x_js` subject to `Σ_s x_js ≤ demand_j` and `Σ_j x_js ≤ CC_s` |
| FR-8.2 | Solved exactly with OR-Tools. No heuristic approximation — the problem is small enough per district |
| FR-8.3 | A household group may split across sites, and any split must be surfaced explicitly as a social cost requiring sign-off |

### 6.10 Explainability

| ID | Requirement |
|---|---|
| FR-9.1 | SHAP values are precomputed per cell; the top five contributing factors are stored as JSONB |
| FR-9.2 | `GET /zones/{h3}` returns the explanation alongside the score |
| FR-9.3 | Per-cell model confidence is stored and rendered as a hatch pattern, not a solid colour |
| FR-9.4 | `POST /scenario` allows re-ranking under adjusted hazard weights, norms or radius |

### 6.11 Interface

| ID | Requirement |
|---|---|
| FR-10.1 | Map renders H3 cells via GPU (deck.gl `H3HexagonLayer` over MapLibre GL JS). **Leaflet is prohibited** — it cannot render at this scale |
| FR-10.2 | Basemap tiles are self-hosted (Protomaps PMTiles or an OSM style). No third-party billing dependency at demo time |
| FR-10.3 | Left panel: prioritised habitation table with tier chips, urgency/caseload toggle, district and hazard filters |
| FR-10.4 | Right panel: dossier — MHI breakdown, SHAP bar chart, loss-history timeline, ranked candidate sites |
| FR-10.5 | Bottom: time slider scrubbing the dynamic trigger layer, spanning −7 days to +3 days. The present moment is marked, and forecast time is styled distinctly from observed time along the whole control |
| FR-10.6 | Scenario drawer with weight sliders, debounced into `POST /scenario` |
| FR-10.7 | All animation respects `prefers-reduced-motion` |
| FR-10.8 | A persistent "screening grade" label appears on every output surface |

---

## 7. Machine learning specification

### 7.1 Models

| Model | Method | Labels | Features |
|---|---|---|---|
| **Landslide susceptibility** | XGBoost binary classifier, one per physiographic zone | ~5,500 open India records (§8.3) | Slope, aspect, plan & profile curvature, TWI, SPI, local relief, soil class, distance to fault, distance to stream, **distance to road**, NDVI, land cover, mean annual rainfall |
| **Flood susceptibility** | Empirical, not modelled — Sentinel-1 SAR water-mask stack → inundation frequency, combined with HAND. Scenes from the **pre-terrain-corrected S1 RTC collection via STAC** (§8.2a). Built on Barpeta, then run over the remaining pilots (§9.4). Writes `riverine_flood` (FR-3.16) | Sen1Floods11 India chips score the water-detection rule (M-7, ML-6); India Flood Inventory v3 and INDOFLOODS for event-date corroboration | HAND, flow accumulation, TWI, elevation above river, historical frequency |
| **Coastal erosion** | Shoreline change rate (EPR/LRR) from Landsat/Sentinel-2 time series, projected to a 25-year setback line. Tractable via STAC rather than local bulk download | Derived | Shoreline transects |
| **Encroachment detection** | Annual diff of Open Buildings 2.5D Temporal inside Permanent Red Zones, with Sentinel-2 via STAC where the annual product is too coarse | N/A | Building presence, height, count 2016–2023 |
| **Trigger thresholds** | Power-law fit `I = α·D^(−β)` per zone | INDOFLOODS event dates (§8.2b) vs CHIRPS v3 gridded rainfall — see FR-4.8 | Rainfall intensity, duration |
| **Vulnerability downscaling** | Dasymetric redistribution of district PCA ratios, constrained to reproduce the district mean | Census 2011 district PCA (anchor) | Building height & density, distance to road/school/health, VIIRS nightlights |

### 7.2 Validation protocol

| ID | Requirement |
|---|---|
| ML-1 | **Spatial block cross-validation is mandatory.** Random k-fold leaks through spatial autocorrelation and produces meaningless scores |
| ML-2 | Report AUC on a held-out *region*, plus a success-rate curve |
| ML-3 | Negative class sampled from low-slope, inventory-free cells with spatial stratification; ratio 1:1 to 1:3 |
| ML-4 | **Never train on IIT Delhi's India Landslide Susceptibility Map.** It is a model output; training on it leaks. Use it for benchmark comparison only |
| ML-5 | Publish a model card documenting label count, feature list, validation scheme and known weak features |
| ML-6 | The SAR water-detection rule is scored **quantitatively** against Sen1Floods11 hand-labelled India chips and reported as precision/recall. Visual inspection selects candidate rules; it does not validate them. Radar shadow is spectrally indistinguishable from open water, so an unscored threshold in hilly terrain is an unmeasured error, not a small one |

### 7.3 Known model limitations to state explicitly

- Lithology is the weakest feature. No open lithology map exists at usable resolution;
  SoilGrids WRB soil class is used as a proxy.
- Only ~5,500 open landslide labels exist for all of India, concentrated in the Western
  Ghats and Sikkim. The model generalises to unlabelled terrain by design and this is
  validated by spatial block CV, not assumed.
- Census 2011 demographics are fifteen years old and used for ratios only. The
  within-district downscaling (FR-5.5) introduces its own assumption — that building
  height, service distance and nightlight intensity track the Census dimensions they
  proxy. This is stated, not validated; the constraint in FR-5.6 bounds the error at
  district level but not below it.
- Forecast skill degrades with horizon. The 72-hour bound in FR-3.12 is a deliberate
  limit, not a technical ceiling. Extending it would raise the honesty cost faster
  than the operational value.

---

## 8. Data requirements

### 8.1 Selection rules and access tiers

**Rule 1 is absolute and unchanged.** Every dataset must carry a **permissive
licence** — attribution-only, permitting commercial use and redistribution.

Authentication and metering are no longer disqualifying. They determine which tier a
source occupies and what obligations attach to it.

| Tier | Definition | Where it may be used |
|---|---|---|
| **A** | Anonymous, unmetered, bulk | Anywhere, including the critical path. **Mandatory** for terrain, land cover, boundaries and training labels |
| **B** | Keyed, generous quota, cached to Postgres at build time | Anywhere, with a declared Tier-A or Tier-B fallback |
| **C** | Keyed with tight quota, or a licence that expires on productionisation | One-off enrichment only. Never in a loop, never a dependency |

The runtime rule is unchanged and non-negotiable: **keys change how data is acquired,
never how it is served.** Adapters write to Postgres, the UI reads only Postgres
(FR-1.3), and the demo snapshot carries no credentials and makes no external calls
(NFR-4).

37 datasets were audited; 25 cleared and 12 excluded. Of the 12 exclusions, 10 were
licence decisions — a key does not fix a non-commercial clause — and 2 have no API to
key into. **The exclusion list is therefore substantially unchanged**, and with it the
Himalayan label gap and the train/infer pilot split in §9.4.

### 8.2 Tier A core stack (anonymous, unmetered, permissive)

| Layer | Source | Access | Licence |
|---|---|---|---|
| Elevation & all terrain derivatives | Copernicus DEM GLO-30 | `s3://copernicus-dem-30m` | Copernicus (commercial + redistribution OK) |
| Land cover | ESA WorldCover v200 10 m | `s3://esa-worldcover/v200/2021/map` | CC BY 4.0 |
| Soil / lithology proxy | SoilGrids 250 m | `files.isric.org/soilgrids/latest/data/` | CC BY 4.0 |
| Permanent water mask | JRC Global Surface Water v1.4 | Direct GCS tiles | Copernicus, unrestricted |
| Rainfall (historical) | CHIRPS **v3.0** | `data.chc.ucsb.edu/products/CHIRPS/v3.0/` | Public domain / CC BY |
| Reanalysis | ERA5 | `s3://nsf-ncar-era5` | UCAR terms |
| Population | WorldPop India 100 m constrained | `data.worldpop.org` | CC BY 4.0 |
| Buildings + growth | Google Open Buildings 2.5D Temporal | GCS, 2016–2023 annual | CC BY 4.0 or ODbL |
| Building footprints | Microsoft GlobalMLBuildingFootprints | Azure Blob | CDLA-Permissive-2.0 |
| Boundaries | geoBoundaries IND + DataMeet | GitHub `/raw/<sha>/` | CC BY 2.5 IN |
| Admin codes | LGD via ramseraph / planemad mirrors | GitHub | GODL-India |
| Roads, schools, health | OpenStreetMap India (Geofabrik) | `india-latest.osm.pbf`, 1.6 GB | ODbL (share-alike) |
| Nightlights (economic covariate) | VIIRS annual composite, EOG Colorado Mines | Direct download | CC BY 4.0 |
| Forecast rainfall | ECMWF open-data | Keyless, 0.25°, 4 cycles/day | CC BY 4.0 |

### 8.2a Tier B — keyed, cached at build time, fallback declared

| Source | Auth | Used for | Fallback |
|---|---|---|---|
| **Microsoft Planetary Computer** (STAC catalogue) | **Anonymous SAS — verified 2026-08-31, no key** | Sentinel-1 **RTC**, Sentinel-2, Landsat | CDSE → AWS Open Data |
| Copernicus Data Space Ecosystem | Instant registration | S1 GRD, S2 L2A | AWS Open Data (`sentinel-s1-l1c`, `sentinel-cogs`) |
| GPM IMERG Early (NASA GESDISC) | Earthdata Login | Live ARI, live trigger | CHIRPS v3 at degraded cadence |
| IMD district APIs | Registration; turnaround unknown | Nowcast, warnings, basin QPF | Recorded snapshot + ECMWF |
| CWC / India-WRIS | Registration | River levels | Recorded snapshot |
| data.gov.in | Instant key | Census PCA, UDISE+, IPHS reference | Downscaled district PCA (FR-5.5) |
| MOSDAC (ISRO) | Slow approval | INSAT-3D cyclone / rainfall for storm surge | IMD cyclone track |
| Open-Meteo | Keyless | Forecast rainfall, last resort | — **Tier C**: free tier is non-commercial, build window only |

**MSPC is used as a STAC catalogue, not a compute environment.** Query STAC, pull
COGs, process on our own machines, land the result in Postgres. The pre-terrain-
corrected S1 RTC collection removes the SNAP orbit-correct → calibrate →
terrain-correct chain from the flood pipeline, which is the largest single time saving
available.

**Verified 2026-08-31 — the Day-0 check is done and the collection cleared.** Recorded
so nobody re-runs it:

| Check | Result |
|---|---|
| STAC endpoint | `planetarycomputer.microsoft.com/api/stac/v1` — HTTP 200 |
| Collection `sentinel-1-rtc` | Live, licensed **CC BY 4.0** on the collection |
| Asset auth | `GET /api/sas/v1/token/sentinel-1-rtc` issues an **anonymous** SAS token, ~1 h expiry. No subscription key, no login |
| Unsigned asset read | HTTP 409 — assets **must** be signed; sign per session and refresh on expiry |
| Signed read | HTTP 200; HTTP 206 on range request, valid COG header — windowed reads work |
| Scenes over **Barpeta** | **1,697** (2015–2025); tracks 41 asc / 150 desc / 114 asc / 77 desc; 557 in JJAS; 1,583 dual-pol VV+VH, 114 VV-only |
| Scenes over **Wayanad** | **632** (2015–2025); tracks 63 desc (327) / 165 desc (304); 225 in JJAS; all dual-pol |
| Asset size | ~1.9 GB per band per full swath — read an overview level, never the full COG |

Two consequences. The CDSE fallback and its ~1 day of pyroSAR terrain correction leave
the critical path, and the §12 risk row for this is closed. The 114 VV-only scenes over
Barpeta are a real inhomogeneity: a stack mixing VV-only and dual-pol dates silently
changes the detection rule mid-series, so pick one polarisation configuration and hold it.

### 8.2b INDOFLOODS — gauge flood-event catalogue

Zenodo record `14584655`, downloaded and audited. A gauge **stage-exceedance** catalogue,
not an inundation dataset: `Flood` means peak stage above the station's Warning Level,
`Severe Flood` above its Danger Level.

| Contents | Figures |
|---|---|
| Gauges | 214 total — **155 Open**, 59 Restricted (no events released) |
| Events | **4,548**, across the 155 open gauges, 1965-07 → 2020-09 |
| Event-scale precipitation | `T1d`–`T10d` antecedent rainfall, from **EM-Earth 0.1°** — see FR-4.8 |
| Catchment attributes | 107 columns × 155 catchments, plus catchment polygons |
| Class split | 2,919 `Flood` / 1,629 `Severe Flood`; no missing values in events or precipitation |

**What it is used for.** Three roles, all real:

1. **I–D threshold fitting (FR-4.2, FR-4.8).** 4,548 dated events give the
   intensity–duration cloud per physiographic zone. This is the slot that previously had
   no data behind it, and a positives-only lower-envelope fit is the standard method.
2. **`disaster_event` and loss history (FR-6.2).** 4,548 dated, severity-tiered,
   geolocated events feed `L̂_j`. It carries no fatality or damage counts, so FR-3.8's
   "fatal event in the cell" still requires India Flood Inventory v3 and COOLR.
3. **Corroborating the empirical flood surface.** Event dates select which S1 scenes to
   pull, and catchment-level event frequency is an independent check on inundation
   frequency.

**What it is not used for.** It is **not** a training set for a per-cell flood classifier
and must not become one. It contains **zero negatives** — all 4,548 rows are floods, so
ML-3's 1:1–1:3 negative sampling has nothing to sample. Its labels are catchment-integrated
over a median catchment of 4,400 km² (≈ 850 H3 res-7 cells, mean 22,623 km²), so a cell-level
target is undefined. And the effective spatial sample size is **155, not 4,548** — events
cluster at up to 419 per gauge with a median of 10, so any per-cell AUC computed on the row
count is spatial pseudo-replication of exactly the kind the M-1 note warns about.

**Licence — unresolved, blocking.** Nothing in the download states a licence: no LICENSE
file, nothing in `variables_description_indofloods.pdf`. §8.1 Rule 1 is absolute, so the
Zenodo record must be checked before this enters `sources.yaml`, and the derived EM-Earth
precipitation columns need their own check. Tracked as Q-7.

### 8.3 Training labels

| Source | Licence | Labels | Count | Coverage |
|---|---|---|---|---|
| Kerala 2018 monsoon inventory | CC BY 4.0 | Points | 4,728 | All Kerala incl. Wayanad |
| NASA COOLR / GLC | Unstated (cite Kirschbaum et al.) | Points | 321 fatal | India, highest of any country |
| Southern Sikkim multi-temporal | CC BY 4.0 | 255 polygons + 185 points | 440 | ~3,000 km², 2002–2019 |
| HR-GLDD | CC BY 4.0 | Segmentation masks, 3 m | 576 MB | Kodagu, Karnataka |
| India Flood Inventory v3 | CC BY 4.0 | Event records + district impact | 1967–2023 | All India |
| Sen1Floods11 | Unstated upstream; mirrors CC BY 4.0 | Segmentation masks 10 m | 467 weak + 68 hand-labeled India chips | India is 3rd largest contributor |
| MMFlood | CC BY 4.0 | S1 GRD + flood masks | 1,748 pairs | India coverage unconfirmed |
| INDOFLOODS (§8.2b) | **Unstated — verify, Q-7** | Gauge stage-exceedance events + 107 catchment attributes | 4,548 events / 155 catchments | 15 states; none in Assam, Sikkim or the restricted Ganga basin |

### 8.4 Live feeds (with recorded fallback)

| Feed | Endpoint | Cadence |
|---|---|---|
| **Gridded precipitation (live trigger)** | GPM IMERG Early via GESDISC | Half-hourly, ~4 h latency |
| **Forecast precipitation** | ECMWF open-data | 4 cycles daily, 72 h horizon used |
| District rainfall & departure | `api.imd.gov.in/api/v1/districtrainfall` | Daily |
| District nowcast | `/api/v1/districtnowcast` | 3-hourly |
| District warnings (17 hazard types) | `/api/v1/districtwarning` | Daily, 5-day horizon |
| River basin QPF | `/api/v1/basinqpf` | Daily, 5-day |
| AWS/ARG station observations | `/api/v1/aws_data` | Hourly |
| Cyclone track, wind, cone | `/api/v1/cyclone_track` and siblings | Event-driven |
| River water levels | CWC Flood Forecast / India-WRIS | Daily |

### 8.5 Excluded datasets — do not re-add

**Excluded on licence.** Authentication changes nothing here; a key does not fix a
non-commercial or share-alike clause. The temptation after relaxing the access rule is
to re-add anything merely *reachable* — these are still poison for the same reasons.

| Dataset | Reason |
|---|---|
| GADM | "Redistribution or commercial use is not allowed without prior permission" |
| FABDEM | CC BY-NC-SA 4.0; share-alike could reach model derivatives |
| MERIT-Hydro / MERIT DEM | CC BY-NC or ODbL, redistribution prohibited, Google Form → Dropbox delivery |
| GEM Global Seismic Hazard (GIS files) | CC BY-NC-SA; only the PNG is open. Use IS 1893 zonation |
| SHRUG | CC BY-NC-SA |
| Global Flood Database | CC BY-NC / CC BY-NC-ND |
| WorldFloods | CC BY-NC-SA; India coverage unverified |
| CAS Landslide Dataset | CC BY-NC, no India data |
| **Google Earth Engine** | Free tier is research / non-commercial. Reintroduces exactly the trap GADM was rejected over, and inverts the architecture by moving computation out of artefacts we own |
| Bhuvan bulk downloads | Single-user licence prohibiting internet hosting. Permitted as a screenshot-grade visual cross-check during validation; never enters the data store |

**Excluded on access — no API exists to key into.**

| Dataset | Reason |
|---|---|
| GSI Bhukosh / Bhusanket | Viewer-only, per-toposheet click-through; nothing on data.gov.in |
| ISRO Landslide Atlas | PDF report only; underlying inventory on internal WebGIS |

**Re-opened by the tier revision, declined on merit.**

| Dataset | Reason |
|---|---|
| OpenTopography | The 450,000 km² cap only bit at national scale, and GLO-30 on S3 already works. Retained only as an optional Day-8 alternate-DEM sensitivity check |

### 8.6 Known data gaps

| Gap | Mitigation |
|---|---|
| **Lithology** — no open map at usable resolution; full-res GLiM has no stated licence | SoilGrids WRB soil class (250 m) as proxy + GLiM 0.5° as coarse regional categorical. Declare weakest feature in the model card |
| **Himalayan landslide labels** — none open for Uttarakhand, Himachal, Darjeeling, Mizoram | Train in Western Ghats + Sikkim; run held-out inference on Uttarakhand; benchmark against published ILSM |
| **Flash floods are shorter than the S1 revisit** — near Wayanad, 2015–2020, flood events run a median 1.5 days and occupy 51 of 2,191 days (a 2.3% duty cycle). Against 355 RTC scenes in that window, ~8 acquisitions coincide with a flood day; Barpeta's floodplain regime gives ~55 from 869 scenes. Inundation frequency cannot measure a hazard it never observes | Build the empirical pipeline on Barpeta where the signal exists (§9.4, §11). Over Wayanad, weight HAND primary, drive `confidence` off `valid_observation_count`, and let NFR-9 hatching carry the sparsity. Wayanad's flash-flood hazard comes from the I–D threshold path (FR-4.2), not from SAR |
| **SAR false positives in the pilot terrain** — radar shadow on steep slopes is spectrally indistinguishable from open water, and flooded paddy in the Kabini and Brahmaputra valleys reads as water while JRC permanent water does not remove it | Exclude slopes > 15° from water detection (FR-3.17), mask or flag ESA WorldCover cropland — already in the Tier A stack — and score the detection rule against Sen1Floods11 chips (ML-6) rather than by eye |
| **Open river gauges stop at the Vindhyas** — every INDOFLOODS gauge in Uttar Pradesh (22), Bihar (12), Uttarakhand (6), Himachal (1) and Delhi (1) is Restricted, and there are **no Assam gauges at all**. The Himalayan label gap is therefore a flood gap as well as a landslide one | Barpeta's flood history comes from India Flood Inventory v3 district records, not from gauges. Rudraprayag has no open gauge within 611 km and stays held-out inference, which was already the design |
| **Census 2011 village PCA** — exists as hundreds of per-district NADA entries, not one file | **Resolved — see FR-5.5.** Do not scrape and do not fall back to flat district values. Downscale district PCA ratios dasymetrically using building, access and nightlight covariates already in the stack, constrained to reproduce the district mean. Costs roughly one raster plus a calibration step and yields within-district variation from 2023 observations rather than 2011 enumeration |

### 8.7 Access traps

- **geoBoundaries** API returns HTTP 429. The repo uses Git LFS — plain
  `raw.githubusercontent.com` URLs return pointer files, not geometry. Use
  `/raw/<commit-sha>/` media URLs or the HDX mirror.
- **GPM IMERG** requires an Earthdata Login *and* authorisation of the "NASA GESDISC DATA
  ARCHIVE" application in the URS profile. Missing the second step returns 401 and looks
  like a bad password. IMERG is now on the critical path as the live trigger source, so
  this trap is expensive rather than merely annoying.
- **Registration latency is the critical-path access risk.** Earthdata, CDSE and
  data.gov.in issue instantly. MOSDAC approval can take days. IMD turnaround is unknown.
  All registrations are a **Day 0** task — see §11.
- **No credential enters git.** `.env.example` documents variable names with no values;
  `.env` is gitignored; the demo snapshot is verified credential-free before freeze.
- **Copernicus DEM** tile directories carry HEM/EDM/FLM/WBM auxiliary layers. Sync with
  `--include "*_DEM.tif"` or download roughly double what is needed.
- **CHIRPS v2** production ends after December 2026. Use v3.
- **LGD codes** are the join key for every Indian government dataset. Load them Day 1 or
  every downstream join degrades to fuzzy name matching.

---

## 9. Technical architecture

### 9.1 Three architectural decisions

1. **One grid, every layer.** All inputs resample onto a single H3 hexagonal index. Spatial
   joins become integer key joins; adding a hazard becomes adding a column.
2. **Susceptibility ≠ trigger.** Terrain does not change hourly; rainfall does. Static and
   dynamic quantities are stored separately and composed at read time. This mirrors GSI's
   operational landslide early-warning method.
3. **Two zones, two decisions.** Permanent Red Zone → relocation budget over months. Active
   Alert Zone → NDRF evacuation tonight.

### 9.2 Pipeline layers

| Layer | Function | Key libraries |
|---|---|---|
| **L0** Ingestion | Adapters pull, cache raw response, emit normalised records | rasterio, geopandas, httpx, APScheduler |
| **L1** Gridding | Rasters → zonal statistics per H3 cell; dasymetric population | h3-py, exactextract, rioxarray |
| **L2** Hazard scoring | Susceptibility models + trigger streams → MHI + zone class | XGBoost, scikit-learn, SHAP |
| **L3** Exposure & vulnerability | Population, demographics, service access → V index; cells → habitations | pandas, geopandas |
| **L4** Capacity & matching | Candidate sites, carrying capacity, allocation | PostGIS, OR-Tools |
| **L5** Serving | JSON API + vector tiles + web client | FastAPI, Martin, Next.js, deck.gl |

### 9.3 Resolution strategy

| H3 res | Avg cell area | Cells for India | Used for |
|---|---|---|---|
| 6 | 36.1 km² | ~91,000 | National overview, state dashboards |
| **7** | 5.16 km² | ~637,000 | **National working resolution** |
| **8** | 0.74 km² | ~4.5 M | **Pilot districts** |
| 9 | 0.105 km² | ~31 M | Candidate site micro-siting only |

### 9.4 Pilot districts

| District | Hazard | Labels | Role |
|---|---|---|---|
| Wayanad, Kerala | Landslide + flash flood | Kerala 2018 inventory (4,728 pts) | **Train** |
| Kodagu, Karnataka | Landslide | HR-GLDD masks | **Train** |
| South Sikkim | Landslide (Himalayan) | 440 polygons + points | **Train** — only open Himalayan set |
| Barpeta, Assam | Riverine flood | Sen1Floods11 + IFI v3 | **Train — flood pipeline is built here first** |
| Rudraprayag, Uttarakhand | Landslide | COOLR points only | **Held-out inference** |
| Puri, Odisha | Cyclone, coastal erosion | Derived shoreline change | **Held-out inference** |

> This selection is driven by label availability, not hazard diversity. Training in the
> Western Ghats and Sikkim and running inference on Uttarakhand — where the model has never
> seen a label — is what a national screening tool must do, since most Indian districts have
> no inventory.

> **Build order for the flood pipeline: Barpeta first, Wayanad second.** The two are not
> interchangeable starting points. Barpeta sits in the Brahmaputra floodplain — flat,
> riverine, inundation persisting for weeks — which is the regime inundation frequency was
> designed to measure, and it carries 1,697 RTC scenes against Wayanad's 632. Wayanad is a
> plateau whose floods last a median 1.5 days, so a pipeline built there would be tuned
> against a near-null surface with no way to tell a working threshold from a broken one.
> Build where the signal is legible, then run the finished pipeline over Wayanad. The code
> is AOI-parameterised under FR-2.3, so this costs nothing but the order of two runs.
>
> The landslide track is unaffected: Wayanad's headline hazard is landslide, and its 4,728
> Kerala-2018 points still make it the primary landslide training district.

### 9.5 Data model

```sql
-- reference
admin_boundary(id PK, level, lgd_code UNIQUE, name, parent_id FK, geom)
habitation(id PK, lgd_code, name, type, admin_id FK, geom_point, geom_footprint,
           population INT, households INT)

-- the grid
grid_cell(h3 BIGINT PK, res SMALLINT, admin_id FK, habitation_id FK NULL,
          centroid GEOGRAPHY, population REAL, built_area_m2 REAL)

-- hazard
hazard_static(h3 BIGINT, hazard_type TEXT, susceptibility REAL, confidence REAL,
              model_version TEXT, PRIMARY KEY (h3, hazard_type))
hazard_dynamic(h3 BIGINT, hazard_type TEXT, ts TIMESTAMPTZ, trigger_value REAL, source TEXT)
              -- PARTITION BY RANGE (ts), BRIN index on ts
mhi_snapshot(h3 BIGINT, ts TIMESTAMPTZ, mhi_static REAL, mhi_live REAL,
             dominant_hazard TEXT, zone_class TEXT, PRIMARY KEY (h3, ts))
explanation(h3 BIGINT PK, model_version TEXT, factors JSONB)

-- exposure & history
vulnerability(habitation_id PK, v_demographic REAL, v_structural REAL,
              v_access REAL, v_economic REAL, v_index REAL)
disaster_event(id PK, ts DATE, hazard_type, geom, fatalities INT, injured INT,
               houses_damaged INT, source TEXT, source_ref TEXT)

-- decisions
candidate_site(id PK, geom, area_ha REAL, tenure TEXT, slope_mean REAL, mhi_max REAL,
               cc_land INT, cc_water INT, cc_school INT, cc_health INT,
               cc_final INT, binding_constraint TEXT, augmented JSONB, suitability SMALLINT)
relocation_plan(id PK, habitation_id FK, site_id FK, households INT, tier TEXT,
                priority_score REAL, rationale JSONB, status TEXT, created_at)
```

**Indexing:** GIST on every geometry · BRIN on `hazard_dynamic.ts` · monthly partitions on
`hazard_dynamic`, dropped rather than DELETEd · materialised views `mhi_res6`, `mhi_res7`
via `h3_cell_to_parent()`.

### 9.6 API surface

| Method | Path | Returns |
|---|---|---|
| `GET` | `/tiles/{layer}/{z}/{x}/{y}.mvt` | Vector tiles from PostGIS |
| `GET` | `/zones?bbox=&res=&t=` | H3 cells with MHI, zone class, dominant hazard |
| `GET` | `/zones/{h3}` | Full breakdown + SHAP explanation |
| `GET` | `/habitations?admin=&tier=&sort=` | Prioritised queue, paginated |
| `GET` | `/habitations/{id}/risk` | Risk dossier |
| `GET` | `/habitations/{id}/sites` | Ranked candidate sites with capacity |
| `POST` | `/sites/{id}/capacity` | Recompute capacity with overridden norms |
| `POST` | `/plan/allocate` | Run min-cost matching for an admin unit |
| `GET` | `/alerts/active` | Current Active Alert Zones |
| `GET` | `/alerts/forecast?horizon=` | Forecast Alert Zones, 72 h max, pilot districts, with issuing model and cycle time |
| `POST` | `/scenario` | Re-rank under adjusted weights or norms |
| `GET` | `/export/{admin}/briefing.pdf` | SDMA briefing pack |

### 9.7 Stack

| Tier | Choice | Rationale |
|---|---|---|
| Frontend | Next.js 16 App Router, TypeScript strict | Team strength |
| Map | MapLibre GL JS + deck.gl `MapboxOverlay` | GPU rendering of 1M+ hexes; Leaflet cannot |
| Basemap | Self-hosted Protomaps PMTiles / OSM style | No third-party billing at demo time |
| Tables & state | TanStack Table + TanStack Query + Zustand | — |
| API | FastAPI, Pydantic v2, SQLAlchemy + GeoAlchemy2 | Team strength |
| Database | **Neon** — PostgreSQL 16 + PostGIS 3.4 + `h3` 4.2 / `h3_postgis` | One store; Martin serves tiles from the same tables. Neon carries `h3`; Supabase does not (ADR 0001). Direct, non-pooled connection string — Martin and SQLAlchemy need prepared statements |
| Migrations | Numbered SQL in `infra/migrations/`, applied by `infra/migrate.sh` | The schema is defined once in §9.5, not evolved for years. Alembic is more machinery than that earns |
| Tiles | Martin or `pg_tileserv` | MVT straight from PostGIS |
| Pipeline | h3-py, geopandas, rasterio, pysheds, XGBoost, SHAP | — |
| Satellite access | `pystac-client` + `stackstac` / `odc-stac`, `planetary-computer` | Query STAC, pull COGs, process locally. Catalogue only — computation stays on our machines and outputs land in Postgres |
| Secrets | `python-dotenv`, env vars only | Keys never in source, manifest or snapshot |
| Scheduling | APScheduler | Celery is over-engineered for 8 days. `pg_cron` exists on Neon but fires only while compute is active, so it cannot carry FR-4.4 |
| Types | TypeScript client generated from FastAPI OpenAPI | Prevents contract drift between tracks |

### 9.8 Repository layout

```
/web          Next.js 16 App Router, TypeScript, MapLibre + deck.gl
/api          FastAPI, Pydantic v2, SQLAlchemy + GeoAlchemy2
/pipeline     Python ETL & ML, layers L0–L4 — h3, geopandas, rasterio, xgboost, shap
/core         Shared Pydantic models, hazard weights, capacity norms — imported by both
/infra        docker-compose, Dockerfile.postgres, migrations/, migrate.sh, martin.yaml
/data         raw / interim / processed     (gitignored)
/models       trained model artifacts       (gitignored)
/docs         PRD, ADRs, TEAM-GUIDE.md
```

`apps/` and `packages/` are collapsed: they cost two directory levels to hold one JS app.
`core/` replaces `packages/schemas` — the TypeScript client is generated by a script
(`pnpm generate:types`), not by a package, so what actually needs a shared home is the
constants both halves compute against (FR-3.5 weights, §6.8 norms, zone thresholds).

Two workspaces, one command each: `pnpm install` (root `pnpm-workspace.yaml` → `web`) and
`uv sync` (root `pyproject.toml` → `core`, `api`, `pipeline`). `api` and `pipeline` stay
separate packages because their dependency sets diverge sharply — the API must stay light,
the pipeline drags in GDAL, rasterio and XGBoost.

---

## 10. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | Map first paint under 2 s for a 500k-cell viewport |
| NFR-2 | API p95 under 300 ms for `/zones/{h3}` and `/habitations` |
| NFR-3 | Full pipeline rerun for one pilot district under 45 minutes |
| NFR-4 | The demo must run with **zero live external API calls** |
| NFR-5 | Page body never scrolls horizontally; wide content scrolls inside its own container |
| NFR-6 | All interactive elements have a visible keyboard focus state |
| NFR-7 | All animation respects `prefers-reduced-motion` |
| NFR-8 | Every licence requiring attribution has its string carried into the output |
| NFR-9 | Uncertainty is rendered, never hidden — low-confidence cells hatch rather than showing a false-precision colour |

---

## 11. Build plan

| Day | Python / data track | Next.js / frontend track |
|---|---|---|
| **0** | **Registrations, ordered by latency risk.** MOSDAC first (slow approval), then IMD (unknown turnaround), then the instant ones: NASA Earthdata — authorising the GESDISC application separately — plus CDSE, CWC/India-WRIS and data.gov.in. Verify the MSPC S1 RTC collection is live and its terms unchanged. **Provision the Neon project on the Launch plan with scale-to-zero disabled** and record the direct, non-pooled connection string. Populate `.env` | — |
| **1** | Verify every data source responds, including auth probes and quota-headroom checks. `docker compose up` (Postgres 16 + PostGIS 3.4 + h3 4.2) and `infra/migrate.sh` against both local and Neon. Load admin boundaries with LGD codes. Generate H3 grids for pilot districts | Next.js scaffold, MapLibre basemap with self-hosted PMTiles, three-panel shell, shared types wired to OpenAPI |
| **2** | DEM derivatives (slope, curvature, TWI, HAND), land cover, rainfall climatology → zonal stats. Dasymetric population | **One real hexagon rendering end-to-end from Postgres.** This is the milestone that de-risks the week |
| **3** | Train landslide XGBoost with spatial block CV. SAR flood-frequency from S1 RTC via STAC **over Barpeta** + HAND surface; score the water-detection rule on Sen1Floods11 chips (M-7); rerun the finished pipeline over Wayanad. Write `hazard_static` and first `MHI_static`. **Timebox the flood layer:** one orbit track, VV only, monsoon months, 20 m overview — the full-fidelity version does not fit beside the landslide model | Real choropleth, dominant-hazard symbology, legend, zone filter, cell click → dossier |
| **4** | Census district PCA, VIIRS + building + access covariates, dasymetric downscaling with district-mean constraint, SoVI weights, vulnerability index. Ingest disaster events. Aggregate cells → habitations. Priority scores and triage tiers | Prioritised habitation table, tier chips, urgency/caseload toggle, map ↔ table selection sync |
| **5** | Candidate site generation with eligibility mask. Land/water/school/health capacities, binding constraint, augmented capacity, suitability | Ranked site cards, capacity bar showing the binding constraint, site polygons on map |
| **6** | IMERG / IMD / CWC / ECMWF adapters on a schedule, ARI and I–D thresholds, `MHI_live`, Active Alert Zones and 72 h Forecast Alert Zones. OR-Tools allocation. Precompute SHAP | Alert overlay with distinct observed/forecast states, −7 d to +3 d time slider, allocation arcs, SHAP bar chart in dossier |
| **7** | `POST /scenario` re-ranking. PDF briefing pack. Record demo snapshot, wire `DEMO_MODE` | Scenario drawer, empty/error states, loading skeletons, focus states, responsive check, dark mode |
| **8** | **Freeze.** Full rehearsal against offline snapshot, README, architecture diagram, deployment | **Freeze.** Rehearse the click path twice on the machine and network you will present from |

---

## 12. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| IMD API undocumented shape, rate-limited or down | High | Adapter pattern + aggressive caching + recorded snapshot replay. UI never calls external APIs |
| Only ~5,500 open landslide labels nationally | Certain | Spatially stratified negative sampling at 1:1–1:3, spatial block CV, benchmark against published ILSM |
| No open lithology map | Certain | SoilGrids WRB proxy; declare weakest feature |
| No Himalayan landslide labels | Certain | Train Western Ghats + Sikkim, held-out inference on Uttarakhand — turn the constraint into the demonstration |
| Census 2011 fifteen years stale | Certain | Ratios only; population counts from WorldPop; within-district variation from 2023 covariates via FR-5.5; state in UI |
| **Registration approval latency** — MOSDAC days, IMD unknown | High | Day 0 task, ordered by latency. MOSDAC feeds only the storm-surge layer and is optional; IMD has a recorded-snapshot fallback |
| **Quota exhaustion mid-build** | Medium | Headroom computed before Day 1 (FR-1.8), target 5–10×. Adapters fall back and log rather than nulling (FR-1.9). Raw responses cached, so a rerun costs no quota |
| ~~MSPC RTC collection moved or terms changed~~ | **Closed** | Verified 2026-08-31 (§8.2a): collection live, CC BY 4.0, anonymous SAS, 1,697 scenes over Barpeta and 632 over Wayanad. CDSE fallback is off the critical path |
| **Empirical flood layer measures nothing in a flash-flood district** | Certain in Wayanad | Build on Barpeta (§9.4). In Wayanad, HAND-primary weighting, confidence from observation count, sparsity hatched per NFR-9. Flash flood is carried by FR-4.2 thresholds, not SAR |
| **Radar shadow or flooded paddy read as inundation** | High | FR-3.17 slope exclusion, WorldCover cropland flagging, and ML-6 quantitative scoring against Sen1Floods11 rather than visual validation |
| **INDOFLOODS licence turns out to be non-permissive** | Medium | §8.1 Rule 1 is absolute. Q-7 resolves before it enters `sources.yaml`. If it fails, I–D thresholds fall back to India Flood Inventory v3 event dates against CHIRPS v3 — fewer events, same method |
| **Keyed source becomes a hidden runtime dependency** | Medium | FR-1.3 and NFR-4 unchanged. Snapshot verified credential-free at freeze; rehearsal runs with network disabled |
| **Forecast AAZ read as disaster prediction** | Medium | FR-3.15 — forecast attributed to the met agency, our claim is only the threshold crossing. Interface strings reviewed against this before demo |
| Monsoon cloud blocks optical imagery | High | Sentinel-1 SAR for all water and flood work |
| National res-8 grid too large to process in time | High | Res-7 nationally, res-8/9 in pilots. Pipeline is AOI-parameterised from Day 1 |
| Land tenure unavailable for candidate sites | High | Ship an explicit "tenure unverified" state. An honest gap is a feature request; a wrong ownership claim is a liability |
| Data source URL rot between now and Day 1 | Medium | `verify_sources.py` smoke test; exits non-zero on any core failure |
| Frontend and backend contracts drift | Medium | Generate the TypeScript client from FastAPI's OpenAPI schema |
| **Neon storage exceeded mid-build** | Medium | `hazard_dynamic` is the table that grows — pilot-only hourly recompute lands near 2 GB, national hourly would not. National cadence stays daily (FR-4.4 applies hourly in pilots); monthly partitions are dropped, not `DELETE`d |
| **Demo depends on a reachable Neon** | High | NFR-4 already forbids live external calls, and a hosted database is one. The Day-8 rehearsal runs against the local `infra/docker-compose.yml` stack loaded from the snapshot, with the network disabled |
| **Pooled connection breaks Martin or SQLAlchemy** | Low | Both need prepared statements, which Neon's pooler drops. Use the direct connection string; `.env.example` says so |

---

## 13. Open questions

| # | Question | Owner | Needed by |
|---|---|---|---|
| ~~Q-1~~ | ~~Scrape village-level Census PCA, or fall back to district-level?~~ **Closed.** Neither — downscale district PCA dasymetrically (FR-5.5). A village PCA via data.gov.in, if reachable in a 90-minute timebox, refines the anchor but is not a dependency | Data track | Resolved |
| **Q-7** | **What licence does INDOFLOODS (Zenodo 14584655) carry?** Nothing in the download states one. §8.1 Rule 1 is absolute, so this gates FR-4.2 threshold fitting and the `disaster_event` load. Check the Zenodo record page; the derived EM-Earth precipitation columns need a separate check | Data track | **Day 1** |
| Q-5 | Does the demo lead with the observed alert overlay or the forecast one? The forecast is the stronger story and the weaker claim | Team lead | Day 7 |
| Q-6 | If IMD registration has not cleared by Day 3, do we ship IMD-shaped adapters against the recorded snapshot only, or drop the IMD branding from the demo narrative? | Team lead | Day 3 |
| Q-2 | File a formal GSI data request for the Bhukosh landslide inventory? Would not arrive in time for the build but strengthens the roadmap narrative | Team lead | Day 2 |
| Q-3 | Which state's rural housing plot norm to use as the default for `a_hh`? | Data track | Day 5 |
| Q-4 | Does the demo present the pan-India view first or a pilot district first? | Team lead | Day 7 |

---

## 14. Appendix

### 14.1 Formula reference

```
Per-hazard score     H_h(c,t) = clamp( S_h(c) · (1 + β_h · T_h(c,t)), 0, 1 )      β_h ≈ 1.0

Multi-hazard index   MHI(c,t) = 1 − Π_h ( 1 − w_h · H_h(c,t) )
                     w: landslide 1.0, flash flood 1.0, surge 0.9,
                        riverine flood 0.8, erosion 0.7

Antecedent rainfall  API_t = Σ kⁱ · P_(t−i)                    k ≈ 0.9, 15-day window
I–D threshold        I = α · D^(−β)                            fitted per zone

Carrying capacity    CC(s) = min( CC_land, CC_water, CC_school, CC_health ) × μ_livelihood

Priority score       PS_j = ( ĥ_j · f̂_j · V̂_j ) × ( 1 + γ · L̂_j )              γ ≈ 0.5
Loss history         L̂_j = Σ e^(−λ(t_now − t_i)) · severity_i    10-year half-life

Allocation           max Σ_{j,s} x_js · ( PS_j · suit_s ) − c_js · x_js
                     s.t.  Σ_s x_js ≤ demand_j ,  Σ_j x_js ≤ CC_s
```

### 14.2 Toolkit

`sih-data-toolkit.tar.gz` contains:

- `sources.yaml` — 25 datasets with licence, access method, size and caveats; 12 exclusions with reasons; 3 known gaps. **Revised:** every entry gains `tier`, `auth` (env var name, never a value), `quota` (limit, window, calls_needed) and `fallback` (id of another source)
- `verify_sources.py` — Day-1 smoke test; exits non-zero on any core failure; detects a blanket proxy block rather than reporting false failures. **Revised:** `--tier {core,A,B,C}`; an auth probe distinguishing *missing credential* from *dead endpoint*; a quota-headroom check warning under 5× and failing under 2×
- `fetch_terrain.py` — GLO-30 → slope, aspect, curvature, TWI, SPI, flow accumulation, HAND, relief
- `.env.example` — every credential variable name, no values

> Every URL in `sources.yaml` was compiled from documentation on a machine with no outbound
> network. None were fetched successfully. Run `verify_sources.py --tier core` before
> planning a day around any of them.

### 14.3 Standards and norms referenced

| Norm | Source |
|---|---|
| 55 LPCD rural / 135 LPCD urban water supply | CPHEEO Manual on Water Supply |
| 1 PHC per 30,000 (plains) / 20,000 (hilly & tribal) | Indian Public Health Standards (IPHS) |
| Seismic zonation | IS 1893 (BIS) |
| Coastal Regulation Zone I / II exclusions | CRZ Notification, MoEFCC |
| Groundwater block categorisation | Central Ground Water Board (CGWB) |
| School enrolment vs sanctioned capacity | UDISE+ |
| Administrative join key | Local Government Directory (LGD) codes |

---

*Document ends.*
