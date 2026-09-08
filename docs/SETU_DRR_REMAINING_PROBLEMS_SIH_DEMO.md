# SETU-DRR — Remaining Problems & SIH Demo Readiness Plan

## Purpose

This document consolidates the **remaining verified problems** after the Day 8 remediation work and pairs issues that should be tackled together because they share a root cause, code path, or verification strategy.

**Source of truth:** `DAY8_FIX_VERIFICATION.md`, verified against `origin/main @ 1ab3489`.

The goal is to make the project **safe and convincing for the SIH hackathon demo first**, while preserving the existing P0 invariants and avoiding unnecessary refactoring.

---

## 1. Current verified status

Of the original 20 blocker + high findings:

- **14 fully fixed**
- **3 partially fixed**
- **3 not fixed**

New findings from the verification:

- **N1** — Python 3.11–3.13 import failure
- **N2** — broken Argon2 dummy hash / timing oracle
- **N3** — test-order pollution
- **N4** — duplicate migration number `007`

The most important demo problem is **B6**: the dynamic alert machinery exists, but the seeded demo path never runs it, so the Active Alert and Forecast endpoints remain empty.

---

# 2. Paired implementation batches

## Batch A — Core SIH Demo Alert Path
### Pair: B6 + H3 + H11

**Priority: P0 — MUST FIX**

### Why these belong together

All three affect the **alert experience shown in the demo**:

- **B6**: seeded data produces no active/forecast alerts.
- **H3**: forecast horizon uses exact equality instead of “within horizon”.
- **H11**: alert response schemas reject valid MHI values below `.75`.

Fixing them together lets us verify the complete alert flow rather than fixing the database path while leaving API/query defects behind.

### B6 — Seeded Active/Forecast alerts are empty

Current verified behavior:

- `compute_and_persist_dynamic_snapshots` exists and correctly computes live/forecast MHI.
- The production caller is the flood ingestion job.
- `seed_pilot_data.py` does not create dynamic trigger rows or invoke the dynamic job.
- Seeded `mhi_live` remains equal to static MHI and `mhi_fcst` remains NULL.
- `/alerts/active` and `/alerts/forecast` therefore return empty results.

### Required fix

At the end of `seed_database()`:

1. Create a small deterministic set of synthetic dynamic trigger rows.
2. Run `compute_and_persist_dynamic_snapshots`.
3. Ensure the resulting seeded snapshots contain meaningful `mhi_live` and `mhi_fcst` values.
4. Ensure at least some cells satisfy the active and forecast alert predicates.
5. Keep the permanent relocation classification independent from transient alerts.

Replace the three vacuous alert test guards in `test_day6_alerts_api.py` with real assertions.

### H3 — Forecast horizon

Change forecast filtering from:

```sql
... = :horizon_hours
```

to:

```sql
... <= :horizon_hours
```

The documented meaning is “within the configured horizon”, not “exactly at the requested hour”.

Add/adjust a focused test proving that forecasts at 24h and 48h are included by a 72h query.

### H11 — MHI response bounds

The query accepts `min_mhi >= 0.0`, but response fields require `mhi >= 0.75`.

Relax:

- `ActiveAlertItem.mhi_live`
- `ForecastAlertItem.mhi_fcst`

to allow `0.0–1.0`.

Add a regression test using a value such as `0.60`.

### Batch acceptance criteria

- `/alerts/active` returns non-empty seeded demo data.
- `/alerts/forecast` returns non-empty seeded demo data.
- `horizon=72` includes forecasts at 24h/48h/72h, not only exactly 72h.
- `min_mhi=0.5` does not cause a 500.
- Static relocation tier does not change merely because a transient alert is present.
- Full relevant alert tests pass without vacuous guards.

---

# Batch B — Demo Data Honesty + Alert Freshness
### Pair: M3 + H5

**Priority: P0/P1 — MUST FIX FOR A CREDIBLE DEMO**

### Why these belong together

Both concern the **trustworthiness of information displayed to an officer**.

### M3 — Synthetic data is labelled as observed/valid/complete

Current verified behavior:

Synthetic demo values are still labelled with values such as:

- `valid`
- `observed`
- `complete`

This can make generated demo data look like real observations.

### Required fix

When `DEMO_MODE=true`:

- use `SYNTHETIC` consistently for generated data;
- preserve genuine provenance where real source data is actually used;
- make the UI visibly communicate that demo values are synthetic.

Do not fabricate real-world provenance.

