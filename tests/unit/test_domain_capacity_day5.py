"""Unit tests for Carrying Capacity Domain Engine, Norms, and Bottleneck Bottlenecks (Day 5).

Section refs: docs/PRD1.md §6.8, §9.5, §9.6, FR-7.1–FR-7.7
Audit pass: Post-implementation hardening for Day 5.
"""

import pytest
from core.domain.capacity import (
    CapacityEngine,
    CapacityNormsConfig,
    CandidateSitePolicy,
    CapacityDataQuality,
    EligibilityResult,
    AugmentedCapacityResult,
    CapacityEvaluationResult,
    compute_land_capacity,
    compute_water_capacity,
    compute_school_capacity,
    compute_health_capacity,
    compute_carrying_capacity,
    compute_augmented_capacity,
)
from core.enums import BindingConstraint, TenureType
from core.constants import INFRA_OVERHEAD


class TestCapacityNormsAndEngine:
    """Tests for carrying capacity formulas, norms, and immutable configurations."""

    def test_default_norms_configuration(self):
        engine = CapacityEngine()
        assert engine.norms.plot_area_m2 == 90.0
        assert engine.norms.non_residential_overhead_pct == INFRA_OVERHEAD
        assert engine.norms.lpcd_rural == 55
        assert engine.norms.lpcd_urban == 135
        assert engine.norms.phc_norm_pop_hilly_tribal == 20000
        assert engine.norms.phc_norm_pop_plain == 30000
        assert engine.norms.students_per_hh == 1.2
        assert engine.norms.persons_per_hh == 4.5
        assert engine.norms.policy_version == "capacity-norms-v1.0"
        assert engine.norms.calculation_version == "calc-v1.0"

    def test_land_capacity_calculation(self):
        engine = CapacityEngine()
        # 10,000 m2 (1 ha). Effective area per HH = 90 * (1 + 0.40) = 126.0 m2
        # floor(10000 / 126.0) = 79 HH.
        assert engine.calculate_land_capacity(10000.0) == 79

        # 50,000 m2 (5 ha) => floor(50000 / 126.0) = 396 HH.
        assert engine.calculate_land_capacity(50000.0) == 396

        # Custom plot area override (e.g. 120 m2) => floor(50000 / (120 * 1.40)) = 297 HH.
        assert engine.calculate_land_capacity(50000.0, plot_area_m2=120.0) == 297

        # Zero or negative area => 0
        assert engine.calculate_land_capacity(0.0) == 0
        assert engine.calculate_land_capacity(-100.0) == 0

    def test_water_capacity_calculation(self):
        engine = CapacityEngine()
        # Rural (55 LPCD, 4.5 pers/HH => 247.5 L/day/HH)
        # 24750 L/day => 24750 / 247.5 = 100 HH.
        assert engine.calculate_water_capacity(24750.0, is_urban=False) == 100

        # Urban (135 LPCD, 4.5 pers/HH => 607.5 L/day/HH)
        # 60750 L/day => 60750 / 607.5 = 100 HH.
        assert engine.calculate_water_capacity(60750.0, is_urban=True) == 100

        # Zero yield => 0 HH
        assert engine.calculate_water_capacity(0.0) == 0

    def test_school_capacity_calculation(self):
        engine = CapacityEngine()
        # 120 spare seats => 120 / 1.2 = 100 HH
        assert engine.calculate_school_capacity(120) == 100
        # 0 spare seats => 0 HH
        assert engine.calculate_school_capacity(0) == 0
        # Negative => 0 HH
        assert engine.calculate_school_capacity(-10) == 0

    def test_health_capacity_calculation(self):
        engine = CapacityEngine()
        # Hilly / tribal norm: 20,000. Catchment: 15,500. Spare: 4,500.
        # 4,500 / 4.5 = 1,000 HH.
        assert engine.calculate_health_capacity(catchment_pop=15500, is_hilly_or_tribal=True) == 1000

        # Plain norm: 30,000. Catchment: 25,500. Spare: 4,500 => 1,000 HH.
        assert engine.calculate_health_capacity(catchment_pop=25500, is_hilly_or_tribal=False) == 1000

        # Oversubscribed catchment => 0 HH
        assert engine.calculate_health_capacity(catchment_pop=35000) == 0


