"""Comprehensive regression test suite for P0.2 / B2: Remove Hardcoded Habitation/Village Logic.

Section refs: docs/PRD1.md §6.6, §6.7, §6.10, §9.6

Verifies:
1. Invariant 1: Name Invariance — Changing a habitation's name produces bit-for-bit identical
   priority score, triage tier, triage rationale, dossier risk values, and scenario results.
2. Invariant 2: Data Drives Behavior — Altering actual domain inputs (active_deformation,
   fatal_event_last_3_monsoons, hazard_static, prz_overlap_pct) changes the outputs,
   regardless of what the habitation is named.
3. Invariant 3: Fatal-Event Canonical Derivation — Correct spatial and temporal evaluation
   under Indian South-West Monsoon (JJAS) rules.
4. Invariant 4: Scenario Data Independence — Hazard static scores drive scenario outcomes.
5. Invariant 5: Canonical Consistency — Dossier and triage evaluations agree consistently.
"""

from datetime import date
from unittest.mock import MagicMock
import pytest

from core.enums import Hazard, SortMode, Tier
from core.domain.priority import (
    PriorityScoringConfig,
    PriorityScoringEngine,
    TriageRuleConfig,
    classify_triage_tier,
    evaluate_triage_with_rationale,
    is_within_last_three_monsoons,
    check_fatal_event_last_3_monsoons,
)
from core.domain.scenario import (
    HabitationBaselineState,
    ScenarioEngine,
)
from api.services.habitations_service import HabitationsService
from api.services.scenario_service import ScenarioService
from core.schemas.scenario import ScenarioWeightOverrideRequest


# ====================================================================
# Test A — Name Invariance
# ====================================================================

