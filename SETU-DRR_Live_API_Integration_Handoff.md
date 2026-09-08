# SETU-DRR Live API Integration Handoff
## Phase B — Wayanad Rainfall / Flash Flood Forecast Integration

**Status:** Phase B1 approved and completed  
**Target:** Wayanad District, Kerala · LGD 555  
**Hazard:** Flash flood  
**Forecast source:** Open-Meteo ECMWF IFS HRES  
**Decision output:** Forecast Alert Zone (FAZ) only  
**Prototype mode:** Manual, reproducible execution; no scheduler yet

---

## 1. Purpose

This handoff captures the agreed architecture, constraints, decisions, and implementation boundaries for integrating live Open-Meteo forecast precipitation into SETU-DRR.

The integration must reuse the existing SETU-DRR spatial grid, hazard engine, database schema, and alert API.

The intended flow is:

```text
Open-Meteo ECMWF forecast
        ↓
raw provider response
        ↓
source_snapshot + raw artifact
        ↓
12 prototype spatial samples
        ↓
existing Wayanad H3-8 decision grid (3,602 cells)
        ↓
rainfall validation
        ↓
prototype heuristic T_flood
        ↓
hazard_dynamic
        ↓
existing dynamic hazard engine
        ↓
mhi_snapshot.mhi_fcst
        ↓
existing GET /alerts/forecast
```

---

## 2. Scope

### In scope

- One district: Wayanad, Kerala
- LGD code: `555`
- Admin ID: `178`
- H3 resolution: `8`
- Existing operational decision cells: `3,602`
- Flash flood only
- Forecast precipitation only
- FAZ only
- Open-Meteo ECMWF IFS HRES
- 72-hour forecast evaluation
- Raw-response provenance
- Manual/reproducible prototype execution

### Explicitly out of scope

- Permanent Red Zone (PRZ) changes
- Active Alert Zone (AAZ) logic
- Landslide forecast integration
- New rainfall database tables
- Database migrations
- Changes to core hazard mathematics
- Changes to `hazard_dynamic` schema
- Changes to `/alerts/forecast`
- APScheduler/cron automation
- Production-grade empirical rainfall calibration
- National-scale deployment

---

# 3. Existing Architecture to Reuse

Do not create parallel implementations of existing functionality.

### Existing components

- `grid_cell` — existing H3 decision grid
- `core/src/core/h3_utils.py`
- `pipeline/src/pipeline/grid/district_grid.py`
- Existing H3 conversion/storage machinery
- Existing flash-flood `hazard_static`
- Existing `hazard_dynamic`
- Existing `compute_dynamic_hazard.py`
- Existing `mhi_snapshot`
- Existing `/alerts/forecast`
- Existing `source_snapshot`
- Existing `pipeline_run`
- Existing provenance conventions

### Important spatial fact

H3-8 is the **decision geometry**, not the rainfall observation resolution.

The ECMWF IFS HRES source is approximately 9 km native resolution. Do not imply that the 3,602 H3-8 cells represent independently observed 460 m rainfall.

---

# 4. Open-Meteo Source

## Endpoint

Use the dedicated ECMWF endpoint:

```text
https://api.open-meteo.com/v1/ecmwf
```

Do not substitute the generic `/v1/forecast` endpoint while claiming ECMWF IFS HRES provenance.

The intended model is:

```text
ECMWF IFS HRES
~9 km native resolution
```

## Forecast request

The prototype requests hourly precipitation in UTC for enough data to guarantee at least 72 future hourly values.

Example conceptual request:

```text
/v1/ecmwf
  ?latitude=<12 comma-separated latitudes>
  &longitude=<12 comma-separated longitudes>
  &hourly=precipitation
  &timezone=UTC
  &forecast_days=3
```

The implementation must validate the actual returned range rather than assuming the provider response contains exactly 72 entries.

---

# 5. Spatial Strategy

## Approved prototype method

Use **12 deterministic spatial sampling points** distributed across Wayanad.

These are prototype sampling points at approximately model scale. They are not a custom meteorological grid.

The current validated points are:

```text
(11.5364, 75.8500)
(11.5364, 76.2500)
(11.5727, 76.1500)
(11.6091, 76.0500)
(11.6455, 75.9500)
(11.6818, 75.8500)
(11.6818, 76.2500)
(11.7182, 76.1500)
(11.7545, 76.0500)
(11.7909, 75.9500)
(11.8273, 75.8500)
(11.8273, 76.2500)
```

All 12 points were verified against the actual Wayanad administrative polygon.

## Mapping to H3

For every one of the existing 3,602 H3-8 Wayanad cells:

1. Read the existing cell centroid.
2. Find the nearest of the 12 sample points.
3. Assign that sample's hourly precipitation series to the cell.

The method must be explicitly recorded as:

```text
nearest_sample
```

or:

```text
nearest_sample_prototype
```

This is a prototype downscaling method, not fine-scale meteorological interpolation.

Use a geodesic-aware or appropriately projected distance calculation rather than assuming raw latitude/longitude degrees are equal-distance units.

