# Relocation & Candidate Site Pipeline — Steps 11–20 (v2, consolidated)

**Supersedes:** `docs/relocation_plan_steps_11_20.md` (v1).
**Status:** Review + revised build plan. Self-contained — v1 is retained for history only.
**Date:** 2026-09-06
**Reviewed against:** `docs/PRD1.md` v1.3 and the actual repository state.

v1's formulas, norms and rationale were sound and are carried forward here **unchanged**. What
changes is **scoping, sequencing, and four correctness gaps** found by checking the plan against
the code and data that actually exist. Every change is tagged inline:

- **[NEW]** — not in v1; a prerequisite or missing module v1 assumed away
- **[REVISED]** — v1's substance kept, corrected
- **[CUT]** — removed from prototype scope, with the reason
- **[KEEP]** — v1 text carried forward verbatim in substance; do not re-litigate

---

# PART I — REVIEW FINDINGS

## 1. Verdict

v1's *reasoning* is sound — formulas, norms, `min()`-not-average honesty, screening-grade framing,
and the config registry are all correct and PRD-faithful. The problem is **scoping inversion**: v1
treats the parts already built and tested as the body of work, and describes the parts that do not
exist in one line each.

| Step | v1 describes it as | Verified repo state |
|---|---|---|
| R13, R18 — capacity, binding, augmented | "wire into `capacity.py`" | **Built + tested** — `core/src/core/domain/capacity.py`, `tests/unit/test_domain_capacity*.py`, `test_h7_candidate_site_eligibility.py` |
| R19 — allocation | "wire into `allocation.py`" | **Built + tested** — `core/src/core/domain/allocation.py` incl. `_solve_no_splits_cp_sat`, `tests/unit/test_allocation_ortools.py` |
| R17 — suitability 0–100 | "weighted composite, feeds allocation" | **Does not exist.** `suitability` is a stored column only; no `compute_suitability` anywhere |
| R12 — eligibility mask | "polygonize, zonal stats" | **Does not exist.** No vector GIS / polygonize code in `pipeline/` |
| R14 / R15 — water, school, health | "CGWB, PHED, UDISE+, IPHS" | **No ingestion for any of them.** No code hits for `CGWB`, `UDISE`, `IPHS` |
| R11 — demand | "triaged habitations" | **No habitation ingestion pipeline.** `habitation` rows are hardcoded fixtures in `pipeline/src/pipeline/jobs/seed_pilot_data.py` |

Roughly 55% of v1 is unbuilt, and it is exactly the 55% v1 compresses into single lines.

**It is feasible** — nothing is technically out of reach — but as written it is a 10–12 day effort
with several data-acquisition gambles, not a prototype plan. Part III below is the ~3–4 day version.

## 2. Verified repo state

### Exists and works
- `core/src/core/domain/capacity.py` (583 LOC) — `CapacityEngine`, `CandidateSitePolicy`,
  `CapacityNormsConfig`, `evaluate_site_eligibility()`, `evaluate_site_capacity()`,
  `calculate_augmented_capacity()`. The `None`-if-unknown convention and `data_gaps` are
  implemented exactly as v1 describes.
- `core/src/core/domain/allocation.py` (605 LOC) — `MinCostFlowAllocationSolver` (OR-Tools
  `SimpleMinCostFlow`), CP-SAT no-split path, slack arc for unmet demand,
  `validate_allocation_invariants()`, group-split warnings.
- `core/src/core/constants.py` — every threshold v1's config registry asks for already exists:
  `SITE_SEARCH_RADIUS_KM=15.0`, `SITE_MAX_MHI_STATIC=0.25`, `SITE_MAX_SLOPE_DEG=15.0`,
  `SITE_MIN_AREA_HA=2.0`, `AREA_PER_HOUSEHOLD_M2=126.0`, `LPCD_RURAL=55`, `PHC_POP_*`.
- `pipeline/src/pipeline/capacity/site_generator.py` — `build_candidate_site_record()`, currently
  fed by synthetic fixtures.
- `infra/migrations/002_core_schema.sql` + `005_candidate_site_metadata.sql` — `candidate_site`
  and `relocation_plan` tables with indexes.
- API surface: `routes/sites.py`, `routes/plan.py`, `routes/habitations.py`, `routes/scenario.py`
  with matching repos and services.
- **Barpeta flood layer (Steps 1–10) is real and complete:**
  `data/processed/flood/barpeta/flood_susceptibility_h3_res8.parquet` — 7,497 res-8 cells,
  `hazard_type: riverine_flood`, `model_version: flood-susceptibility-v0.1`.
  `metadata.yaml`: `mean_susceptibility 0.446`, `mean_confidence 0.147`,
  `mean_cropland_fraction 0.489`, `mean_hand_m 1.83`.
  Rasters present: HAND, slope, DEM, inundation frequency, valid-observation count, confidence,
  cropland fraction, JRC permanent water, WorldPop.

### Does not exist
- Any habitation ingestion (LGD codes, geometry, population join).
- Any Barpeta habitation records — `seed_pilot_data.py` seeds **Wayanad (LGD 555) and Kodagu
  (LGD 540) only**.
- Any vector/polygonize step; any tenure source; any OSM, CGWB, UDISE+, IPHS or VIIRS ingestion.
- Any suitability scorer.
- Any trained landslide model — `models/` contains only `.gitkeep`, so `MHI_static` outside the
  Barpeta flood layer is currently synthetic fixture data.

## 3. The four blockers

### B1 — The pilot district has hazard data but no people; the other has people but no hazard
The largest practical gap. v1 says "run on Barpeta first" and assumes a triaged demand list exists
at R11. It does not: Barpeta has 7,497 scored cells and **zero habitations**, while Wayanad/Kodagu
have habitation fixtures and no real hazard layer. Nothing downstream of R11 can start.
→ **Fix: Step 10.5 [NEW]**, specified in Part II.

### B2 — v1 contradicts the code on tenure, and as coded it returns zero sites
v1 §Step 12 task 3: *"`tenure_unverified` is kept but flagged."*
Code, `evaluate_site_eligibility()`: `tenure is None` → reject; `TENURE_UNVERIFIED` → reject.
That hard rejection was a deliberate P0 audit fix (H7, per
`docs/SETU-DRR_REMAINING_PROBLEM_ANALYSIS_HANDOFF.md`). With **no tenure source in the repo**,
R12 as coded yields **zero eligible polygons for every habitation**.
→ **Fix: `allow_unverified_tenure` policy flag**, specified in Step 12 below. Do not flip the
default silently — bump the policy version.