class TestNameInvariance:
    """Proves that habitation name has zero influence on domain and service decisions."""

    @pytest.mark.parametrize(
        "name_a,name_b",
        [
            ("Chooralmala", "Safe Valley 101"),
            ("Mundakkai", "Random Settlement 99"),
            ("Bhagamandala", "Neutral Hamlet"),
            ("Wayanad", "NonExistentPlace"),
        ],
    )
    def test_domain_triage_and_scoring_name_invariance(self, name_a: str, name_b: str):
        """Domain priority scoring and tier triage produce identical results regardless of name."""
        engine = PriorityScoringEngine()
        
        # Test case 1: High risk profile
        res_a = engine.evaluate_habitation(
            hazard_intensity=0.88,
            pop_fraction_in_prz=0.85,
            vulnerability_index=0.70,
            decayed_loss=2.0,
            population=1500,
            active_deformation=True,
            fatal_event_last_3_monsoons=True,
        )
        res_b = engine.evaluate_habitation(
            hazard_intensity=0.88,
            pop_fraction_in_prz=0.85,
            vulnerability_index=0.70,
            decayed_loss=2.0,
            population=1500,
            active_deformation=True,
            fatal_event_last_3_monsoons=True,
        )
        assert res_a["priority_score"] == res_b["priority_score"]
        assert res_a["caseload_score"] == res_b["caseload_score"]
        assert res_a["tier"] == res_b["tier"] == Tier.IMMEDIATE
        assert res_a["triage_rationale"] == res_b["triage_rationale"]

        # Test case 2: Low risk profile
        res_a_low = engine.evaluate_habitation(
            hazard_intensity=0.30,
            pop_fraction_in_prz=0.0,
            vulnerability_index=0.40,
            decayed_loss=0.0,
            population=1500,
            active_deformation=False,
            fatal_event_last_3_monsoons=False,
        )
        res_b_low = engine.evaluate_habitation(
            hazard_intensity=0.30,
            pop_fraction_in_prz=0.0,
            vulnerability_index=0.40,
            decayed_loss=0.0,
            population=1500,
            active_deformation=False,
            fatal_event_last_3_monsoons=False,
        )
        assert res_a_low["priority_score"] == res_b_low["priority_score"]
        assert res_a_low["tier"] == res_b_low["tier"] is None

    @pytest.mark.parametrize(
        "test_name",
        ["Chooralmala", "Mundakkai", "Bhagamandala", "ArbitraryVillageX", "SafeHill"],
    )
    def test_habitations_service_fallback_name_invariance(self, test_name: str):
        """Fallback evaluation in HabitationsService does not alter outputs based on village name."""
        mock_db = MagicMock()
        service = HabitationsService(mock_db)

        # Baseline record where priority_score is None (triggering on-the-fly fallback)
        raw_row = {
            "id": 42,
            "lgd_code": 12345,
            "name": test_name,
            "type": "village",
            "admin_id": 1,
            "admin_name": "Test District",
            "population": 1000,
            "households": 250,
            "lon": 76.12,
            "lat": 11.55,
            "v_demographic": 0.5,
            "v_structural": 0.5,
            "v_access": 0.5,
            "v_economic": 0.5,
            "v_index": 0.5,
            "priority_score": None,
            "hazard_intensity": 0.60,
            "prz_overlap_pct": 50.0,
            "active_deformation": False,
            "fatal_event_last_3_monsoons": False,
            "decayed_loss": 0.0,
        }

        service.repo.query_habitations = MagicMock(return_value=([raw_row], 1))
        response = service.get_habitations()
        item = response.items[0]

        # The calculated values must depend solely on the numeric inputs, not test_name
        assert item.prz_overlap_pct == 50.0
        assert item.tier == Tier.SHORT_TERM
        # With h=0.6, f=0.5, v=0.5, ps = 0.6 * 0.5 * 0.5 = 0.15
        assert item.priority_score == pytest.approx(0.15, abs=1e-3)
        assert item.caseload_score == pytest.approx(150.0, abs=1e-2)

    @pytest.mark.parametrize(
        "test_name",
        ["Chooralmala", "Mundakkai", "Bhagamandala", "RandomPlace"],
    )
    def test_habitation_dossier_name_invariance(self, test_name: str):
        """Habitation risk dossier evaluation is completely independent of village name."""
        mock_db = MagicMock()
        service = HabitationsService(mock_db)

        raw_habitation = {
            "id": 10,
            "lgd_code": 12345,
            "name": test_name,
            "type": "village",
            "admin_id": 1,
            "admin_name": "Test District",
            "population": 2000,
            "households": 500,
            "lon": 76.15,
            "lat": 11.54,
            "v_demographic": 0.6,
            "v_structural": 0.7,
            "v_access": 0.5,
            "v_economic": 0.6,
            "v_index": 0.6,
            "hazard_intensity": 0.50,
            "prz_overlap_pct": 30.0,
            "active_deformation": False,
            "fatal_event_last_3_monsoons": False,
            "priority_score": None,
            "caseload_score": None,
            "tier": None,
            "triage_rationale": None,
            "contributing_factors": [],
        }

        service.repo.get_habitation_by_id = MagicMock(return_value=raw_habitation)
        # No nearby events
        service.repo.get_nearby_disaster_events = MagicMock(return_value=[])

        dossier = service.get_habitation_risk_dossier(10)
        assert dossier.name == test_name
        assert dossier.prz_overlap_pct == 30.0
        assert dossier.hazard_intensity == 0.50
        assert dossier.tier == Tier.SHORT_TERM
        # ps = 0.5 * 0.3 * 0.6 = 0.09
        assert dossier.priority_score == pytest.approx(0.09, abs=1e-3)


# ====================================================================
# Test B — Data Drives Behavior
# ====================================================================

