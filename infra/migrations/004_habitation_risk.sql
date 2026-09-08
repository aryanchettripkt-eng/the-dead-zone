-- 004_habitation_risk.sql
-- Day 4: Habitation Risk, Vulnerability Metadata, and Prioritisation Storage

-- 1. Add metadata column to vulnerability table for downscaling validation & source metadata
ALTER TABLE vulnerability ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

-- 2. Create authoritative persisted habitation_risk table
CREATE TABLE IF NOT EXISTS habitation_risk (
    habitation_id BIGINT PRIMARY KEY REFERENCES habitation(id) ON DELETE CASCADE,
    admin_id BIGINT REFERENCES admin_boundary(id) ON DELETE SET NULL,
    population INT NOT NULL DEFAULT 0 CHECK (population >= 0),
    households INT NOT NULL DEFAULT 0 CHECK (households >= 0),
    hazard_intensity REAL NOT NULL DEFAULT 0.0 CHECK (hazard_intensity >= 0.0 AND hazard_intensity <= 1.0),
    prz_overlap_pct REAL NOT NULL DEFAULT 0.0 CHECK (prz_overlap_pct >= 0.0 AND prz_overlap_pct <= 100.0),
    decayed_loss REAL NOT NULL DEFAULT 0.0 CHECK (decayed_loss >= 0.0),
    v_index REAL NOT NULL DEFAULT 0.0 CHECK (v_index >= 0.0 AND v_index <= 1.0),
    priority_score REAL NOT NULL DEFAULT 0.0 CHECK (priority_score >= 0.0),
    caseload_score REAL NOT NULL DEFAULT 0.0 CHECK (caseload_score >= 0.0),
    tier TEXT NOT NULL DEFAULT 'medium_term', -- immediate, short_term, medium_term, mitigate_in_situ
    triage_rationale TEXT NOT NULL DEFAULT '',
    contributing_factors JSONB NOT NULL DEFAULT '[]'::jsonb,
    dominant_hazard TEXT NOT NULL DEFAULT 'landslide',
    model_version TEXT NOT NULL DEFAULT 'baseline-v1',
    scoring_version TEXT NOT NULL DEFAULT 'priority-v1.0',
    dataset_version TEXT NOT NULL DEFAULT 'v1.0',
    data_quality TEXT NOT NULL DEFAULT 'observed',
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    pipeline_run_id UUID REFERENCES pipeline_run(id) ON DELETE SET NULL
);

-- 3. Query optimization and performance indexes
CREATE INDEX IF NOT EXISTS idx_vulnerability_v_index ON vulnerability (v_index DESC);
CREATE INDEX IF NOT EXISTS idx_habitation_population ON habitation (population DESC);
CREATE INDEX IF NOT EXISTS idx_habitation_lgd_code ON habitation (lgd_code);
CREATE INDEX IF NOT EXISTS idx_habitation_risk_admin_id ON habitation_risk (admin_id);
CREATE INDEX IF NOT EXISTS idx_habitation_risk_tier ON habitation_risk (tier);
CREATE INDEX IF NOT EXISTS idx_habitation_risk_priority_score ON habitation_risk (priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_habitation_risk_caseload_score ON habitation_risk (caseload_score DESC);
