-- 007_habitation_risk_deformation_monsoon.sql
-- Add authoritative active_deformation and fatal_event_last_3_monsoons to habitation_risk (P0.2 / B2)

ALTER TABLE habitation_risk
ADD COLUMN IF NOT EXISTS active_deformation BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS fatal_event_last_3_monsoons BOOLEAN NOT NULL DEFAULT FALSE;

-- ====================================================================
-- ONE-TIME LEGACY MIGRATION COMPATIBILITY BACKFILL ONLY:
-- Note: This is strictly for preserving historical state of pre-existing rows.
-- Application runtime MUST NEVER parse triage_rationale text.
-- ====================================================================

-- 1. Backfill active_deformation for legacy pre-migration rows from historical audit text
UPDATE habitation_risk
SET active_deformation = TRUE
WHERE triage_rationale ILIKE '%active deformation (True)%';

-- 2. Backfill fatal_event_last_3_monsoons from authoritative disaster_event spatial-temporal data
-- Within 2.0 km of habitation centroid and occurred within the last three monsoons (since 2024-06-01)
UPDATE habitation_risk hr
SET fatal_event_last_3_monsoons = TRUE
FROM habitation h, disaster_event de
WHERE hr.habitation_id = h.id
  AND de.fatalities > 0
  AND ST_DWithin(de.geom::geography, h.geom_point::geography, 2000.0)
  AND de.ts >= '2024-06-01'::date;
