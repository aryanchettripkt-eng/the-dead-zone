"""Test script to prove complete fresh import lifecycle, idempotency, and rollback isolation (Phase 3 & 4)."""

import uuid
from sqlalchemy import create_engine, text
from core.config import settings
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "pipeline") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "pipeline"))
from scripts.load_barpeta_relocation import BarpetaLoader

def run_fresh_import_test():
    base_url = settings.get_sqlalchemy_url()
    admin_engine = create_engine(base_url)

    schema_name = "disposable_barpeta_test"
    print(f"[*] Setting up isolated schema: {schema_name}...")

    with admin_engine.connect() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE;"))
        conn.execute(text(f"CREATE SCHEMA {schema_name};"))
        conn.commit()

        # Recreate required tables in isolated schema
        for tbl in ["admin_boundary", "data_import_run", "habitation", "candidate_site", "external_relocation_recommendation"]:
            conn.execute(text(f"""
                CREATE TABLE {schema_name}.{tbl} (
                    LIKE public.{tbl} INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES
                );
            """))
        conn.commit()
        print("[*] Isolated tables created cleanly.")

    # Isolated engine that always sets search_path to the disposable schema
    isolated_engine = create_engine(
        base_url,
        connect_args={"options": f"-c search_path={schema_name},public"}
    )

    loader = BarpetaLoader(engine=isolated_engine)

    # -------------------------------------------------------------
    # 1. TEST --check
    # -------------------------------------------------------------
    print("\n[STEP 1] Testing --check...")
    report = loader.check()
    assert report.is_valid, f"Artifact check failed: {report.errors}"
    assert report.habitations_count == 14
    assert report.candidate_sites_count == 629
    assert report.external_recommendations_count == 14
    print("[PASSED] --check verified all artifacts.")

    # -------------------------------------------------------------
    # 2. TEST --dry-run
    # -------------------------------------------------------------
    print("\n[STEP 2] Testing --dry-run...")
    loader.dry_run()

    with isolated_engine.connect() as conn:
        h_cnt = conn.execute(text("SELECT count(*) FROM habitation;")).scalar()
        s_cnt = conn.execute(text("SELECT count(*) FROM candidate_site;")).scalar()
        r_cnt = conn.execute(text("SELECT count(*) FROM external_relocation_recommendation;")).scalar()
        run_cnt = conn.execute(text("SELECT count(*) FROM data_import_run;")).scalar()

        assert h_cnt == 0, f"Dry-run leaked habitations: {h_cnt}"
        assert s_cnt == 0, f"Dry-run leaked candidate sites: {s_cnt}"
        assert r_cnt == 0, f"Dry-run leaked recommendations: {r_cnt}"
        assert run_cnt == 0, f"Dry-run leaked import runs: {run_cnt}"
    print("[PASSED] --dry-run staged and rolled back completely with 0 leaked rows.")

    # -------------------------------------------------------------
    # 3. TEST FIRST --load (STAGED -> VALIDATED -> PROMOTED)
    # -------------------------------------------------------------
    print("\n[STEP 3] Testing first-time --load...")
    run_id_1 = loader.load()
    assert isinstance(run_id_1, uuid.UUID), f"Invalid run_id: {run_id_1}"

    with isolated_engine.connect() as conn:
        run_row = conn.execute(text("SELECT id, status, manifest_hash, promoted_at FROM data_import_run;")).mappings().first()
        assert run_row is not None
        assert run_row["id"] == run_id_1
        assert run_row["status"] == "PROMOTED"
        assert run_row["promoted_at"] is not None

        h_cnt = conn.execute(text("SELECT count(*) FROM habitation;")).scalar()
        s_cnt = conn.execute(text("SELECT count(*) FROM candidate_site;")).scalar()
        r_cnt = conn.execute(text("SELECT count(*) FROM external_relocation_recommendation;")).scalar()
        run_cnt = conn.execute(text("SELECT count(*) FROM data_import_run;")).scalar()

        assert h_cnt == 14, f"Expected 14 habitations, got {h_cnt}"
        assert s_cnt == 629, f"Expected 629 candidate sites, got {s_cnt}"
        assert r_cnt == 14, f"Expected 14 external recommendations, got {r_cnt}"
        assert run_cnt == 1, f"Expected 1 import run, got {run_cnt}"

        # Verify honest NULLs on candidate sites
        null_stats = conn.execute(text("""
            SELECT
                count(*) as total,
                count(CASE WHEN assessment_status = 'screening_only' THEN 1 END) as screening_only,
                count(CASE WHEN eligibility_status = 'unknown' THEN 1 END) as unknown_elig,
                count(mhi_max) as non_null_mhi,
                count(cc_water) as non_null_water,
                count(cc_school) as non_null_school,
                count(cc_health) as non_null_health,
                count(cc_final) as non_null_final,
                count(binding_constraint) as non_null_binding
            FROM candidate_site;
        """)).mappings().first()

        assert null_stats["screening_only"] == 629
        assert null_stats["unknown_elig"] == 629
        assert null_stats["non_null_mhi"] == 0
        assert null_stats["non_null_water"] == 0
        assert null_stats["non_null_school"] == 0
        assert null_stats["non_null_health"] == 0
        assert null_stats["non_null_final"] == 0
        assert null_stats["non_null_binding"] == 0

        # Verify habitations have risk_status = 'pending'
        pending_h = conn.execute(text("SELECT count(*) FROM habitation WHERE risk_status = 'pending';")).scalar()
        assert pending_h == 14

    print("[PASSED] First load successfully created 14 habitations, 629 candidate sites, 14 external recs, and 1 PROMOTED import_run.")

    # -------------------------------------------------------------
    # 4. TEST SECOND --load (IDEMPOTENT NO-OP)
    # -------------------------------------------------------------
    print("\n[STEP 4] Testing second --load (idempotent no-op)...")
    run_id_2 = loader.load()
    assert run_id_2 == run_id_1, f"Expected same run_id {run_id_1}, got {run_id_2}"

    with isolated_engine.connect() as conn:
        h_cnt = conn.execute(text("SELECT count(*) FROM habitation;")).scalar()
        s_cnt = conn.execute(text("SELECT count(*) FROM candidate_site;")).scalar()
        r_cnt = conn.execute(text("SELECT count(*) FROM external_relocation_recommendation;")).scalar()
        run_cnt = conn.execute(text("SELECT count(*) FROM data_import_run;")).scalar()

        assert h_cnt == 14, f"Idempotency violation: habitations became {h_cnt}"
        assert s_cnt == 629, f"Idempotency violation: candidate sites became {s_cnt}"
        assert r_cnt == 14, f"Idempotency violation: recommendations became {r_cnt}"
        assert run_cnt == 1, f"Idempotency violation: import runs became {run_cnt}"
    print("[PASSED] Second --load was a true idempotent no-op. Zero duplication.")

    # -------------------------------------------------------------
    # 5. CLEANUP
    # -------------------------------------------------------------
    print("\n[STEP 5] Cleaning up isolated schema...")
    with admin_engine.connect() as conn:
        conn.execute(text(f"DROP SCHEMA {schema_name} CASCADE;"))
        conn.commit()
    print("[PASSED] Isolated schema cleanly dropped. Real dev database remains 100% untouched.")
    print("\n==================================================================")
    print("FRESH-IMPORT TEST: ALL 5 PHASES PASSED 100%")
    print("==================================================================")

if __name__ == "__main__":
    run_fresh_import_test()
