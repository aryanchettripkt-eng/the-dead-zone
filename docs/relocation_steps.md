# Relocation — Build Steps

**Goal:** produce **relocation data**. A table of candidate sites per at-risk habitation, each
saying how many households it holds, what limits it, how good it is, and how far. Choosing and
executing an actual relocation is a manual, human decision downstream — this pipeline does not
attempt it.

**Reference:** `docs/relocation_plan_review_and_revision.md` has the reasoning, formulas, norms and
PRD trace for every step below. This file is just the running order.

**District:** Barpeta (the only district with a real hazard surface on disk).
**Estimate:** ~3–4 focused days.

---

## The deliverable

One row per (habitation, candidate site):

```text
habitation_id, name, tier, priority_score, demand_households,
site_id, area_ha, tenure, slope_mean, mhi_max, cropland_fraction,
cc_land, cc_water, cc_school, cc_health, cc_final,
binding_constraint, augmented, suitability, distance_km,
data_quality, data_gaps
```

Anything not measured is `None` and shows as a gap. Nothing is invented to fill a column.

---

## Step 0 — Fix four known defects

Small, do them first so nothing downstream inherits them.

| ID | File | Fix |
|---|---|---|
| D1 | `core/domain/capacity.py` | `evaluate_site_capacity` passes `lpcd` positionally, killing `is_urban`. Pass `lpcd=None`. |
| D2 | `core/domain/capacity.py` | `phc_norm_pop` is fed *spare* population; `is_hilly_or_tribal` is dead on that path. Rename / compute inside. |
| D3 | `core/domain/capacity.py` | LAND-binding augmentation is fabricated. Return `None` + "land-limited — no augmentation without acquisition". |
| D4 | `pipeline/capacity/site_generator.py:68-69` | `is_hilly_or_tribal=True` hardcoded. Barpeta is **plains** (30,000). Move to district config. |

D2 and D4 must be fixed together — D2 currently masks D4.

**Done when:** `uv run pytest tests/unit/test_domain_capacity*.py -v` is green.
**~2 hours.**

---

## Step 1 — Habitations for Barpeta

Nothing exists here. `habitation` rows today are Wayanad/Kodagu fixtures.

**In:** `data/raw/boundaries/barpeta.geojson`, `data/raw/worldpop/ind_ppp_2020_constrained.tif`,
OSM `place=village|hamlet|town`

**Do:**
1. Clip OSM settlement points to the Barpeta boundary.
2. Assign population from WorldPop dasymetrically (onto built-up, not spread evenly).
3. `households = population / 4.5`.
4. Join LGD codes where they resolve; `NULL` + flag where they don't. **Never fuzzy-match names.**
5. Write `habitation` + `habitation_risk`.
6. Run existing `core/domain/priority.py` → `priority_score` + triage tier against the Barpeta
   `MHI_static`.

**Out:** `data/interim/relocation/barpeta/habitations.parquet` + DB rows

**Done when:** settlement count is the same order as Barpeta's Census village count, and
`Σ population` matches the district WorldPop total.

**Note:** vulnerability `V̂` will be flat until FR-5.5 downscaling runs — label it as a failure
state in any output, per FR-5.7.

**~0.5 day.**

---

## Step 2 — Demand + search envelope

**In:** Step 1 output

**Do:**
1. Keep habitations in a relocation tier. **Drop `Mitigate in situ`** — the tool must be able to
   say "don't move them".
2. `demand_j = households`.
3. Buffer each geometry by 15 km (`SITE_SEARCH_RADIUS_KM`) → `search_polygon`.
4. Clip everything downstream to the union of those polygons.

**Out:** `data/interim/relocation/barpeta/demand.parquet`
→ `habitation_id, name, demand_households, priority_score, tier, search_polygon`

**Done when:** `Σ demand_j` reconciles against district totals with no double counting.

**~2 hours.**

---

## Step 3 — Eligibility mask → candidate polygons

The main GIS step. Nothing here exists yet.

**In:** Barpeta `MHI_static` (H3 res-8 parquet), `slope.tif`, ESA WorldCover,
`barpeta_jrc_permanent_water.tif`, `barpeta_cropland_fraction.tif`

**Do:**
1. Keep only cells where **all** hold:
   ```text
   MHI_static < 0.25
   AND slope < 15°
   AND NOT (forest OR protected OR CRZ-I/II OR water body)
   AND NOT built_up          <-- WorldCover class 50
   ```
   The built-up exclusion is not optional: without it the mask hands back existing villages as
   "empty land".