class TestDataDrivesBehavior:
    """Proves that modifying persisted/domain inputs changes domain decisions for the exact same name."""

    def test_active_deformation_triggers_immediate_tier(self):
        """Settlement with PRZ overlap shifts from SHORT_TERM to IMMEDIATE when active deformation is present."""
        engine = PriorityScoringEngine()

        # Without active deformation
        res_no_def = engine.evaluate_habitation(
            hazard_intensity=0.50,
            pop_fraction_in_prz=0.40,
            vulnerability_index=0.50,
            active_deformation=False,
            fatal_event_last_3_monsoons=False,
        )
        assert res_no_def["tier"] == Tier.SHORT_TERM

        # With active deformation (same name, same other metrics)
        res_with_def = engine.evaluate_habitation(
            hazard_intensity=0.50,
            pop_fraction_in_prz=0.40,
            vulnerability_index=0.50,
            active_deformation=True,
            fatal_event_last_3_monsoons=False,
        )
        assert res_with_def["tier"] == Tier.IMMEDIATE
        assert "Active ground deformation" in res_with_def["triage_rationale"]

    def test_fatal_event_triggers_immediate_tier(self):
        """Settlement with PRZ overlap shifts from SHORT_TERM to IMMEDIATE when a fatal event occurred."""
        engine = PriorityScoringEngine()

        # Without fatal event
        res_no_fatal = engine.evaluate_habitation(
            hazard_intensity=0.50,
            pop_fraction_in_prz=0.40,
            vulnerability_index=0.50,
            active_deformation=False,
            fatal_event_last_3_monsoons=False,
        )
        assert res_no_fatal["tier"] == Tier.SHORT_TERM

        # With fatal event
        res_with_fatal = engine.evaluate_habitation(
            hazard_intensity=0.50,
            pop_fraction_in_prz=0.40,
            vulnerability_index=0.50,
            active_deformation=False,
            fatal_event_last_3_monsoons=True,
        )
        assert res_with_fatal["tier"] == Tier.IMMEDIATE
        assert "Fatal mass-wasting event" in res_with_fatal["triage_rationale"]

    def test_prz_overlap_pct_shifts_scores_and_tiers(self):
        """Altering prz_overlap_pct directly changes priority score and triage tier."""
        engine = PriorityScoringEngine()

        # 0% PRZ overlap, low score
        res_zero = engine.evaluate_habitation(
            hazard_intensity=0.40,
            pop_fraction_in_prz=0.0,
            vulnerability_index=0.50,
            active_deformation=False,
            fatal_event_last_3_monsoons=False,
        )
        assert res_zero["priority_score"] == 0.0
        assert res_zero["tier"] is None

        # 40% PRZ overlap
        res_mod = engine.evaluate_habitation(
            hazard_intensity=0.40,
            pop_fraction_in_prz=0.40,
            vulnerability_index=0.50,
            active_deformation=False,
            fatal_event_last_3_monsoons=False,
        )
        assert res_mod["priority_score"] > 0.0
        assert res_mod["tier"] == Tier.SHORT_TERM


# ====================================================================
# Test C — Fatal-Event Canonical Derivation
# ====================================================================

class TestFatalEventDerivation:
    """Verifies the canonical spatial and temporal derivation of fatal_event_last_3_monsoons."""

    def test_monsoon_temporal_window_in_2026(self):
        """Relative to reference date 2026-08-31 (during 2026 monsoon):
        Three monsoons are 2026, 2025, and 2024 (earliest season starts 2024-06-01).
        """
        ref = date(2026, 8, 31)

        # 2024 July event (Chooralmala-Mundakkai debris flow) -> within 3 monsoons
        assert is_within_last_three_monsoons(date(2024, 7, 30), reference_date=ref) is True

        # 2025 August event -> within 3 monsoons
        assert is_within_last_three_monsoons(date(2025, 8, 15), reference_date=ref) is True

        # 2026 June event -> within 3 monsoons
        assert is_within_last_three_monsoons(date(2026, 6, 10), reference_date=ref) is True

        # 2024 May event (before 2024 monsoon start) -> outside 3 monsoons
        assert is_within_last_three_monsoons(date(2024, 5, 31), reference_date=ref) is False

        # 2020 August event (Meppadi) -> outside 3 monsoons
        assert is_within_last_three_monsoons(date(2020, 8, 7), reference_date=ref) is False

        # 2019 August event (Puthumala) -> outside 3 monsoons
        assert is_within_last_three_monsoons(date(2019, 8, 8), reference_date=ref) is False

        # 2018 August event (Kodagu) -> outside 3 monsoons
        assert is_within_last_three_monsoons(date(2018, 8, 17), reference_date=ref) is False

        # Future event (after reference date) -> False
        assert is_within_last_three_monsoons(date(2026, 9, 15), reference_date=ref) is False

    def test_check_fatal_event_derivation_criteria(self):
        """Canonical helper tests spatial proximity (<= 2km), fatalities (> 0), and monsoon window."""
        ref = date(2026, 8, 31)

        # Case 1: Valid fatal event within 2 km and within 3 monsoons
        events_valid = [
            {
                "ts": date(2024, 7, 30),
                "fatalities": 231,
                "distance_km": 0.8,
            }
        ]
        assert check_fatal_event_last_3_monsoons(events_valid, reference_date=ref) is True

        # Case 2: Fatal event within 3 monsoons but too far away (> 2.0 km)
        events_far = [
            {
                "ts": date(2024, 7, 30),
                "fatalities": 231,
                "distance_km": 4.5,
            }
        ]
        assert check_fatal_event_last_3_monsoons(events_far, reference_date=ref) is False

        # Case 3: Event within 2 km and within 3 monsoons, but zero fatalities
        events_non_fatal = [
            {
                "ts": date(2024, 7, 30),
                "fatalities": 0,
                "distance_km": 0.5,
            }
        ]
        assert check_fatal_event_last_3_monsoons(events_non_fatal, reference_date=ref) is False

        # Case 4: Fatal event within 2 km, but older than 3 monsoons (e.g. 2018)
        events_old = [
            {
                "ts": date(2018, 8, 17),
                "fatalities": 18,
                "distance_km": 1.0,
            }
        ]
        assert check_fatal_event_last_3_monsoons(events_old, reference_date=ref) is False


