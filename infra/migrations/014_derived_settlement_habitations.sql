-- 014_derived_settlement_habitations.sql
-- Enables habitations derived from settlement-constrained population rather than an official
-- habitation list, for districts that have a hazard layer but no gazetteer (blocker B1).
--
-- Derived records carry no LGD code, so `source_habitation_id` becomes their stable identity:
-- it encodes the seeding population-peak cell, which is deterministic for a given raster and
-- resolution. A unique index on it makes re-running the derivation an idempotent upsert instead
-- of an append, so a district can be re-segmented without accumulating duplicates.

-- Partial: only rows that actually carry a source key participate, leaving seeded and
-- externally-imported habitations (which identify by lgd_code) untouched.
CREATE UNIQUE INDEX IF NOT EXISTS uq_habitation_source_habitation_id
    ON habitation (source_habitation_id)
    WHERE source_habitation_id IS NOT NULL;

-- Derived settlements are agglomerations of populated cells, not revenue villages; the distinct
-- type keeps them legible as such wherever habitation.type is displayed.
COMMENT ON COLUMN habitation.type IS
    'Settlement class: village | hamlet | ward | derived_settlement (population-derived agglomeration, no official identity).';

COMMENT ON COLUMN habitation.source_habitation_id IS
    'Stable external/derived identity. For derived_settlement rows, encodes district, H3 resolution and seeding peak cell.';
