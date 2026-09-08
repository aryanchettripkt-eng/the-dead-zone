"""Unit and Regression Tests for M10: Remove the hardcoded 500-scenario truncation.

Verifies:
- Test M10-A: More than 500 scenarios survive (e.g. 501 valid scenarios) without truncation;
  pagination works across the full cohort; total_habitations_evaluated == 501.
- Test M10-B: Exactly 500 scenarios continue to evaluate and paginate correctly.
- Test M10-C: Fewer than 500 scenarios continue to behave identically.
- Test M10-D: Deterministic ordering is preserved across large scenario collections.
- Test M10-E: No hidden secondary truncation in downstream scenario allocation simulation.
"""

from unittest.mock import MagicMock
import pytest

from api.services.scenario_service import ScenarioService
from core.domain.scenario import HabitationBaselineState, ScenarioEngine
from core.enums import Hazard, SortMode, Tier
from core.schemas.scenario import (
    ScenarioAllocationParams,
    ScenarioWeightOverrideRequest,
)


def _generate_mock_habitation_row(idx: int, priority_score: float = 0.5, tier: str = "immediate") -> dict:
    """Generates a raw database dictionary representation of a habitation."""
    return {
        "id": idx,
        "name": f"Habitation-{idx}",
        "population": 100 + (idx % 50),
        "households": 25 + (idx % 10),
        "lat": 11.5 + (idx * 0.0001),
        "lon": 76.1 + (idx * 0.0001),
        "centroid_lat": 11.5 + (idx * 0.0001),
        "centroid_lon": 76.1 + (idx * 0.0001),
        "priority_score": priority_score,
        "hazard_intensity": 0.6,
        "prz_overlap_pct": 40.0,
        "v_index": 0.5,
        "decayed_loss": 1.0,
        "tier": tier,
        "active_deformation": False,
        "fatal_event_last_3_monsoons": False,
        "mitigation_cost": None,
        "relocation_cost": None,
        "adverse_trend": False,
        "dominant_hazard": "landslide",
    }


