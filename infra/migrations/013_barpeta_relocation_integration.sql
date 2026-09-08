-- 013_barpeta_relocation_integration.sql
-- Integrates Barpeta offline relocation artifacts into SETU-DRR with strict provenance,
-- honest NULL gaps for unassessed lifelines, and decoupled external recommendations.

-- ====================================================================
-- 1. DATA IMPORT RUN (PROVENANCE & LIFECYCLE)
-- ====================================================================

CREATE TABLE IF NOT EXISTS data_import_run (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_name TEXT NOT NULL,
    district_name TEXT NOT NULL,
    source_pipeline TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    artifact_hashes JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('STAGED', 'VALIDATED', 'PROMOTED', 'SUPERSEDED', 'FAILED')),
    row_counts JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    validated_at TIMESTAMPTZ,
    promoted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_data_import_run_district ON data_import_run (district_name, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_data_import_run_active ON data_import_run (dataset_name, district_name, manifest_hash) WHERE status = 'PROMOTED';

-- ====================================================================
-- 2. CANDIDATE SITE SCHEMA ADJUSTMENTS (HONEST NULL GAPS)
-- ====================================================================

-- Add provenance, administrative, and decoupled status dimensions
ALTER TABLE candidate_site
    ADD COLUMN IF NOT EXISTS source_site_id TEXT,
    ADD COLUMN IF NOT EXISTS admin_id BIGINT REFERENCES admin_boundary(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS import_run_id UUID REFERENCES data_import_run(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS assessment_status TEXT NOT NULL DEFAULT 'screening_only'
        CHECK (assessment_status IN ('fully_assessed', 'partial', 'screening_only')),
    ADD COLUMN IF NOT EXISTS eligibility_status TEXT NOT NULL DEFAULT 'unknown'
        CHECK (eligibility_status IN ('eligible', 'ineligible', 'unknown'));

-- Drop NOT NULL constraints on columns where unmeasured lifelines must be represented honestly
ALTER TABLE candidate_site ALTER COLUMN mhi_max DROP NOT NULL;
ALTER TABLE candidate_site ALTER COLUMN cc_water DROP NOT NULL;
ALTER TABLE candidate_site ALTER COLUMN cc_school DROP NOT NULL;
ALTER TABLE candidate_site ALTER COLUMN cc_health DROP NOT NULL;
ALTER TABLE candidate_site ALTER COLUMN cc_final DROP NOT NULL;
ALTER TABLE candidate_site ALTER COLUMN binding_constraint DROP NOT NULL;
ALTER TABLE candidate_site ALTER COLUMN suitability DROP NOT NULL;

-- Relax CHECK constraints to permit NULL without compromising range integrity when present
ALTER TABLE candidate_site DROP CONSTRAINT IF EXISTS candidate_site_mhi_max_check;
ALTER TABLE candidate_site ADD CONSTRAINT candidate_site_mhi_max_check
    CHECK (mhi_max IS NULL OR (mhi_max >= 0.0 AND mhi_max <= 1.0));

ALTER TABLE candidate_site DROP CONSTRAINT IF EXISTS candidate_site_cc_final_check;
ALTER TABLE candidate_site ADD CONSTRAINT candidate_site_cc_final_check
    CHECK (cc_final IS NULL OR cc_final >= 0);

ALTER TABLE candidate_site DROP CONSTRAINT IF EXISTS candidate_site_suitability_check;
ALTER TABLE candidate_site ADD CONSTRAINT candidate_site_suitability_check
    CHECK (suitability IS NULL OR (suitability >= 0 AND suitability <= 100));

CREATE INDEX IF NOT EXISTS idx_candidate_site_admin_id ON candidate_site (admin_id);
CREATE INDEX IF NOT EXISTS idx_candidate_site_source_site_id ON candidate_site (source_site_id);
CREATE INDEX IF NOT EXISTS idx_candidate_site_import_run ON candidate_site (import_run_id);
CREATE INDEX IF NOT EXISTS idx_candidate_site_assessment_status ON candidate_site (assessment_status);
CREATE INDEX IF NOT EXISTS idx_candidate_site_eligibility_status ON candidate_site (eligibility_status);

-- ====================================================================
-- 3. HABITATION SCHEMA ADJUSTMENTS
-- ====================================================================

ALTER TABLE habitation
    ADD COLUMN IF NOT EXISTS source_habitation_id TEXT,
    ADD COLUMN IF NOT EXISTS import_run_id UUID REFERENCES data_import_run(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS risk_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (risk_status IN ('scored', 'partial', 'pending'));

CREATE INDEX IF NOT EXISTS idx_habitation_source_id ON habitation (source_habitation_id);
CREATE INDEX IF NOT EXISTS idx_habitation_import_run ON habitation (import_run_id);
CREATE INDEX IF NOT EXISTS idx_habitation_risk_status ON habitation (risk_status);

-- ====================================================================
-- 4. EXTERNAL RELOCATION RECOMMENDATION (DECOUPLED EVIDENCE LAYER)
-- ====================================================================

CREATE TABLE IF NOT EXISTS external_relocation_recommendation (
    id BIGSERIAL PRIMARY KEY,
    import_run_id UUID NOT NULL REFERENCES data_import_run(id) ON DELETE RESTRICT,
    habitation_id BIGINT NOT NULL REFERENCES habitation(id) ON DELETE RESTRICT,
    site_id BIGINT NOT NULL REFERENCES candidate_site(id) ON DELETE RESTRICT,
    external_habitation_key TEXT NOT NULL,
    external_site_key TEXT NOT NULL,
    origin_type TEXT NOT NULL DEFAULT 'external' CHECK (origin_type IN ('setu', 'external')),
    decision_status TEXT NOT NULL DEFAULT 'recommendation' CHECK (decision_status IN ('recommendation', 'authoritative')),
    households INT NOT NULL CHECK (households >= 0),
    tier TEXT NOT NULL,
    priority_score REAL NOT NULL DEFAULT 0.0,
    distance_km REAL NOT NULL DEFAULT 0.0,
    site_suitability SMALLINT,
    site_cc_final INT,
    site_binding TEXT,
    has_group_split BOOLEAN NOT NULL DEFAULT FALSE,
    rationale JSONB NOT NULL DEFAULT '{}'::jsonb,
    screening_grade TEXT NOT NULL DEFAULT 'Screening Grade: Cell-level external recommendation',
    screening_caveats TEXT,
    source_pipeline TEXT NOT NULL DEFAULT 'external_gis_v1',
    pipeline_version TEXT NOT NULL DEFAULT 'v1.0',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ext_rec_import_run ON external_relocation_recommendation (import_run_id);
CREATE INDEX IF NOT EXISTS idx_ext_rec_habitation ON external_relocation_recommendation (habitation_id);
CREATE INDEX IF NOT EXISTS idx_ext_rec_site ON external_relocation_recommendation (site_id);
