# SETU-DRR — Day 8 Backend Freeze Audit

**Audited commit:** `64a850a` (main)
**Scope:** complete backend — `core/`, `api/`, `pipeline/`, `infra/`, `tests/`, `openapi.json`, plus the frontend contract surface in `web/`
**Method:** full source read of every backend module; test suite executed on a clean checkout; `app.openapi()` regenerated and diffed against the committed contract; Python import resolution verified under the configured test path; schema constraints exercised directly.

**Result:** 54 findings — 7 blockers, 13 high, 18 medium, 16 low — plus 12 areas verified sound.

---

## Contents

1. [Headline corrections](#1-headline-corrections)
2. [Blockers](#2-blockers)
3. [High](#3-high)
4. [Medium](#4-medium)
5. [Low](#5-low)
6. [Verified sound](#6-verified-sound)
7. [Suggested order of work](#7-suggested-order-of-work)

---

## 1. Headline corrections

Three claims in `docs/BACKEND_COMPLETE_HANDOFF.md` do not survive verification. They are stated here first because three teams are working from that document.

| Claim | Reality |
|---|---|
| "187/187 automated tests passing" | 187 collected is accurate. On a clean checkout with no `.env`: **140 passed, 47 failed**, all on `psycopg.OperationalError: connection refused`. The DB-dependent suites have no skip guard. |
| "Full `DEMO_MODE=true` enforcement ensuring zero external network calls" | `DEMO_MODE` is read in exactly two places, both of which only log or echo it. No adapter, ingester or STAC client checks it. |
| "Day 6 — Active & Forecast Alert Zones" | Both endpoints return **zero rows by construction** against the seeded dataset. See [B6](#b6). |

A fourth, softer one: the handoff's Day 7 `DataQuality` state list (`observed`, `nowcast`, `forecast_72h`, `proxy`, `interpolated`, `stale`, `synthetic`) does not match the enum in the code. See [M2](#m2).

---

## 2. Blockers

Each of these means the system is **not malleable** in the way the handoff promises — the seam exists as a shape, but nothing flows through it.

### B1 — The ML plug-in point is dead code

**Files:** `core/src/core/ml/registry.py:272`, `pipeline/src/pipeline/hazard/terrain_zonal.py:27-28`

The global `model_registry` singleton has **zero production references**. Grepped across `api/`, `core/`, `pipeline/`: it appears only in its own module and in two unit tests. The only consumer of any provider is `TerrainHazardEvaluator`, which constructs `BaselineLandslideProvider()` and `BaselineFloodProvider()` by name in its constructor defaults.

The handoff instructs the ML team: *"wrap it in a class conforming to the protocol and register it in `ModelRegistry`. The backend will consume it automatically."* It will not. Registering a trained XGBoost model changes nothing about what the pipeline computes.

The underlying architecture is correct — the API deliberately never calls a model at request time, it reads precomputed columns. So the real swap point is the pipeline, not the serving layer. That is fine. It simply is not the swap point the document names.

**Remediation.** Change `TerrainHazardEvaluator.__init__` defaults to `model_registry.landslide_model` / `.flood_model`. Add a loader that reads a checkpoint path from env at pipeline start and calls `register_landslide_model()`. Then add one test that registers a stub returning `0.99` and asserts the emitted `hazard_static` row changes — that test is what makes the seam real.

---

### B2 — Three village names are hardcoded into the serving layer and drive Tier-1 triage

**Files:** `api/src/api/services/habitations_service.py:96,98,107,173,175,185`; `api/src/api/services/scenario_service.py:105-113`; also `pipeline/src/pipeline/jobs/seed_pilot_data.py:516`

Whether a habitation has **active ground deformation** and a **fatal event in the last three monsoons** — the two criteria that define Tier 1 (Immediate, 0–6 months) — is decided by string equality against `("Chooralmala", "Mundakkai", "Bhagamandala")`.

In `/scenario`, flash-flood susceptibility is the literal `0.85 if is_high_risk else 0.35` and riverine flood is the constant `0.20`.

Consequences:
- The demo looks completely correct; the moment real data lands, every other habitation is scored with fabricated constants — silently, with no warning and no test failure.
- `hazard_scores` in the scenario path only ever contains three keys, so two of the five hazard weight sliders (`storm_surge`, `coastal_erosion`) are **no-ops**.

**Remediation.** Migration `007`: add `active_deformation BOOLEAN` and `fatal_event_last_3_monsoons BOOLEAN` to `habitation_risk`, populated by the pipeline (the second is already derivable from `disaster_event` — the dossier path computes it as `has_fatal` and then discards it in favour of the name check). Read per-hazard scores from `hazard_static` instead of constants. Delete every name comparison; the three villages belong in `seed_pilot_data.py` only.

---

### B3 — Falsy-zero fallbacks convert a genuinely safe habitation into a moderate-risk one

**Files:** `api/src/api/services/habitations_service.py:174,175,188,189`; same idiom across `zones_service`, `alerts_service`, `sites_service`

The idiom used throughout is:

```python
float(r.get("hazard_intensity") or (0.85 if is_high_risk else 0.45))
```

In Python, `0.0 or 0.45` evaluates to `0.45`. A habitation the model correctly scores at zero hazard is served as moderate hazard. The same applies to `priority_score`, `caseload_score`, `prz_overlap_pct`, `v_index` and the `mhi_*` reads.

Today the seed never writes a zero, so it is invisible. A trained model will write zeros, and this is exactly the class of bug that produces a plausible-looking wrong ranking rather than a crash.

**Remediation.** Mechanical sweep — replace every `.get(k) or default` on a numeric field with an explicit `is not None` check. Grep: `\.get\([^)]*\)\s+or\s`. Add a unit test that feeds a zero-hazard row through `get_habitation_risk_dossier` and asserts the response is zero.

---

### B4 — `pnpm generate:types`, the frontend team's first instruction, cannot run

**Files:** `web/package.json:9`, `pnpm-lock.yaml`

`openapi-typescript` is not in `devDependencies`, not in the lockfile (0 occurrences), and not in `node_modules`. `web/lib/` does not exist. The script fails with "command not found" on the very first thing the handoff asks the frontend team to do.

Separately, the script reads `http://localhost:8000/openapi.json`, not the committed `openapi.json` the handoff says it reads — so generating types requires a running API **and** a reachable Neon database.

**Remediation.**
```bash
cd web && pnpm add -D openapi-typescript && mkdir -p lib
# package.json:
"generate:types": "openapi-typescript ../openapi.json -o lib/api-types.ts"
```
Commit the generated `lib/api-types.ts` so the frontend can work with the backend switched off. Keep the live-server variant as a second script for verification.

---

### B5 — The OpenAPI contract documents no errors, and the 422 it does document is wrong

**Files:** `openapi.json`, `api/src/api/main.py:78-86`

Every path declares only `200` and `422`. There is no `400`, `404` or `500` anywhere in the schema, so the error envelope

```json
{"error": {"code": "...", "message": "...", "request_id": "...", "details": {}}}
```

appears nowhere in the generated types. The frontend gets no typed handling for `HABITATION_NOT_FOUND`, `INVALID_H3`, `INVALID_BBOX` or `DATA_UNAVAILABLE`, all of which the backend genuinely returns.

Worse, the `422` that *is* documented is FastAPI's stock `HTTPValidationError` (`{"detail": [...]}`), but `main.py` installs a custom handler returning the `error` envelope instead. The contract actively misdescribes the one failure shape it covers — the frontend will write `err.detail` and get `undefined`.

**Remediation.** Add an `ErrorEnvelope` model in `core/schemas/common.py`, attach a shared `responses={400:…, 404:…, 422:…, 500:…}` dict on each `include_router` call in `main.py`, regenerate `openapi.json`. Roughly thirty lines; unblocks all error-path UI work.

---

### B6 — Both Day 6 alert endpoints return zero rows by construction {#b6}

**Files:** `pipeline/src/pipeline/hazard/terrain_zonal.py:137`, `pipeline/src/pipeline/jobs/seed_pilot_data.py:693`, `api/src/api/repositories/alerts_repo.py:34-36,109`

`terrain_zonal.py:137` writes:

```python
"mhi_live": mhi_static,  # In Day 2 static baseline, live matches static
"mhi_fcst": None,
```

The seed job persists those values verbatim into `mhi_snapshot`. The active-alerts query then filters:

```sql
m.mhi_live >= :min_mhi        -- 0.75
AND m.mhi_static < :prz_threshold  -- 0.75
```

With `mhi_live == mhi_static` for every row, those two predicates are **mutually unsatisfiable**. `/alerts/active` returns an empty list for every possible query.

`/alerts/forecast` filters `m.mhi_fcst >= :min_mhi`, and `mhi_fcst` is `NULL` on every seeded row, so `NULL >= 0.75` is never true. Also empty.

The Active Alert (hatched) and 72-hour Forecast (blue dashed) hex layers in the PRD's centre panel will render nothing at the demo.

The tests cannot detect this. Every meaningful assertion in `tests/integration/test_day6_alerts_api.py` sits inside a guard:

```python
if data["total_active_cells"] > 0 and len(data["items"]) > 0:
    ...
```

which is never entered. The same vacuous-guard pattern appears at `test_day6_alerts_api.py:34,59,101`, `test_day5_sites_api.py:42`, and `test_sentinel1_pipeline.py:129`.

**Remediation.** Two parts, both needed.
1. Implement the trigger chain (see [B7](#b7)) so `mhi_live` and `mhi_fcst` are actually computed. Until then, seed a handful of demonstrably-alerting cells so the layer has something to draw.
2. Replace the `if total > 0:` guards with explicit assertions — either `assert total > 0` where the seed guarantees rows, or a dedicated fixture that inserts a known alerting cell. A test that passes on an empty list is not testing the endpoint.

---

### B7 — The trigger → hazard amplification chain is not implemented end to end {#b7}

**Files:** `core/src/core/domain/hazard.py:19`, `core/src/core/constants.py:23`, `pipeline/src/pipeline/hazard/terrain_zonal.py:137`

`compute_hazard_score` implements FR-3.2:

```
H_h = clamp(S_h · (1 + β · T_h), 0, 1)
```

It has **zero callers outside tests**. `BETA` is imported by `governance.py` and `hazard.py` and applied nowhere. Nothing in the codebase reads a `hazard_dynamic.trigger_value`, or the `TriggerResult` from `BaselineTriggerProvider.evaluate()`, and turns it into an `mhi_live`.

So the whole documented chain — *rainfall trigger → ARI / I-D threshold → amplified hazard → MHI_live crosses 0.75 → Active Alert Zone* — exists as four disconnected pieces. The trigger adapter parses feeds into `CanonicalTriggerRecord`s; the baseline provider computes ARI and a trigger ratio; `compute_hazard_score` knows the formula; `classify_zone` knows the thresholds. Nothing joins them.

This is the root cause of [B6](#b6).

**Remediation.** Add a pipeline job — `pipeline/jobs/recompute_mhi_live.py` — that, for each cell and each `valid_at`: reads `hazard_static` susceptibilities, reads the latest `hazard_dynamic.trigger_value` per hazard, applies `compute_hazard_score`, recombines with `compute_mhi`, re-runs `classify_zone`, and upserts `mhi_snapshot` with real `mhi_live` / `mhi_fcst`. That single job closes B6, B7, and makes H3, H4 and H5 meaningful rather than cosmetic.

---

## 3. High

### H1 — `/zones?valid_at=` is accepted, documented, and silently ignored

**Files:** `api/src/api/services/zones_service.py:79-86`, `api/src/api/repositories/zones_repo.py:23-32`

The parameter is validated as ISO-8601, described in OpenAPI as "historical timestamp to evaluate", then dropped — the service never forwards it, and `query_zones` has no such parameter. The map time slider (−7d to +3d) is the headline interaction in the PRD's centre panel. It will move and nothing will change, with no error to explain why.

**Remediation.** Add `valid_at` to `query_zones` and bound the LATERAL subquery: `WHERE h3 = g.h3 AND valid_at <= :valid_at ORDER BY valid_at DESC LIMIT 1`. The BRIN index on `mhi_snapshot.valid_at` is already in place.

---

### H2 — `/zones` always returns `mhi_live: null` and `mhi_fcst: null`

**Files:** `api/src/api/services/zones_service.py:105-106,178-179`

Both are pinned to `None` with the comment `# Null in Day 2 baseline`. **The repository already selects them** (`zones_repo.py`, the LATERAL join returns `m.mhi_live, m.mhi_fcst`) — the service fetches the values and throws them away.

Without them the map cannot colour Active Alert or Forecast hexes from `/zones` at all; the frontend would have to fetch `/alerts/active` and `/alerts/forecast` separately and join by H3 index client-side, for every viewport pan.

**Remediation.** Pass through the values already in `r`. One line in each of two places.

---

### H3 — `/alerts/forecast?horizon=` has no effect on the result set

**Files:** `api/src/api/repositories/alerts_repo.py:95-119`

`horizon_hours` is a parameter of `query_forecast_alerts`, is range-checked to [1, 72] in the service, is echoed back in the response body — and never enters `where_clauses` or `params`. A 6-hour horizon returns identical cells to a 72-hour horizon.

**Remediation.** `AND m.valid_at <= now() + make_interval(hours => :horizon_hours)`, and bind the parameter.

---

### H4 — Alert provenance is fabricated at response time

**Files:** `api/src/api/services/alerts_service.py:74,130,131`; `infra/migrations/002_core_schema.sql:102,104`

```python
trigger_source="IMERG Early / Live Ingestion"   # string literal
issuing_model="ECMWF Open Data"                  # string literal
forecast_cycle_at=now_utc                        # request time, not the model cycle
```

`hazard_dynamic` has real `source` and `forecast_cycle_at` columns. The alerts repository never joins that table — it reads only `mhi_snapshot`. `horizon_hours` on each item is likewise echoed from the request, not derived from the data.

For a product an NDRF officer acts on, showing a fabricated model cycle is materially worse than showing nothing.

**Remediation.** Join `hazard_dynamic` on `(h3, valid_at)` — index `idx_hazard_dynamic_h3_valid` already exists for it — and surface the real `source` and `forecast_cycle_at`. Make both fields `Optional` in the schema and render "attribution unavailable" when null.

---

### H5 — No staleness guard: a three-week-old snapshot is served as a live alert

**Files:** `api/src/api/repositories/alerts_repo.py:56-60,122-128`

The `latest_snapshots` CTE is `DISTINCT ON (h3) … ORDER BY h3, valid_at DESC` with no time bound. If ingestion stops — and it will, since there is no scheduler yet — `/alerts/active` keeps confidently returning the last thing it saw, indefinitely, with no indication of age. This is precisely what `DataQuality.STALE` exists for, and it is never set anywhere in the codebase.

**Remediation.** Add `MAX_TRIGGER_AGE_HOURS` to `constants.py`. Keep returning the freshest row, but when it exceeds the threshold, tag the item `data_quality = STALE` and expose `age_hours` so the UI can grey it out. Suppressing it silently would be a different bug.

---

### H6 — The tier filter returns every unscored habitation in every tier

**Files:** `api/src/api/repositories/habitations_repo.py:33`

```python
conditions.append("(hr.tier IS NULL OR hr.tier = :tier)")
```

Filtering `?tier=immediate` also matches every habitation with no `habitation_risk` row. The seed populates all rows, so the tier chips look correct today. The first time a real habitation layer is ingested and only partly scored, the Tier-1 queue fills with unscored villages — and so does Tier 4.

Note the inconsistency: `allocation_repo.get_habitations_for_allocation` uses `hr.tier = ANY(:target_tiers)`, which correctly *excludes* unscored rows. The two paths disagree.

**Remediation.** `hr.tier = :tier`. If unscored habitations should stay visible, give them an explicit `unclassified` tier rather than leaking them into all four.

---

### H7 — The candidate-site eligibility mask is never enforced

**Files:** `core/src/core/domain/capacity.py:306` (`evaluate_site_eligibility`), `api/src/api/repositories/sites_repo.py:38-52`, `pipeline/src/pipeline/capacity/site_generator.py:60-66`, `api/src/api/repositories/allocation_repo.py:70-76`

The handoff describes a strict screening mask: static MHI ≤ 0.25, slope ≤ 15°, area ≥ 2.0 ha, non-protected tenure. `evaluate_site_eligibility` implements it well — including the careful rule that missing data is never assumed safe — and is **called by nothing outside `tests/unit/test_domain_capacity_day5.py`** (6 call sites, all in that file).

- `sites_repo.query_candidate_sites_for_habitation` filters on radius and optional `min_suitability` only.
- `site_generator.build_candidate_site_record` calls `evaluate_site_capacity` but never `evaluate_site_eligibility`, so ineligible parcels are written to the database.
- `allocation_repo.get_candidate_sites_and_distances` filters only on `cs.cc_final > 0`, so ineligible sites are allocated households by the solver.

When the GIS team loads a real land-parcel layer, the platform will recommend relocating villages onto steep, high-hazard or protected land, and the recommendation will look identical to a valid one.

**Remediation.** Two places, deliberately. (1) Push the mask into the SQL `WHERE` in both `sites_repo` and `allocation_repo`, parameterised from `CandidateSitePolicy`. (2) Call `evaluate_site_eligibility` in `site_generator` and persist `rejection_reasons` for anything rejected.

---

### H8 — `core` and `api` do not declare the dependencies they import

**Files:** `core/pyproject.toml`, `api/pyproject.toml`

`core/pyproject.toml` describes itself as *"Pure Python — no geo/ML deps"* and declares only `pydantic`, `pydantic-settings`, `python-dotenv`. But `core` imports:

| Import | Location |
|---|---|
| `h3` | `core/src/core/h3_utils.py:8` |
| `ortools` | `core/src/core/domain/allocation.py:11` |
| `sqlalchemy` | `core/src/core/db_models.py:25` |
| `geoalchemy2` | `core/src/core/db_models.py:26` |

`api/pyproject.toml` does not declare `ortools` either, and pulls it in transitively via `allocation_service`.

This works today only because the uv workspace installs `pipeline` — which does declare them — into the same virtualenv. A container built from `api` + `core` alone dies at import with `ModuleNotFoundError: ortools`. A deployment-day surprise, not a runtime one.

**Remediation.** Move `h3`, `ortools`, `sqlalchemy`, `geoalchemy2` into `core`'s dependency list and fix the description. Verify with a clean `uv pip install ./core ./api` into an empty venv followed by `python -c "import api.main"`. If `core` should stay light, split the ORM and solver into a separate `core-db` package.

---

### H9 — Tier 4 (`mitigate_in_situ`) is unreachable in production

**Files:** `core/src/core/domain/priority.py:157-160`, `api/src/api/services/habitations_service.py:100`, `api/src/api/services/scenario_service.py:115`

```python
if in_situ_cost_cheaper and pop_fraction_in_prz < cfg.mitigate_in_situ_prz_pop_max:
    return Tier.MITIGATE_IN_SITU
```

`in_situ_cost_cheaper` is **never set to `True` anywhere**. `HabitationsService` calls `evaluate_habitation()` without it (default `False`); `ScenarioService` constructs `HabitationBaselineState` without it (default `False`); no pipeline job sets it. Same for `is_caution_with_adverse_trend`, which makes the `MEDIUM_TERM` branch and its fallback identical dead code.

FR-6.5 calls Tier 4 *"a mandatory tier to recommend against relocation when feasible"*. It can never be produced, so the fourth tier chip in the UI will always be empty and the platform can never recommend in-situ mitigation over relocation — which is one of its three stated purposes.

Related: `PriorityScoringEngine.evaluate_habitation` computes

```python
has_prz = pop_fraction_in_prz > 0.0 or (pop_fraction_in_prz * 100.0) >= 30.0
```

The second clause is subsumed by the first, so `short_term_prz_overlap_min` is dead, and *any* nonzero PRZ overlap — 0.1% — sends a habitation to `SHORT_TERM` (6–24 month relocation).

**Remediation.** Add an `in_situ_cost_cheaper` input, either as a persisted column on `habitation_risk` populated by a cost comparison in the pipeline, or as a scenario parameter. Fix `has_prz` to use the threshold it was given.

---

### H10 — `compute_mhi` produces non-monotonic results for weights above 1.0

**Files:** `core/src/core/domain/hazard.py:48-54`

```python
prob_complement_product *= (1.0 - w * clamped_score)
mhi = 1.0 - prob_complement_product
```

`w · H` is not clamped before the complement. With `w = 2.0` and `H = 0.6`, the term is `1 − 1.2 = −0.2`. One such hazard gives `mhi = 1.2`, clamped to `1.0`. **Two** such hazards give `(−0.2)·(−0.2) = 0.04`, so `mhi = 0.96` — *lower* than with one hazard. Adding a second severe hazard reduces the multi-hazard index.

This is directly reachable: the frontend spec puts the hazard weight sliders at 0.0–2.0, and `/scenario` accepts weights up to any finite non-negative value.

**Remediation.** Clamp the per-hazard term before the complement:
```python
term = min(max(w * clamped_score, 0.0), 1.0)
prob_complement_product *= (1.0 - term)
```
Add a property test asserting MHI is monotonically non-decreasing in each hazard score and in each weight.

---

### H11 — `GET /alerts/active?min_mhi=<0.75` returns a 500

**Files:** `api/src/api/routes/alerts.py:33-38`, `core/src/core/schemas/alerts.py:20,40`

The route accepts `min_mhi: float = Query(0.75, ge=0.0, le=1.0)`. The response model declares `mhi_live: float = Field(ge=0.75, le=1.0)`. Any row between the requested floor and 0.75 fails response validation, which raises inside the handler and is caught by the middleware as `INTERNAL_ERROR` → HTTP 500.

Verified directly:
```
ActiveAlertItem(..., mhi_live=0.60, ...)
→ ValidationError: Input should be greater than or equal to 0.75
```
`/alerts/forecast?min_mhi=<0.75` has the identical problem via `ForecastAlertItem.mhi_fcst`.

**Remediation.** Either relax the response fields to `ge=0.0` (the semantic bound belongs to the query, not the payload), or raise the query parameter's floor to `ge=0.75`. The first is preferable — the endpoint is more useful with a tunable threshold.

---

### H12 — `allow_group_splits` has no effect on the solver

**Files:** `core/src/core/domain/allocation.py:55`, `api/src/api/routes/plan.py:22`

`allow_group_splits` appears exactly once in `allocation.py` — the dataclass field declaration. `MinCostFlowAllocationSolver.solve()` never reads it. Splits are detected *after* solving and reported as warnings; nothing prevents them.

The endpoint description states the solver *"prevent[s] community fragmentation (group splits)"*. Setting `allow_group_splits: false` changes nothing about the returned plan. For a relocation tool where splitting a village is a social and political decision, a policy control that silently does nothing is worse than not offering it.

**Remediation.** When `allow_group_splits` is false, the problem stops being a pure min-cost flow (it becomes a generalised assignment problem). Two honest options: (a) switch to `ortools.sat.python.cp_model` with an indicator constraint that each habitation maps to at most one site; or (b) keep min-cost flow and post-process — reassign split habitations to their single best-fitting site and report the resulting unmet demand. Whichever you pick, do not leave the flag accepted-and-ignored.

---

### H13 — `serving_version` never gates what the API serves

**Files:** `api/src/api/routes/health.py:61-67`; absent from every repository

`serving_version` is written by `ingest_flood_data.py` and reported by `/health/ready`. **No data query joins or filters on it.** Neither does anything filter on `pipeline_run.status`.

So the Day 3 "failure-safe staging — invalid data NEVER touches the active serving dataset" guarantee holds only on the write side. On the read side, `/zones`, `/habitations`, `/alerts` and `/scenario` return whatever rows are newest by `valid_at`, regardless of whether that run was promoted, superseded, or marked `FAILED`.

**Remediation.** Add `pipeline_run_id` filtering to the read path: resolve the active `serving_version` once per request (or cache it per process), and constrain each query to rows from that run. Then `PipelineNotReadyError` (already defined at `core/src/core/errors.py:104`, currently never raised) becomes the correct 503 when no version is promoted.

---

## 4. Medium

### M1 — `DEMO_MODE` is not enforced, only logged

Production references: `api/src/api/main.py:36` (log line) and `api/src/api/routes/health.py:28` (echo). Nothing else. `pipeline/hazard/flood/stac.py:19` and the root-level `shrey.py` both hit `planetarycomputer.microsoft.com` unconditionally.

The offline-gate test that supposedly proves the claim (`tests/integration/test_day2_gates.py::test_section_40_offline_mode`) is one of the 47 requiring a database, so it does not run in the state anyone first checks it in.

**Remediation.** A `core/net_guard.py` with `assert_online_allowed(url)` raising when `settings.DEMO_MODE`, called at the top of every function that opens a socket. Then a test that monkeypatches `socket.socket` and asserts nothing connects — it runs without a database and actually proves the claim.

---

### M2 — Four different `data_quality` vocabularies are in play {#m2}

| Source | Values |
|---|---|
| `core/src/core/enums.py:93` `DataQuality` | `valid`, `partial`, `stale`, `fallback`, `missing`, `invalid`, `synthetic` |
| `core/src/core/schemas/habitations.py:81` | bare `str`, default `"observed"` |
| `core/src/core/domain/capacity.py` `CapacityDataQuality` | `complete`, `partial`, `unavailable` |
| `docs/BACKEND_COMPLETE_HANDOFF.md` §Day 7 | `observed`, `nowcast`, `forecast_72h`, `proxy`, `interpolated`, `stale`, `synthetic` |

`infra/migrations/004_habitation_risk.sql:33` defaults the database column to `'observed'`, which is not a member of the enum. The frontend cannot build a single quality badge component against this.

**Remediation.** Pick `core.enums.DataQuality` as the one authority. Type every DTO field as the enum rather than `str`. Migration to rewrite `'observed'` → `'valid'` and change the column default. Fold `CapacityDataQuality` into it. Correct the handoff doc.

---

### M3 — Synthetic demo data is labelled `valid` — "real-world observation meeting all quality controls"

`api/src/api/services/scenario_service.py:236` returns `data_quality=DataQuality.VALID`. `core/src/core/schemas/common.py:30`, `scenario.py:98` and `dynamic_triggers.py:63` all default to `VALID`. The seed writes `'observed'` into `habitation_risk` (`seed_pilot_data.py`).

Only `/zones` is honest (`data_quality="synthetic"`, `zones_service.py:110,171`).

Given that neither the model nor the dataset is trained, this is the finding most likely to embarrass someone in front of the stakeholder, and it is trivially fixable.

**Remediation.** Flip every default to `DataQuality.SYNTHETIC`; derive the real value from `pipeline_run` / `serving_version` provenance once the pipeline writes it. Belt and braces: force `SYNTHETIC` on every response while `DEMO_MODE=true`.

---

### M4 — The Sentinel-1 flood pipeline is unreachable from the packaged app and untested

Two colliding package roots: `pipeline/` (legacy) and `pipeline/src/pipeline/` (packaged). `pyproject.toml` sets `pythonpath = ["core/src","api/src","pipeline/src"]` and hatch packages `src/pipeline`, so the `src` tree shadows the legacy one entirely.

Verified:
```
$ python -c "import sys; sys.path.insert(0,'pipeline/src'); import pipeline.hazard.flood.stac"
ModuleNotFoundError: No module named 'pipeline.hazard.flood'
```

**1,654 lines orphaned**, including all the actual Day 3 SAR raster work:

| File | Lines |
|---|---|
| `pipeline/hazard/flood/frequency_stack.py` | 186 |
| `pipeline/hazard/flood/run_milestone_b.py` | 213 |
| `pipeline/hazard/flood/run_milestone_a.py` | 164 |
| `pipeline/hazard/flood/water_mask.py` | 148 |
| `pipeline/hazard/flood/permanent_water.py` | 144 |
| `pipeline/hazard/flood/stac.py` | 77 |
| `pipeline/hazard/flood/aoi.py` | 70 |
| `pipeline/scripts/extract_rainfall.py` | 642 |

Zero test coverage. `tests/unit/test_sentinel1_adapter.py` exercises `pipeline/src/pipeline/adapters/sentinel1_adapter.py` — a different module doing a different job. There are also four empty legacy packages shadowing real ones: `pipeline/capacity/`, `pipeline/grid/`, `pipeline/exposure/`, `pipeline/ingest/`.

**Remediation.** Move the flood modules to `pipeline/src/pipeline/hazard/flood/`, delete `pipeline/__init__.py` and the four empty packages, and add a smoke test over a small clipped fixture raster so the module cannot silently rot again.

---

### M5 — The processed geospatial data is for the wrong district

| Artifact | AOI |
|---|---|
| `data/interim/frequency/barpeta_*.tif` | Barpeta, Assam |
| `data/raw/INDOFLOODS-gauge-1010.*` | Assam gauge |
| `shrey.py:24` (`barpeta_bbox`) | Barpeta, Assam |
| Everything seeded and served | Wayanad LGD 555, Kodagu LGD 540 |

The inundation-frequency product cannot feed the pilot AOI — they are ~2,500 km apart. The tell is `terrain_zonal.py:66`: `historical_sar_inundation_freq=0.0`, a hardcoded constant, meaning the SAR layer was never joined to the H3 grid. The baseline flood provider weights that feature at 0.3, so 30% of the flood score is currently zeroed.

Two side notes on `shrey.py`: it is a stray script at repo root, outside every package, untested, calling the network with no `DEMO_MODE` guard; and its comment refers to `PC_SDK_SUBSCRIPTION_KEY` while `.env.example` defines `PLANETARY_COMPUTER_SUBSCRIPTION_KEY`, so the key would never be picked up.

**Remediation.** A scoping decision, not a code fix, and it belongs to whoever owns the pilot: either re-run the Sentinel-1 milestone over Wayanad/Kodagu, or move the pilot AOI to Barpeta and reseed. Decide before the ML team invests in calibration. Move `shrey.py` under `pipeline/scripts/` and align the env var name.

---

### M6 — An unauthenticated POST writes to the database, behind a CORS config browsers reject

`api/src/api/services/allocation_service.py:147-154` persists `allocation_run` + `relocation_plan` rows. There is no auth dependency, API key, or rate limit anywhere in `api/src`.

`api/src/api/main.py:54-59` sets `allow_origins=["*"]` together with `allow_credentials=True` — a combination the CORS spec forbids, so browsers reject the response outright. Simultaneously insecure in intent and broken in practice.

**Remediation.** Read `ALLOWED_ORIGINS` from env and set it to the actual frontend origin. Drop `allow_credentials` unless cookies are in use. Put an API-key or JWT dependency on the two POST routes. Add `slowapi` rate limiting before anything is exposed publicly.

---

### M7 — A database outage returns `500 INTERNAL_ERROR`, indistinguishable from a real bug

`api/src/api/middleware.py:53-66` catches bare `Exception` → 500. This is what all 47 failing tests hit: `psycopg.OperationalError` surfaces as an opaque "An internal server error occurred." The `DATABASE_ERROR` code exists in `ErrorCode` and is never used. `/health/ready` correctly returns 503; the data routes should match.

**Remediation.** Catch `sqlalchemy.exc.OperationalError` and `DBAPIError` ahead of the bare handler and map to `503 DATABASE_ERROR`.

---

### M8 — Six duplicate policy knobs in `CapacityNormsConfig` are declared but never read

**File:** `core/src/core/domain/capacity.py:43-57`

| Never read | Actually read by the engine |
|---|---|
| `lpcd_urban` | `lpcd_urban_sewered` |
| `phc_norm_pop_plain` | `phc_pop_plains` |
| `phc_norm_pop_hilly_tribal` | `phc_pop_hilly_tribal` |
| `persons_per_hh` | `hh_size` |
| `students_per_hh` | `children_per_hh` |
| `non_residential_overhead_pct` | `infra_overhead` |

Each pair holds the same number under two names. A policy analyst who sets `persons_per_hh = 5.0` gets silently no change in carrying capacity — the worst kind of configuration bug, because the value is visibly "set".

**Remediation.** Delete the six unread aliases, or make them read-only `@property` aliases of the live field so they cannot diverge.

---

### M9 — `governance.py` is a mirror, not an authority

171 lines, read by exactly two production lines (`scenario_service.py:56,70`). `DEFAULT_POLICY_PARAMS` is imported and never used. `CapacityNormsConfig`, `PriorityScoringConfig` and `TriageRuleConfig` each re-declare the same numbers from `core/constants.py` rather than reading `PolicyParameters`.

`tests/contract/test_day7_data_quality_ml.py:116-121` asserts the dataclasses hold their own constructor defaults — a tautology.

The handoff tells the ML team to calibrate weights in `constants.py` **and** `governance.py` — two places for one number, which is how they drift.

**Remediation.** Make the three engine configs default their fields from the governance singletons, so `governance.py` becomes the single authority it claims to be. Replace the tautological test with one that changes a governance value and asserts the engine output moves.

---

### M10 — `/scenario` silently truncates at 500 habitations

`api/src/api/services/scenario_service.py:72-77` hardcodes `limit=500, offset=0` and ignores `request.offset` for the DB query, paginating in memory afterwards. Above 500 habitations the ranking and every `rank_delta` is computed over an arbitrary subset with nothing in the response saying so; paging past 500 returns empty rather than the next page. The endpoint also has no tier filter, unlike `/habitations`.

**Remediation.** Minimum: compare `total_count` against the cap and append to `outcome.warnings` when truncated — the array already exists and the frontend can surface it. Better: push scenario scoring into SQL, or page the fetch loop.

---

### M11 — Duplicate `FeatureContributionDTO` classes with different fields

Defined twice:
- `core/src/core/schemas/explanation.py:16` — has a `rank: Optional[int]` field
- `core/src/core/schemas/zones.py:14` — does not

`core/src/core/schemas/__init__.py` re-exports the **zones** version, and that is the one that reaches `openapi.json` (verified: the published component has only `feature`, `value`, `contribution`, `method`). The ML team writing SHAP payloads with `rank` will find the field absent from the generated types, and `normalize_feature_contributions` sets a `rank` that never reaches a client.

**Remediation.** Delete the `zones.py` copy; import from `core.schemas.explanation` everywhere.

---

### M12 — Two incompatible explanation payload shapes

| Producer | Shape |
|---|---|
| `terrain_zonal.py` → `explanation.factors` → `/zones/{h3}` | `{feature, value, contribution, method}` |
| `seed_pilot_data.py` → `habitation_risk.contributing_factors` → `/habitations/{id}/risk` | `{name, contribution, type}` |
| `docs/BACKEND_COMPLETE_HANDOFF.md` §4C (told to the ML team) | `{name, contribution, type}` |

`zones_service.py:161` reads `f.get("feature", "unknown")`, so any payload written in the documented shape renders as `"unknown"` on the cell dossier. Meanwhile `HabitationRiskDossier.top_contributing_factors` is typed `List[dict[str, Any]]` — untyped passthrough, so the frontend gets no schema at all.

**Remediation.** One shape — `FeatureContributionDTO` — for both endpoints. Type `top_contributing_factors` as `List[FeatureContributionDTO]`. Update the handoff doc's example to match.

---

### M13 — The allocation path fabricates `suitability = 50` for sites where it is unknown

`api/src/api/services/allocation_service.py:88` and `:205`: `suitability=int(s.get("suitability") or 50)`.

`sites_service.py:140` deliberately does the opposite, with an explicit comment: *"Explicitly preserve None suitability (Audit Requirement 1 & 11)"*. So a site with unverified suitability is shown as "unassigned" in the UI but ranked as a mid-scoring site by the solver. Also note the `or` idiom — a genuine suitability of `0` becomes `50` ([B3](#b3) again).

**Remediation.** Exclude sites with `NULL` suitability from allocation, or treat them as the configured floor with an explicit warning in `group_split_warnings`. Do not silently invent a mid-range score.

---

### M14 — Persistence failure is reported to the client as success

`api/src/api/services/allocation_service.py:146-155` wraps `save_allocation_run` in `try/except Exception` and logs a warning. The API then returns **200** with an `allocation_run_id` that was never written. The client receives an ID it cannot look up, and no error.

Related: `allocation_repo.save_allocation_run` calls `self.db.commit()` inside the repository, while the session from `get_db` never commits — transaction ownership is split across layers.

**Remediation.** Let the exception propagate as a `DATABASE_ERROR`, or return `status: "COMPLETED_NOT_PERSISTED"` with a warning. Move `commit()` to the service or a session dependency.

---

### M15 — `/zones` has a `LIMIT` with no `ORDER BY`, and no pagination

`api/src/api/repositories/zones_repo.py:78` ends `WHERE {where_clause} LIMIT :limit;` with no ordering. Which 1,000 cells you get is planner-dependent and can differ between identical calls — panning the map back and forth may show different hexes.

`/zones` is also the only list endpoint that returns a bare array rather than `PaginatedResponse`, with no `offset` and no total count.

**Remediation.** Add `ORDER BY g.h3` (or by MHI descending, if the intent is "worst first when truncated"). Wrap in `PaginatedResponse` for consistency, or document explicitly that it is a viewport query capped at `limit`.

---

### M16 — `Sentinel1FloodProvider` is a copy of the baseline heuristic and is never used

`core/src/core/ml/sentinel1_flood_provider.py` reproduces `BaselineFloodProvider.predict` verbatim — its own docstring says *"adheres to established repository BaselineFloodProvider computation"* — differing only in `confidence` (0.90 vs 0.80) and metadata strings. It is registered nowhere, and its one distinguishing input (`historical_sar_inundation_freq`) is hardcoded to `0.0` by the only caller of any flood provider ([M5](#m5)).

**Remediation.** Either wire it up with real SAR frequency values from the (relocated) flood pipeline, or delete it and keep one flood provider until the ML team supplies a trained one.

---

### M17 — The livelihood multiplier reported does not match the one applied

`SiteCapacityOverrideRequest.livelihood_multiplier` accepts `ge=0.0`. `CapacityEngine.calculate_final_capacity` clamps to `LIVELIHOOD_MULTIPLIER_RANGE = (0.6, 1.0)`. `sites_service.py:318` then reports the **unclamped** request value in `scenario_capacity.livelihood_multiplier` alongside a `cc_final` computed from the clamped one. A request with `0.0` returns a response claiming multiplier 0.0 and a capacity computed at 0.6.

**Remediation.** Have `calculate_final_capacity` return the effective multiplier and report that; or tighten the request schema to `ge=0.6`.

---

### M18 — `zone_class` conflates permanent classification with transient alert state

`core/src/core/domain/hazard.py:107-125` returns a single `ZoneClass`. Because Active/Forecast are checked before Caution, a cell that is chronically `caution` (MHI_static 0.50) and currently alerting is returned as `active_alert` — its Caution status is lost for the duration.

This works against the platform's own stated thesis: *"strictly separate chronic permanent risk (Permanent Red Zones) from temporary weather emergencies (Active Alert Zones)."* One column cannot represent both.

**Remediation.** Split into two fields on `mhi_snapshot` and in `ZoneCellSummary`: a `static_class` (`permanent_red` / `caution` / `none`) and an `alert_state` (`active` / `forecast` / `none`). The map then styles fill by static class and overlay by alert state, which is what the PRD's legend actually describes.

---

## 5. Low

| ID | Finding | File |
|---|---|---|
| **L1** | `distance_km=0.0` hardcoded in site detail — the UI shows "0.0 km away" on every site. | `sites_service.py:236` |
| **L2** | `tied_constraints=[binding_enum]` is always a single element, and the detail endpoint omits the field entirely. The "tied constraints" concept never fires. | `sites_service.py:135` |
| **L3** | `has_more` computed two ways: `offset + limit < total` (habitations) vs `offset + len(items) < total` (sites). Infinite scroll behaves differently per panel. | `habitations_service.py:143`, `sites_service.py:162` |
| **L4** | LPCD override always rescales from `lpcd_rural`, so an urban site's override is scaled off the wrong baseline. There is also no `is_urban` flag on the request. | `sites_service.py:296` |
| **L5** | `overrides.spare_health_capacity_pop` is passed as the `phc_norm_pop` argument. The field name says "spare capacity", the parameter means "norm population". One of the two is wrong. | `sites_service.py:311` |
| **L6** | A contract test **writes** `openapi.json` into the repo as a side effect — a test run can silently change a committed contract. | `tests/contract/test_openapi.py:34-40` |
| **L7** | Every link in the handoff doc is `file:///d:/the-dead-zone/…`, a Windows path from one machine. Nobody else can open them. | `docs/BACKEND_COMPLETE_HANDOFF.md` |
| **L8** | `README.md` is empty (0 bytes). The handoff says `hazard_dynamic` is unpartitioned; `002_core_schema.sql:110` already creates a DEFAULT partition — the doc is behind the code. | — |
| **L9** | Four error classes defined and never raised: `PipelineNotReadyError`, `AdminBoundaryNotFoundError`, `InvalidTimeError`, `AllocationFailedError`. Consequence: `?admin=99999` returns `[]`, not 404. | `core/src/core/errors.py` |
| **L10** | Inconsistent status codes for the same class of input error: bbox → 400 (`InvalidBboxError`), forecast horizon → 422 (`InvalidParametersError`). | `core/src/core/errors.py:113,155` |
| **L11** | Two migration runners doing the same job with different transaction semantics (`infra/migrate.sh` uses `--single-transaction` per file; `infra/apply_migrations.py` uses `conn.transaction()`). Neither checksums applied migrations, so an edited file is silently skipped. | `infra/` |
| **L12** | `requirements.txt` (570 lines, uv-exported) committed beside `uv.lock` — two lockfiles that can drift. The venv runs Python 3.14.5 while ruff targets `py311`. | root |
| **L13** | `/zones` returns centroids only, though `grid_cell.geom` (the hex polygon) is in the database and `h3_to_wkt_polygon()` exists. Meanwhile `NEXT_PUBLIC_TILE_BASE_URL` points at a Martin service whose `mhi_res6`/`mhi_res7` views do not exist, and whose compose entry passes `${DATABASE_URL}` (usually Neon) rather than the local db. The tile path is half-wired. | `zones_repo.py`, `infra/martin.yaml`, `infra/docker-compose.yml` |
| **L14** | `HazardPrediction.__post_init__` silently clamps out-of-range susceptibility; `MLHazardOutput.__post_init__` raises. Two validation contracts for the same concept — a model returning 1.5 is clamped on one path and rejected on the other. | `ml/types.py:41`, `ml/contracts.py:47` |
| **L15** | `compute_integer_edge_cost` hardcodes `base_offset=10_000` as a default parameter, ignoring `OperationalConfig.solver_base_offset`. Same class as M8/M9 — a governance knob that does not reach the engine. | `domain/allocation.py:140` |
| **L16** | `core/ml/contracts.py` (`MLHazardOutput`, `MLVulnerabilityOutput`) has zero production consumers — referenced only in one contract test. A second ML output vocabulary beside `ml/types.py`. | `core/src/core/ml/contracts.py` |

---

## 6. Verified sound

Areas examined specifically looking for problems, where none were found. This is why most of the fixes above are local rather than structural.

1. **Layering.** `routes → services → repositories → PostgreSQL`, with pure domain logic isolated in `core/domain/`. The API never calls a model or an external service at request time.

2. **OpenAPI is genuinely in sync.** `app.openapi()` regenerated and diffed against the committed `openapi.json`: byte-identical. 14 paths, 37 component schemas.

3. **The test suite is real.** 187 collected, exactly as claimed; the 140 that do not need a database pass. The domain suites carry real assertions with real edge cases. (The vacuous `if total > 0:` guards in five integration tests are the exception — see [B6](#b6).)

4. **Schema and migrations.** Numbered idempotent SQL tracked in `schema_migrations`. Primary-key-enforced 1:1 on `vulnerability` and `habitation_risk`, so the LEFT JOINs cannot fan out and corrupt pagination counts. CHECK constraints on every score range. GiST spatial, BRIN temporal, and partial indexes on the alert thresholds. `mhi_snapshot` PK `(h3, valid_at)` supports the per-cell latest lookup. ORM models match the migrations table for table.

5. **Secrets and data hygiene.** `.env.example` lists variable names with no values. `.gitignore` covers `.env`, `data/*/*`, `models/*`. `git ls-files data` returns three `.gitkeep` files and nothing else — no credentials, no rasters in history.

6. **Input validation on read paths.** Bounding boxes parsed, range-checked, inversion-checked, area-capped at 5 deg². H3 indices format-validated, resolutions allowlisted, limits clamped, NaN/Inf rejected. SQL parameterised everywhere — the only f-string interpolation is of internally-built WHERE/ORDER clauses from fixed allowlists, never user input.

7. **The min-cost flow construction is textbook-correct.** Explicit source/sink node indexing, deterministic sorting for reproducibility, capacity-bounded arcs, a slack source→sink arc with an unmet-demand penalty, integer cost scaling, solver status mapped honestly, and post-solve invariant validation. (Its `allow_group_splits` flag is [H12](#h12); the construction itself is sound.)

8. **Scenario simulation really is stateless.** `simulate_allocation` shares the solver with the persisting path but has no `save_allocation_run` call, and there is a test asserting the baseline is unmutated.

9. **`classify_zone` implements the PRD rules correctly.** PRZ precedence, the three PRZ triggers, the fatal-event-with-MHI-floor rule, and the implied `mhi_static < 0.75` on alert classes all follow from the ordering. (The single-column conflation is a design issue — [M18](#m18) — not a logic error.)

10. **Time-decayed loss.** `compute_time_decayed_loss` implements `L̂ = Σ e^(−λΔt)·severity` with `λ = ln2 / half_life`, clamps future dates, handles both `date` and ISO-string inputs, and skips malformed rows rather than crashing.

11. **`h3_utils` is properly centralised.** One module owns every conversion, accepts both int and hex string, validates before converting, raises a typed `InvalidH3IndexError`, and closes polygon rings. No duplicate H3 logic anywhere else.

12. **Dasymetric population distribution preserves district totals.** `district_grid.dasymetrically_distribute_population` allocates proportional to built area, handles the zero-built-area case by falling back to uniform, and applies an explicit residual correction so the sum matches the input exactly.

Also worth keeping: the deliberate refusal to invent financial figures — `AugmentedCapacityResult.indicative_cost_inr_lakhs` is explicitly `None` with the comment *"Do not invent unverified financial figures"* (`capacity.py:303`). That is the right call. Note that it contradicts the handoff's frontend spec, which promises a *"If water pipeline expanded (+₹18.5L)"* toggle the API can never populate — **the doc is wrong here, not the code.**

---

## 7. Suggested order of work

Grouped by what each batch unblocks rather than by severity.

| # | Unblocks | Findings | Notes |
|---|---|---|---|
| 1 | **Frontend can start** | B4, B5, H1, H2, H3, H11 | Type generation, typed errors, working time slider, live/forecast MHI on the map, a horizon control that filters, no 500 on a valid query. All small, mechanical changes. |
| 2 | **A demonstrable Day 6** | B7, B6 | The trigger→MHI_live job. Closes both, and turns H3/H4/H5 from cosmetic into meaningful. Largest single piece of new code in this list. |
| 3 | **ML model can land** | B1, B2, B3, H8, H9, H10 | Registry actually consulted, risk flags from the database instead of village names, zero-safe fallbacks, honest dependency declarations, a reachable Tier 4, and an MHI that is monotonic under the sliders the UI ships. Do these **before** the model is trained. |
| 4 | **Honest demo to NDRF** | M3, H4, H5, H13 | Stop labelling synthetic data as observed, stop fabricating forecast attribution, stop serving indefinitely stale alerts as live, gate reads on the promoted serving version. Cheap, and the hardest to defend if questioned. |
| 5 | **Correctness under real data** | H6, H7, H12, M10, M13 | Tier filter, eligibility mask, group-split enforcement, scenario truncation, fabricated suitability. Invisible against the seed; wrong the moment a real layer is ingested. |
| 6 | **Deployable beyond localhost** | M6, M7, M14, M1 | CORS, auth on the writing endpoints, 503 vs 500, persistence failures surfaced, real offline enforcement. |
| 7 | **Repo hygiene** | M2, M4, M8, M9, M11, M12, M15, M16, M17, M18, L1–L16 | One data-quality vocabulary, one package root, one explanation shape, no dead knobs, one governance authority. Best done as a single pass while the ML and frontend work is in flight. |
| 8 | **Pilot AOI decision** | M5 | Not a code change. Barpeta rasters versus Wayanad/Kodagu seed — somebody has to choose, and the ML team's calibration depends on the answer. |
