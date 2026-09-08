-- 012_consolidate_rescue_officer_role.sql
-- Consolidate RESCUE_OFFICER into GOVERNMENT_OFFICIAL and update CHECK constraint.

-- 1. Migrate any existing users with RESCUE_OFFICER role to GOVERNMENT_OFFICIAL
UPDATE app_user
SET role = 'GOVERNMENT_OFFICIAL', updated_at = now()
WHERE role = 'RESCUE_OFFICER';

-- 2. Update CHECK constraint on app_user.role to canonical roles
ALTER TABLE app_user
    DROP CONSTRAINT IF EXISTS app_user_role_check;

ALTER TABLE app_user
    ADD CONSTRAINT app_user_role_check
    CHECK (role IN ('CIVILIAN', 'GOVERNMENT_OFFICIAL', 'SYSTEM_ADMIN'));
