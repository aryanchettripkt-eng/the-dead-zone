-- 015_derived_candidate_sites.sql
-- Supports candidate relocation sites derived from the habitable-land eligibility mask
-- (relocation plan Steps 12-13) rather than supplied by an external GIS pipeline.
--
-- Derived parcels identify by `source_site_id`, which encodes the district, the mask version and
-- the parcel's rank within that run. A unique index makes re-running the mask an idempotent
-- upsert, so a district can be re-screened at different thresholds without accumulating
-- duplicate parcels. `idx_candidate_site_source_site_id` already exists but is non-unique, so it
-- cannot back an ON CONFLICT target.
CREATE UNIQUE INDEX IF NOT EXISTS uq_candidate_site_source_site_id
    ON candidate_site (source_site_id)
    WHERE source_site_id IS NOT NULL;

COMMENT ON COLUMN candidate_site.source_site_id IS
    'Stable external/derived identity. For mask-derived parcels, encodes district, mask version and parcel rank.';
