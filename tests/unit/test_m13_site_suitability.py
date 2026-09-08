"""Unit and Regression Tests for M13: Stop fabricating / overstating relocation-site suitability.

Verifies:
- Test M13-A: Missing suitability evidence: When candidate site suitability is None,
  AllocationAssignmentDTO outputs site_suitability=None (not a fabricated positive value like 50).
- Test M13-B: Verified positive evidence: Sites with verified suitability (e.g. 90) retain their score
  and benefit in the solver.
- Test M13-C: Hard exclusion constraints remain strictly enforced regardless of suitability.
- Test M13-D: Previously problematic path: repo providing None suitability never substitutes 50.
- Test M13-E: JSON serialization of AllocationAssignmentDTO preserves null for unverified suitability.
- Test M13-F: Explicit zero preservation: suitability=0 is preserved as 0, not None or 50.
- Test M13-G: Solver comparison: Verified high suitability is preferred over unverified (None) suitability.
- Test M13-H: Both allow_group_splits=True and allow_group_splits=False correctly handle None suitability.
"""

from unittest.mock import MagicMock
import json
import pytest

from api.services.allocation_service import AllocationService
from core.domain.allocation import (
    AllocationConfig,
    CandidateSiteCapacity,
    HabitationDemand,
    HabitationSiteDistance,
    MinCostFlowAllocationSolver,
    compute_assignment_benefit,
)
from core.enums import Tier
from core.schemas.allocation import (
    AllocationAssignmentDTO,
    AllocationPlanRequest,
    AllocationPlanResponse,
)