---

# 6. Temporal / Forecast Cycle Semantics

## Critical rule

`forecast_cycle_at` must **not** be represented as a verified ECMWF model initialization timestamp unless the Open-Meteo response directly establishes that fact.

For the current normal ECMWF endpoint integration, the agreed semantics are:

```text
forecast_cycle_semantics = "derived_provider_run_anchor"
cycle_anchor_verified = false
```

The provider-run anchor may be derived for prototype horizon filtering, but it must not be described elsewhere as authoritative model initialization metadata.

## Current B1 observation

The B1 run retrieved data at:

```text
2026-09-08T13:48:15.831174Z
```

and used:

```text
2026-09-08T12:00:00Z
```

as the derived provider-run anchor.

The response contained:

```text
96 hourly values
83 values strictly after the anchor
```

so at least 72 future hourly values were available.

## Future improvement

For stronger production provenance, investigate the Open-Meteo Single Runs API, which allows an explicit model run to be requested. This is a future improvement and is not required to invalidate the current B1 prototype.

---

# 7. Rainfall Semantics

Open-Meteo `hourly.precipitation` must be treated according to the provider's documented temporal semantics.

Before trigger generation, B3 must explicitly verify that the implementation interprets the hourly value as the appropriate hourly precipitation accumulation.

Do not treat precipitation as an instantaneous rate.

The prototype trigger expects hourly precipitation amounts in millimetres:

```text
P(t) [mm]
```

---

# 8. Prototype Trigger Mathematics

The trigger conversion is intentionally isolated from the existing core hazard mathematics.

Do **not** modify:

```text
core/src/core/ml/registry.py
```

and do not modify the existing hazard scoring implementation.

## Trigger contract

For each H3 cell and forecast timestamp:

### Rolling accumulation

```text
A3(t) = P(t) + P(t-1) + P(t-2)
```

Units:

```text
mm / 3 hours
```

### Three-hour intensity

```text
I3(t) = A3(t) / 3.0
```

Units:

```text
mm/h
```

### Prototype thresholds

```text
I0 = 10.0 mm/h
Ic = 29.0 mm/h
Tmax = 3.0
```

### Piecewise trigger

```text
if I3 < 10.0:
    T_flood = 0.0

elif 10.0 <= I3 < 29.0:
    T_flood = ((I3 - 10.0) / 19.0) * 0.60

else:
    T_flood = 0.60 + ((I3 - 29.0) / 29.0) * 1.0

T_flood = min(T_flood, 3.0)
```

## Scientific status

This is:

```text
Prototype Heuristic Calibration
```

It is **not** an empirically calibrated Wayanad rainfall-event model.

The heuristic must not be presented to users as validated disaster-prediction science.

Empirical calibration using historical rainfall/event data is a post-prototype task.

---

# 9. Existing Hazard Mathematics

Do not alter the existing formula:

```text
H = clamp(S * (1 + beta * T), 0, 1)
```

with the existing beta behavior.

The existing hard invariant must remain intact:

```text
S = 0  =>  H = 0
```

The existing MHI calculation and alert thresholds remain unchanged.

The Open-Meteo integration supplies a dynamic trigger; it does not redefine hazard science.

---

# 10. Existing `hazard_dynamic` Contract

The existing schema is reused without modification.

Important fields:

```text
h3
hazard_type
valid_at
forecast_cycle_at
trigger_value
source
pipeline_run_id
```

For forecast records:

```text
forecast_cycle_at IS NOT NULL
valid_at > forecast_cycle_at
```

The raw precipitation amount must **never** be inserted directly into:

```text
hazard_dynamic.trigger_value
```

`trigger_value` receives the dimensionless:

```text
T_flood
```

value.

---

# 11. Provenance

B1 successfully registered the raw artifact using the existing `source_snapshot` mechanism.

Example:

```text
source_id:
open_meteo_ecmwf
```

Metadata should preserve at least:

```json
{
  "provider": "Open-Meteo",
  "provider_endpoint": "https://api.open-meteo.com/v1/ecmwf",
  "source_model": "ECMWF_IFS_HRES",
  "native_resolution_km": 9.0,
  "district": "Wayanad",
  "lgd_code": 555,
  "sample_points_count": 12,
  "forecast_cycle_semantics": "derived_provider_run_anchor",
  "cycle_anchor_verified": false
}
```

The raw response must be retained before parsing.

Record:

- raw file URI
- SHA256
- byte size
- retrieval timestamp
- provider metadata
- forecast-cycle semantics
- pipeline provenance

Never place credentials/API keys into raw artifacts, manifests, source code, or demo snapshots.

---

# 12. Phase Boundaries

## B1 — Completed

```text
Open-Meteo
→ validate response
→ save raw JSON
→ source_snapshot
→ STOP
```

B1 completed successfully.

It did not:

- calculate triggers
- write `hazard_dynamic`
- mutate `mhi_snapshot`
- modify schemas
- modify hazard math
- modify alert APIs

## B2 — Spatial Mapping

Create/use:

