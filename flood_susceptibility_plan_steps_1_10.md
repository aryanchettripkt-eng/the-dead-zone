# Flood Susceptibility Pipeline — Wayanad Pilot

## Scope

This plan covers the flood-susceptibility workflow from **Step 1 through Step 10**:

1. Define the pilot area
2. Query Sentinel-1 RTC scenes
3. Obtain Sentinel-1 VV/VH data
4. Generate water masks
5. Remove permanent water
6. Build the multi-date water-mask stack
7. Calculate inundation frequency
8. Calculate HAND
9. Combine inundation frequency + HAND into a flood-susceptibility surface
10. Aggregate the resulting surface to H3 resolution 8

The plan follows the SETU-DRR PRD. In particular, the PRD defines flood susceptibility as **empirical, not modelled**, using a Sentinel-1 SAR water-mask stack, inundation frequency, and HAND. It does not prescribe an exact mathematical weighting for combining inundation frequency and HAND; that combination must therefore be treated as an implementation decision and documented.

---

## 0. Target Outcome

For the Wayanad pilot district, produce a reproducible H3-resolution flood-susceptibility layer:

```text
Sentinel-1 RTC scenes
        ↓
VV / VH backscatter
        ↓
Water masks for each date
        ↓
Permanent-water removal
        ↓
Multi-date water-mask stack
        ↓
Inundation frequency
        +
Copernicus DEM GLO-30
        ↓
HAND
        ↓
Flood susceptibility raster
        ↓
H3 resolution 8
        ↓
hazard_static-ready flood layer
```

The output is a **susceptibility score**, not a flood probability and not a hydrodynamic simulation.

---

# Step 1 — Define the Pilot Area

## Objective

Create the exact spatial boundary used for every downstream operation.

### Inputs

- Wayanad district boundary
- LGD administrative code, where available
- CRS appropriate for raster processing

### Tasks

1. Obtain the authoritative Wayanad district polygon already selected by the PRD.
2. Validate that the polygon is valid and has no unexpected geometry defects.
3. Store the boundary in a canonical local format, preferably GeoPackage.
4. Define a small processing buffer around the district if required for:
   - drainage-network calculation,
   - HAND calculation,
   - Sentinel-1 edge effects,
   - neighbouring terrain contributing to drainage.
5. Keep the **reporting AOI** separate from the **processing AOI**.

### Recommended structure

```text
data/
└── raw/
    └── boundaries/
        └── wayanad.gpkg

data/
└── interim/
    └── aoi/
        ├── wayanad_reporting.gpkg
        └── wayanad_processing.gpkg
```

### Validation

- Plot the boundary on a basemap.
- Confirm it corresponds to Wayanad.
- Confirm the CRS and units.
- Record the area in km².

### Output

```text
wayanad_reporting.gpkg
wayanad_processing.gpkg
```

---

# Step 2 — Query Sentinel-1 RTC Scenes

## Objective

Find suitable Sentinel-1 RTC scenes covering Wayanad over a sufficiently long historical period.

The PRD specifies the **pre-terrain-corrected Sentinel-1 RTC collection via STAC** and identifies Microsoft Planetary Computer as the preferred STAC catalogue, with fallback options if required.

### Tools

Use:

- `pystac-client`
- `planetary-computer`
- STAC API
- `stackstac` / `odc-stac` downstream where useful

### Query requirements

Filter scenes by:

- spatial intersection with Wayanad
- Sentinel-1 mission
- RTC collection
- acquisition date
- available polarization
- suitable observation geometry

Prefer a consistent acquisition configuration where practical.

### Time period

Start with a historical period that captures multiple monsoon seasons.

For the first implementation, do **not** attempt a pan-India or multi-year exhaustive download.

Use Wayanad as the end-to-end pilot.

### Scene inventory

Create a machine-readable inventory:

```text
scene_id
acquisition_time
orbit
relative_orbit
polarization
bbox
cloud_cover_if_available
stac_url
asset_urls
```

Cloud cover is not the primary selection criterion for SAR.

### Selection principle

Prefer:

- complete spatial coverage,
- consistent polarization,
- reasonable temporal distribution,
- multiple monsoon observations,
- scenes with valid RTC assets.