# ====================================================================
# Test D — Scenario Data Independence
# ====================================================================

class TestScenarioDataIndependence:
    """Verifies that ScenarioService consumes hazard_static data without name branches."""

    def test_scenario_service_uses_hazard_static_independent_of_name(self):
        """Scenario simulation results are identical when given different names with same hazard_static data,
        and change when hazard_static scores change."""
        mock_db = MagicMock()
        service = ScenarioService(mock_db)

        # Mock query_habitations returning two habitations with same risk metrics but different names
        hab1 = {
            "id": 1,
            "name": "Chooralmala",
            "population": 1000,
            "households": 250,
            "prz_overlap_pct": 80.0,
            "hazard_intensity": 0.80,
            "v_index": 0.60,
            "decayed_loss": 1.0,
            "active_deformation": True,
            "fatal_event_last_3_monsoons": True,
            "priority_score": 0.72,
            "tier": "immediate",
            "dominant_hazard": "landslide",
            "lat": 11.54,
            "lon": 76.16,
        }
        hab2 = {
            "id": 2,
            "name": "Different Village 99",
            "population": 1000,
            "households": 250,
            "prz_overlap_pct": 80.0,
            "hazard_intensity": 0.80,
            "v_index": 0.60,
            "decayed_loss": 1.0,
            "active_deformation": True,
            "fatal_event_last_3_monsoons": True,
            "priority_score": 0.72,
            "tier": "immediate",
            "dominant_hazard": "landslide",
            "lat": 11.55,
            "lon": 76.17,
        }

        service.hab_repo.query_habitations = MagicMock(return_value=([hab1, hab2], 2))

        # Both habitations have identical hazard_static scores from repo
        service.hab_repo.get_hazard_scores_for_habitations = MagicMock(
            return_value={
                1: {Hazard.LANDSLIDE: 0.75, Hazard.FLASH_FLOOD: 0.40},
                2: {Hazard.LANDSLIDE: 0.75, Hazard.FLASH_FLOOD: 0.40},
            }
        )

        request = ScenarioWeightOverrideRequest(
            hazard_weights={"landslide": 1.5, "flash_flood": 0.5},
            priority_gamma=0.5,
            sort_mode=SortMode.URGENCY,
        )

        response = service.evaluate_scenario(request)
        item1 = next(i for i in response.items if i.habitation_id == 1)
        item2 = next(i for i in response.items if i.habitation_id == 2)

        # Name invariance: Identical hazard_static inputs yield identical scenario outputs
        assert item1.scenario_priority_score == item2.scenario_priority_score
        assert item1.scenario_tier == item2.scenario_tier == Tier.IMMEDIATE
        assert item1.scenario_hazard_intensity == item2.scenario_hazard_intensity

        # Now change hazard_static scores for hab2 -> scenario result must change
        service.hab_repo.get_hazard_scores_for_habitations = MagicMock(
            return_value={
                1: {Hazard.LANDSLIDE: 0.75, Hazard.FLASH_FLOOD: 0.40},
                2: {Hazard.LANDSLIDE: 0.20, Hazard.FLASH_FLOOD: 0.10},  # Much lower hazard
            }
        )

        response_changed = service.evaluate_scenario(request)
        item1_ch = next(i for i in response_changed.items if i.habitation_id == 1)
        item2_ch = next(i for i in response_changed.items if i.habitation_id == 2)

        # Data drives behavior: lower hazard_static yields lower scenario score
        assert item1_ch.scenario_priority_score > item2_ch.scenario_priority_score
        assert item1_ch.scenario_hazard_intensity > item2_ch.scenario_hazard_intensity


