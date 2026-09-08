# Relocation & Candidate Site Pipeline — Steps 11–20

## Scope

This plan covers the relocation workflow from **Step 11 through Step 20**. It starts
where `flood_susceptibility_plan_steps_1_10.md` ends and produces ranked,
capacity-checked relocation options plus an optimal habitation-to-site assignment.

| Phase | Steps | Output |
|---|---|---|
| Flood / hazard (done) | 1–10 | `hazard_static`-ready flood layer (H3 res-8) |
| **Relocation (this doc)** | **11–20** | **`candidate_site` + `relocation_plan`-ready records** |

```text
Steps 1-10:  S1 RTC -> water masks -> frequency + HAND -> S_f -> H3 res-8
Steps 11-20: triaged habitations + H3 MHI/slope
                -> search envelope -> eligibility mask
                -> CC_land | CC_water | CC_school/health | jobs mu | transport
                -> CC_final + binding + augmented + suitability
                -> allocation -> dossier
```

The plan follows the SETU-DRR PRD. In particular:

- §6.8 Carrying capacity (FR-7.1–7.7)
- §6.9 Allocation (FR-8.1–8.3)
- §6.6–6.7 Prioritisation + triage tiers (FR-6.1–6.5)
- §6.10 Explainability + §9.5 data model (`candidate_site`, `relocation_plan`)
- §14.1 Formula reference, §14.3 norms (CPHEEO, IPHS, UDISE+)

It does **not** re-decide anything Steps 1–10 decided. `MHI_static`, slope, HAND,
and inundation frequency are **inputs** here, not recomputed.

Two corrections to the flood plan that this phase depends on:

1. Step 10.4 writes `hazard_type = "flash_flood"`. Per PRD FR-3.16 the empirical
   Sentinel-1 layer **must** be stored as `hazard_type = 'riverine_flood'`.
   Flash flood is carried by the I–D threshold path (FR-4.2), never by SAR.
2. The flood plan builds Wayanad-first. Per PRD v1.3 §9.4 the flood pipeline is
   **built on Barpeta first, then run over Wayanad** (Barpeta yields ~55
   flood-coincident acquisitions vs ~8 in Wayanad). This relocation pipeline is
   AOI-parameterised, so it runs identically on either district once Step 10 is done.

Existing code this plan wires into (do not reimplement):

- `core/src/core/domain/capacity.py` — `CapacityEngine`, `CandidateSitePolicy`,
  `evaluate_site_eligibility()`, `evaluate_site_capacity()`
- `pipeline/src/pipeline/capacity/site_generator.py` —
  `build_candidate_site_record()` (today fed by synthetic fixtures; this plan
  replaces the fixture inputs with R12–R17 outputs)
- `core/src/core/domain/allocation.py` — `MinCostFlowAllocationSolver` (exact
  OR-Tools, FR-8.2)

---

## 0. Target Outcome

For one pilot district (Barpeta first, then Wayanad), produce reproducible,
per-habitation relocation options:

```text
triaged source habitations (demand HH, PS_j, tier)
        +
H3 MHI_static, slope, land-cover, services, jobs, roads
        ↓
eligible candidate polygons (>= 2 ha, safe, buildable)
        ↓
CC_land, CC_water, CC_school, CC_health, mu_livelihood
        ↓
CC_final = min(...) x mu + binding_constraint + augmented + suitability (0-100)
        ↓
min-cost-flow assignment (habitation -> site, HH flows)
        ↓
candidate_site + relocation_plan-ready records
```

The output is a **screening-grade recommendation**, not a relocation order.
Per PRD §1.3 every output surface must carry the persistent screening-grade
label: cell scores identify where scarce survey capacity goes first; any actual
order requires ground verification, geotechnical/hydraulic study, and community
consultation.

### Key vocabulary (what each term means and why it exists)