Avoid building the first version around a huge number of scenes. First establish the pipeline with a small test subset, then scale.

### Validation

For a sample of scenes:

1. Open the STAC item.
2. Confirm the VV/VH assets exist.
3. Confirm the assets intersect Wayanad.
4. Confirm acquisition dates are sensible.
5. Visualize one scene before bulk processing.

### Output

```text
data/
└── interim/
    └── sentinel1/
        └── wayanad_scene_inventory.parquet
```

---

# Step 3 — Obtain Sentinel-1 VV/VH Data

## Objective

Read the Sentinel-1 RTC backscatter data required for water detection.

### Preferred workflow

```text
STAC item
   ↓
asset selection
   ↓
COG access/download
   ↓
clip to processing AOI
   ↓
VV / VH raster
```

Use STAC metadata to locate assets rather than hard-coding individual file URLs.

### Data organisation

Keep raw/derived data separate:

```text
data/
├── raw/
│   └── sentinel1/
│       └── <scene_id>/
│
└── interim/
    └── sentinel1/
        └── wayanad/
            ├── <date>_vv.tif
            └── <date>_vh.tif
```

### Preprocessing

For each selected scene:

1. Read VV.
2. Read VH if available and useful.
3. Clip to the processing AOI.
4. Ensure nodata is handled correctly.
5. Confirm spatial alignment.
6. Convert to a consistent numerical representation.
7. Preserve acquisition timestamp and source metadata.

Do not silently mix differently processed Sentinel-1 products.

### Important distinction

RTC is already terrain corrected. The PRD specifically chooses this route to avoid rebuilding the Sentinel-1 GRD → calibration → terrain-correction chain.

### Validation

For several scenes:

- inspect VV histogram,
- inspect VH histogram,
- inspect spatial coverage,
- inspect nodata areas,
- verify raster transform and CRS,
- verify VV and VH align.

### Output

For every usable acquisition:

```text
<date>_vv.tif
<date>_vh.tif
```

plus metadata.

---

# Step 4 — Generate a Water Mask for Each Scene

## Objective

Convert each Sentinel-1 acquisition into a binary estimate of surface water.

Conceptually:

```text
SAR backscatter
      ↓
water-detection rule
      ↓
0 = not water
1 = water
```

## 4.1 Start with a baseline rule

Low SAR backscatter is generally associated with smooth open water.

However, **do not assume one universal threshold is correct for all land cover and terrain**.

Create a configurable water-detection function:

```text
water_mask = detect_water(VV, VH, parameters)
```

The exact threshold/combination should be treated as a calibration parameter.

## 4.2 Use both VV and VH where justified

Test:

- VV-only threshold
- VH-only threshold
- combined VV/VH rule

Do not automatically assume the most complicated rule is best.

Select the simplest rule that produces a credible mask after visual validation.

## 4.3 Handle invalid pixels

Explicitly distinguish:

```text
0 = valid non-water
1 = valid water
nodata = invalid observation
```

Do not turn missing observations into non-water.

## 4.4 Visual validation

Inspect masks over:

- known rivers,
- reservoirs,
- ponds,
- agricultural areas,
- built-up areas,
- vegetated terrain,
- known flood events if available.

The purpose is to identify obvious false positives before generating the historical stack.

### Output

For each Sentinel-1 date:

```text
<date>_water_mask.tif
```

with:

```text
0      valid non-water
1      valid water
nodata invalid
```

---

# Step 5 — Remove Permanent Water

## Objective

Separate persistent water bodies from temporary inundation.

The PRD includes **JRC Global Surface Water** as the permanent-water source.

### Concept

```text
Sentinel-1 water mask
        ↓
       MINUS
        ↓
JRC permanent water
        ↓
potential flood inundation
```

### Procedure

1. Obtain the JRC Global Surface Water permanent-water layer.
2. Reproject/resample it to the Sentinel-1 processing grid.
3. Define a permanent-water mask.
4. For every Sentinel-1 date:

```text
if permanent_water:
    flood_water = 0
else:
    flood_water = sentinel_water
```

5. Preserve nodata separately.

### Why this matters

Without this step:

```text
large reservoir
    ↓
detected as water every month
    ↓
high inundation frequency
    ↓
incorrectly interpreted as flood susceptibility
```