### B3 — The exclusion list has two holes that matter specifically in Barpeta
v1's rule omits **built-up** and **cropland**. In the Brahmaputra floodplain — flat, and
`mean_cropland_fraction 0.489` per your own metadata — surviving polygons will be dominated by
(a) existing settlements surfaced as empty relocation land, and (b) prime paddy whose acquisition
is a political and legal non-starter.
→ **Fix: built-up = hard exclusion, cropland = flagged penalty into μ**, specified in Step 12.

### B4 — CC_water is the headline number and is currently a config constant
The dossier's marquee string is *"218 HH, water-limited"*, and water is the constraint most likely
to bind. But v1 derives `Y_sustainable` by apportioning a **CGWB block-level** category down to a
2-ha polygon — a lookup table, not a measurement. v1 concedes this itself.
→ **Fix: versioned category→yield table printed in the dossier, labelled `norm-derived, not
observed`; `None` where absent**, specified in Step 14.

## 4. Code defects found during review

D1–D3 are in `core/src/core/domain/capacity.py :: evaluate_site_capacity()`;
D4 is in `pipeline/src/pipeline/capacity/site_generator.py`.

**D1 — `is_urban` is dead on the water path.**
```python
cc_water = self.calculate_water_capacity(
    water_yield_liters_per_day,
    active_norms.lpcd_rural,   # positional → binds to `lpcd`
    active_norms.hh_size,
    is_urban,                  # ignored: explicit lpcd already won
)
```
`calculate_water_capacity` consults `is_urban` only when `lpcd is None`. Urban sites silently get
55 LPCD instead of 135. Fix: pass `lpcd=None` and let `is_urban` select, or resolve LPCD before
the call.

**D2 — `phc_norm_pop` parameter name lies about its contract.**
```python
cc_health = self.calculate_health_capacity(
    catchment_pop=0,
    phc_norm_pop=spare_health_capacity_pop,   # caller must pre-subtract catchment
    is_hilly_or_tribal=is_hilly_or_tribal,    # dead: only consulted when phc_norm_pop is None
)
```
The caller must pass **spare** population while the parameter is named **norm**, and
`is_hilly_or_tribal` has no effect. Works today only because `site_generator.py` happens to pass
spare. A live footgun for R15.

**D3 — augmented capacity for LAND-binding sites is fabricated.**
`calculate_augmented_capacity()` falls back to `surrogate_high = max(known + [1000]) * 2`, which is
correct for water/school/health (the result is just the second-smallest constraint). For
`binding == LAND` it implies land can be doubled by "boundary consolidation", which is not an
intervention with a budget line. Report `augmented = None` with *"land-limited — no augmentation
without acquisition"* instead.

**D4 — `site_generator.py` hardcodes the wrong physiographic norm for Barpeta.**
`build_candidate_site_record()` (`pipeline/src/pipeline/capacity/site_generator.py:68-69`) passes
`is_urban=False, is_hilly_or_tribal=True` for every site. Barpeta is **plains** — IPHS norm 30,000,
not the 20,000 hilly/tribal figure. The flag is inert today only because D2 makes it dead on that
path, so it is masked now and becomes a **live wrong-norm bug the moment D2 is fixed**. Both flags
belong on `RawCandidateSiteSpec` or the district config, not hardcoded in the builder.

---

# PART II — THE CONSOLIDATED PLAN (Steps 10.5–20)

## Scope

Starts where `docs/flood_susceptibility_plan_steps_1_10.md` ends and produces ranked,
capacity-checked relocation options plus an optimal habitation-to-site assignment.

| Phase | Steps | Output |
|---|---|---|
| Flood / hazard (done) | 1–10 | `hazard_static`-ready flood layer (H3 res-8) — **verified present for Barpeta** |
| **Relocation (this doc)** | **10.5–20** | **`candidate_site` + `relocation_plan`-ready records** |

```text
Steps 1-10:   S1 RTC -> water masks -> frequency + HAND -> S_f -> H3 res-8
Step  10.5:   habitations (OSM places + WorldPop + LGD)          [NEW]
Steps 11-20:  triaged habitations + H3 MHI/slope
                 -> search envelope -> eligibility mask
                 -> CC_land | CC_water | CC_school/health | jobs mu | transport
                 -> CC_final + binding + augmented + suitability
                 -> allocation -> dossier
```

PRD sections this implements: §6.8 carrying capacity (FR-7.1–7.7), §6.9 allocation (FR-8.1–8.3),
§6.6–6.7 prioritisation and triage (FR-6.1–6.5), §6.10 explainability, §9.5 data model
(`candidate_site`, `relocation_plan`), §14.1 formulas, §14.3 norms (CPHEEO, IPHS, UDISE+).

It does **not** re-decide anything Steps 1–10 decided. `MHI_static`, slope, HAND and inundation
frequency are **inputs** here, never recomputed.

### v1's two "corrections to the flood plan" — both now CLOSED [REVISED]
v1 listed these as pending. Both are already honoured in the shipped artefacts:
1. `hazard_type = 'riverine_flood'` (FR-3.16) — ✅ confirmed in
   `data/processed/flood/barpeta/metadata.yaml`.
2. Barpeta-first build order (PRD §9.4) — ✅ the shipped layer is Barpeta.

Do not re-open either.

## 0. Target outcome [KEEP]

For one pilot district (Barpeta), produce reproducible, per-habitation relocation options:

```text
triaged source habitations (demand HH, PS_j, tier)
        +
H3 MHI_static, slope, land-cover, services, jobs, roads
        ↓
eligible candidate polygons (>= 2 ha, safe, buildable, NOT built-up)
        ↓
CC_land, CC_water, CC_school, CC_health, mu_livelihood
        ↓
CC_final = min(...) x mu + binding_constraint + augmented + suitability (0-100)
        ↓
min-cost-flow assignment (habitation -> site, HH flows)
        ↓
candidate_site + relocation_plan-ready records
```

The output is a **screening-grade recommendation, not a relocation order**. Per PRD §1.3 every
output surface carries the persistent screening-grade label: cell scores identify where scarce
survey capacity goes first; any actual order requires ground verification, geotechnical/hydraulic
study, and community consultation. `SCREENING_GRADE_NOTICE` in `core/constants.py` is the
canonical string.