class TestM10ScenarioTruncationRemoval:
    """Test suite verifying removal of artificial 500-scenario truncation."""

    def test_m10_a_more_than_500_scenarios_survive_and_paginate(self):
        """Test M10-A: 501 habitations must all be evaluated, not truncated at 500.
        
        Pagination must allow accessing all 501 items.
        """
        total_count = 501
        raw_habs = [
            _generate_mock_habitation_row(i, priority_score=0.9 - (i * 0.001))
            for i in range(1, total_count + 1)
        ]

        mock_db = MagicMock()
        mock_hab_repo = MagicMock()
        # Habitation repo returns all 501 habitations when limit=None
        mock_hab_repo.query_habitations.return_value = (raw_habs, total_count)
        mock_hab_repo.get_hazard_scores_for_habitations.return_value = {}

        service = ScenarioService(db=mock_db)
        service.hab_repo = mock_hab_repo

        # 1. First page: limit=50, offset=0
        req_page1 = ScenarioWeightOverrideRequest(
            admin_id=10,
            limit=50,
            offset=0,
            sort_mode=SortMode.URGENCY,
        )
        res_page1 = service.evaluate_scenario(req_page1)

        # Total habitations evaluated must be 501, NOT 500!
        assert res_page1.total_habitations_evaluated == 501
        assert len(res_page1.items) == 50
        assert res_page1.items[0].habitation_id == 1
        assert res_page1.items[0].scenario_rank == 1

        # Check repository was called with limit=None (no truncation)
        mock_hab_repo.query_habitations.assert_called_with(
            admin_id=10,
            limit=None,
            offset=0,
            sort=SortMode.URGENCY,
        )

        # 2. Access the 501st item via offset=500, limit=50
        req_last_page = ScenarioWeightOverrideRequest(
            admin_id=10,
            limit=50,
            offset=500,
            sort_mode=SortMode.URGENCY,
        )
        res_last = service.evaluate_scenario(req_last_page)

        assert res_last.total_habitations_evaluated == 501
        assert len(res_last.items) == 1
        assert res_last.items[0].habitation_id == 501
        assert res_last.items[0].scenario_rank == 501

    def test_m10_b_exactly_500_scenarios_boundary(self):
        """Test M10-B: Exactly 500 habitations continue to evaluate correctly without off-by-one."""
        total_count = 500
        raw_habs = [
            _generate_mock_habitation_row(i, priority_score=0.8)
            for i in range(1, total_count + 1)
        ]

        mock_db = MagicMock()
        mock_hab_repo = MagicMock()
        mock_hab_repo.query_habitations.return_value = (raw_habs, total_count)
        mock_hab_repo.get_hazard_scores_for_habitations.return_value = {}

        service = ScenarioService(db=mock_db)
        service.hab_repo = mock_hab_repo

        req = ScenarioWeightOverrideRequest(
            admin_id=10,
            limit=100,
            offset=400,
            sort_mode=SortMode.URGENCY,
        )
        res = service.evaluate_scenario(req)

        assert res.total_habitations_evaluated == 500
        assert len(res.items) == 100
        assert res.items[-1].habitation_id == 500
        assert res.items[-1].scenario_rank == 500

    def test_m10_c_fewer_than_500_scenarios(self):
        """Test M10-C: Existing behavior is preserved for small scenario sets (< 500)."""
        total_count = 4
        raw_habs = [
            _generate_mock_habitation_row(1, priority_score=0.9),
            _generate_mock_habitation_row(2, priority_score=0.7),
            _generate_mock_habitation_row(3, priority_score=0.5),
            _generate_mock_habitation_row(4, priority_score=0.3),
        ]

        mock_db = MagicMock()
        mock_hab_repo = MagicMock()
        mock_hab_repo.query_habitations.return_value = (raw_habs, total_count)
        mock_hab_repo.get_hazard_scores_for_habitations.return_value = {}

        service = ScenarioService(db=mock_db)
        service.hab_repo = mock_hab_repo

        req = ScenarioWeightOverrideRequest(
            admin_id=1,
            limit=50,
            offset=0,
            sort_mode=SortMode.URGENCY,
        )
        res = service.evaluate_scenario(req)

        assert res.total_habitations_evaluated == 4
        assert len(res.items) == 4
        assert [item.habitation_id for item in res.items] == [1, 2, 3, 4]

    def test_m10_d_deterministic_ordering_preserved(self):
        """Test M10-D: Tie-breaking and sorting order remain strictly deterministic across 600 items."""
        total_count = 600
        # All items have identical priority score to test deterministic secondary sort by ID
        raw_habs = [
            _generate_mock_habitation_row(i, priority_score=0.75)
            for i in range(1, total_count + 1)
        ]

        mock_db = MagicMock()
        mock_hab_repo = MagicMock()
        mock_hab_repo.query_habitations.return_value = (raw_habs, total_count)
        mock_hab_repo.get_hazard_scores_for_habitations.return_value = {}

        service = ScenarioService(db=mock_db)
        service.hab_repo = mock_hab_repo

        req = ScenarioWeightOverrideRequest(
            admin_id=2,
            limit=200,
            offset=0,
            sort_mode=SortMode.URGENCY,
        )
        res = service.evaluate_scenario(req)

        assert res.total_habitations_evaluated == 600
        # Check ascending order of IDs in tie-break
        ids = [item.habitation_id for item in res.items]
        assert ids == list(range(1, 201))

    def test_m10_e_no_hidden_second_truncation_in_allocation_simulation(self):
        """Test M10-E: Scenario allocation simulation receives all 550 habitations without secondary truncation."""
        total_count = 550
        raw_habs = [
            _generate_mock_habitation_row(i, priority_score=0.8, tier="immediate")
            for i in range(1, total_count + 1)
        ]

        mock_db = MagicMock()
        mock_hab_repo = MagicMock()
        mock_hab_repo.query_habitations.return_value = (raw_habs, total_count)
        mock_hab_repo.get_hazard_scores_for_habitations.return_value = {}

        service = ScenarioService(db=mock_db)
        service.hab_repo = mock_hab_repo

        # Intercept AllocationService.simulate_allocation to verify demanded count
        demands_captured = []

        class MockAllocService:
            def __init__(self, db):
                pass

            def simulate_allocation(self, simulated_demands, **kwargs):
                demands_captured.extend(simulated_demands)
                mock_res = MagicMock()
                mock_res.status = "OPTIMAL"
                mock_res.total_demand_households = sum(d.demand_households for d in simulated_demands)
                mock_res.total_relocated_households = 0
                mock_res.unmet_demand_households = mock_res.total_demand_households
                mock_res.assignments = []
                mock_res.solver_latency_ms = 1.0
                mock_res.group_split_warnings = []
                mock_res.policy_version = "allocation-v1.0"
                return mock_res

        import api.services.scenario_service as scen_mod
        orig_alloc_svc = scen_mod.AllocationService
        scen_mod.AllocationService = MockAllocService

        try:
            req = ScenarioWeightOverrideRequest(
                admin_id=1,
                include_allocation=True,
                limit=50,
                offset=0,
            )
            res = service.evaluate_scenario(req)

            assert res.total_habitations_evaluated == 550
            # All 550 immediate tier habitations must have reached allocation simulation
            assert len(demands_captured) == 550
            assert res.allocation_simulation is not None
            assert res.allocation_simulation.status == "OPTIMAL"
        finally:
            scen_mod.AllocationService = orig_alloc_svc