Permanent water should therefore not contribute to the flood-inundation-frequency calculation.

### Validation

Overlay:

- Sentinel-1 water mask
- JRC permanent water
- resulting temporary/potential inundation mask

Inspect several known water bodies.

### Output

```text
<date>_inundation_mask.tif
```

---

# Step 6 — Build the Multi-Date Water-Mask Stack

## Objective

Create a time series from all valid Sentinel-1 observations.

Conceptually:

```text
Date 1 → binary inundation mask
Date 2 → binary inundation mask
Date 3 → binary inundation mask
...
Date N → binary inundation mask
```

Align every raster to exactly the same:

- CRS
- pixel size
- extent
- transform
- row/column dimensions

### Stack representation

For each pixel:

```text
pixel X:
[0, 0, 1, 0, 0, 1, 0, ...]
```

where:

```text
1 = observed water/inundation
0 = valid non-water
```

### Valid-observation mask

Maintain a second logical quantity:

```text
valid_i(x,y)
```

because a missing Sentinel-1 observation must not be counted as a non-flood observation.

### Recommended storage

For a manageable pilot:

```text
inundation_stack.zarr
```

or a cloud-optimized raster representation if the workflow benefits from it.

Also retain the acquisition-date index:

```text
observation_id
timestamp
source_scene_id
```

### Validation

For several pixels/areas, manually inspect the time series:

```text
date        water
-----------------
2019-06-10   0
2019-06-22   0
2019-07-04   1
2019-07-16   1
2019-07-28   0
```

Confirm the stack preserves the correct dates and masks.

---

# Step 7 — Calculate Inundation Frequency

## Objective

Calculate how frequently each pixel was observed as inundated.

Use:

\[
F(x,y)=
\frac{\sum_i W_i(x,y)}
{\sum_i V_i(x,y)}
\]

where:

- \(W_i=1\) if water/inundation is detected
- \(W_i=0\) if valid non-water
- \(V_i=1\) if the pixel is a valid observation
- \(V_i=0\) if it is unavailable/nodata

Thus:

```text
10 water detections
50 valid observations

frequency = 10 / 50
           = 0.20
```

### Important

Do **not** use:

```text
water detections / total number of downloaded scenes
```

if some scenes have invalid observations at that pixel.

### Output range

\[
0 \leq F \leq 1
\]

Interpretation:

```text
0.00 → never observed inundated
0.10 → inundated in ~10% of valid observations
0.50 → inundated in ~50%
1.00 → inundated in every valid observation
```

### Quality information

Also calculate:

```text
observation_count(x,y)
water_count(x,y)
```

This is useful for confidence assessment.

A pixel with:

```text
frequency = 0.5
observations = 4
```

should not be treated with the same confidence as:

```text
frequency = 0.5
observations = 100
```

### Output

```text
inundation_frequency.tif
valid_observation_count.tif
water_detection_count.tif
```

---

# Step 8 — Calculate HAND

## Objective

Generate **Height Above Nearest Drainage (HAND)** from Copernicus DEM GLO-30.

HAND provides terrain context for flood susceptibility:

```text
low HAND
   ↓
closer in elevation to drainage
   ↓
generally more susceptible to riverine inundation
```

The PRD includes Copernicus DEM GLO-30 as the terrain source and explicitly includes HAND in the flood-susceptibility design.

## 8.1 Obtain DEM

Use:

**Copernicus DEM GLO-30**

Clip it to the processing AOI, including sufficient surrounding terrain for drainage calculations.

## 8.2 Prepare the DEM

Perform the terrain preprocessing required by the selected HAND implementation.

The workflow should include, as appropriate:

```text
DEM
 ↓
hydrologically conditioned DEM
 ↓
flow direction
 ↓
flow accumulation
 ↓
drainage network
 ↓
HAND
```

The exact conditioning method must be recorded because different hydrological preprocessing choices can alter drainage extraction.

## 8.3 Extract drainage

Create a drainage network from flow accumulation.

The threshold used to define a drainage cell is an implementation parameter.

Do not hide this parameter.

Record:

```text
flow_accumulation_threshold
DEM version
DEM preprocessing method
HAND algorithm/version
```