### Key vocabulary [KEEP — v1's strongest section, carried verbatim in substance]

| Term | What it is | Why it exists |
|---|---|---|
| **Source habitation** | A village/settlement that may need to move (LGD-coded, with population, households, priority score, triage tier) | Relocation starts from people at risk, not from empty land. Demand (`demand_j`) comes from here. |
| **Candidate site** | A nearby polygon that could receive relocated households | Destinations must be found before anyone can be assigned. Each gets a capacity and a suitability. |
| **Eligibility mask** | Binary go/no-go layer (safe + buildable + legally usable) | Filters out unsafe or illegal land *before* expensive capacity math. FR-7.2. |
| **Carrying capacity (CC)** | Max households a site can absorb, in HH units | Land alone is not enough — sites with land but no water/school fail within ~2 years and families return (PRD §1.1, failure #2). |
| **Binding constraint** | The single smallest of the four capacities (`argmin`) | Tells the investor exactly what to fix ("218 HH, water-limited"). FR-7.5. Capacity is a **minimum, never an average** (FR-7.4) — averaging hides the bottleneck. |
| **Augmented capacity** | Capacity after relieving the binding constraint, with named intervention | Turns a diagnosis into a budget decision ("+ borewell scheme → 340 HH"). FR-7.6. Cost stays `None` until verified — never invented. |
| **Suitability (0–100)** | How *desirable* a site is (access, services, jobs proximity) | Stored and displayed **separately** from capacity (FR-7.7). A large but remote site has high capacity and low suitability — conflating them corrupts the allocation benefit term. |
| **Livelihood multiplier μ ∈ [0.6, 1.0]** | Down-rating for poor jobs/market/cultivable-land access | A site with no commute-viable livelihood empties out. μ multiplies the min-capacity rather than adding a fifth constraint, so it can only shrink, never inflate. |
| **Allocation (`x_js`)** | Household flows from habitation j to site s | Solves "who goes where" district-wide under capacity limits. Exact min-cost flow (FR-8.2), not a greedy heuristic. |
| **Group split** | One habitation's households divided across ≥2 sites | Sometimes mathematically necessary, always socially costly. Must be surfaced explicitly for sign-off (FR-8.3). |

### Prerequisites [REVISED — availability column added]

| Input | Source | Used in | Available? |
|---|---|---|---|
| H3 res-8 `MHI_static`, `dominant_hazard` | Steps 1–10 | R12 eligibility (`MHI_static < 0.25`) | ✅ Barpeta, flood-only (no landslide model) |
| Slope, HAND, drainage | `fetch_terrain.py` / Step 8 | R12, R17 access cut-off | ✅ Barpeta rasters on disk |
| Habitation list (LGD, population, households, geom) | L3 exposure track | R11 demand | ❌ **Step 10.5 [NEW]** |
| Priority score `PS_j`, triage tier | FR-6.1–6.5 | R11, R19 benefit | ✅ code exists (`core/domain/priority.py`), needs real inputs |
| Land cover, forest, protected, CRZ, water | ESA WorldCover, OSM, JRC GSW, MoEFCC | R12 exclusions | ⚠️ WorldCover + JRC on disk; forest/protected/CRZ not fetched |
| Buildings, roads, schools, health | Open Buildings, OSM, UDISE+, IPHS | R13–R17 | ❌ **OSM fetch required for R16/R17** |
| Groundwater yield / CGWB block category | CGWB, PHED | R14 | ❌ **[CUT]** → `None` + data gap |
| Nightlights, cropland, markets | VIIRS, WorldCover, OSM | R16–R17 | ⚠️ cropland ✅; **VIIRS [CUT]**; markets via OSM |
| Tenure (government / private / unverified) | Revenue records | R12 (FR-7.3) | ❌ → `tenure_unverified`, flagged not fatal (B2) |

---

# Step 10.5 — Habitation Ingestion (Barpeta) **[NEW]**

## Objective
Create the demand side. v1 assumed this existed; it does not (B1).

### Inputs
- `data/raw/boundaries/barpeta.geojson` (present)
- OSM `place=village|hamlet|town` points, clipped to that boundary
- `data/raw/worldpop/ind_ppp_2020_constrained.tif` (present)
- Open Buildings 2.5D footprints (optional, for household counts)
- LGD code list

### Tasks
1. Extract settlement points from OSM within the Barpeta boundary.
2. Assign population dasymetrically from WorldPop per FR-2.6 — redistribute onto built-up
   footprints, never spread evenly.
3. `households = population / 4.5` as v0 (or Open Buildings footprint count where available).
4. Join LGD codes where resolvable. Where not resolvable, write `lgd_code = NULL` and flag it —
   **never fuzzy-match on names** (PRD §8.7: every downstream government join degrades if you do).
5. Write `habitation` + `habitation_risk` rows.
6. Run existing `core/domain/priority.py` (`compute_priority_score`, `compute_time_decayed_loss`,
   `classify_triage_tier`) over them against the Barpeta `MHI_static`.

### Why this way
Barpeta is the only district with a real hazard surface. Seeding demand anywhere else means the
entire relocation chain runs on fixtures, which proves nothing. OSM + WorldPop is the only
combination in the Tier-A stack that yields settlement geometry *and* population without a keyed
source.

### Known limitation to state
Vulnerability `V̂` will be flat or fixture-derived until the FR-5.5 downscaling runs. Per FR-5.7 a
flat `V̂` must be **labelled as a failure state in the interface**, not silently accepted.

### Validation
- Settlement count vs. Barpeta's Census village count — same order of magnitude.
- `Σ habitation.population` vs. district WorldPop total — no double counting.

### Output
```text
habitation, habitation_risk rows for Barpeta
data/interim/relocation/barpeta/habitations.parquet
```

**Estimated effort: ~0.5 day. Unblocks R11–R20.**

---

# Step 11 — Define Demand + Search Envelope

## Objective [KEEP]
Decide **who needs to move** and **how far we look** for each of them. Relocation is demand-driven:
without a ranked, tiered demand list, site generation optimises land nobody needs.

### Inputs
- Habitation table from Step 10.5: `habitation_id, lgd_code, name, households, population, geom`
- Priority score `PS_j = (ĥ·f̂·V̂) × (1 + 0.5·L̂)` (FR-6.1) + urgency/caseload toggle (FR-6.3)
- Triage tier per PRD §6.7 rule (Immediate / Short-term / Medium-term / Mitigate in situ)
- Config: `search_radius_km` (default **15 km**, FR-7.1 — `SITE_SEARCH_RADIUS_KM`)

### Tasks [KEEP]
1. Filter to habitations in a relocation tier (Immediate first; Short-term next).
   `Mitigate in situ` habitations are explicitly **excluded** from demand — the tool must be able
   to recommend *against* relocation (FR-6.5).
2. Set `demand_j = households` requiring relocation (full or partial per tier note).
3. Buffer each source geometry by `search_radius_km` → `search_polygon`.
4. Clip all downstream work (R12–R17) to the union of search polygons for the batch being planned.

### How it works
A fixed-radius buffer is a deliberate simplification: it bounds computation, matches the
`POST /scenario` radius slider, and feeds the allocation solver's `max_search_radius_km` edge
filter. Distance beyond the radius is not "expensive" — it is **ineligible** (no edge created).

### Why this way
- Radius-bounded search keeps compute tractable (NFR-3: full district rerun < 45 min) and matches
  how DMs actually think ("nearby places").
- Tier-first ordering ensures Immediate (0–6 mo) habitations consume the best nearby capacity
  before Medium-term ones do.

### Validation
- Plot search polygons over habitations + `MHI_static`; confirm 15 km covers plausible
  destinations without crossing into a different hazard regime.
- Confirm `Σ demand_j` for the batch vs district totals (no double counting).

### Output
```text
data/interim/relocation/barpeta/demand.parquet
  habitation_id, name, demand_households, priority_score, tier, search_polygon
```

---

# Step 12 — Habitable-Land Eligibility Mask **[REVISED — B2, B3]**

## Objective [KEEP]
Throw away land that is **unsafe, unbuildable, or legally excluded** before any capacity math.
What survives is "habitable land available" in the PRD sense.

### Inputs
- `MHI_static` per H3 cell (Barpeta flood layer; landslide MHI absent — state this)
- Slope raster (`data/processed/flood/barpeta/slope.tif`)
- ESA WorldCover v200, JRC GSW permanent water (`barpeta_jrc_permanent_water.tif`)
- Protected-area polygons, CRZ-I/II, OSM water bodies
- Cropland fraction (`barpeta_cropland_fraction.tif`, already computed)
- Tenure attribute per parcel — **absent for Barpeta; see the tenure rule below**

### Tasks [REVISED]
1. Build a binary raster/vector mask. A cell/parcel is eligible **only if all hold** (FR-7.2):
   ```text
   MHI_static < 0.25
   AND slope < 15°
   AND NOT (forest OR protected OR CRZ-I/II OR water body)
   AND NOT built_up                        <-- [NEW, B3] WorldCover class 50
   ```
2. **[NEW, B3]** Record `cropland_fraction` per polygon (WorldCover class 40). It is **not** a
   hard exclusion — some conversion is legitimate — but it is a **flagged penalty routed into μ**
   at R16 and shown in the dossier.
3. Polygonize surviving areas; drop fragments with contiguous area **< 2 ha**.
4. **[REVISED, B2]** Tag each polygon with tenure. Add to `CandidateSitePolicy`:
   ```python
   allow_unverified_tenure: bool = False   # screening mode sets True
   ```
   - **Screening mode (prototype default `True`):** `tenure_unverified` survives eligibility, is
     recorded in `data_gaps`, and renders as a "tenure unverified" badge (FR-7.3, PRD §12 risk row).
   - **Order-grade mode (`False`):** preserves the existing H7 hard-reject invariant.
   Bump the policy version to `site-eligibility-v1.1` and record the mode in `metadata.yaml`.
   **Do not flip the default in `capacity.py` without the version bump** — a P0 invariant would
   regress silently.
5. Record per-polygon `mhi_max`, `slope_mean`, `area_ha`, `cropland_fraction`, and exclusion
   reasons for rejected candidates.

### Why built-up and cropland matter here specifically [NEW]
Barpeta is the Brahmaputra floodplain: flat, and `mean_cropland_fraction 0.489` per the shipped
metadata. Without a built-up exclusion the mask surfaces **existing settlements as empty
relocation land**. Without a cropland flag it recommends **prime paddy**, whose acquisition is a
political and legal non-starter. v1's exclusion list covered neither.

### How it works
`CapacityEngine.evaluate_site_eligibility()` in `core/src/core/domain/capacity.py` with
`CandidateSitePolicy`. The function is strict about missing data: **missing MHI, slope, area or
tenure → reject with a named reason**, never assume safe. That is the "missing data ≠ safe"
invariant the backend audit enforces, and the tenure flag above is the *only* sanctioned
relaxation of it.

### Why this way [KEEP]
- Hazard-first (`MHI < 0.25`, far stricter than the PRZ cutoff 0.75) guarantees destinations are
  not tomorrow's sources — the failure mode the whole platform exists to prevent.
- Slope + contiguous-area gates enforce *buildability*: a safe but 30° or fragmented parcel cannot
  take a layout + roads + drainage.
- Legal exclusions prevent recommending land the state cannot lawfully allot, which would kill a
  relocation order on challenge.

### Validation
- Overlay mask on `MHI_static` + slope + WorldCover; spot-check 3 known-good and 3 known-bad
  locations (steep ridge, reservoir edge, forest block).
- Confirm no surviving polygon overlaps JRC permanent water.
- **[NEW]** Confirm no surviving polygon overlaps WorldCover built-up.
- Count surviving polygons + total ha per search envelope. In Barpeta, `mean_susceptibility 0.446`
  means the `MHI < 0.25` gate alone should eliminate the majority of cells — if it does not,
  the mask is wired wrong.

### Output
```text
data/interim/relocation/barpeta/eligible_polygons.gpkg
  polygon_id, area_ha, slope_mean, mhi_max, cropland_fraction, tenure, source_habitation_id
```

---

# Step 13 — Land Capacity (CC_land) [KEEP — already implemented]

## Objective
Convert each eligible polygon's area into **households it can physically house**.

### Formula (PRD §6.8)
```text
CC_land = floor(A_developable_m2 / 126)
126 = ~90 m² plot + 40% infrastructure overhead (roads, drains, open space)
```
(PRD Q-3 may refine the state-specific plot norm; until then 90 m² holds. Both values live in
`core/constants.py` as `PLOT_AREA_M2` and `INFRA_OVERHEAD`.)

### How it works
`CapacityEngine.calculate_land_capacity()`: `floor(area / (plot_area × (1 + overhead)))`. Pure
geometry — no survey needed, so it is always computable and forms the capacity ceiling nothing
else can exceed unless augmented.

### Why this way
- Floor (not round) because half a plot houses nobody.
- Overhead is structural, not padding: layouts without roads/drains fail PWD approval and flood in
  the first monsoon.
- Land is evaluated first because it is the cheapest input and the hardest constraint to relieve
  (acquiring adjacent land ≫ drilling a borewell).

### Validation
- Hand-check: 2 ha (20,000 m²) → `floor(20000/126)` = **158 HH**.
- Confirm `A_developable` excludes internal water/steep pockets, not just the bounding box.

### Output
Per-polygon `cc_land` (integer HH). Feeds R18. **Status: real data, no new code needed.**

---

# Step 14 — Water Capacity (CC_water) **[REVISED — B4, CUT]**

## Objective [KEEP]
Cap each site by **sustainable potable water** — the most common binding constraint in practice.

### Formula (CPHEEO norm, PRD §6.8)
```text
CC_water = floor(Y_sustainable_LPD / (LPCD × HH_size))
LPCD = 55 rural, 135 urban-with-sewerage; HH_size ≈ 4.5
```

### **[CUT]** CGWB / PHED acquisition
Not obtainable at village granularity in the prototype window; no ingestion exists. Do not chase it.

### Prototype rule [REVISED]
1. **Default: `cc_water = None`.** `evaluate_site_capacity()` already routes `None` into
   `data_gaps`, excludes it from the `min()`, and sets `data_quality = partial`. That is the
   honest output, and it is already implemented.
2. **If** a CGWB block category is available, derive yield from an explicit, versioned
   `cgwb_category → litres/day/ha` table in `core/constants.py`, and:
   - print the mapping verbatim in the dossier and `metadata.yaml`
   - label the value **`norm-derived, not observed`** in the UI, visually distinct from a
     measured value
3. **Never** silently treat "no data" as infinite water.

### Why the labelling matters [NEW, B4]
The demo's marquee string is *"218 HH, water-limited"*. If that number comes from a block-scale
category divided by nothing, it is a config constant wearing the costume of a measurement. Saying
so on the surface is the difference between a defensible screening tool and a demo that the first
hydrogeologist in the room takes apart.

### Why the formula is right regardless [KEEP]
Water is flow-limited (L/day), not stock-limited: a site with 500 plots and a 20,000 LPD source
houses `floor(20000/247.5)` ≈ **80 HH** — the other 420 plots are uninhabitable until supply is
augmented. Averaging would hide this; the `min()` exposes it as the binding constraint (FR-7.4).
Rural 55 LPCD is the CPHEEO design norm DMs defend in sanctions.

### Validation [REVISED]
- For each site, list source → yield → `cc_water`, or `None` → gap note.
- Flag any site where `cc_water < 0.5 × cc_land` (water-limited).
- **[CUT]** v1's "cross-check against nearest habitation's current supply complaints" — no data
  source exists.

### Also fix while here — **defect D1**
`evaluate_site_capacity()` passes `active_norms.lpcd_rural` positionally into
`calculate_water_capacity()`, which overrides `is_urban=True`. Urban sites silently receive 55
LPCD instead of 135. Pass `lpcd=None` and let `is_urban` select.

### Output
Per-polygon `cc_water` (integer HH or `None` + gap note). Feeds R18.

---

# Step 15 — School + Health Capacity **[REVISED — CUT]**

## Objective [KEEP]
Cap each site by **absorptive social infrastructure within access distance** — the constraint that
causes resettlement failure in year 2 (children drop out, families return).

### Formulas (UDISE+ / IPHS norms, PRD §6.8)
```text
CC_school = floor(spare_seats_within_1km / 1.2 children_per_HH)
CC_health = floor(max(0, PHC_norm - catchment_pop) / 4.5)
PHC_norm  = 20,000 hilly/tribal
            30,000 plains  <-- Barpeta floodplain uses this
```

### **[CUT]** UDISE+ / IPHS acquisition
Both are data.gov.in Tier-B keyed sources; per-school sanctioned capacity is not reliably in OSM.
No ingestion exists. **Prototype: `cc_school = None`, `cc_health = None` → `data_gaps` →
`data_quality = partial`.** The code already handles this correctly; no new work.

### Re-add path (post-prototype)
- Schools: OSM points + UDISE+ enrolment vs sanctioned within 1 km of centroid;
  `spare_seats = Σ (sanctioned − enrolled)` floored at 0.
- Health: nearest PHC + catchment population (Census + WorldPop dasymetric); spare = norm − catchment.

### Why the formula is right regardless [KEEP]
- 1 km is the walking-access norm for primary schooling; capacity 10 km away is not capacity for a
  relocated child.
- IPHS norms are the sanctioning authority's own yardstick — quoting them makes the
  "health-limited" verdict defensible in a funding proposal (G-1, G-4).
- Capping (not scoring) forces honesty: a site 500 m from a full school gets `cc_school = 0`,
  which is correct until classrooms are sanctioned.

### Also fix while here — **defect D2**
`evaluate_site_capacity()` passes `spare_health_capacity_pop` into the `phc_norm_pop` parameter
with `catchment_pop=0`, so the caller must pre-subtract catchment while the parameter is named
"norm", and `is_hilly_or_tribal` is dead on that path. Rename to `spare_pop` on a dedicated path,
or compute `norm − catchment` inside using the real catchment. This is a live footgun for the
re-add path above — and it currently masks **defect D4**: `site_generator.py:68-69` hardcodes
`is_hilly_or_tribal=True`, wrong for Barpeta (plains, 30,000). Fix D2 and D4 together, or the
health norm silently switches to the wrong figure.

### Validation [REVISED]
- With both `None`, confirm the dossier renders "school capacity: not assessed" rather than 0.
- **[CUT until UDISE+ lands]** v1's shared-catchment pre-split check (two sites double-counting the
  same spare seats). Real, but moot while `cc_school = None`. Re-add with the data.