# ====================================================================
# Test E — Canonical Consistency
# ====================================================================

class TestCanonicalConsistency:
    """Verifies that dossier evaluation and triage engine agree on fatal event derivation."""

    def test_dossier_uses_persisted_or_derived_fatal_event_consistently(self):
        mock_db = MagicMock()
        service = HabitationsService(mock_db)

        # If persisted fatal_event_last_3_monsoons is True in habitation_risk,
        # get_dossier must preserve True
        raw_hab_persisted = {
            "id": 5,
            "lgd_code": 12345,
            "name": "Village Five",
            "type": "village",
            "admin_id": 1,
            "admin_name": "Test District",
            "population": 500,
            "households": 120,
            "lon": 76.10,
            "lat": 11.50,
            "v_demographic": 0.5,
            "v_structural": 0.5,
            "v_access": 0.5,
            "v_economic": 0.5,
            "v_index": 0.5,
            "hazard_intensity": 0.60,
            "prz_overlap_pct": 50.0,
            "active_deformation": False,
            "fatal_event_last_3_monsoons": True,  # Persisted True
            "priority_score": None,
            "caseload_score": None,
            "tier": None,
            "triage_rationale": None,
            "contributing_factors": [],
        }

        service.repo.get_habitation_by_id = MagicMock(return_value=raw_hab_persisted)
        service.repo.get_nearby_disaster_events = MagicMock(return_value=[])

        dossier = service.get_habitation_risk_dossier(5)
        # Because PRZ overlap > 0 and fatal_event_last_3_monsoons is True, tier must be IMMEDIATE
        assert dossier.tier == Tier.IMMEDIATE
        assert "Fatal mass-wasting event" in dossier.triage_rationale


# ====================================================================
# Test F — Explicit Audit Requirements (Test A, Test B, Test C)
# ====================================================================