class TestM13CandidateSiteSuitability:
    """Test suite ensuring honest, non-fabricated representation of candidate-site suitability."""

    def test_m13_a_missing_suitability_evidence_returns_none(self):
        """Test M13-A: Missing suitability evidence results in site_suitability=None, not fabricated 50."""
        repo = MagicMock()
        repo.get_habitations_for_allocation.return_value = [
            {"id": 1, "name": "Hab1", "households": 20, "priority_score": 0.8, "tier": "immediate", "lat": 11.5, "lon": 76.1}
        ]
        repo.get_candidate_sites_and_distances.return_value = (
            [
                {
                    "id": 101,
                    "name": "Site_Unverified_Suitability",
                    "capacity": 50,
                    "suitability": None,  # No verified suitability evidence
                    "lat": 11.55,
                    "lon": 76.15,
                    "mhi_max": 0.10,
                    "slope_mean": 5.0,
                    "area_ha": 4.0,
                    "tenure": "government_revenue",
                    "is_forest": False,
                    "is_protected_area": False,
                    "is_crz": False,
                    "is_water_body": False,
                }
            ],
            [
                {"habitation_id": 1, "site_id": 101, "distance_km": 5.0}
            ],
        )

        service = AllocationService(db=MagicMock())
        service.repo = repo

        req = AllocationPlanRequest(admin_id=1, max_search_radius_km=15.0, target_tiers=[Tier.IMMEDIATE])
        plan = service.generate_allocation_plan(req)

        assert plan.status == "COMPLETED"
        assert len(plan.assignments) == 1
        assignment = plan.assignments[0]
        # Must be None, NOT 50!
        assert assignment.site_suitability is None

    def test_m13_b_verified_positive_evidence_preserved(self):
        """Test M13-B: Verified suitability evidence (e.g. 92) is accurately preserved and applied."""
        repo = MagicMock()
        repo.get_habitations_for_allocation.return_value = [
            {"id": 1, "name": "Hab1", "households": 30, "priority_score": 0.8, "tier": "immediate", "lat": 11.5, "lon": 76.1}
        ]
        repo.get_candidate_sites_and_distances.return_value = (
            [
                {
                    "id": 202,
                    "name": "Site_Verified_Safe",
                    "capacity": 50,
                    "suitability": 92,  # Verified evidence
                    "lat": 11.55,
                    "lon": 76.15,
                    "mhi_max": 0.08,
                    "slope_mean": 4.0,
                    "area_ha": 6.0,
                    "tenure": "government_revenue",
                    "is_forest": False,
                    "is_protected_area": False,
                    "is_crz": False,
                    "is_water_body": False,
                }
            ],
            [
                {"habitation_id": 1, "site_id": 202, "distance_km": 4.0}
            ],
        )

        service = AllocationService(db=MagicMock())
        service.repo = repo

        req = AllocationPlanRequest(admin_id=1, max_search_radius_km=15.0, target_tiers=[Tier.IMMEDIATE])
        plan = service.generate_allocation_plan(req)

        assert len(plan.assignments) == 1
        assert plan.assignments[0].site_suitability == 92

    def test_m13_c_hard_exclusion_constraints_never_weakened(self):
        """Test M13-C: A site failing a hard constraint remains excluded even with high suitability."""
        repo = MagicMock()
        repo.get_habitations_for_allocation.return_value = [
            {"id": 1, "name": "Hab1", "households": 20, "priority_score": 0.8, "tier": "immediate", "lat": 11.5, "lon": 76.1}
        ]
        repo.get_candidate_sites_and_distances.return_value = (
            [
                {
                    "id": 303,
                    "name": "Site_High_Suit_In_Forest",
                    "capacity": 50,
                    "suitability": 99,  # Even with 99 suitability
                    "lat": 11.55,
                    "lon": 76.15,
                    "mhi_max": 0.05,
                    "slope_mean": 3.0,
                    "area_ha": 10.0,
                    "tenure": "government_revenue",
                    "is_forest": True,  # Hard exclusion!
                    "is_protected_area": False,
                    "is_crz": False,
                    "is_water_body": False,
                }
            ],
            [
                {"habitation_id": 1, "site_id": 303, "distance_km": 3.0}
            ],
        )

        service = AllocationService(db=MagicMock())
        service.repo = repo

        req = AllocationPlanRequest(admin_id=1, max_search_radius_km=15.0, target_tiers=[Tier.IMMEDIATE])
        plan = service.generate_allocation_plan(req)

        # Must be rejected due to forest exclusion
        assert len(plan.assignments) == 0
        assert plan.total_relocated_households == 0
        assert plan.unmet_demand_households == 20

    def test_m13_d_no_fake_defaults_in_simulate_allocation(self):
        """Test M13-D: simulate_allocation also preserves None suitability without fake 50 fallback."""
        repo = MagicMock()
        repo.get_candidate_sites_and_distances.return_value = (
            [
                {
                    "id": 404,
                    "name": "SimSite",
                    "capacity": 40,
                    "suitability": None,
                    "lat": 11.55,
                    "lon": 76.15,
                    "mhi_max": 0.05,
                    "slope_mean": 3.0,
                    "area_ha": 5.0,
                    "tenure": "government_revenue",
                    "is_forest": False,
                    "is_protected_area": False,
                    "is_crz": False,
                    "is_water_body": False,
                }
            ],
            [
                {"habitation_id": 1, "site_id": 404, "distance_km": 4.0}
            ],
        )

        service = AllocationService(db=MagicMock())
        service.repo = repo

        demands = [HabitationDemand(id=1, name="Hab1", demand_households=15, priority_score=0.7, tier=Tier.IMMEDIATE)]
        res = service.simulate_allocation(demands, max_search_radius_km=15.0)

        assert len(res.assignments) == 1
        assert res.assignments[0].site_suitability is None

    def test_m13_e_json_serialization_renders_null_honestly(self):
        """Test M13-E: DTO serializes site_suitability as null, not missing or positive default."""
        dto = AllocationAssignmentDTO(
            habitation_id=1,
            habitation_name="Habitation One",
            site_id=101,
            site_distance_km=4.2,
            households=20,
            tier=Tier.IMMEDIATE,
            priority_score=0.85,
            site_suitability=None,  # Unverified
            has_group_split=False,
        )

        serialized = json.loads(dto.model_dump_json())
        assert "site_suitability" in serialized
        assert serialized["site_suitability"] is None

        # Verify envelope serialization
        resp = AllocationPlanResponse(
            allocation_run_id="00000000-0000-0000-0000-000000000001",
            status="COMPLETED",
            total_demand_households=20,
            total_relocated_households=20,
            unmet_demand_households=0,
            solver_latency_ms=1.5,
            assignments=[dto],
        )
        resp_dict = json.loads(resp.model_dump_json())
        assert resp_dict["assignments"][0]["site_suitability"] is None

    def test_m13_f_explicit_zero_suitability_preserved(self):
        """Test M13-F: Explicit 0 suitability is preserved as 0, not None and not 50."""
        assert compute_assignment_benefit(priority_score=0.8, suitability=0) == 0.0
        assert compute_assignment_benefit(priority_score=0.8, suitability=None) == 0.0
        assert compute_assignment_benefit(priority_score=0.8, suitability=50) == 40.0

        dto = AllocationAssignmentDTO(
            habitation_id=2,
            habitation_name="Habitation Two",
            site_id=102,
            site_distance_km=3.0,
            households=10,
            tier=Tier.SHORT_TERM,
            priority_score=0.6,
            site_suitability=0,
        )
        assert dto.site_suitability == 0

    def test_m13_g_solver_prefers_verified_suitable_site_over_unverified(self):
        """Test M13-G: At equal distance and capacity, solver prefers site with verified suitability."""
        habs = [HabitationDemand(id=1, name="V1", demand_households=50, priority_score=0.8, tier=Tier.IMMEDIATE)]
        sites = [
            CandidateSiteCapacity(id=10, name="UnverifiedSite", capacity_households=50, suitability=None),
            CandidateSiteCapacity(id=20, name="VerifiedSite", capacity_households=50, suitability=90),
        ]
        distances = [
            HabitationSiteDistance(habitation_id=1, site_id=10, distance_km=5.0),
            HabitationSiteDistance(habitation_id=1, site_id=20, distance_km=5.0),
        ]

        solver = MinCostFlowAllocationSolver(AllocationConfig(allow_group_splits=True))
        res = solver.solve(habs, sites, distances)

        assert len(res.assignments) == 1
        # Must pick verified site (id=20) because it provides legitimate objective benefit b_js
        assert res.assignments[0].site_id == 20
        assert res.assignments[0].site_suitability == 90

    def test_m13_h_both_split_and_nosplit_solvers_handle_none_suitability(self):
        """Test M13-H: Both allow_group_splits=True and allow_group_splits=False handle suitability=None."""
        habs = [HabitationDemand(id=1, name="V1", demand_households=40, priority_score=0.7, tier=Tier.IMMEDIATE)]
        sites = [CandidateSiteCapacity(id=101, name="SiteA", capacity_households=50, suitability=None)]
        distances = [HabitationSiteDistance(habitation_id=1, site_id=101, distance_km=3.0)]

        # 1. Flow path (splits allowed)
        solver_flow = MinCostFlowAllocationSolver(AllocationConfig(allow_group_splits=True))
        res_flow = solver_flow.solve(habs, sites, distances)
        assert res_flow.solver_status == "OPTIMAL"
        assert res_flow.status == "COMPLETED"
        assert res_flow.assignments[0].site_suitability is None

        # 2. CP-SAT path (H12 no splits allowed)
        solver_cpsat = MinCostFlowAllocationSolver(AllocationConfig(allow_group_splits=False))
        res_cpsat = solver_cpsat.solve(habs, sites, distances)
        assert res_cpsat.solver_status == "OPTIMAL"
        assert res_cpsat.status == "COMPLETED"
        assert res_cpsat.assignments[0].site_suitability is None