### Output
Per-polygon `cc_school`, `cc_health` (`None` + gap notes in prototype). Feeds R18.

---

# Step 16 — Livelihood Multiplier μ **[REVISED — reduced]**

## Objective [KEEP]
Down-rate sites where relocated households **cannot earn a living within commute distance** — the
constraint that causes silent abandonment (houses occupied on paper, empty in practice).

### Formula (PRD §14.1)
```text
CC(s) = min(CC_land, CC_water, CC_school, CC_health) × μ,  μ ∈ [0.6, 1.0]
```

### Inputs [REVISED — reduced to what exists]
**Kept:**
- Cultivable land share within commute — ESA WorldCover cropland, ~10 km plains (Barpeta).
  `barpeta_cropland_fraction.tif` is already on disk.
- Market/mandi + town distance — OSM places, roads.
- **[NEW, B3]** Cropland fraction *of the site itself* from R12, as a conversion penalty.

**[CUT]:**
- VIIRS nightlight intensity — not downloaded; second-order for a prototype.
- Census occupation-profile weighting (cultivator / agri-labour / non-farm) — adds a join for a
  second-order effect.

### How it works — μ v0 rule (recorded in config)
```text
μ = 1.0  if market < 5 km AND cultivable share within commute > 30%
μ → 0.6  as distances double / shares halve (linear decay, clamped)
μ       further penalised in proportion to the site's own cropland_fraction
```
Applied in `calculate_final_capacity()`, clamped to `[0.6, 1.0]` by
`livelihood_multiplier_min/max`. It **multiplies the minimum** — it can only shrink capacity,
never rescue a water-limited site.