2. Record `cropland_fraction` per polygon (WorldCover class 40). **Not** a hard exclusion — it
   becomes a penalty in Step 4 and a dossier flag.
3. Polygonize; drop anything under **2 ha**.
4. Tenure: no source exists, so everything is `tenure_unverified`. Add
   `allow_unverified_tenure: bool = False` to `CandidateSitePolicy` and set it `True` for
   screening. Bump the policy version to `site-eligibility-v1.1`. **Do not just flip the
   existing hard-reject** — that is a P0 invariant.
5. Zonal stats per polygon: `area_ha, slope_mean, mhi_max, cropland_fraction`.

**Out:** `data/interim/relocation/barpeta/eligible_polygons.gpkg`

**Done when:** no polygon overlaps JRC permanent water or WorldCover built-up, and the
`MHI < 0.25` gate has removed the majority of cells (district mean susceptibility is 0.446 — if
most cells survive, the mask is wired wrong).

**~1 day. Every unknown in this plan lives in this step.**

---

## Step 4 — Livelihood multiplier μ

**In:** `barpeta_cropland_fraction.tif`, OSM roads + `place`/market points, Step 3 polygons

**Do:** rule-based, clamped to `[0.6, 1.0]`:
```text
μ = 1.0  if market < 5 km AND cultivable share within ~10 km > 30%
μ → 0.6  as distances double / shares halve (linear decay)
μ        further penalised by the site's own cropland_fraction
```

Skipping VIIRS nightlights and Census occupation mix — second-order, not downloaded.

**Out:** `livelihood_multiplier` per polygon

**Done when:** each site has a printable μ worksheet (distances, shares, cropland → μ) that a
person can argue with.

**~0.5 day.**

---

## Step 5 — Suitability + distances

**This module does not exist.** Write `core/domain/suitability.py`.

Right now every site has `suitability = None`, so `compute_assignment_benefit()` returns `0.0` for
every edge and the allocation solver is doing pure distance minimisation with no benefit term.

**In:** OSM roads (`india-latest.osm.pbf`), OSM school/health/market points, Step 2 + 3 geometries

**Do:**
```text
suitability = w_road·f(road_dist) + w_services·f(count within 1-3 km) + w_proximity·f(source_dist)
```
0–100 int, weights in config. Also emit `distance_km` for every (habitation, site) pair in range.

Deferring access-route HAND/slope and internal slope dispersion — right idea, add after v0 works.

**Out:** `suitability` per polygon + `data/interim/relocation/barpeta/distances.parquet`

**Done when:** ranking by suitability alone puts a road-adjacent, service-near, source-near site on
top — i.e. the one a field officer would point at.

**~0.5 day.**

---

## Step 6 — Capacity, binding constraint, augmented

Already built (`CapacityEngine`). This step is wiring, not new math.

**In:** Steps 3–5 outputs

**Do:** call `evaluate_site_capacity()` per polygon:
- `cc_land` — real, pure geometry: `floor(area_m2 / 126)`
- `cc_water`, `cc_school`, `cc_health` — **`None`**. No CGWB / UDISE+ / IPHS ingestion exists and
  we are not chasing it. The engine already routes `None` to `data_gaps` and sets
  `data_quality = partial`.
- `cc_final = min(available) × μ`, `binding_constraint = argmin`
- augmented capacity, with `indicative_cost_inr_lakhs = None` always

If a CGWB block category ever does land, drive water off a versioned
`category → litres/day/ha` table and label the result **`norm-derived, not observed`**. Never
treat missing water as unlimited water.

**Out:** `data/processed/relocation/barpeta/candidate_sites.parquet` + `candidate_site` rows

**Done when:** for each site the four-way bar prints and the shortest bar equals
`binding_constraint`. Three of four bars reading "not assessed" is correct output, not a bug.

**~0.5 day.**

---

## Step 7 — Allocation

Already built (`MinCostFlowAllocationSolver`, OR-Tools). One village, not the district.

**In:** demand (Step 2), capacities (Step 6), distances (Step 5)

**Do:** `solve()`. Edges only within 15 km. Slack arc absorbs unmet demand rather than failing.
Flag any habitation touching ≥2 sites as `has_group_split`.

