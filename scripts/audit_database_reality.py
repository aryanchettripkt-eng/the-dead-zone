"""Database reality check script for Phase 2."""

from sqlalchemy import create_engine, text
from core.config import settings

url = settings.get_sqlalchemy_url()
engine = create_engine(url)

with engine.connect() as conn:
    print("--- MIGRATION 013 ---")
    m013 = conn.execute(text("SELECT version, applied_at FROM schema_migrations WHERE version LIKE '%013%';")).fetchall()
    print("Migration 013:", m013)

    print("--- DATA IMPORT RUN ---")
    runs = conn.execute(text("SELECT id, dataset_name, district_name, status, manifest_hash, promoted_at FROM data_import_run WHERE district_name = 'Barpeta';")).fetchall()
    for r in runs:
        print("Import run:", dict(r._mapping))

    print("--- BARPETA COUNTS ---")
    hab_cnt = conn.execute(text("SELECT count(*) FROM habitation h JOIN admin_boundary ab ON h.admin_id = ab.id WHERE ab.name = 'Barpeta';")).scalar()
    print("Habitations:", hab_cnt)
    
    site_cnt = conn.execute(text("SELECT count(*) FROM candidate_site cs JOIN admin_boundary ab ON cs.admin_id = ab.id WHERE ab.name = 'Barpeta';")).scalar()
    print("Candidate sites:", site_cnt)
    
    rec_cnt = conn.execute(text("SELECT count(*) FROM external_relocation_recommendation;")).scalar()
    print("External recommendations:", rec_cnt)
    
    alloc_cnt = conn.execute(text("SELECT count(*) FROM allocation_run;")).scalar()
    print("Canonical allocation_run count:", alloc_cnt)
    
    plan_cnt = conn.execute(text("SELECT count(*) FROM relocation_plan;")).scalar()
    print("Canonical relocation_plan count:", plan_cnt)

    print("--- CANDIDATE SITES HONEST NULLS & STATUS ---")
    site_stats = conn.execute(text("""
        SELECT
            count(*) as total,
            count(CASE WHEN assessment_status = 'screening_only' THEN 1 END) as screening_only_count,
            count(CASE WHEN eligibility_status = 'unknown' THEN 1 END) as unknown_elig_count,
            count(mhi_max) as non_null_mhi,
            count(cc_water) as non_null_water,
            count(cc_school) as non_null_school,
            count(cc_health) as non_null_health,
            count(cc_final) as non_null_final,
            count(binding_constraint) as non_null_binding
        FROM candidate_site cs
        JOIN admin_boundary ab ON cs.admin_id = ab.id
        WHERE ab.name = 'Barpeta';
    """)).mappings().first()
    print("Site stats:", dict(site_stats))

    print("--- HABITATION RISK STATUS ---")
    hab_stats = conn.execute(text("""
        SELECT
            count(*) as total,
            count(CASE WHEN risk_status = 'pending' THEN 1 END) as pending_risk_count,
            count(CASE WHEN risk_status = 'scored' THEN 1 END) as scored_risk_count
        FROM habitation h
        JOIN admin_boundary ab ON h.admin_id = ab.id
        WHERE ab.name = 'Barpeta';
    """)).mappings().first()
    print("Habitation stats:", dict(hab_stats))

    print("--- EXTERNAL RECOMMENDATION COLUMNS ---")
    cols = conn.execute(text("""
        SELECT column_name FROM information_schema.columns WHERE table_name = 'external_relocation_recommendation';
    """)).scalars().all()
    print("Columns in external_relocation_recommendation:", cols)
    has_alloc = any("allocation" in c.lower() or "plan" in c.lower() for c in cols)
    print("Has allocation/plan reference column?:", has_alloc)