### Why this way [KEEP]
A multiplier (not a fifth `min()` term) reflects reality: poor livelihood does not cap plots, it
causes attrition. The 0.6 floor bounds the judgement so a remote-but-serviced site is not scored
as worthless.

### Validation [REVISED]
- For each site, publish the μ worksheet (distances, shares, cropland fraction → μ). A DM must be
  able to argue with it — that is the point (G-4).
- **[CUT]** v1's μ ∈ {0.6, 0.8, 1.0} sensitivity re-run of R18 — validation luxury, not a demo
  requirement.

### Output
Per-polygon `livelihood_multiplier μ`. Feeds R18.

---

# Step 17 — Transport + Suitability Score (0–100) **[NEW MODULE — does not exist]**

## Objective [KEEP]
Score **how desirable and connected** each site is, separately from how many households it can
take (FR-7.7). Transport answers "can people live their lives from here?" — school bus, PHC
referral, market trip, evacuation route.

## ⚠️ This is new code, not a wiring exercise [NEW]
v1 describes R17 as feeding two places in `allocation.py`. Those two consumers exist; **the
producer does not**. There is no `compute_suitability` anywhere in `core/`, `api/` or `pipeline/`
— `suitability` is a stored column only.

**Consequence today:** every candidate site carries `suitability = None`, so
`compute_assignment_benefit()` returns `0.0` for every edge, and the allocation solver is running
**pure distance minimisation with no benefit term at all**. The objective in FR-8.1 is currently
half-implemented in practice. Write `core/domain/suitability.py`.