**Out:** `data/processed/relocation/barpeta/allocation.parquet` + `relocation_plan` rows

**Done when:** `validate_allocation_invariants()` returns no violations — no site over `CC_s`, no
habitation over `demand_j`.

**~2 hours.**

---

## Step 8 — Export

The humans doing the actual relocation read this.

**Do:**
1. Load `candidate_site` + `relocation_plan` into Postgres; serve via existing
   `GET /habitations/{id}/sites` and `POST /plan/allocate`.
2. Export the flat CSV/parquet of the deliverable table at the top of this file.
3. Every surface and every export carries `SCREENING_GRADE_NOTICE` from `core/constants.py`, plus
   the three pre-order requirements: ground verification, slope-stability/hydraulic study,
   community consultation.
4. Render `None` as **"not assessed"**, never as `0`. Badge `tenure_unverified`. Badge any
   norm-derived number.

No PDF pack.

**Done when:** someone who has never seen the pipeline can read one habitation's rows and say
which sites are worth surveying and what would need fixing at each.

**~2 hours.**

---

## Order and checkpoints

```text
Step 0  defects            (2h)
   ↓
Step 1  habitations        (0.5d)   <-- nothing works without this
   ↓
Step 2  demand + envelope  (2h)
   ↓
Step 3  eligibility mask   (1d)     <-- CHECKPOINT: 5-10 real polygons for one village
   ↓
Step 4  μ                  (0.5d)
Step 5  suitability        (0.5d)
   ↓
Step 6  capacity + binding (0.5d)
   ↓
Step 7  allocation         (2h)     <-- CHECKPOINT: one village, end to end
   ↓
Step 8  export             (2h)
```

**Stop after Step 3** and look at the polygons before building anything on top of them. If they
land on paddy, on existing villages, or there are 4,000 of them, the mask is wrong and every step
after it is wasted.

**Stop after Step 7.** District-wide runs and a second district come later; they exercise the same
code path and prove nothing new.

---

## Explicitly not doing

| Skipped | Why |
|---|---|
| CGWB / PHED water yield | No village-granularity source; `cc_water = None` |
| UDISE+ / IPHS school + health | Tier-B keyed, no ingestion; `cc_school`/`cc_health = None` |
| VIIRS nightlights, Census occupation mix | Second-order inputs to μ |
| Sensitivity sweeps (μ, radius) | Validation luxury |
| District-wide run, second district | Same code path |
| PDF briefing pack | Already on the PRD cut-line |
| Anything resembling an actual relocation order | Human decision. This produces data, not orders. |

---

## Implementation status — Steps 12-13 (added)

Both steps are implemented and have been run for Dholpur and Morena.

| Piece | Where |
|---|---|
| WorldCover class fractions (tree cover, built-up) | `pipeline/src/pipeline/relocation/landcover.py` |
| Step 12 mask + polygonisation | `pipeline/src/pipeline/relocation/eligibility_mask.py` |
| Step 13 CC_land | `CapacityEngine.calculate_land_capacity()` (pre-existing) |
| Runner | `pipeline/src/pipeline/jobs/derive_candidate_sites.py --district <key>` |
| Schema | `infra/migrations/015_derived_candidate_sites.sql` |
| Tests | `tests/unit/test_eligibility_mask.py` |

Gates applied: `susceptibility < 0.25`, `slope < 15°`, not permanent water, tree cover below
threshold, built-up below threshold, inside the district polygon, contiguous area ≥ 2 ha.
Cropland is recorded per parcel, never used as a gate.

**Not allocatable by design.** Parcels carry `cc_land` but `cc_water`/`cc_school`/`cc_health`
stay NULL — no CGWB, UDISE+ or IPHS source is ingested — so `cc_final` is NULL and the allocation
repository's `cc_final > 0` filter excludes them. Tenure is likewise unverified for every parcel.
They surface through `GET /habitations/{id}/sites?include_screening=true` with their rejection
reasons, which is the honest end state for Steps 12-13 alone: Steps 14-17 supply what allocation
needs.

`CandidateSitePolicy` gained `allow_unverified_tenure` (default `False`, preserving the H7
order-grade invariant) and each environmental exclusion now only rejects on missing data while
that exclusion is enabled — a disabled rule ignores its attribute instead of rejecting every
parcel. Policy version is now `site-eligibility-v1.1`.