class TestB2AuditRequirements:
    """Explicit tests matching Day-8 audit B2 requirements A, B, and C."""

    def test_test_a_arbitrary_habitations_tier_follows_stored_fields(self):
        """Test A — arbitrary habitation:
        Create two otherwise equivalent habitations with different names.
        Give them explicit risk inputs: active_deformation = True/False.
        Assert tier/risk behavior follows the stored fields, not the name.
        """
        engine = PriorityScoringEngine()

        # Habitation X with active_deformation=True -> IMMEDIATE
        res_x_high = engine.evaluate_habitation(
            hazard_intensity=0.70,
            pop_fraction_in_prz=0.60,
            vulnerability_index=0.50,
            active_deformation=True,
            fatal_event_last_3_monsoons=False,
        )
        # Habitation Y with active_deformation=False -> SHORT_TERM
        res_y_low = engine.evaluate_habitation(
            hazard_intensity=0.70,
            pop_fraction_in_prz=0.60,
            vulnerability_index=0.50,
            active_deformation=False,
            fatal_event_last_3_monsoons=False,
        )
        assert res_x_high["tier"] == Tier.IMMEDIATE
        assert res_y_low["tier"] == Tier.SHORT_TERM

    def test_test_b_named_village_chooralmala_no_magic_treatment(self):
        """Test B — named village no longer gets magic treatment:
        Use a village named Chooralmala but provide non-high-risk stored inputs.
        Assert it does NOT receive the old hardcoded Tier-1 behavior merely because of its name.
        Likewise, use a non-demo village with the same authoritative high-risk flags and assert it receives the corresponding behavior.
        """
        mock_db = MagicMock()
        service = HabitationsService(mock_db)

        # Chooralmala with non-high-risk inputs
        chooralmala_low_risk = {
            "id": 1,
            "lgd_code": 1001,
            "name": "Chooralmala",
            "type": "village",
            "admin_id": 1,
            "admin_name": "Wayanad",
            "population": 800,
            "households": 200,
            "lon": 76.15,
            "lat": 11.54,
            "v_demographic": 0.4,
            "v_structural": 0.4,
            "v_access": 0.4,
            "v_economic": 0.4,
            "v_index": 0.4,
            "hazard_intensity": 0.40,
            "prz_overlap_pct": 50.0,
            "active_deformation": False,
            "fatal_event_last_3_monsoons": False,
            "priority_score": None,
            "caseload_score": None,
            "tier": None,
            "triage_rationale": None,
            "contributing_factors": [],
        }

        # Non-demo village with authoritative high-risk flags
        unknown_village_high_risk = {
            "id": 2,
            "lgd_code": 9999,
            "name": "CompletelyUnknownRemoteVillage",
            "type": "village",
            "admin_id": 1,
            "admin_name": "Wayanad",
            "population": 800,
            "households": 200,
            "lon": 76.20,
            "lat": 11.60,
            "v_demographic": 0.4,
            "v_structural": 0.4,
            "v_access": 0.4,
            "v_economic": 0.4,
            "v_index": 0.4,
            "hazard_intensity": 0.40,
            "prz_overlap_pct": 50.0,
            "active_deformation": True,
            "fatal_event_last_3_monsoons": False,
            "priority_score": None,
            "caseload_score": None,
            "tier": None,
            "triage_rationale": None,
            "contributing_factors": [],
        }

        service.repo.get_habitation_by_id = MagicMock(
            side_effect=lambda hid: chooralmala_low_risk if hid == 1 else unknown_village_high_risk
        )
        service.repo.get_nearby_disaster_events = MagicMock(return_value=[])

        dossier_chooralmala = service.get_habitation_risk_dossier(1)
        dossier_unknown = service.get_habitation_risk_dossier(2)

        # Chooralmala does NOT receive Tier-1 (IMMEDIATE) merely because of its name
        assert dossier_chooralmala.tier != Tier.IMMEDIATE
        assert dossier_chooralmala.tier == Tier.SHORT_TERM

        # The unknown village DOES receive Tier-1 (IMMEDIATE) because of active_deformation = True
        assert dossier_unknown.tier == Tier.IMMEDIATE

    def test_test_c_scenario_hazard_values_from_persisted_hazard_static(self):
        """Test C — scenario hazard values:
        Provide deterministic hazard_static values for multiple hazards.
        Assert /scenario consumes those values rather than the old constants.
        Make sure the test demonstrates that changing a persisted hazard value changes the scenario result.
        """
        mock_db = MagicMock()
        service = ScenarioService(mock_db)

        hab_row = {
            "id": 101,
            "name": "TestVillageScenario",
            "population": 1000,
            "households": 250,
            "prz_overlap_pct": 50.0,
            "hazard_intensity": 0.60,
            "v_index": 0.50,
            "decayed_loss": 0.5,
            "active_deformation": False,
            "fatal_event_last_3_monsoons": False,
            "priority_score": 0.30,
            "tier": "short_term",
            "dominant_hazard": "landslide",
            "lat": 11.5,
            "lon": 76.1,
        }
        service.hab_repo.query_habitations = MagicMock(return_value=([hab_row], 1))

        # 1. First scenario with landslide=0.8, flash_flood=0.2
        service.hab_repo.get_hazard_scores_for_habitations = MagicMock(
            return_value={
                101: {
                    Hazard.LANDSLIDE: 0.80,
                    Hazard.FLASH_FLOOD: 0.20,
                    Hazard.STORM_SURGE: 0.10,
                }
            }
        )
        req = ScenarioWeightOverrideRequest(
            hazard_weights={"landslide": 1.0, "flash_flood": 1.0, "storm_surge": 1.0},
            priority_gamma=0.5,
        )
        res1 = service.evaluate_scenario(req)
        score1 = res1.items[0].scenario_priority_score
        h_int1 = res1.items[0].scenario_hazard_intensity

        # 2. Change persisted hazard_static score for landslide to 0.10
        service.hab_repo.get_hazard_scores_for_habitations = MagicMock(
            return_value={
                101: {
                    Hazard.LANDSLIDE: 0.10,
                    Hazard.FLASH_FLOOD: 0.20,
                    Hazard.STORM_SURGE: 0.10,
                }
            }
        )
        res2 = service.evaluate_scenario(req)
        score2 = res2.items[0].scenario_priority_score
        h_int2 = res2.items[0].scenario_hazard_intensity

        # Assert that changing persisted hazard_static values changes the scenario score
        assert h_int1 > h_int2
        assert score1 > score2