## 8.4 Calculate HAND

For each DEM cell:

\[
HAND = Elevation(cell) - Elevation(nearest\ drainage)
\]

Result:

```text
HAND = 2 m
```

means the cell is approximately 2 m above its nearest drainage reference under the chosen drainage definition.

### Output

```text
hand.tif
drainage_network.gpkg
flow_accumulation.tif
```

### Validation

Inspect:

- major rivers,
- valley floors,
- steep slopes,
- hilltops.

Expected pattern:

```text
river/valley floor → low HAND
hill/ridge          → high HAND
```

---

# Step 9 — Combine Inundation Frequency + HAND

## Objective

Create the empirical flood-susceptibility raster.

At this point you have:

```text
A = inundation frequency
B = HAND
```

### 9.1 Normalize HAND

Because low HAND should correspond to higher susceptibility, transform it into a susceptibility-oriented quantity.

For example:

\[
H_{hand}=1-N(HAND)
\]

where \(N(HAND)\) is a normalized HAND value.

The normalization method must be documented.

Possible choices include:

- percentile-based normalization,
- min-max normalization over the AOI,
- a domain threshold-based transformation.

Do not choose based only on whichever produces the prettiest map.

### 9.2 Combine the two signals

The PRD requires:

> Sentinel-1 SAR water-mask stack → inundation frequency + HAND.

It does **not** prescribe a specific formula for their combination.

Therefore define and document an explicit implementation choice.

A simple starting point is:

\[
S_f=w_FF+w_HH_{hand}
\]

with:

\[
w_F+w_H=1
\]

For example, an initial experiment might use equal weights:

\[
S_f=0.5F+0.5H_{hand}
\]

but this should be treated as a **baseline**, not as a PRD-mandated value.

### 9.3 Validate the combination

Use INDOFLOODS as an **independent historical event reference**, not as a per-pixel training label.

Ask:

- Do high-susceptibility areas occur near historically flood-affected catchments?
- Does susceptibility increase toward known river corridors?
- Does the surface incorrectly assign high susceptibility to hills?
- Are permanent water bodies excluded?
- Are results sensible in known flood-prone locations?

### 9.4 Do not call this probability

The output should be named something like:

```text
flood_susceptibility
```

not:

```text
flood_probability
```

unless a separate probabilistic calibration is performed.

### 9.5 Confidence

Maintain supporting quality variables, at minimum:

```text
inundation_frequency
valid_observation_count
HAND
```

These can later contribute to the PRD's per-cell confidence representation.

### Output

```text
flood_susceptibility.tif
```

plus a metadata/configuration file containing:

```text
sentinel1_collection
observation_period
water_detection_method
permanent_water_source
hand_dem
hand_method
hand_parameters
hand_normalization
frequency_formula
combination_formula
weights
software/model version
```

---

# Step 10 — Aggregate to H3 Resolution 8

## Objective

Convert the flood-susceptibility raster into the common H3 grid used by the SETU-DRR platform.

The PRD uses:

- H3 resolution 7 nationally
- H3 resolution 8/9 in pilot districts

Wayanad should therefore initially use **H3 resolution 8**.

## 10.1 Generate H3 cells

Generate all H3 res-8 cells intersecting the Wayanad reporting AOI.

```text
Wayanad polygon
      ↓
H3 polyfill
      ↓
H3 res-8 cells
```

Each cell receives a unique H3 identifier.

## 10.2 Aggregate raster values

For every H3 cell, calculate zonal statistics over the underlying flood-susceptibility raster.

At minimum calculate:

```text
mean_flood_susceptibility
max_flood_susceptibility
mean_inundation_frequency
mean_HAND
valid_pixel_fraction
```

The primary susceptibility value should be selected deliberately.

A reasonable first implementation is:

```text
flood_susceptibility = mean raster susceptibility
```

while retaining maximum susceptibility and supporting statistics for inspection.

## 10.3 Quality control

Reject or flag cells with insufficient raster coverage.

For example:

```text
valid_pixel_fraction < threshold
```

should result in:

```text
low confidence / insufficient coverage
```

rather than silently producing a value.

The exact threshold should be recorded as a pipeline parameter.

