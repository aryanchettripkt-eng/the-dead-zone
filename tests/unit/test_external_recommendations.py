"""Unit tests proving external recommendations are strictly decoupled from canonical SETU decisions."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from core.config import settings


def test_external_recommendations_create_zero_canonical_plans():
    """Verifies that external pipeline recommendations never create allocation_run or relocation_plan rows."""
    eng = create_engine(settings.get_sqlalchemy_url())
    with eng.connect() as conn:
        ext_count = conn.execute(text("SELECT count(*) FROM external_relocation_recommendation")).scalar()
        alloc_count = conn.execute(text("SELECT count(*) FROM allocation_run")).scalar()
        plan_count = conn.execute(text("SELECT count(*) FROM relocation_plan")).scalar()

        assert ext_count == 14, f"Expected 14 external recommendations, found {ext_count}"
        assert alloc_count == 0, f"Expected 0 canonical allocation runs, found {alloc_count}"
        assert plan_count == 0, f"Expected 0 canonical relocation plan rows, found {plan_count}"


def test_external_recommendations_properties():
    """Verifies origin_type, decision_status, and referential integrity of external recommendations."""
    eng = create_engine(settings.get_sqlalchemy_url())
    with eng.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                err.origin_type,
                err.decision_status,
                err.external_habitation_key,
                err.external_site_key,
                h.source_habitation_id,
                cs.source_site_id
            FROM external_relocation_recommendation err
            JOIN habitation h ON err.habitation_id = h.id
            JOIN candidate_site cs ON err.site_id = cs.id;
        """)).fetchall()

        assert len(rows) == 14
        for r in rows:
            origin_type, decision_status, ext_hkey, ext_skey, h_source, s_source = r
            assert origin_type == "external"
            assert decision_status == "recommendation"
            assert ext_hkey == h_source
            assert ext_skey == s_source