### H5 — No staleness guard

Current verified behavior:

The coherent snapshot fix is present, but there is no actual age/staleness policy.

### Required fix

Add:

- `MAX_TRIGGER_AGE_HOURS`;
- alert `age_hours`;
- `DataQuality.STALE` where appropriate;
- stale handling in active/forecast alert responses.

Do not silently present an old snapshot as current.

### Batch acceptance criteria

- Demo-generated values are clearly marked synthetic.
- No synthetic value is labelled as observed/valid merely because it was successfully generated.
- A deliberately old trigger/snapshot is identified as stale.
- Fresh demo alerts remain available.
- No fabricated source, cycle, timestamp, or model provenance is introduced.

---

# Batch C — Runtime & Verification Reliability
### Pair: N1 + N3

**Priority: P0 — MUST FIX BEFORE DEPLOYMENT/FINAL DEMO**

### Why these belong together

Both are “works on my machine” failures that can undermine the final demo environment or CI.

### N1 — Python compatibility

`api/src/api/dependencies.py` uses `Optional` without importing it and without postponed annotations.

It fails on supported Python 3.11–3.13, while the current machine's Python 3.14 masks the problem.

### Required fix

Add `Optional` to the relevant `typing` import.

Verify the API dependency module imports on the project's supported Python versions, especially the deployment version.

### N3 — Test-order pollution

`tests/unit/test_flood_h3_zonal.py`:

- is an integration/DB test living under `tests/unit`;
- mutates `sys.path` at import time;
- causes a shared FastAPI dependency override to persist;
- makes eight later tests fail when the full suite is run.

### Required fix

1. Move `test_flood_h3_zonal.py` to `tests/integration/`.
2. Remove the obsolete `sys.path` insertion.
3. Ensure DB dependency overrides are function-scoped and always torn down.
4. Run the full unit suite and relevant integration suite in a clean environment.

### Batch acceptance criteria

- API imports on all supported Python versions.
- Unit tests pass independently and in the complete unit suite.
- No shared `app.dependency_overrides` leak remains.
- No test depends on execution order.

---

# Batch D — Relocation Candidate Consistency
### Pair: H7 + existing eligibility policy

**Priority: P1 — IMPORTANT FOR THE RELOCATION DEMO**

### Why this belongs together

The solver is now protected, but the **site list and site generator are not using the same eligibility rule**.

### Current verified behavior

Fixed:

- `allocation_repo.get_candidate_sites_and_distances`
- `allocation_service` pre-solve validation

Still open:

- `sites_repo.query_candidate_sites_for_habitation`
- `pipeline/capacity/site_generator.py`

### Required fix

Use the canonical `evaluate_site_eligibility` policy consistently for:

1. candidate site generation;
2. candidate site listing;
3. allocation.

Do not show a site in the officer-facing candidate list if the solver will reject it.

Persist honest rejection reasons where appropriate.

Avoid duplicating policy constants in SQL; keep thresholds aligned with `CandidateSitePolicy`.

### Batch acceptance criteria

- High-hazard sites are not shown as eligible relocation candidates.
- Excessive-slope sites are not shown as eligible.
- Protected/forest/CRZ/water-ineligible sites are not shown as eligible.
- Distance and area constraints are consistent.
- UI candidate list and allocation solver agree.

---

# Batch E — Authentication Security
### Pair: N2 + login rate limiting

**Priority: P1 — SECURITY HARDENING**

### Why these belong together

Both affect the login attack surface.

### N2 — Broken dummy Argon2 hash

The current dummy hash is invalid, so the unknown-email path returns much faster than the known-email path.

This defeats the intended timing defence and enables reliable account enumeration.

### Required fix

Replace the dummy hash with a real Argon2id hash generated once using the same password hashing configuration.

Add a regression test showing the dummy verification performs actual Argon2 work.

Do not log or expose authentication internals.

### Login rate limiting

There is currently no rate limiting/lockout on `POST /auth/login`.

### Required fix

Add a modest, configurable login rate limit appropriate for the prototype deployment.

Do not weaken the Argon2 configuration merely to compensate for missing rate limiting.

### Batch acceptance criteria

- Unknown and known emails both execute real password-hash verification work.
- Invalid-email timing is no longer trivially distinguishable by the dummy-hash failure.
- Login attempts are rate-limited.
- Successful authentication and existing authorization behavior remain unchanged.

---

# Batch F — Migration / Repository Hygiene
### Pair: N4 + migration runner hardening

