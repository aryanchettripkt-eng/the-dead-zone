"""End-to-end check that the allocation solver actually places households against seeded data.

Guards the failure mode where every candidate site is silently filtered out before the solver
runs, which surfaces as a COMPLETED allocation with zero assignments rather than as an error.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from api.repositories.allocation_repo import AllocationRepository
from api.services.allocation_service import AllocationService
from core.domain.capacity import CandidateSitePolicy
from core.enums import Tier
from core.schemas.allocation import AllocationPlanRequest

@pytest.fixture
def service(db_session):
    return AllocationService(db_session)


@pytest.fixture
def wayanad_admin_id(db_session):
    """Resolves the seeded district id rather than assuming one — ids differ per database."""
    admin_id = db_session.execute(
        text("SELECT id FROM admin_boundary WHERE name = 'Wayanad' AND level = 'district' LIMIT 1")
    ).scalar()
    if admin_id is None:
        pytest.skip("Wayanad pilot district not seeded in this database")
    return int(admin_id)


def test_eligible_sites_survive_the_h7_filter(db_session, wayanad_admin_id):
    """The filter must not reject every site; that is what produced an empty allocation."""
    repo = AllocationRepository(db_session)
    habs = repo.get_habitations_for_allocation(
        admin_id=wayanad_admin_id, target_tiers=[Tier.IMMEDIATE.value]
    )
    assert habs, "Seed data should provide immediate-tier habitations for Wayanad"

    raw_sites, raw_distances = repo.get_candidate_sites_and_distances(
        habitation_ids=[h["id"] for h in habs],
        max_radius_m=15_000.0,
        policy=CandidateSitePolicy(),
    )
    assert raw_sites, "Seed data should provide candidate sites within 15 km"

    service = AllocationService(db_session)
    sites, distances = service._filter_eligible_candidates(
        site_rows=raw_sites, distance_rows=raw_distances, max_search_radius_km=15.0
    )
    assert sites, "H7 filter rejected every candidate site — exclusion flags are missing from the row"
    assert distances, "Eligible sites must retain their habitation distance pairs"


def test_allocation_places_households(service, wayanad_admin_id):
    """A solvable district must relocate a positive number of households."""
    result = service.generate_allocation_plan(
        AllocationPlanRequest(
            admin_id=wayanad_admin_id,
            max_search_radius_km=15.0,
            target_tiers=[Tier.IMMEDIATE],
            allow_group_splits=True,
            distance_penalty_weight=1.0,
        )
    )

    assert result.status == "COMPLETED"
    assert result.total_demand_households > 0
    assert result.total_relocated_households > 0, (
        "Solver placed nobody despite eligible sites being available"
    )
    assert result.assignments, "A non-zero relocation count must be itemised in assignments"

    placed = sum(a.households for a in result.assignments)
    assert placed == result.total_relocated_households
    assert (
        result.total_relocated_households + result.unmet_demand_households
        == result.total_demand_households
    ), "Demand conservation invariant violated"


def test_assignments_respect_search_radius(service, wayanad_admin_id):
    """No assignment may exceed the requested radius."""
    result = service.generate_allocation_plan(
        AllocationPlanRequest(
            admin_id=wayanad_admin_id,
            max_search_radius_km=10.0,
            target_tiers=[Tier.IMMEDIATE],
            allow_group_splits=True,
            distance_penalty_weight=1.0,
        )
    )
    for a in result.assignments:
        assert a.site_distance_km <= 10.0, f"Site {a.site_id} at {a.site_distance_km} km exceeds radius"
