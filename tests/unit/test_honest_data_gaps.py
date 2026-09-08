"""Unit tests asserting honest data gaps (NULLs) are strictly preserved across all layers.

Guarantees that missing MHI, missing lifelines (water, school, health), and unassessed
final capacities NEVER fall back to 0, 50, or arbitrary heuristics.
"""

from __future__ import annotations

import json
from sqlalchemy import create_engine, text

from core.config import settings
from core.domain.capacity import CapacityEngine, CandidateSitePolicy
from core.enums import EligibilityStatus
from core.schemas.sites import CapacityBreakdownDTO, CandidateSiteItem


def test_capacity_engine_preserves_honest_null_when_lifelines_missing():
    """CapacityEngine must return (None, None, []) when lifelines are unmeasured."""
    engine = CapacityEngine()
    cc_final, binding, tied = engine.calculate_final_capacity(
        cc_land=1500,
        cc_water=None,
        cc_school=None,
        cc_health=None,
        livelihood_multiplier=1.0,
    )
    assert cc_final is None
    assert binding is None
    assert tied == []


def test_site_policy_marks_unmeasured_mhi_as_unknown():
    """CandidateSitePolicy must evaluate missing MHI as UNKNOWN (not eligible, not 0)."""
    engine = CapacityEngine()
    policy = CandidateSitePolicy()
    result = engine.evaluate_site_eligibility(
        mhi_static=None,
        slope_mean=1.2,
        area_ha=10.0,
        tenure="government_revenue",
        policy=policy,
    )
    assert result.is_eligible is False
    assert result.eligibility_status == EligibilityStatus.UNKNOWN
    assert any("Multi-hazard index" in r for r in result.rejection_reasons)


def test_dto_json_serialization_preserves_nulls():
    """CapacityBreakdownDTO and CandidateSiteItem must serialize honest NULLs as null in JSON."""
    dto = CapacityBreakdownDTO(
        cc_land=1200,
        land_screening_capacity=1200,
        cc_water=None,
        cc_school=None,
        cc_health=None,
        livelihood_multiplier=1.0,
        cc_final=None,
        binding_constraint=None,
        tied_constraints=[],
        assessment_status="screening_only",
        data_quality="unavailable",
    )
    payload = json.loads(dto.model_dump_json())
    assert payload["cc_final"] is None
    assert payload["binding_constraint"] is None
    assert payload["cc_water"] is None
    assert payload["land_screening_capacity"] == 1200


def test_database_barpeta_sites_have_honest_nulls():
    """Barpeta sites in the database must store NULL for mhi_max, cc_water, cc_final, and binding_constraint."""
    eng = create_engine(settings.get_sqlalchemy_url())
    with eng.connect() as conn:
        row = conn.execute(text("""
            SELECT
                count(*) as total,
                count(mhi_max) as non_null_mhi,
                count(cc_water) as non_null_water,
                count(cc_final) as non_null_final,
                count(binding_constraint) as non_null_binding
            FROM candidate_site
            WHERE import_run_id IS NOT NULL;
        """)).mappings().first()

        assert row is not None
        assert row["total"] == 629
        assert row["non_null_mhi"] == 0, "mhi_max was unexpectedly populated"
        assert row["non_null_water"] == 0, "cc_water was unexpectedly populated"
        assert row["non_null_final"] == 0, "cc_final was unexpectedly populated"
        assert row["non_null_binding"] == 0, "binding_constraint was unexpectedly populated"