class TestBottleneckAndTieBreaking:
    """Tests for strict bottleneck principle and deterministic tie-breaking."""

    def test_bottleneck_minimum_rule_no_averaging(self):
        engine = CapacityEngine()
        # Land: 500, Water: 100, School: 300, Health: 800 => min is Water (100)
        # Final capacity must be 100, never an average of 425!
        final_cc, binding, tied = engine.calculate_final_capacity(
            cc_land=500, cc_water=100, cc_school=300, cc_health=800, livelihood_multiplier=1.0
        )
        assert final_cc == 100
        assert binding == BindingConstraint.WATER
        assert tied == [BindingConstraint.WATER]

    def test_deterministic_tie_breaking_order(self):
        engine = CapacityEngine()
        # Deterministic hierarchy: LAND > WATER > SCHOOL > HEALTH

        # Case 1: Land and Water tied at 100 => LAND breaks tie
        _, b1, t1 = engine.calculate_final_capacity(100, 100, 300, 400)
        assert b1 == BindingConstraint.LAND
        assert t1 == [BindingConstraint.LAND, BindingConstraint.WATER]

        # Case 2: Water and Health tied at 100 => WATER breaks tie
        _, b2, t2 = engine.calculate_final_capacity(500, 100, 300, 100)
        assert b2 == BindingConstraint.WATER
        assert t2 == [BindingConstraint.WATER, BindingConstraint.HEALTH]

        # Case 3: School and Health tied at 100 => SCHOOL breaks tie
        _, b3, t3 = engine.calculate_final_capacity(500, 500, 100, 100)
        assert b3 == BindingConstraint.SCHOOL
        assert t3 == [BindingConstraint.SCHOOL, BindingConstraint.HEALTH]

        # Case 4: All four tied at 100 => LAND breaks tie
        _, b4, t4 = engine.calculate_final_capacity(100, 100, 100, 100)
        assert b4 == BindingConstraint.LAND
        assert len(t4) == 4

    def test_livelihood_multiplier_scaling(self):
        engine = CapacityEngine()
        # Land: 100 (bottleneck), livelihood multiplier = 0.80 => 80 HH
        final_cc, _, _ = engine.calculate_final_capacity(100, 300, 400, 500, livelihood_multiplier=0.80)
        assert final_cc == 80


class TestAugmentedCapacity:
    """Tests for augmented carrying capacity assessment when relieving bottlenecks."""

    def test_augmented_water_bottleneck(self):
        engine = CapacityEngine()
        # Land: 500, Water: 100 (binding), School: 300, Health: 800
        # If Water is relieved, next constraint is School (300)
        aug = engine.calculate_augmented_capacity(
            cc_land=500, cc_water=100, cc_school=300, cc_health=800, binding_constraint=BindingConstraint.WATER
        )
        assert aug.relieved_constraint == BindingConstraint.WATER
        assert aug.augmented_capacity == 300
        assert aug.next_binding_constraint == BindingConstraint.SCHOOL
        assert "piped water supply" in aug.indicative_intervention.lower()
        assert aug.indicative_cost_inr_lakhs is None  # Unfabricated cost

    def test_augmented_land_bottleneck(self):
        engine = CapacityEngine()
        # Land: 100 (binding), Water: 250, School: 300, Health: 800
        aug = engine.calculate_augmented_capacity(
            cc_land=100, cc_water=250, cc_school=300, cc_health=800, binding_constraint=BindingConstraint.LAND
        )
        assert aug.relieved_constraint == BindingConstraint.LAND
        assert aug.augmented_capacity == 250
        assert aug.next_binding_constraint == BindingConstraint.WATER


