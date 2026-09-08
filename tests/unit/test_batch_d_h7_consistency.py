"""Unit and Regression Tests for Batch D / H7 Relocation Candidate Eligibility Consistency.

Section refs: docs/PRD1.md §6.8, §9.5, §9.6, FR-7.1, FR-7.2, FR-7.3

Verifies that the backend maintains ONE canonical eligibility policy (CandidateSitePolicy / evaluate_site_eligibility)
and that:
1. Canonical policy correctly rejects violating candidate sites with standard rejection reasons.
2. Candidate-site listing / API path does not expose ineligible candidates.
3. Allocation solver excludes ineligible candidate sites.
4. Valid eligible candidate sites continue through normal listing and allocation flows.
5. Candidate site generator uses the canonical evaluator and persists canonical eligibility in metadata.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock
import pytest

from core.domain.capacity import (
    CapacityEngine,
    CandidateSitePolicy,
    EligibilityResult,
)
from core.enums import BindingConstraint, TenureType, Tier
from core.domain.allocation import HabitationDemand
from api.repositories.sites_repo import SitesRepository
from api.repositories.allocation_repo import AllocationRepository
from api.services.sites_service import SitesService
from api.services.allocation_service import AllocationService
from core.schemas.allocation import AllocationPlanRequest
from pipeline.capacity.site_generator import (
    RawCandidateSiteSpec,
    build_candidate_site_record,
)


# ==============================================================================
# TEST 1: Canonical Policy Rejection
# ==============================================================================
class TestCanonicalPolicyRejection:
    """Proves that evaluate_site_eligibility rejects sites violating known policy constraints."""

    @pytest.fixture
    def engine(self) -> CapacityEngine:
        return CapacityEngine()

    @pytest.fixture
    def policy(self) -> CandidateSitePolicy:
        return CandidateSitePolicy()

    def test_rejects_static_mhi_at_or_above_threshold(self, engine: CapacityEngine, policy: CandidateSitePolicy):
        """MHI >= policy threshold (default 0.25) must be rejected with canonical reason."""
        res_at = engine.evaluate_site_eligibility(
            mhi_max=policy.max_static_mhi,
            slope_mean=5.0,
            area_ha=3.0,
            tenure=TenureType.GOVERNMENT_REVENUE,
        )
        assert res_at.is_eligible is False
        assert f"Static MHI {policy.max_static_mhi:.2f} >= threshold {policy.max_static_mhi:.2f}" in res_at.rejection_reasons

        res_above = engine.evaluate_site_eligibility(
            mhi_max=0.35,
            slope_mean=5.0,
            area_ha=3.0,
            tenure=TenureType.GOVERNMENT_REVENUE,
        )
        assert res_above.is_eligible is False
        assert "Static MHI 0.35 >= threshold 0.25" in res_above.rejection_reasons

    def test_rejects_slope_at_or_above_threshold(self, engine: CapacityEngine, policy: CandidateSitePolicy):
        """Mean slope >= policy threshold (default 15.0 deg) must be rejected."""
        res_at = engine.evaluate_site_eligibility(
            mhi_max=0.05,
            slope_mean=policy.max_slope_deg,
            area_ha=3.0,
            tenure=TenureType.GOVERNMENT_REVENUE,
        )
        assert res_at.is_eligible is False
        assert f"Mean slope {policy.max_slope_deg:.1f}° >= threshold {policy.max_slope_deg:.1f}°" in res_at.rejection_reasons

        res_above = engine.evaluate_site_eligibility(
            mhi_max=0.05,
            slope_mean=20.0,
            area_ha=3.0,
            tenure=TenureType.GOVERNMENT_REVENUE,
        )
        assert res_above.is_eligible is False
        assert "Mean slope 20.0° >= threshold 15.0°" in res_above.rejection_reasons

    def test_rejects_area_below_minimum_threshold(self, engine: CapacityEngine, policy: CandidateSitePolicy):
        """Contiguous area < policy minimum (default 2.0 ha) must be rejected."""
        res = engine.evaluate_site_eligibility(
            mhi_max=0.05,
            slope_mean=5.0,
            area_ha=1.8,
            tenure=TenureType.GOVERNMENT_REVENUE,
        )
        assert res.is_eligible is False
        assert "Contiguous area 1.80 ha < minimum 2.00 ha" in res.rejection_reasons

    def test_rejects_unverified_or_invalid_tenure(self, engine: CapacityEngine):
        """Tenure must be valid government_revenue or private; unverified/unknown is rejected."""
        res_unverified = engine.evaluate_site_eligibility(
            mhi_max=0.05,
            slope_mean=5.0,
            area_ha=3.0,
            tenure=TenureType.TENURE_UNVERIFIED,
        )
        assert res_unverified.is_eligible is False
        assert "Land tenure is unverified" in res_unverified.rejection_reasons

        res_unknown = engine.evaluate_site_eligibility(
            mhi_max=0.05,
            slope_mean=5.0,
            area_ha=3.0,
            tenure="disputed_land",
        )
        assert res_unknown.is_eligible is False
        assert "Land tenure is unknown or invalid" in res_unknown.rejection_reasons

    def test_rejects_environmental_exclusions(self, engine: CapacityEngine):
        """Sites overlapping designated forest, protected area, CRZ, or water body are rejected."""
        res_forest = engine.evaluate_site_eligibility(
            mhi_max=0.05, slope_mean=5.0, area_ha=3.0, tenure=TenureType.GOVERNMENT_REVENUE,
            is_forest=True,
        )
        assert res_forest.is_eligible is False
        assert "Site overlaps designated forest land" in res_forest.rejection_reasons

        res_protected = engine.evaluate_site_eligibility(
            mhi_max=0.05, slope_mean=5.0, area_ha=3.0, tenure=TenureType.GOVERNMENT_REVENUE,
            is_protected_area=True,
        )
        assert res_protected.is_eligible is False
        assert "Site overlaps protected ecological area / sanctuary" in res_protected.rejection_reasons

        res_crz = engine.evaluate_site_eligibility(
            mhi_max=0.05, slope_mean=5.0, area_ha=3.0, tenure=TenureType.GOVERNMENT_REVENUE,
            is_crz=True,
        )
        assert res_crz.is_eligible is False
        assert "Site overlaps Coastal Regulation Zone (CRZ-I/II)" in res_crz.rejection_reasons

        res_water = engine.evaluate_site_eligibility(
            mhi_max=0.05, slope_mean=5.0, area_ha=3.0, tenure=TenureType.GOVERNMENT_REVENUE,
            is_water_body=True,
        )
        assert res_water.is_eligible is False
        assert "Site overlaps surface water body" in res_water.rejection_reasons

    def test_rejects_excessive_search_radius_distance(self, engine: CapacityEngine, policy: CandidateSitePolicy):
        """Distance exceeding policy search radius is rejected when distance is evaluated."""
        res = engine.evaluate_site_eligibility(
            mhi_max=0.05, slope_mean=5.0, area_ha=3.0, tenure=TenureType.GOVERNMENT_REVENUE,
            distance_km=18.5,
            require_distance=True,
        )
        assert res.is_eligible is False
        assert f"Site distance 18.50 km > search radius {policy.search_radius_km:.1f} km" in res.rejection_reasons

    def test_missing_data_is_never_assumed_safe(self, engine: CapacityEngine):
        """Missing attributes produce explicit rejection reasons and are not assumed safe."""
        res = engine.evaluate_site_eligibility(
            mhi_max=None,
            slope_mean=None,
            area_ha=None,
            tenure=None,
            is_forest=None,
            is_protected_area=None,
            is_crz=None,
            is_water_body=None,
        )
        assert res.is_eligible is False
        assert len(res.rejection_reasons) >= 8


# ==============================================================================
# TEST 2: Listing Consistency
# ==============================================================================
class TestListingConsistency:
    """Proves that candidate-site listing enforces canonical eligibility."""

    def test_sites_repo_query_includes_eligibility_mask(self):
        """SitesRepository retrieves candidates without duplicating H7 policy in SQL (Phase 5)."""
        mock_db = MagicMock()
        mock_db.execute.return_value.mappings.return_value.fetchall.return_value = []

        repo = SitesRepository(mock_db)
        custom_policy = CandidateSitePolicy(
            max_static_mhi=0.20,
            max_slope_deg=12.0,
            min_contiguous_area_ha=3.5,
            search_radius_km=25.0,
        )

        repo.query_candidate_sites_for_habitation(
            habitation_id=42,
            radius_m=25000.0,
            policy=custom_policy,
        )

        assert mock_db.execute.called
        call_args = mock_db.execute.call_args
        sql_text = str(call_args[0][0])

        # Repositories retrieve candidates spatially; CandidateSitePolicy is the sole authority
        assert "ST_DWithin" in sql_text
        assert "cs.mhi_max <" not in sql_text
        assert "cs.slope_mean <" not in sql_text

    def test_sites_service_passes_canonical_policy_to_repo(self):
        """SitesService.get_candidate_sites_for_habitation propagates CandidateSitePolicy to repository."""
        mock_db = MagicMock()
        repo_mock = MagicMock()
        repo_mock.check_habitation_exists.return_value = True
        repo_mock.query_candidate_sites_for_habitation.return_value = ([], 0)

        custom_policy = CandidateSitePolicy(max_static_mhi=0.18, max_slope_deg=10.0)
        service = SitesService(db=mock_db, policy=custom_policy)
        service.repo = repo_mock

        service.get_candidate_sites_for_habitation(habitation_id=10, radius_km=20.0)

        assert repo_mock.query_candidate_sites_for_habitation.called
        call_kwargs = repo_mock.query_candidate_sites_for_habitation.call_args.kwargs
        passed_policy = call_kwargs.get("policy")
        assert passed_policy is not None
        assert passed_policy.max_static_mhi == 0.18
        assert passed_policy.max_slope_deg == 10.0
        assert passed_policy.search_radius_km == 20.0


# ==============================================================================
# TEST 3: Allocation Consistency
# ==============================================================================
class TestAllocationConsistency:
    """Proves that ineligible candidate sites cannot enter the allocation solver."""

    def test_allocation_repo_parameterizes_policy_mask(self):
        """AllocationRepository must parameterize the SQL WHERE mask from CandidateSitePolicy."""
        mock_db = MagicMock()
        mock_db.execute.return_value.mappings.return_value.fetchall.return_value = []

        repo = AllocationRepository(mock_db)
        custom_policy = CandidateSitePolicy(
            max_static_mhi=0.22,
            max_slope_deg=11.0,
            min_contiguous_area_ha=4.0,
        )

        repo.get_candidate_sites_and_distances(
            habitation_ids=[1, 2],
            max_radius_m=15000.0,
            policy=custom_policy,
        )

        assert mock_db.execute.called
        call_args = mock_db.execute.call_args
        sql_text = str(call_args[0][0])
        params = call_args[0][1]

        assert "cs.mhi_max < :max_static_mhi" in sql_text
        assert "cs.slope_mean < :max_slope_deg" in sql_text
        assert "cs.area_ha >= :min_area_ha" in sql_text
        assert "cs.tenure IN ('government_revenue', 'private')" in sql_text
        assert "metadata->>'is_eligible'" not in sql_text
        assert "metadata->>'is_forest'" not in sql_text

        assert params["max_static_mhi"] == 0.22
        assert params["max_slope_deg"] == 11.0
        assert params["min_area_ha"] == 4.0

    def test_ineligible_sites_excluded_from_solver(self):
        """Solver must not receive any site rejected by canonical evaluate_site_eligibility."""
        repo = MagicMock()
        repo.get_habitations_for_allocation.return_value = [
            {
                "id": 1,
                "name": "Habitation A",
                "households": 40,
                "priority_score": 0.85,
                "tier": "immediate",
                "lat": 11.5,
                "lon": 76.1,
            }
        ]
        # Mix of sites: MHI violation, slope violation, tenure violation, area violation, environmental violation
        repo.get_candidate_sites_and_distances.return_value = (
            [
                # Site 101: MHI 0.35 >= 0.25 -> REJECT
                {"id": 101, "name": "HighMHISite", "capacity": 100, "suitability": 80, "lat": 11.5, "lon": 76.1,
                 "mhi_max": 0.35, "slope_mean": 5.0, "area_ha": 5.0, "tenure": "government_revenue",
                 "is_forest": False, "is_protected_area": False, "is_crz": False, "is_water_body": False},
                # Site 102: Slope 22° >= 15° -> REJECT
                {"id": 102, "name": "SteepSite", "capacity": 100, "suitability": 80, "lat": 11.5, "lon": 76.1,
                 "mhi_max": 0.05, "slope_mean": 22.0, "area_ha": 5.0, "tenure": "government_revenue",
                 "is_forest": False, "is_protected_area": False, "is_crz": False, "is_water_body": False},
                # Site 103: Tenure unverified -> REJECT
                {"id": 103, "name": "UnverifiedTenureSite", "capacity": 100, "suitability": 80, "lat": 11.5, "lon": 76.1,
                 "mhi_max": 0.05, "slope_mean": 5.0, "area_ha": 5.0, "tenure": "tenure_unverified",
                 "is_forest": False, "is_protected_area": False, "is_crz": False, "is_water_body": False},
                # Site 104: Area 1.2 ha < 2.0 ha -> REJECT
                {"id": 104, "name": "SmallSite", "capacity": 100, "suitability": 80, "lat": 11.5, "lon": 76.1,
                 "mhi_max": 0.05, "slope_mean": 5.0, "area_ha": 1.2, "tenure": "government_revenue",
                 "is_forest": False, "is_protected_area": False, "is_crz": False, "is_water_body": False},
                # Site 105: Forest land -> REJECT
                {"id": 105, "name": "ForestSite", "capacity": 100, "suitability": 80, "lat": 11.5, "lon": 76.1,
                 "mhi_max": 0.05, "slope_mean": 5.0, "area_ha": 5.0, "tenure": "government_revenue",
                 "is_forest": True, "is_protected_area": False, "is_crz": False, "is_water_body": False},
            ],
            [
                {"habitation_id": 1, "site_id": 101, "distance_km": 3.0},
                {"habitation_id": 1, "site_id": 102, "distance_km": 3.0},
                {"habitation_id": 1, "site_id": 103, "distance_km": 3.0},
                {"habitation_id": 1, "site_id": 104, "distance_km": 3.0},
                {"habitation_id": 1, "site_id": 105, "distance_km": 3.0},
            ],
        )

        service = AllocationService(db=MagicMock())
        service.repo = repo

        req = AllocationPlanRequest(admin_id=1, max_search_radius_km=15.0, target_tiers=[Tier.IMMEDIATE])
        plan = service.generate_allocation_plan(req)

        # Zero households relocated since every candidate was ineligible
        assert plan.total_relocated_households == 0
        assert plan.unmet_demand_households == 40
        assert len(plan.assignments) == 0

    def test_missing_metadata_never_establishes_eligibility_in_allocation(self):
        """H7 Concern 1: Candidate site with missing/empty metadata must never become eligible."""
        repo = MagicMock()
        repo.get_habitations_for_allocation.return_value = [
            {
                "id": 1,
                "name": "Habitation Missing Meta Test",
                "households": 30,
                "priority_score": 0.88,
                "tier": "immediate",
                "lat": 11.5,
                "lon": 76.1,
            }
        ]
        # Site 106 has valid physical columns but empty metadata (no is_eligible, no environmental flags)
        repo.get_candidate_sites_and_distances.return_value = (
            [
                {
                    "id": 106,
                    "name": "SiteWithEmptyMetadata",
                    "capacity": 100,
                    "suitability": 85,
                    "lat": 11.5,
                    "lon": 76.1,
                    "mhi_max": 0.05,
                    "slope_mean": 4.0,
                    "area_ha": 5.0,
                    "tenure": "government_revenue",
                    "metadata": {},
                }
            ],
            [
                {"habitation_id": 1, "site_id": 106, "distance_km": 3.0},
            ],
        )

        service = AllocationService(db=MagicMock())
        service.repo = repo

        req = AllocationPlanRequest(admin_id=1, max_search_radius_km=15.0, target_tiers=[Tier.IMMEDIATE])
        plan = service.generate_allocation_plan(req)

        # Site with missing metadata must be rejected by canonical evaluate_site_eligibility
        assert plan.total_relocated_households == 0
        assert plan.unmet_demand_households == 30
        assert len(plan.assignments) == 0


# ==============================================================================
# TEST 4: Eligible Site Still Works
# ==============================================================================
class TestEligibleSiteFlow:
    """Proves that a valid eligible candidate successfully completes candidate/allocation flows."""

    def test_eligible_candidate_allocated_successfully(self):
        """A valid candidate site conforming to all canonical constraints receives allocation."""
        repo = MagicMock()
        repo.get_habitations_for_allocation.return_value = [
            {
                "id": 1,
                "name": "Habitation Safe Test",
                "households": 25,
                "priority_score": 0.90,
                "tier": "immediate",
                "lat": 11.55,
                "lon": 76.10,
            }
        ]
        repo.get_candidate_sites_and_distances.return_value = (
            [
                {
                    "id": 201,
                    "name": "Valid Revenue Plain",
                    "capacity": 50,
                    "suitability": 92,
                    "lat": 11.58,
                    "lon": 76.12,
                    "mhi_max": 0.04,
                    "slope_mean": 3.2,
                    "area_ha": 8.0,
                    "tenure": "government_revenue",
                    "is_forest": False,
                    "is_protected_area": False,
                    "is_crz": False,
                    "is_water_body": False,
                }
            ],
            [
                {"habitation_id": 1, "site_id": 201, "distance_km": 4.5},
            ],
        )

        service = AllocationService(db=MagicMock())
        service.repo = repo

        req = AllocationPlanRequest(admin_id=1, max_search_radius_km=15.0, target_tiers=[Tier.IMMEDIATE])
        plan = service.generate_allocation_plan(req)

        assert plan.total_relocated_households == 25
        assert plan.unmet_demand_households == 0
        assert len(plan.assignments) == 1
        assert plan.assignments[0].site_id == 201
        assert plan.assignments[0].households == 25


# ==============================================================================
# TEST 5: Generation Consistency
# ==============================================================================
class TestCandidateGenerationConsistency:
    """Proves candidate generator uses canonical evaluate_site_eligibility and persists status in metadata."""

    def test_generator_evaluates_and_persists_ineligible_mhi(self):
        """Candidate generator flags and records MHI violation via canonical evaluator."""
        spec = RawCandidateSiteSpec(
            name="Hazard Terrace",
            lat=11.6,
            lon=76.2,
            area_ha=5.0,
            tenure=TenureType.GOVERNMENT_REVENUE,
            slope_mean=5.0,
            mhi_max=0.32,  # > 0.25
            water_yield_liters_per_day=100000.0,
            spare_school_seats=200,
            spare_health_capacity_pop=2000,
            livelihood_multiplier=1.0,
        )

        record = build_candidate_site_record(spec)

        assert record["is_eligible"] is False
        assert any("Static MHI 0.32 >= threshold 0.25" in r for r in record["rejection_reasons"])

        meta = json.loads(record["metadata"])
        assert meta["is_eligible"] is False
        assert any("Static MHI 0.32 >= threshold 0.25" in r for r in meta["rejection_reasons"])

    def test_generator_evaluates_and_persists_unverified_tenure(self):
        """Candidate generator flags unverified tenure via canonical evaluator."""
        spec = RawCandidateSiteSpec(
            name="Unverified Tenure Land",
            lat=11.6,
            lon=76.2,
            area_ha=5.0,
            tenure=TenureType.TENURE_UNVERIFIED,
            slope_mean=4.0,
            mhi_max=0.05,
            water_yield_liters_per_day=100000.0,
            spare_school_seats=200,
            spare_health_capacity_pop=2000,
            livelihood_multiplier=1.0,
        )

        record = build_candidate_site_record(spec)

        assert record["is_eligible"] is False
        assert "Land tenure is unverified" in record["rejection_reasons"]

        meta = json.loads(record["metadata"])
        assert meta["is_eligible"] is False
        assert "Land tenure is unverified" in meta["rejection_reasons"]

    def test_generator_evaluates_and_persists_eligible_site(self):
        """Candidate generator correctly identifies eligible site and records empty rejection list."""
        spec = RawCandidateSiteSpec(
            name="Safe Green Plain",
            lat=11.6,
            lon=76.2,
            area_ha=10.0,
            tenure=TenureType.GOVERNMENT_REVENUE,
            slope_mean=3.0,
            mhi_max=0.03,
            water_yield_liters_per_day=200000.0,
            spare_school_seats=500,
            spare_health_capacity_pop=4000,
            livelihood_multiplier=1.0,
            suitability=90,
            is_forest=False,
            is_protected_area=False,
            is_crz=False,
            is_water_body=False,
        )

        record = build_candidate_site_record(spec)

        assert record["is_eligible"] is True
        assert record["rejection_reasons"] == []

        meta = json.loads(record["metadata"])
        assert meta["is_eligible"] is True
        assert meta["rejection_reasons"] == []
        assert meta["is_forest"] is False
        assert meta["is_protected_area"] is False

    def test_generator_respects_custom_engine_policy(self):
        """Candidate generator respects custom policy passed in engine."""
        custom_policy = CandidateSitePolicy(max_static_mhi=0.08)
        engine = CapacityEngine(site_policy=custom_policy)

        spec = RawCandidateSiteSpec(
            name="Borderline Hazard Site",
            lat=11.6,
            lon=76.2,
            area_ha=6.0,
            tenure=TenureType.GOVERNMENT_REVENUE,
            slope_mean=4.0,
            mhi_max=0.12,  # > 0.08 under custom policy, but < 0.25 under default
            water_yield_liters_per_day=100000.0,
            spare_school_seats=200,
            spare_health_capacity_pop=2000,
            livelihood_multiplier=1.0,
        )

        record = build_candidate_site_record(spec, engine=engine)

        assert record["is_eligible"] is False
        assert "Static MHI 0.12 >= threshold 0.08" in record["rejection_reasons"]