### Inputs [REVISED — reduced]
**Kept:**
- OSM roads (Geofabrik `india-latest.osm.pbf`): all-weather road distance, footpath-only flag
- Distance to source habitation (social continuity + move cost)
- Service density: schools / health / markets within 1–3 km (OSM points, count only — no UDISE+ join)

**Deferred:**
- HAND/slope of the **access route** (a safe site behind a flood-cut road is seasonally stranded).
  Right idea, meaningful cost; add after v0 works.
- Site-internal slope dispersion.

### How it works — suitability v0
Weighted 0–100 composite (weights in config, exposed to `POST /scenario`):
```text
suitability = w_road·f(road_dist) + w_services·f(1-3km count) + w_proximity·f(source_dist)
```
Feeds two places in `core/domain/allocation.py`:
- Benefit: `b_js = PS_j × (suit/100) × scale` (`compute_assignment_benefit`).
  `suitability = None` (unverified) → **zero bonus**, never a penalty or a guess.
- Cost: `c_js = dist × penalty` (`compute_relocation_cost`); net edge cost `c_js − b_js`
  (`compute_assignment_cost`).

### Why this way [KEEP]
- Separation of capacity vs suitability is load-bearing: the allocation objective
  `Σ x·(PS·suit) − c·x` needs both independently. Merging them into one "goodness" number would
  let a close-but-tiny site outrank a farther site that actually fits the village.
- Transport enters **twice** (suitability bonus + distance cost) deliberately: proximity is both a
  preference and a budget line.

### Validation
- Rank sites by suitability alone; confirm the top site is also the one a field officer would pick
  on a map (road-adjacent, near services, near source).
- Confirm `suitability = None` sites get no benefit bonus in a dry-run allocation
  (already covered by `tests/unit/test_m13_site_suitability.py`).

### Output
Per-polygon `suitability` (0–100 int or `None`), plus `distance_km` to each source habitation in
range. **[REVISED]** v1's file tree listed `distances.parquet` with no step producing it — distance
computation belongs here.
```text
data/interim/relocation/barpeta/distances.parquet
```

---