**Priority: P2 — CLEANUP**

### N4 — Duplicate `007` migrations

Current files include:

```text
007_flood_hazard_detail.sql
007_habitation_risk_deformation_monsoon.sql
```

They currently both apply because the runner sorts filenames and tracks filenames, but the numbering collision is fragile.

### Existing related issue

The migration runner does not checksum applied migrations.

### Required fix

Prefer:

- renumbering to create a unique sequence, or
- moving to timestamp-prefixed migration names.

Do not rewrite already-applied migrations casually.

If touching the migration runner, consider checksum validation so edited applied migrations are detected.

### Acceptance criteria

- Migration ordering is deterministic and unambiguous.
- Existing database upgrade path remains valid.
- No migration is silently skipped because of filename changes.

---

# 3. Remaining medium findings that can wait

These should **not block the SIH demo** unless they surface during testing:

- M2 — inconsistent `data_quality` vocabularies
- M6 — login/read security hardening beyond the core login fix
- M8/M9 — duplicate/unused capacity policy knobs and governance constants
- M10 — scenario truncation at 500
- M11/M12 — duplicate/incompatible explanation DTOs
- M13 — fabricated suitability fallback
- M14 — allocation persistence failure semantics
- M15 — zones pagination/order
- M16 — Sentinel-1 provider cleanup
- M17 — livelihood multiplier response consistency
- M18 — static `zone_class` vs transient alert state separation
- N4 — duplicate migration numbering

**Exception:** M18 should be revisited if the alert UI currently visually conflates permanent red-zone classification with transient active alerts. The product requirement is that permanent relocation classification and temporary alert state remain separate.

---

# 4. SIH demo acceptance checklist

Before declaring the build demo-ready, manually verify:

### Hazard / map

- [ ] Pilot district loads.
- [ ] Permanent Red Zones appear.
- [ ] Caution zones appear.
- [ ] Active Alert layer contains actual seeded alert hexagons.
- [ ] Forecast Alert layer contains actual seeded forecast hexagons.
- [ ] 24/48/72h forecast filtering behaves as “within horizon”.

### Habitation prioritisation

- [ ] A high-priority habitation can be selected.
- [ ] Hazard, exposure and vulnerability information is visible.
- [ ] Tier is explainable.
- [ ] Temporary alert state does not silently change permanent relocation tier.
- [ ] No village name is used to determine risk/tier.

### Relocation

- [ ] Candidate sites are shown.
- [ ] Ineligible sites are not presented as eligible.
- [ ] Capacity is shown.
- [ ] Binding constraint is shown.
- [ ] Allocation can be run.
- [ ] Group splits are handled according to the configured policy.
- [ ] No fabricated cost/suitability values appear.

### Trust / provenance

- [ ] Synthetic demo data is clearly labelled.
- [ ] Real source names are not fabricated.
- [ ] Forecast cycle/timestamps do not change merely because the endpoint was read.
- [ ] Stale data is identified.

### Reliability

- [ ] Full test suite passes in a clean environment.
- [ ] Tests pass regardless of order.
- [ ] API starts on the actual deployment Python version.
- [ ] `uv sync` succeeds.
- [ ] OpenAPI and generated frontend types are synchronized.

---

# 5. Recommended implementation order

If time is limited, execute in this order:

1. **Batch A — B6 + H3 + H11**
2. **Batch C — N1 + N3**
3. **Batch B — M3 + H5**
4. **Batch D — H7**
5. **Batch E — N2 + login rate limiting**
6. **Batch F — N4**

The first four batches are the most important for the SIH demo.

---

# 6. Definition of done for every batch

For each implementation batch:

1. Investigate the existing code path first.
2. Make the smallest correct change.
3. Preserve all existing P0 invariants.
4. Do not fabricate data, provenance, costs, or uncertainty.
5. Add focused regression tests for the actual failure.
6. Run the relevant existing tests.
7. Run the full suite when the change can affect shared state or contracts.
8. Report:
   - files changed;
   - tests added/changed;
   - test results;
   - pre-existing failures;
   - git diff summary;
   - git status;
   - remaining concerns.

Do not combine unrelated refactors into these batches.

---

## Final target

The SIH-ready prototype should tell a coherent story:

**Hazard → Alert → Priority Habitation → Explain Why → Find Safe Relocation Sites → Check Capacity → Allocate**

The demo should visibly work end-to-end while clearly distinguishing **synthetic demonstration data** from real observations.