class TestCandidateSiteEligibilityAndHardening:
    """Tests for site screening, static MHI rules, and missing data hardening."""

    def test_eligible_site(self):
        engine = CapacityEngine()
        res = engine.evaluate_site_eligibility(
            area_ha=5.0,
            slope_mean=6.5,
            mhi_static=0.08,
            tenure=TenureType.GOVERNMENT_REVENUE,
        )
        assert res.is_eligible is True
        assert len(res.exclusion_reasons) == 0

    def test_ineligible_excessive_slope(self):
        engine = CapacityEngine()
        res = engine.evaluate_site_eligibility(
            area_ha=5.0,
            slope_mean=18.5,  # > 15 deg threshold
            mhi_static=0.08,
            tenure=TenureType.GOVERNMENT_REVENUE,
        )
        assert res.is_eligible is False
        assert any("slope" in r.lower() for r in res.exclusion_reasons)

    def test_ineligible_static_mhi_threshold(self):
        engine = CapacityEngine()
        # Static MHI >= 0.25 is rejected
        res = engine.evaluate_site_eligibility(
            area_ha=5.0,
            slope_mean=5.0,
            mhi_static=0.35,
            tenure=TenureType.GOVERNMENT_REVENUE,
        )
        assert res.is_eligible is False
        assert any("static mhi" in r.lower() for r in res.exclusion_reasons)

    def test_ineligible_missing_mhi_not_assumed_safe(self):
        engine = CapacityEngine()
        # Missing MHI data must NOT be assumed safe (0.0)
        res = engine.evaluate_site_eligibility(
            area_ha=5.0,
            slope_mean=5.0,
            mhi_static=None,  # Missing MHI
            tenure=TenureType.GOVERNMENT_REVENUE,
        )
        assert res.is_eligible is False
        assert any("mhi" in r.lower() and "missing" in r.lower() for r in res.exclusion_reasons)

    def test_ineligible_missing_slope_not_assumed_flat(self):
        engine = CapacityEngine()
        # Missing slope data must NOT be assumed flat (0.0)
        res = engine.evaluate_site_eligibility(
            area_ha=5.0,
            slope_mean=None,  # Missing slope
            mhi_static=0.05,
            tenure=TenureType.GOVERNMENT_REVENUE,
        )
        assert res.is_eligible is False
        assert any("slope" in r.lower() and "missing" in r.lower() for r in res.exclusion_reasons)

    def test_ineligible_undersized_area(self):
        engine = CapacityEngine()
        res = engine.evaluate_site_eligibility(
            area_ha=1.2,  # < 2.0 ha threshold
            slope_mean=5.0,
            mhi_static=0.05,
            tenure=TenureType.GOVERNMENT_REVENUE,
        )
        assert res.is_eligible is False
        assert any("contiguous area" in r.lower() for r in res.exclusion_reasons)

    def test_data_quality_tracking_with_missing_inputs(self):
        engine = CapacityEngine()
        res = engine.evaluate_site_capacity(
            area_developable_m2=50000.0,
            water_yield_liters_per_day=None,  # missing water data
            spare_school_seats=120,
            spare_health_capacity_pop=4500,
        )
        assert res.data_quality == CapacityDataQuality.PARTIAL
        assert len(res.data_gaps) == 1
        assert "Water" in res.data_gaps[0]
        assert res.cc_water is None
        # Missing water should NOT collapse capacity to 0!
        # cc_land = 396, cc_school = 100, cc_health = 1000 => bottleneck is School (100)
        assert res.cc_final == 100
        assert res.binding_constraint == BindingConstraint.SCHOOL

    def test_day7_scenario_readiness_on_same_engine(self):
        """Confirms that the exact same CapacityEngine can evaluate baseline and scenario overrides without duplicate math."""
        engine = CapacityEngine()
        area_m2 = 50000.0  # 5 ha

        # Baseline: 90 m2 plot => 396 HH
        baseline_land = engine.calculate_land_capacity(area_m2)
        assert baseline_land == 396

        # Scenario: 120 m2 plot override => 297 HH
        scenario_land = engine.calculate_land_capacity(area_m2, plot_area_m2=120.0)
        assert scenario_land == 297

        delta = scenario_land - baseline_land
        assert delta == -99
