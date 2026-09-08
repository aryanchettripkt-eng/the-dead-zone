# Barpeta Relocation Data Contract

## 1. Candidate Site Honest Data Gaps
In Barpeta, candidate site screening is based on satellite land cover and slope, but geotechnical multi-hazard indexes (MHI) and infrastructure lifelines (water yield, school seating, healthcare capacity) have not been assessed in the field.

These are represented honestly as `NULL`:
- `mhi_max`: `NULL` (unmeasured; never assumed safe).
- `cc_water`: `NULL` (unmeasured).
- `cc_school`: `NULL` (unmeasured).
- `cc_health`: `NULL` (unmeasured).
- `cc_final`: `NULL` (unmeasured; never equated with `cc_land`).
- `binding_constraint`: `NULL` (unmeasured; never defaulted to `land`).
- `suitability`: 0..100 (composite suitability score where calculated, or `NULL`).
- `tenure`: `'tenure_unverified'`.
- `assessment_status`: `'screening_only'`.
- `eligibility_status`: `'unknown'`.

### Land-Only Screening Capacity
- `cc_land` represents household capacity derived strictly from developable land area:
  $$\text{cc\_land} = \lfloor \frac{\text{area\_developable\_m2}}{\text{plot\_area} \times (1 + \text{infra\_overhead})} \rfloor$$
- In the UI and API, `cc_land` is labeled as **"Land-only screening capacity"**. It is **not** final carrying capacity.

## 2. Habitation Risk Gaps
- `v_index`: `NULL`.
- `risk_status`: `'pending'`.
- Barpeta habitations are not assumed scored until downstream riverine flood hazard aggregation is completed.

## 3. External Relocation Recommendation
- Preserves offline GIS allocation from `relocation_plan_rows.jsonl`.
- `origin_type`: `'external'`.
- `decision_status`: `'recommendation'`.
- `is_authoritative`: `false`.
