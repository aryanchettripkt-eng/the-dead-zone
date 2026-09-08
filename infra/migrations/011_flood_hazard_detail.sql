-- 011_flood_hazard_detail.sql
-- Coverage provenance + per-hazard driver metrics for the vector map layer (Step 10 / FR-9.3, FR-10.1).
--
-- Rationale: `apply_quality_flags()` fills no-coverage cells with susceptibility = 0.0, which is
-- indistinguishable from a genuine FR-3.17 hard-zero (steep/elevated terrain that is truly safe).
-- Without `quality_flag` on the serving table the client cannot tell "no data" from "safe" and would
-- paint blind cells green. The flag lives in the pipeline's GeoParquet already; this promotes it.

-- ====================================================================
-- 1. COVERAGE PROVENANCE ON THE SERVING TABLE
-- ====================================================================

ALTER TABLE hazard_static
    ADD COLUMN IF NOT EXISTS quality_flag TEXT NOT NULL DEFAULT 'full';

ALTER TABLE hazard_static
    DROP CONSTRAINT IF EXISTS hazard_static_quality_flag_check;

ALTER TABLE hazard_static
    ADD CONSTRAINT hazard_static_quality_flag_check
    CHECK (quality_flag IN ('full', 'low_coverage', 'no_coverage'));

COMMENT ON COLUMN hazard_static.quality_flag IS
    'Zonal coverage class: full (valid_pixel_fraction >= 0.5), low_coverage (> 0), no_coverage (0). '
    'A no_coverage cell has susceptibility 0.0 by fill, NOT by measurement — never render it as safe.';

-- ====================================================================
-- 2. FLOOD DRIVER METRICS (DOSSIER / EXPLAINABILITY)
-- ====================================================================
-- The Step 10 GeoParquet carries 20 columns; hazard_static carries 4. These are the
-- physical drivers the dossier panel needs to explain *why* a cell scores as it does.

CREATE TABLE IF NOT EXISTS hazard_static_flood (
    h3 BIGINT PRIMARY KEY REFERENCES grid_cell(h3) ON DELETE CASCADE,
    max_susceptibility REAL CHECK (max_susceptibility >= 0.0 AND max_susceptibility <= 1.0),
    valid_pixel_fraction REAL CHECK (valid_pixel_fraction >= 0.0 AND valid_pixel_fraction <= 1.0),
    hard_zero_fraction REAL CHECK (hard_zero_fraction >= 0.0 AND hard_zero_fraction <= 1.0),
    mean_inundation_frequency REAL,
    mean_hand_m REAL,
    min_hand_m REAL,
    mean_slope_deg REAL,
    mean_cropland_fraction REAL,
    observation_ceiling SMALLINT NOT NULL DEFAULT 30,
    model_version TEXT NOT NULL DEFAULT 'flood-susceptibility-v0.1',
    pipeline_run_id UUID REFERENCES pipeline_run(id) ON DELETE SET NULL
);

COMMENT ON TABLE hazard_static_flood IS
    'Per-cell riverine flood drivers from pipeline/hazard/flood Step 10 zonal aggregation. '
    'One row per grid_cell; joined by GET /hazard/cells/{h3} for the dossier panel.';

COMMENT ON COLUMN hazard_static_flood.hard_zero_fraction IS
    'Fraction of the cell excluded by FR-3.17 (HAND > 30m OR slope > 15deg). '
    'High value + susceptibility 0.0 means structurally safe, not unobserved.';

COMMENT ON COLUMN hazard_static_flood.observation_ceiling IS
    'Denominator used for confidence = min(1, n_valid / ceiling). Clients must normalise '
    'displayed confidence against the layer maximum, not against 1.0.';

-- ====================================================================
-- 3. VIEWPORT QUERY INDEXES
-- ====================================================================

-- grid_cell geom/res GIST + btree indexes already exist (003_indexes.sql); only the
-- hazard_type-leading index is new, and it is what the viewport query filters on first.

CREATE INDEX IF NOT EXISTS idx_hazard_static_type_susceptibility
ON hazard_static (hazard_type, susceptibility DESC);

CREATE INDEX IF NOT EXISTS idx_hazard_static_type_quality
ON hazard_static (hazard_type, quality_flag);