```text
pipeline/src/pipeline/ingestion/open_meteo_regrid.py
```

Responsibilities:

- load the 3,602 existing H3-8 cells
- map each to one of the 12 sample points
- retain mapping/provenance in memory
- verify 3,602/3,602 cells assigned

Do not introduce a second spatial database/grid.

## B3 — Rainfall Validation

Before trigger generation:

- inspect representative lead times
- verify non-negative finite precipitation
- verify timestamp uniqueness
- verify temporal ordering
- verify sufficient future coverage
- verify precipitation temporal semantics
- verify spatial mapping completeness

No hazard writes.

## B4 — Trigger Contract Freeze

Review the exact prototype formula.

No implementation should silently alter thresholds, window length, ramp behavior, or cap.

## B5 — Canonical Trigger Generation

Create/use:

```text
pipeline/src/pipeline/ingestion/open_meteo_trigger.py
```

Responsibilities:

- compute rolling 3-hour precipitation
- compute `I3`
- compute `T_flood`
- produce validated canonical forecast trigger records

Do not modify core hazard code.

## B6 — Hazard Evaluation

Create/use:

```text
pipeline/src/pipeline/jobs/run_open_meteo_wayanad.py
```

Responsibilities:

1. create pipeline provenance
2. bulk insert forecast trigger records
3. invoke existing dynamic hazard engine once for the forecast sequence
4. verify `mhi_snapshot.mhi_fcst`

Do not invoke the dynamic engine 72 separate times.

Before relying on the existing `valid_at=None` behavior, confirm that its timestamp query is correctly scoped for this run/AOI and cannot accidentally process unrelated forecast data.

## B7 — API Verification

Verify:

```text
GET /alerts/forecast?admin=555&horizon=72
```

Confirm:

- correct forecast records
- correct lead times
- correct H3 cells
- correct MHI values
- expected hazard provenance
- no accidental PRZ/AAZ changes

Frontend verification should confirm that the existing forecast layer/time-slider consumes the API without requiring a new external API call.

## B8 — Automation

Deferred.

Do not add APScheduler/cron in this prototype phase.

---

# 13. Safety / Failure Rules

The integration must fail explicitly rather than silently produce bad hazard data.

If any prerequisite is missing, the implementation agent must:

1. stop;
2. report exactly what is missing;
3. explain why it is required;
4. wait for the necessary input/access/configuration.

The agent must not:

- invent credentials
- invent database records
- invent provider metadata
- invent model-cycle timestamps
- create migrations
- create parallel H3 infrastructure
- silently substitute another rainfall source
- silently change the trigger formula
- write raw rainfall directly as `trigger_value`
- bypass provenance
- modify unrelated existing code to make the integration appear successful

If Open-Meteo is unavailable, the prototype should fail clearly unless an explicitly approved fallback is introduced later.

---

# 14. Current B1 Artifact

The completed B1 run produced:

```text
data/raw/open_meteo/ecmwf_wayanad_20260908T120000Z.json
```

Reported:

```text
size:
30,921 bytes

sha256:
7eaef14c0001ebc0b1b97257de2054e0ccd4833d6be26af9267c2951ad367039

source_id:
open_meteo_ecmwf
```

The corresponding `source_snapshot` record was successfully registered.

---

# 15. Acceptance Criteria for the Live Integration

The prototype is complete only when all of the following are true:

- [ ] Open-Meteo ECMWF endpoint is used.
- [ ] 12 deterministic Wayanad sample points are validated inside the district polygon.
- [ ] At least 72 future hourly precipitation values are available.
- [ ] Raw response is persisted before parsing.
- [ ] `source_snapshot` provenance is complete.
- [ ] 3,602 H3-8 cells receive deterministic sample assignments.
- [ ] No false claim is made that H3-8 is rainfall observation resolution.
- [ ] Rainfall temporal semantics are correctly interpreted.
- [ ] Prototype trigger formula is frozen and documented.
- [ ] `T_flood`, not raw rainfall, enters `hazard_dynamic.trigger_value`.
- [ ] Existing hazard mathematics remains unchanged.
- [ ] Existing dynamic hazard engine remains unchanged.
- [ ] `mhi_snapshot.mhi_fcst` is populated for the forecast sequence.
- [ ] `/alerts/forecast` returns the resulting FAZ records.
- [ ] No PRZ or AAZ logic is affected.
- [ ] No database schema changes occur.
- [ ] No live external API calls are required by the demo/replay mode.
- [ ] Failures are explicit and provenance is preserved.

---

# 16. Recommended Next Action

**Proceed with B2 only.**

B2 should be treated as a validation/mapping phase, not as an opportunity to redesign the spatial architecture.

After B2, review the resulting 3,602-cell mapping and B3 rainfall diagnostics before allowing any trigger calculation.

The core principle for the remainder of Phase B is:

> **Reuse the existing SETU-DRR architecture wherever possible. Keep Open-Meteo-specific logic isolated at the ingestion boundary. Never allow provider-specific assumptions to leak into the core hazard engine.**