## 10.4 Prepare the database record

The resulting H3 records should map naturally to the PRD's `hazard_static` structure:

```text
h3
hazard_type
susceptibility
confidence
model_version
```

For example:

```text
h3              = <H3 index>
hazard_type     = "flash_flood"
susceptibility  = 0.73
confidence      = 0.91
model_version   = "flood-susceptibility-v0.1"
```

The PRD's database schema stores hazard susceptibility and confidence per H3 cell/hazard. 

## 10.5 Final validation

Before inserting into PostgreSQL:

1. Render the H3 layer.
2. Compare it with:
   - Sentinel-1 inundation-frequency raster,
   - HAND,
   - major rivers,
   - JRC permanent water,
   - known historical flood locations/events.
3. Inspect high-score and low-score cells individually.
4. Confirm no permanent-water region dominates the susceptibility layer.
5. Check that values remain in the intended range.
6. Confirm H3 coverage completely covers the pilot AOI.

### Final output

```text
data/
└── processed/
    └── flood/
        └── wayanad/
            ├── flood_susceptibility_h3_res8.parquet
            ├── flood_susceptibility.tif
            ├── inundation_frequency.tif
            ├── hand.tif
            └── metadata.yaml
```

---

# End-to-End Deliverables

At the end of Step 10, you should have:

```text
                 Wayanad boundary
                       │
                       ↓
              Sentinel-1 RTC inventory
                       │
                       ↓
                 VV / VH scenes
                       │
                       ↓
                  Water masks
                       │
                       ↓
             Permanent-water removal
                       │
                       ↓
              Inundation mask stack
                       │
                       ↓
             Inundation frequency
                       │
                       ├──────────────┐
                       │              │
                       ↓              ↓
                    HAND        Observation count
                       │              │
                       └──────┬───────┘
                              ↓
                  Flood susceptibility
                              │
                              ↓
                       H3 resolution 8
                              │
                              ↓
                    hazard_static-ready
```

## Recommended implementation order

Do **not** implement everything at once.

### Milestone A — One scene

Get:

```text
STAC
 ↓
one Sentinel-1 scene
 ↓
VV/VH
 ↓
water mask
```

working.

### Milestone B — Ten scenes

Get:

```text
10 scenes
 ↓
10 masks
 ↓
permanent-water removal
 ↓
stack
 ↓
frequency
```

working.

### Milestone C — HAND

Independently produce:

```text
GLO-30
 ↓
drainage
 ↓
HAND
```

and visually validate it.

### Milestone D — Combined surface

Produce:

```text
frequency + HAND
       ↓
flood susceptibility
```

and validate against known flood locations.

### Milestone E — H3

Finally:

```text
raster
 ↓
H3 res-8 zonal statistics
 ↓
PostgreSQL-ready table
```

Only after this Wayanad pipeline works should you generalise it to Barpeta and the other pilot areas.

---

# Important Decisions That Must Be Documented

Before calling this production-ready, explicitly record:

1. Sentinel-1 RTC collection and STAC catalogue
2. Observation date range
3. Polarization(s)
4. Water-detection rule
5. Water-detection thresholds
6. Permanent-water definition
7. Minimum valid observations
8. HAND drainage extraction threshold
9. HAND normalization method
10. Inundation-frequency aggregation method
11. Frequency/HAND combination formula
12. Combination weights
13. H3 zonal-statistics method
14. Minimum valid raster coverage per H3 cell
15. Confidence calculation
16. Dataset licences and attribution

These parameters should live in configuration rather than being buried inside Python code.

---

# Success Criterion for This Phase

The phase is complete when you can take a fresh Wayanad AOI and run:

```text
STAC → Sentinel-1 → water masks → frequency
                                      ↓
GLO-30 → HAND ────────────────────────┤
                                      ↓
                             susceptibility
                                      ↓
                                H3 res-8
```

and obtain a reproducible map where:

- permanent water is not interpreted as flood susceptibility,
- low-HAND areas generally receive greater terrain-based susceptibility,
- historical inundation is reflected spatially,
- insufficient observations are flagged,
- every H3 cell has a traceable source and processing version,
- and the result can be loaded directly into the PRD's `hazard_static` layer.
