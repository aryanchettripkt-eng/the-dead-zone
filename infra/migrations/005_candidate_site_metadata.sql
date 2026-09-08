-- 005_candidate_site_metadata.sql
-- Add metadata column to candidate_site for policy audit and data quality provenance

ALTER TABLE candidate_site
ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