| Term | What it is | Why it exists |
|---|---|---|
| **Source habitation** | A village/settlement that may need to move (LGD-coded, with population, households, priority score, triage tier) | Relocation starts from people at risk, not from empty land. Demand (`demand_j`) comes from here. |
| **Candidate site** | A nearby polygon that could receive relocated households | Destinations must be found before anyone can be assigned. Each gets a capacity and a suitability. |
| **Eligibility mask** | Binary go/no-go layer (safe + buildable + legally usable) | Filters out unsafe or illegal land *before* expensive capacity math. FR-7.2. |
| **Carrying capacity (CC)** | Max households a site can absorb, in HH units | Land alone is not enough — sites with land but no water/school fail within ~2 years and families return (PRD §1.1, failure #2). |
| **Binding constraint** | The single smallest of the four capacities (`argmin`) | Tells the investor exactly what to fix ("218 HH, water-limited"). FR-7.5. Capacity is a **minimum, never an average** (FR-7.4) — averaging hides the bottleneck. |
| **Augmented capacity** | Capacity after relieving the binding constraint, with named intervention | Turns a diagnosis into a budget decision ("+ borewell scheme → 340 HH"). FR-7.6. Cost is left `None` until verified — never invented. |
| **Suitability (0–100)** | How *desirable* a site is (access, services, jobs proximity) | Stored and displayed **separately** from capacity (FR-7.7). A large but remote site has high capacity and low suitability — conflating them corrupts the allocation benefit term. |
| **Livelihood multiplier μ ∈ [0.6, 1.0]** | Down-rating for poor jobs/market/cultivable-land access | A site with no commute-viable livelihood empties out. μ multiplies the min-capacity rather than adding a fifth constraint, so it can only shrink, never inflate. |
| **Allocation (`x_js`)** | Household flows from habitation j to site s | Solves "who goes where" district-wide under capacity limits. Exact min-cost flow (FR-8.2), not a greedy heuristic. |
| **Group split** | One habitation's households divided across ≥2 sites | Sometimes mathematically necessary, always socially costly. Must be surfaced explicitly for sign-off (FR-8.3). |

### Prerequisites (inputs from Steps 1–10 + parallel tracks)

| Input | Source | Used in |
|---|---|---|
| H3 res-8 `MHI_static`, `dominant_hazard` | Steps 1–10 + landslide track | R12 eligibility (`MHI_static < 0.25`) |
| H3 / raster slope, HAND, drainage | `fetch_terrain.py` / Step 8 | R12 (`slope < 15°`), R17 access cut-off |
| Habitation list with LGD code, population, households, geom | L3 exposure track (PRD §9.2) | R11 demand |
| Priority score `PS_j`, triage tier | FR-6.1–6.5, §6.7 | R11 demand, R19 benefit term |
| Land cover, forest, protected areas, CRZ, water bodies | ESA WorldCover, OSM, JRC GSW, MoEFCC | R12 exclusions |
| Buildings, roads, schools, health facilities | Open Buildings, OSM Geofabrik, UDISE+, IPHS | R13–R17 |
| Groundwater yield / CGWB block category | CGWB, PHED | R14 |
| Nightlights, cropland, markets | VIIRS, WorldCover, OSM | R16–R17 |
| Tenure (government / private / unverified) | Revenue records | R12 (FR-7.3 — never guessed) |

---

# Step 11 — Define Demand + Search Envelope

## Objective

Decide **who needs to move** and **how far we look** for each of them.

Relocation is demand-driven: without a ranked, tiered demand list, site
generation optimises land nobody needs.

### Inputs

- Habitation table: `habitation_id, LGD code, name, households, population, geom`
- Priority score `PS_j = (ĥ·f̂·V̂) × (1 + 0.5·L̂)` (FR-6.1) + urgency/caseload toggle (FR-6.3)
- Triage tier per §6.7 rule (Immediate / Short-term / Medium-term / Mitigate in situ)
- Config: `search_radius_km` (default **15 km**, FR-7.1)

### Tasks

1. Filter to habitations in a relocation tier (Immediate first; Short-term next).
   `Mitigate in situ` habitations are explicitly **excluded** from demand — the
   tool must be able to recommend *against* relocation (FR-6.5).
2. Set `demand_j = households` requiring relocation (full or partial per tier note).
3. Buffer each source geometry by `search_radius_km` → `search_polygon`.
4. Clip all downstream work (R12–R17) to the union of search polygons for the
   batch being planned (one village, or one district allocation run).

### How it works

A fixed-radius buffer is a deliberate simplification: it bounds computation,
matches the `POST /scenario` radius slider, and feeds the allocation solver's
`max_search_radius_km` edge filter (`allocation.py`). Distance beyond the radius
is not "expensive" — it is **ineligible** (no edge created).

### Why this way

- Radius-bounded search keeps the Day-5/6 compute tractable (NFR-3: full district
  rerun < 45 min) and matches how DMs actually think ("nearby places").
- Tier-first ordering ensures Immediate (0–6 mo) habitations consume the best
  nearby capacity before Medium-term ones do — allocation is run per admin unit.

### Validation

- Plot search polygons over habitations + MHI_static; confirm 15 km covers
  plausible destinations without crossing into a different hazard regime.
- Confirm `Σ demand_j` for the batch vs district totals (sanity: no double counting).

### Output

```text
data/interim/relocation/<district>/demand.parquet
  habitation_id, name, demand_households, priority_score, tier, search_polygon
```

---

# Step 12 — Habitable-Land Eligibility Mask

## Objective

Throw away land that is **unsafe, unbuildable, or legally excluded** before any
capacity math. What survives is "habitable land available" in the PRD sense.

### Inputs

- `MHI_static` per H3 cell (Steps 1–10 + landslide MHI via probabilistic union FR-3.4)
- Slope raster (Copernicus GLO-30 derivatives)
- ESA WorldCover v200 (forest, cropland, built-up, water), JRC GSW permanent water
- Protected-area polygons, CRZ-I/II, OSM water bodies
- Tenure attribute per parcel (government/revenue, private, **tenure unverified**)

### Tasks

1. Build a binary raster/vector mask. A cell/parcel is eligible **only if all hold**
   (FR-7.2):
   ```text
   MHI_static < 0.25
   AND slope < 15°
   AND NOT (forest OR protected OR CRZ-I/II OR water body)
   ```
2. Polygonize surviving areas; drop fragments with contiguous area **< 2 ha**.
3. Tag each polygon with tenure. `tenure_unverified` is **kept but flagged** —
   per FR-7.3 tenure is reported, never guessed. An honest gap is a feature
   request; a wrong ownership claim is a liability (PRD §12 risks).
4. Record per-polygon `mhi_max`, `slope_mean`, `area_ha`, exclusion reasons for
   rejected candidates.

### How it works

Implemented as `CapacityEngine.evaluate_site_eligibility()` in
`core/src/core/domain/capacity.py:306` with `CandidateSitePolicy`
(`capacity.py:70`). The function is strict about missing data: **missing MHI,
slope, area, or tenure → reject with a named reason**, never assume safe. This
is the "missing data ≠ safe" invariant the backend audit enforces.

### Why this way

- Hazard-first (`MHI < 0.25` is far stricter than the PRZ cutoff 0.75) guarantees
  destinations are not tomorrow's sources — the failure mode the whole platform
  exists to prevent.
- Slope + contiguous-area gates enforce *buildability*: a safe but 30° or
  fragmented parcel cannot take a layout + roads + drainage.
- Legal exclusions (forest/CRZ/protected) prevent recommending land the state
  cannot lawfully allot, which would kill a relocation order on challenge.

### Validation

- Overlay mask on MHI_static + slope + WorldCover; spot-check 3 known-good and
  3 known-bad locations (e.g. steep ridge, reservoir edge, forest block).
- Confirm no surviving polygon overlaps JRC permanent water.
- Count surviving polygons + total ha per search envelope (expect single digits
  per village in hill districts, more in plains).

### Output

```text
data/interim/relocation/<district>/eligible_polygons.gpkg
  polygon_id, area_ha, slope_mean, mhi_max, tenure, source_habitation_id
```

---

# Step 13 — Land Capacity (CC_land)

## Objective

Convert each eligible polygon's area into **households it can physically house**.

### Formula (PRD §6.8 norms table)

```text
CC_land = floor(A_developable_m2 / 126)
126 = ~90 m² plot + 40% infrastructure overhead (roads, drains, open space)
```

(Q-3 in PRD §13 may refine the state-specific plot norm; until then 90 m² holds.)

### How it works

`CapacityEngine.calculate_land_capacity()` (`capacity.py:136`):
`floor(area / (plot_area × (1 + overhead)))`. Pure geometry — no survey needed,
so it is always computable and forms the capacity ceiling nothing else can exceed
unless augmented (land consolidation is itself an intervention, R18).

### Why this way

- Floor (not round) because half a plot houses nobody.
- Overhead is structural, not padding: layouts without roads/drains fail
 PWD approval and flood in the first monsoon.
- Land is evaluated first because it is the cheapest input and the hardest
  constraint to relieve (acquiring adjacent land >> drilling a borewell).

### Validation

- Hand-check: 2 ha (20,000 m²) → `floor(20000/126)` = **158 HH**.
- Confirm `A_developable` excludes internal water/steep pockets, not just the
  bounding box.

### Output

Per-polygon `cc_land` (integer HH). Feeds R18.

---

# Step 14 — Water Capacity (CC_water, resources)

## Objective

Cap each site by **sustainable potable water** — the most common binding
constraint in practice.

### Formula (CPHEEO norm, PRD §6.8)

```text
CC_water = floor(Y_sustainable_LPD / (LPCD × HH_size))
LPCD = 55 rural, 135 urban-with-sewerage; HH_size ≈ 4.5
```

### Inputs

- `Y_sustainable`: CGWB block safe yield apportioned to site + PHED scheme
  spare + perennial source distance check. If only a categorical CGWB status
  (safe/semi-critical) exists, map it to a conservative yield with the mapping
  recorded in config — never silently treat "no data" as infinite water.

### How it works

`calculate_water_capacity()` (`capacity.py:155`). If `Y` is unknown,
`cc_water = None` → excluded from the `min()` and recorded in `data_gaps`
(`evaluate_site_capacity():408`). The site gets `data_quality = partial`, not a
false zero.

### Why this way

- Water is flow-limited (L/day), not stock-limited: a site with 500 plots and a
  20,000 LPD source houses `floor(20000/247.5)` ≈ **80 HH** — the other 420 plots
  are uninhabitable until supply is augmented. Averaging would hide this; the
  `min()` exposes it as the binding constraint (FR-7.4).
- Rural 55 LPCD is the CPHEEO design norm DMs defend in sanctions; using it
  keeps the dossier legally coherent.

### Validation

- For each site, list source → yield → `cc_water`; flag any site where
  `cc_water < 0.5 × cc_land` (water-limited — expect many).
- Cross-check against nearest habitation's current supply complaints if available.

### Output

Per-polygon `cc_water` (integer HH or `None` + gap note). Feeds R18.

---

# Step 15 — School + Health Capacity (infra)

## Objective

Cap each site by **absorptive social infrastructure within access distance** —
the constraint that causes resettlement failure in year 2 (children drop out,
families return).

### Formulas (UDISE+ / IPHS norms, PRD §6.8)

```text
CC_school = floor(spare_seats_within_1km / 1.2 children_per_HH)
CC_health = floor(max(0, PHC_norm - catchment_pop) / 4.5)
PHC_norm  = 20,000 hilly/tribal (Wayanad, Barpeta-adjacent hill tracts)
            30,000 plains (Barpeta floodplain)
```

### Inputs

- Schools: OSM points + UDISE+ enrolment vs sanctioned capacity within 1 km of
  site centroid. `spare_seats = Σ (sanctioned − enrolled)` floored at 0.
- Health: nearest PHC + current catchment population (census + WorldPop
  dasymetric). Spare = norm − catchment.

### How it works

`calculate_school_capacity()` (`capacity.py:177`),
`calculate_health_capacity()` (`capacity.py:193`). Same `None`-if-unknown
convention as water. Power supply and all-weather road *access* are recorded
here as suitability modifiers (R17), not capacity caps — the PRD caps capacity
on exactly these four constraints.

### Why this way

- 1 km is the walking-access norm for primary schooling; capacity 10 km away is
  not capacity for a relocated child.
- IPHS norms are the sanctioning authority's own yardstick — quoting them makes
  the "health-limited" verdict defensible in a funding proposal (G-1, G-4).
- Capping (not scoring) forces honesty: a site 500 m from a full school gets
  `cc_school = 0`, which is correct until classrooms are sanctioned (R18
  augmentation: "additional classroom + teacher intake").

### Validation

- Map each site → serving school/PHC with distances; confirm catchments do not
  double-count the same spare seats across two sites in one allocation run
  (allocation enforces `Σ x ≤ CC_s`, but shared catchments need a pre-split).
- Flag `cc_school = 0` or `cc_health = 0` sites for R18 review.

### Output

Per-polygon `cc_school`, `cc_health` (integers or `None` + gap notes). Feeds R18.

---

# Step 16 — Livelihood Multiplier μ (job availability)

## Objective

Down-rate sites where relocated households **cannot earn a living within
commute distance** — the constraint that causes silent abandonment (houses
occupied on paper, empty in practice).

### Formula (PRD §14.1)

```text
CC(s) = min(CC_land, CC_water, CC_school, CC_health) × μ,  μ ∈ [0.6, 1.0]
```

### Inputs (proxies already in the Tier-A stack — no new procurement)

- Cultivable land share within commute (ESA WorldCover cropland, ~5 km hill / 10 km plains)
- Market/mandi + town distance (OSM places, roads)
- Nightlight intensity (VIIRS annual — economic activity proxy)
- Current occupation profile of source habitation (Census ratios: cultivator /
  agri-labour / non-farm) to weight farm vs non-farm access

### How it works

Rule-based starter (recorded in config, refined after first district run):

```text
μ = 1.0  if market < 5 km AND cultivable share > 30% (farm HH) or town < 10 km (non-farm HH)
μ → 0.6  as distances double / shares halve (linear decay, clamped)
```

Applied in `calculate_final_capacity()` (`capacity.py:244`), clamped to
`[0.6, 1.0]`. It **multiplies the minimum** — it can only shrink capacity,
never rescue a water-limited site.

### Why this way

- A multiplier (not a fifth `min()` term) reflects reality: poor livelihood
  does not cap plots, it causes attrition. 0.6 floor bounds the judgement so a
  remote-but-serviced site is not scored as worthless.
- Using 2023 observables (nightlights, buildings, roads) instead of 2011 Census
  levels follows the same logic as FR-5.5 downscaling: recent proxies beat stale
  enumeration for within-district variation.

### Validation

- For each site, publish the μ worksheet (distances, shares, source occupation
  mix → μ). A DM must be able to argue with it — that is the point (G-4).
- Sensitivity: re-run R18 with μ ∈ {0.6, 0.8, 1.0}; flag sites whose rank flips.

### Output

Per-polygon `livelihood_multiplier μ`. Feeds R18.

---

# Step 17 — Transport + Suitability Score (0–100)

## Objective

Score **how desirable and connected** each site is, separately from how many
households it can take (FR-7.7). Transport answers "can people live their lives
from here?" — school bus, PHC referral, market trip, evacuation route.

### Inputs

- OSM roads (Geofabrik `india-latest.osm.pbf`): all-weather road distance,
  footpath-only flag
- Distance to source habitation (social continuity + move cost)
- HAND/slope of the **access route** (a safe site behind a flood-cut road is
  seasonally stranded)
- Service density: schools/health/markets within 1–3 km; bus stop if mapped
- Site-internal slope dispersion (flat-but-accessible beats flat-but-perched)

### How it works

Weighted 0–100 composite (weights in config, exposed to `POST /scenario`):

```text
suitability = w_road·f(road_dist) + w_access·f(route_HAND/slope)
            + w_services·f(1-3km density) + w_proximity·f(source_dist)
```

Feeds two places in `allocation.py`:

- Benefit: `b_js = PS_j × (suit/100) × scale` (`compute_assignment_benefit():106`).
  `suitability = None` (unverified) → **zero bonus**, never a penalty or a guess.
- Cost: `c_js = dist × penalty` (`compute_relocation_cost():93`); net edge cost
  `c_js − b_js` (`compute_assignment_cost():123`).

### Why this way

- Separation of capacity vs suitability is load-bearing: the allocation
  objective `Σ x·(PS·suit) − c·x` needs both independently. Merging them into one
  "goodness" number would let a close-but-tiny site outrank a farther site that
  actually fits the village.
- Transport enters **twice** (suitability bonus + distance cost) deliberately:
  proximity is both a preference and a budget line (shifting cost, bus service).

### Validation

- Rank sites by suitability alone; confirm the top site is also the one a field
  officer would pick on a map (road-adjacent, near services, near source).
- Confirm `suitability=None` sites get no benefit bonus in a dry-run allocation.

### Output

Per-polygon `suitability` (0–100 int or `None`), `distance_km` to each source
habitation in range. Feeds R19.

---

# Step 18 — Final Capacity + Binding + Augmented

## Objective

Collapse R13–R17 into the **one number + one reason + one fix** the dossier shows.

### Formulas (PRD §14.1, FR-7.4–7.6)

```text
CC_final = min(CC_land, CC_water, CC_school, CC_health) × μ   (floor; never averaged)
binding  = argmin(...)   (tie-break LAND > WATER > SCHOOL > HEALTH)
augmented = recompute with binding relieved → new CC_final + next binding
            + named intervention (cost left None until verified)
```

### How it works

`calculate_final_capacity()` (`capacity.py:244`) →
`calculate_augmented_capacity()` (`capacity.py:265`) →
`evaluate_site_capacity()` (`capacity.py:408`) bundles everything into
`CapacityEvaluationResult` with `data_quality` (`complete/partial/unavailable`)
and `data_gaps`. `build_candidate_site_record()` (`site_generator.py:54`)
serialises to the `candidate_site` row shape:

```text
area_ha, tenure, slope_mean, mhi_max,
cc_land, cc_water, cc_school, cc_health, cc_final,
binding_constraint, augmented JSONB, suitability, metadata JSONB
```

Intervention strings are canned per constraint (e.g. WATER → "piped water supply
scheme / deep borewell with storage"; SCHOOL → "additional classroom + teacher
intake"; HEALTH → "PHC sub-centre upgrade"; LAND → "boundary consolidation +
slope stabilisation").

### Why this way

- `min()` is the honesty mechanism: the site is only as big as its tightest
  lifeline. Tie-break order is deterministic so re-runs are reproducible.
- Augmented capacity converts a veto into a shopping list — the SDMA planning
  officer's actual job (persona §3: "prepares annual relocation proposals
  against a fixed budget").
- `indicative_cost_inr_lakhs = None` is intentional: the engine **refuses to
  invent financial figures**. Costs enter only from verified estimates.

### Validation

- For every site, print the four-way bar (`land | water | school | health → min × μ`).
  The shortest bar must equal `binding_constraint`.
- Confirm `augmented.augmented_capacity ≥ cc_final` and `next_binding ≠ binding`
  (unless all tied).
- Confirm `data_quality`/`data_gaps` round-trip into the dossier UI's
  "tenure unverified / yield unverified" badges.

### Output

```text
data/processed/relocation/<district>/candidate_sites.parquet
  + rows staged for candidate_site table
```

Dossier string per site: `"<CC_final> HH, <binding>-limited"` (e.g. "218 HH,
water-limited").

---

# Step 19 — Allocation (habitation → site assignment)

## Objective

Assign **which households go where** district-wide without exceeding any site's
`CC_final` or any habitation's demand.

### Formula (PRD §14.1, FR-8.1)

```text
max Σ_{j,s} x_js · (PS_j · suit_s) − c_js · x_js
s.t. Σ_s x_js ≤ demand_j ,  Σ_j x_js ≤ CC_s
```

Solved **exactly** with OR-Tools (FR-8.2 — the problem is small per district;
no heuristic).

### How it works

`MinCostFlowAllocationSolver.solve()` (`allocation.py:220`):

1. Nodes: source → habitations (`demand_j`) → sites (`CC_s`) → sink, plus a
   source→sink slack arc (unmet demand at high penalty so the solver prefers
   real assignment but stays feasible when capacity is short).
2. Edges habitation→site exist **only within** `max_search_radius_km`
   (default 15 km) with integer cost `round((c_js − b_js)·100) + offset`.
3. Extract flows `x_js`; any habitation touching ≥2 sites gets
   `has_group_split = True` + warning string requiring social sign-off (FR-8.3).
4. `validate_allocation_invariants()` re-checks both constraint families.
5. `allow_group_splits=False` switches to the CP-SAT whole-village path
   (`_solve_no_splits_cp_sat`) when the DM requires no splits.

### Why this way

- Min-cost flow is the right tool because both the objective (priority ×
  suitability minus move cost) and the constraints (demand, capacity) are linear
  and the graph is bipartite — exact optimum in milliseconds, explainable edge
  by edge.
- The slack arc guarantees an answer even when capacity is insufficient
  ("relocate 60%, unmet 40%") instead of solver failure — the honest output for
  an under-resourced district.
- Splits surfaced (not hidden) because splitting a village across sites is a
  social decision above the model's pay grade.

### Validation

- Invariants: no site over `CC_s`, no habitation over `demand_j`, all flows ≥ 0.
- Unmet-demand review: if `unmet > 0`, the dossier must say which tier went
  unserved and which binding constraints caused it (feeds next year's budget).
- Re-run with varied `distance_penalty_weight` / radius to confirm stability of
  top assignments.

### Output

```text
data/processed/relocation/<district>/allocation.parquet
  habitation_id, site_id, households, distance_km, has_group_split
  + rows staged for relocation_plan table (tier, priority_score, rationale JSONB)
```

---

# Step 20 — Dossier, Export + Ground-Verification Gate

## Objective

Turn model outputs into a **defensible DM briefing** that cannot be mistaken
for a final order.

### Tasks

1. Per source habitation, render (API `GET /habitations/{id}/sites` +
   right-panel dossier per FR-10.4):
   - why it ranks here (MHI breakdown, SHAP top-5, loss timeline, vulnerability)
   - ranked candidate sites: `CC_final`, binding bar, augmented card, suitability,
     distance, tenure badge
   - allocation result + split warnings
2. District pack: `POST /plan/allocate` result + `GET /export/{admin}/briefing.pdf`.
3. **Gate**: every surface carries the screening-grade label + the three
   pre-order requirements (ground verification, detailed slope-stability /
   hydraulic study, community consultation). No export path bypasses the label.

### How it works

Read path only: API serves Postgres (`candidate_site`, `relocation_plan`,
`explanation` JSONB) + MVT tiles. Scenario re-ranks via `POST /scenario`
(weight/radius/norm overrides) without touching stored capacities.

### Why this way

Personas (§3): the DM signs orders and is personally accountable; the SDMA
officer defends a ranked list against a fixed budget; NDRF needs tonight-vs-
months separation. The dossier serves all three only if every number is
inspectable (G-4) and permanent relocation is never confused with evacuation
(FR-3.11/3.14 — alert zones never influence tiers).

### Validation

- Click-path rehearsal: district view → top habitation → dossier → site cards →
  augmented → allocate → PDF, on the offline snapshot (NFR-4, PRD §11 Day 8).
- Interface-string review vs FR-3.15 (forecast claims) and §1.3 (screening label).

### Output

Staged `relocation_plan` rows + briefing PDF. Demo reads from the recorded
snapshot with `DEMO_MODE`; zero live external calls.

---

# End-to-End Deliverables

At the end of Step 20:

```text
              triaged habitations (demand, PS, tier)
                            │
                            ↓
                 15 km search envelopes (R11)
                            │
                            ↓
              eligibility mask -> polygons ≥2 ha (R12)
                 habitable land + tenure tag
                            │
              ┌─────────┬───┴───┬─────────┐
              ↓         ↓       ↓         ↓
          CC_land  CC_water CC_sch/hlth  μ / suit
           (R13)    (R14)    (R15)     (R16/R17)
              └─────────┴───┬───┴─────────┘
                            ↓
              CC_final + binding + augmented (R18)
                            │
                            ↓
              min-cost-flow allocation (R19)
                            │
                            ↓
              dossier + briefing + gate (R20)
                            │
                            ↓
              candidate_site + relocation_plan-ready
```

```text
data/
├── interim/relocation/<district>/
│   ├── demand.parquet
│   ├── eligible_polygons.gpkg
│   └── distances.parquet
└── processed/relocation/<district>/
    ├── candidate_sites.parquet
    ├── allocation.parquet
    └── metadata.yaml
```

## Recommended implementation order

Do **not** implement everything at once.

### Milestone F — Three hand-worked sites

Push 3 synthetic specs (one water-limited, one school-limited, one land-limited)
through `CapacityEngine.evaluate_site_capacity()` + `build_candidate_site_record()`.
Validates R13–R18 math and the `candidate_site` row shape. (Partially exists as
fixtures — replace with one real polygon each.)

### Milestone G — One village, real polygons

R11 envelope + R12 mask for a single Immediate-tier habitation → 5–10 real
eligible polygons with `area_ha/slope_mean/mhi_max/tenure`. Validates the GIS
chain (mask → polygonize → zonal stats) before any capacity data is chased.

### Milestone H — One village, end to end

R13–R19 for that village: four capacities + μ + suitability → binding/augmented
→ 1–2 assignments. Review the dossier strings with a domain reader before
scaling to the district allocation run.

Only after H works should you run the full district and then the second pilot.

---

# Decisions That Must Be Documented (config, not code)

Before calling this production-ready, record in `metadata.yaml` + `core/constants.py`:

1. `search_radius_km` (default 15) + scenario overrides
2. Eligibility thresholds: `MHI_static < 0.25`, `slope < 15°`, `area ≥ 2 ha`,
   exclusion layers + versions
3. `a_hh` plot norm (default 90 m² + 40% overhead = 126) + state norm if Q-3 resolves
4. Water: LPCD used, HH_size, yield sources + yield mapping for categorical CGWB
5. School: search distance (1 km), `children_per_HH` (1.2), UDISE+ snapshot date
6. Health: PHC norm applied (20k/30k), catchment sources + date
7. Livelihood μ rule: commute distances, cropland/nightlight weights, occupation mix
8. Suitability weights + transport inputs (road vintage, access-route check)
9. Allocation: `distance_penalty_weight`, `benefit_scale_factor`,
   `allow_group_splits`, cost strategy version
10. Tenure sources + unverified-handling policy
11. Snapshot dates, dataset versions, licences + attribution strings (NFR-8)
12. Model/policy versions (`capacity-norms-vX`, `site-eligibility-vX`, `allocation-vX`)

---

# Success Criterion for This Phase

The phase is complete when, for a fresh pilot district, you can run:

```text
demand + envelopes -> mask -> CC x4 + μ + suitability
  -> binding/augmented -> allocation -> dossier
```

and obtain, per source habitation, ranked nearby sites each stating **how many
households, limited by what, fixable how, how suitable, how far, and by what
transport** — with every number traceable to a source, a norm, and a version,
and every surface carrying the screening-grade label.
