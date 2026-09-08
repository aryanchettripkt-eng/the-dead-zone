-- 008_habitation_risk_triage_inputs.sql
-- Add authoritative mitigation_cost, relocation_cost, and adverse_trend to habitation_risk (P0.3 / H9)
-- adverse_trend semantics: NULL = unknown/not evaluated, FALSE = evaluated negative, TRUE = adverse trend confirmed

ALTER TABLE habitation_risk
ADD COLUMN IF NOT EXISTS mitigation_cost REAL,
ADD COLUMN IF NOT EXISTS relocation_cost REAL,
ADD COLUMN IF NOT EXISTS adverse_trend BOOLEAN;

-- Permit unclassified/monitoring state where none of the 4 triage rules match
ALTER TABLE habitation_risk
ALTER COLUMN tier DROP NOT NULL,
ALTER COLUMN tier DROP DEFAULT;

CREATE INDEX IF NOT EXISTS idx_habitation_risk_adverse_trend ON habitation_risk (adverse_trend);