# Step 18 — Final Capacity + Binding + Augmented **[KEEP + D3]**

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
`calculate_final_capacity()` → `calculate_augmented_capacity()` → `evaluate_site_capacity()`
bundles everything into `CapacityEvaluationResult` with `data_quality`
(`complete/partial/unavailable`) and `data_gaps`. `build_candidate_site_record()` serialises to the
`candidate_site` row shape:
```text
area_ha, tenure, slope_mean, mhi_max,
cc_land, cc_water, cc_school, cc_health, cc_final,
binding_constraint, augmented JSONB, suitability, metadata JSONB
```
Intervention strings are canned per constraint (WATER → "piped water supply scheme / deep borewell
with storage"; SCHOOL → "additional classroom + teacher intake"; HEALTH → "PHC sub-centre
upgrade"; LAND → see D3 below).

### **[REVISED — defect D3]** LAND-binding augmentation
`calculate_augmented_capacity()` falls back to `surrogate_high = max(known + [1000]) * 2` when no
`relieved_capacity` is given. For water/school/health that is correct — the result is just the
second-smallest constraint. For `binding == LAND` it implies land can be doubled by "boundary
consolidation", which is not an intervention with a budget line.

**Report `augmented = None` for LAND-binding sites**, with the string
*"land-limited — no augmentation without acquisition"*. Inventing a number here contradicts the
same principle that keeps `indicative_cost_inr_lakhs = None`.

### Why this way [KEEP]
- `min()` is the honesty mechanism: the site is only as big as its tightest lifeline. Tie-break
  order is deterministic so re-runs are reproducible.
- Augmented capacity converts a veto into a shopping list — the SDMA planning officer's actual job.
- `indicative_cost_inr_lakhs = None` is intentional: the engine **refuses to invent financial
  figures**. Costs enter only from verified estimates.

### Validation
- For every site print the four-way bar (`land | water | school | health → min × μ`). The shortest
  bar must equal `binding_constraint`. **In the prototype three of four bars will read
  "not assessed"** — that is the correct rendering, not a bug.
- Confirm `augmented.augmented_capacity ≥ cc_final` and `next_binding ≠ binding` (unless all tied,
  or LAND-binding per D3).
- Confirm `data_quality` / `data_gaps` round-trip into the dossier UI's
  "tenure unverified / yield unverified" badges.

### Output
```text
data/processed/relocation/barpeta/candidate_sites.parquet
  + rows staged for candidate_site table
```
Dossier string per site: `"<CC_final> HH, <binding>-limited"`.

---

# Step 19 — Allocation (habitation → site) **[KEEP — already implemented]**

## Objective
Assign **which households go where** without exceeding any site's `CC_final` or any habitation's
demand.

### Formula (PRD §14.1, FR-8.1)
```text
max Σ_{j,s} x_js · (PS_j · suit_s) − c_js · x_js
s.t. Σ_s x_js ≤ demand_j ,  Σ_j x_js ≤ CC_s
```
Solved **exactly** with OR-Tools (FR-8.2 — the problem is small per district; no heuristic).

### How it works
`MinCostFlowAllocationSolver.solve()`:
1. Nodes: source → habitations (`demand_j`) → sites (`CC_s`) → sink, plus a source→sink slack arc
   (unmet demand at high penalty, so the solver prefers real assignment but stays feasible when
   capacity is short).
2. Edges habitation→site exist **only within** `max_search_radius_km` (default 15 km) with integer
   cost `round((c_js − b_js)·100) + offset`.
3. Extract flows `x_js`; any habitation touching ≥2 sites gets `has_group_split = True` + a warning
   string requiring social sign-off (FR-8.3).
4. `validate_allocation_invariants()` re-checks both constraint families.
5. `allow_group_splits=False` switches to the CP-SAT whole-village path (`_solve_no_splits_cp_sat`).

### Why this way [KEEP]
- Min-cost flow is the right tool: the objective and constraints are linear and the graph is
  bipartite — exact optimum in milliseconds, explainable edge by edge.
- The slack arc guarantees an answer even when capacity is insufficient ("relocate 60%, unmet
  40%") instead of solver failure — the honest output for an under-resourced district.
- Splits are surfaced, not hidden, because splitting a village across sites is a social decision
  above the model's pay grade.

### Scope [REVISED]
**One village end-to-end. [CUT] the district-wide run** — village scale exercises the identical
code path and proves the same chain.

### Validation
- Invariants: no site over `CC_s`, no habitation over `demand_j`, all flows ≥ 0.
- Unmet-demand review: if `unmet > 0`, the dossier must say which tier went unserved and which
  binding constraints caused it.
- **[CUT]** v1's re-run sweep over `distance_penalty_weight` / radius for stability.

### Output
```text
data/processed/relocation/barpeta/allocation.parquet
  habitation_id, site_id, households, distance_km, has_group_split
  + rows staged for relocation_plan (tier, priority_score, rationale JSONB)
```

---

# Step 20 — Dossier, Export + Ground-Verification Gate **[REVISED]**

## Objective [KEEP]
Turn model outputs into a **defensible DM briefing that cannot be mistaken for a final order**.

### Tasks
1. Per source habitation, render (`GET /habitations/{id}/sites` + right-panel dossier, FR-10.4):
   - why it ranks here (MHI breakdown, SHAP top-5, loss timeline, vulnerability)
   - ranked candidate sites: `CC_final`, binding bar, augmented card, suitability, distance,
     tenure badge
   - **[NEW]** explicit "not assessed" rendering for `cc_water` / `cc_school` / `cc_health`, and a
     `norm-derived, not observed` badge wherever a value came from a norm table (B4)
   - **[NEW]** flat-`V̂` warning per FR-5.7 while vulnerability downscaling is absent
   - allocation result + split warnings
2. District pack via `POST /plan/allocate`.
   **[CUT]** `GET /export/{admin}/briefing.pdf` — already #2 on the PRD §5.2 cut-line.
3. **Gate:** every surface carries the screening-grade label
   (`SCREENING_GRADE_NOTICE`, `core/constants.py`) plus the three pre-order requirements — ground
   verification, detailed slope-stability / hydraulic study, community consultation. **No export
   path bypasses the label.**

### How it works
Read path only: API serves Postgres (`candidate_site`, `relocation_plan`, `explanation` JSONB) +
MVT tiles. Scenario re-ranks via `POST /scenario` (weight/radius/norm overrides) without touching
stored capacities.

### Why this way [KEEP]
Personas (PRD §3): the DM signs orders and is personally accountable; the SDMA officer defends a
ranked list against a fixed budget; NDRF needs tonight-vs-months separation. The dossier serves all
three only if every number is inspectable (G-4) and permanent relocation is never confused with
evacuation (FR-3.11 / 3.14 — alert zones never influence tiers).

### Validation
- Click-path rehearsal: district view → top habitation → dossier → site cards → augmented →
  allocate, on the offline snapshot (NFR-4).
- Interface-string review against FR-3.15 (forecast claims) and PRD §1.3 (screening label).

### Output
Staged `relocation_plan` rows. Demo reads from the recorded snapshot with `DEMO_MODE`; zero live
external calls.

---

# PART III — SCOPE, MILESTONES, CONFIG

## 5. What changed from v1, at a glance

### Cut outright
| Cut | Reason |
|---|---|
| CGWB / PHED / UDISE+ / IPHS acquisition | Tier-B keyed, village granularity unavailable in window. `None` → `data_gaps`; already handled correctly in code |
| VIIRS nightlights in μ | Not downloaded; μ works without it |
| Census occupation-mix weighting in μ | A join for a second-order effect |
| Sensitivity re-runs (μ sweep, radius sweep) | Validation luxury, not a demo requirement |
| District-wide allocation run | Village scale exercises the identical code path |
| Second pilot district (Wayanad relocation) | Code is AOI-parameterised; running twice proves nothing new |
| PDF briefing pack | Already #2 on the PRD §5.2 cut-line |
| R14 "supply complaints" cross-check | No data source exists |
| R15 shared-catchment pre-split | Moot while `cc_school = None`; re-add with UDISE+ |

### Added (missing from v1)
| Add | Why |
|---|---|
| **Step 10.5 — habitation ingestion (Barpeta)** | B1. Hard prerequisite for R11 |
| **`core/domain/suitability.py`** | R17 has no producer. Until it exists every allocation edge has `suitability=None` → benefit 0.0 → pure distance minimisation |
| **Built-up hard exclusion + cropland flag (R12)** | B3 |
| **`allow_unverified_tenure` policy flag (R12)** | B2 |
| **`norm-derived, not observed` badge (R14, R20)** | B4 |
| **Defect fixes D1, D2, D3** | Live bugs in `capacity.py` |
| **Defect fix D4** | Wrong PHC physiographic norm hardcoded in `site_generator.py` |

## 6. Milestones [REVISED ORDER]

### ~~Milestone F — three hand-worked sites~~ → **one-hour verification, not a milestone**
v1 proposed pushing three synthetic specs through `evaluate_site_capacity()` +
`build_candidate_site_record()`. **This is already covered** by `tests/unit/test_domain_capacity.py`,
`test_domain_capacity_day5.py` and `test_h7_candidate_site_eligibility.py`. Run them, confirm green,
move on.

### **Milestone G — one village, real polygons** ← START HERE
Step 10.5 + R11 envelope + R12 mask for a single Immediate-tier Barpeta habitation → 5–10 real
eligible polygons with `area_ha / slope_mean / mhi_max / cropland_fraction / tenure`. Validates the
GIS chain (mask → polygonize → zonal stats) before any capacity data is chased. **Every unknown in
this plan lives here.**

### Milestone H — one village, end to end
R13 + reduced R14/R15 (`None`) + R16 μ + R17 suitability v0 → binding/augmented → 1–2 assignments.
Review the dossier strings with a domain reader.

**Stop at H for the prototype.** The full district run and the second pilot come after.

## 7. Reduced end-to-end chain

```text
Step 10.5  habitation ingestion (Barpeta)   [NEW — OSM places + WorldPop + LGD]
    ↓
R11        demand + 15 km search envelope    [existing priority.py + tier rules]
    ↓
R12        eligibility mask → polygons ≥2 ha [NEW GIS; + built-up exclusion, cropland flag,
                                              tenure unverified = flagged not fatal]
    ↓
R13        CC_land                           [real — pure geometry, already implemented]
R14/R15    CC_water / CC_school / CC_health   [= None + data_gap badge]
R16        μ from cropland share + road/market distance only   [reduced]
R17        suitability v0 = road dist + service count + source dist   [NEW module]
    ↓
R18        CC_final + binding + augmented     [existing + D3 fix]
    ↓
R19        allocation, one village            [existing, unchanged]
    ↓
R20        dossier + screening-grade gate      [existing API; no PDF]
```

Every number in that output is either measured or explicitly flagged as a gap — which is v1's own
stated success criterion, met at a scope that fits a prototype.

**Estimate: ~3–4 focused days, against ~10–12 for v1 as written.**

## 8. Data layout

```text
data/
├── interim/relocation/barpeta/
│   ├── habitations.parquet          [NEW — Step 10.5]
│   ├── demand.parquet
│   ├── eligible_polygons.gpkg
│   └── distances.parquet            [produced by R17 — v1 orphaned this file]
└── processed/relocation/barpeta/
    ├── candidate_sites.parquet
    ├── allocation.parquet
    └── metadata.yaml
```

## 9. Decisions that must be documented (config, not code) [KEEP — all 12]

Record in `metadata.yaml` + `core/constants.py`. Items marked ✅ already exist in
`core/constants.py`.

1. ✅ `search_radius_km` (15) + scenario overrides — `SITE_SEARCH_RADIUS_KM`
2. ✅ Eligibility thresholds: `MHI_static < 0.25`, `slope < 15°`, `area ≥ 2 ha` +
   **[NEW]** built-up exclusion, cropland flag, exclusion layers + versions
3. ✅ `a_hh` plot norm (90 m² + 40% = 126) + state norm if PRD Q-3 resolves
4. Water: LPCD used, HH_size, yield sources, **[NEW]** the categorical CGWB→yield table and its
   `norm-derived` labelling
5. School: search distance (1 km), `children_per_HH` (1.2), UDISE+ snapshot date *(deferred)*
6. ✅ Health: PHC norm applied (20k hilly / 30k plains — **Barpeta = plains, 30k**), catchment
   sources + date. **[NEW]** `is_hilly_or_tribal` must come from district config, not the
   hardcode in `site_generator.py` (defect D4)
7. Livelihood μ rule: commute distances, cropland weight, **[REVISED]** nightlights and occupation
   mix cut from v0
8. Suitability weights + transport inputs (road vintage) — **[NEW module, must be versioned]**
9. ✅ Allocation: `distance_penalty_weight`, `benefit_scale_factor`, `allow_group_splits`,
   cost strategy version
10. Tenure sources + **[REVISED]** `allow_unverified_tenure` mode and its policy version
11. Snapshot dates, dataset versions, licences + attribution strings (NFR-8) — the Barpeta
    `metadata.yaml` already carries five attribution strings; extend the pattern
12. Model/policy versions (`capacity-norms-vX`, `site-eligibility-vX`, `allocation-vX`) —
    **bump `site-eligibility` to v1.1** for the tenure flag

## 10. Success criterion [REVISED]

The prototype phase is complete when, for **one Barpeta habitation**, you can run:

```text
habitations -> demand + envelope -> mask -> CC_land + mu + suitability
  -> binding/augmented -> allocation -> dossier
```

and obtain ranked nearby sites each stating **how many households, limited by what, fixable how,
how suitable, how far** — with every number either **traceable to a source, a norm and a version**,
or **explicitly rendered as a gap**, and every surface carrying the screening-grade label.

The gaps are not a failure of the prototype. Rendering them honestly is the product.
