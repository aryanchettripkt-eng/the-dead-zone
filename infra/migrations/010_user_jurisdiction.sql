-- 010_user_jurisdiction.sql
-- Part 3: Jurisdiction-Aware Authorization for SETU-DRR
-- Adds authoritative administrative boundary reference to app_user table.
-- Nullable for civilians (unconstrained exploration); populated for privileged roles.

ALTER TABLE app_user
ADD COLUMN IF NOT EXISTS admin_id BIGINT REFERENCES admin_boundary(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_app_user_admin_id ON app_user(admin_id);

-- Backfill pilot demo users with their authoritative administrative jurisdiction (Wayanad)
UPDATE app_user
SET admin_id = (SELECT id FROM admin_boundary WHERE name = 'Wayanad' LIMIT 1)
WHERE email IN ('officer@setu.gov.in', 'rescue@setu.gov.in')
  AND admin_id IS NULL;
