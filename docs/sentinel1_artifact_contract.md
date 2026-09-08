# Sentinel-1 Flood Inundation Artifact Contract Specification

**Document Version:** 1.0  
**Target Audience:** Upstream SAR / Earth Observation Data Engineering Team & SETU-DRR Backend Engineers  
**Scope:** Specification of the boundary transport artifact consumed by the SETU-DRR decision support backend.

---

## 1. Architectural Boundary & Responsibilities

```text
UPSTREAM SENTINEL-1 TEAM                               SETU-DRR BACKEND
┌──────────────────────────────────────┐               ┌──────────────────────────────────────┐
│ Raw Sentinel-1 GRD/RTC STAC Scenes   │               │ Ingestion Adapter (Parser Strategy)  │
│          ↓                           │               │          ↓                           │
│ SAR Calibration & Filtering          │               │ Validation & H3 Integrity Checking   │
│          ↓                           │               │          ↓                           │
│ Water-Mask Extraction & Time Series  │               │ Canonical Flood Model Normalization  │
│          ↓                           │               │          ↓                           │
│ Generate Transport Artifact (.txt)   │ ────────────> │ PostGIS Storage (hazard_static/dyn)  │
└──────────────────────────────────────┘   Transport   │          ↓                           │
                                           Artifact    │ ML Provider (FloodSurfaceProtocol)   │
                                                       │          ↓                           │
                                                       │ Hazard Engine (MHI Union)            │
                                                       │          ↓                           │
                                                       │ FastAPI Serving Layer                │
                                                       └──────────────────────────────────────┘
```

- **Upstream Team Owns:** GeoTIFF raster processing, SAR calibration, terrain correction, Lee/Gamma speckle filtering, thresholding/water-mask classification, and producing the standardized transport artifact.
- **Backend Owns:** Ingestion boundary, schema validation, H3 spatial verification, dataset versioning, provenance tracking, database persistence, flood provider integration, and serving via FastAPI.
- **Independence:** The upstream team may refactor their internal preprocessing algorithms or change internal column orders without requiring changes to the backend domain engine or API contracts.

---

## 2. Artifact Transport Format Specification (Version 1.0)

The transport artifact is a UTF-8 text file (`.txt`, `.csv`, `.tsv`) with metadata header comments followed by a delimited tabular dataset.

### 2.1 Metadata Header Comments
Lines starting with `# ` at the beginning of the file define dataset-level metadata:

| Header Key | Required | Type | Example / Allowed Values | Description |
|---|---|---|---|---|
| `format_version` | Recommended | String | `1.0` | Schema format version of the artifact. |
| `source` | Recommended | String | `sentinel1_rtc_water_mask` | Identifier of the data source / processing pipeline. |
| `dataset_version` | Required | String | `s1-wayanad-2024-v1` | Unique version tag for provenance. |
| `semantic_type` | Required | String | `static_frequency` \| `dynamic_trigger` | Declares whether values represent static historical frequency or dynamic trigger. |
| `target_resolution`| Recommended | Integer | `8` | Expected H3 resolution level (6–9). Defaults to 8. |
| `generated_at` | Optional | ISO 8601 | `2026-08-31T00:00:00Z` | Timestamp when the artifact was generated. |

### 2.2 Tabular Data Schema

Following the metadata header comments, the first non-comment line must contain the column names. Supported delimiters: comma (`,`), tab (`\t`), pipe (`|`), or semicolon (`;`).

| Field Name | Recognized Aliases | Required | Type | Valid Range | Semantic Meaning |
|---|---|---|---|---|---|
| `h3` | `h3_index`, `h3_hex`, `h3_id` | **Yes** | String (Hex) | 15-char hex, valid H3 at target resolution | Unique Uber H3 hexagonal cell identifier. |
| `inundation_frequency` | `value`, `water_prob`, `sar_freq`, `trigger_value` | **Yes** | Float | $[0.0, 1.0]$ for static; $\ge 0.0$ for dynamic | Empirical flood occurrence rate or trigger observation. |
| `confidence` | `conf`, `quality` | No | Float | $[0.0, 1.0]$ | Quality or confidence score (defaults to 1.0). |
| `observation_count` | `obs_count`, `n_scenes` | No | Integer | $\ge 1$ | Number of SAR scenes aggregated (defaults to 1). |
| `valid_at` | `timestamp`, `obs_time` | Dynamic only | ISO 8601 | UTC timestamp | Observation timestamp (mandatory for `dynamic_trigger`). |
| `flags` | `raw_flags`, `quality_flag` | No | String | — | Optional diagnostic or sensor flags (e.g. `VALID`, `CLOUD_MASKED`). |

---

## 3. Sample Artifacts

### 3.1 Static Inundation Frequency Example (`static_frequency`)
```text
# SETU-DRR Sentinel-1 Flood Inundation Artifact
# format_version: 1.0
# source: sentinel1_rtc_water_mask
# dataset_version: s1-wayanad-2024-v1
# semantic_type: static_frequency
# target_resolution: 8
# generated_at: 2026-08-31T00:00:00Z
h3,inundation_frequency,confidence,observation_count,flags
8860064989fffff,0.42,0.95,24,VALID
886006498bfffff,0.15,0.90,24,VALID
8860064981fffff,0.78,0.98,24,VALID
8860064983fffff,0.02,0.85,24,VALID
```

### 3.2 Dynamic Flood Trigger Example (`dynamic_trigger`)
```text
# SETU-DRR Sentinel-1 Live Flood Trigger Artifact
# format_version: 1.0
# source: sentinel1_rtc_live
# dataset_version: s1-monsoon-2026-live
# semantic_type: dynamic_trigger
# target_resolution: 8
# generated_at: 2026-08-31T06:00:00Z
h3,trigger_value,confidence,valid_at,flags
8860064989fffff,1.25,0.92,2026-08-31T05:30:00Z,ACTIVE_FLOOD
886006498bfffff,0.40,0.88,2026-08-31T05:30:00Z,ELEVATED_MOISTURE
```

---

## 4. Backend Validation & Ingestion Rules

1. **Static vs. Dynamic Separation:**
   - Static frequency data is mapped to $S_{\text{flood}}$ and stored in `hazard_static`.
   - Dynamic trigger data is mapped to $T_{\text{flood}}$ and stored in `hazard_dynamic`.
   - The two quantities are **never merged or conflated**.
2. **Failure-Safe Ingestion:**
   - An invalid or corrupted artifact will fail validation and abort the pipeline run.
   - The active serving dataset (`serving_version`) is **never mutated** until validation succeeds.
3. **Idempotency:**
   - Importing the exact same file (verified by SHA256 checksum) multiple times is idempotent and produces zero duplicate database rows.
4. **Deterministic Offline Support:**
   - In `DEMO_MODE=true`, the backend serves from pre-ingested snapshots with zero live external network calls.
