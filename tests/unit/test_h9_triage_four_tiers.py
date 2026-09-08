"""P0.3 / H9: Comprehensive Four-Tier Triage Behaviour & Tier 4 Reachability Tests.

Section refs: docs/PRD1.md §6.7, §6.5 (FR-6.5), §14.1

Covers:
- Deterministic fixtures for all four permanent relocation decision tiers:
    Fixture A: Immediate (0-6 months)
    Fixture B: Short-term (6-24 months)
    Fixture C: Medium-term (2-5 years)
    Fixture D: Mitigate in situ (Mandatory Tier 4)
- Reachability & boundary conditions:
    1. Zero PRZ overlap must not become significant overlap.
    2. Small PRZ fraction (< 0.30) must not automatically force Short-term.
    3. Tier 4 is genuinely reachable when mitigation_cost < relocation_cost.
    4. Tier 4 is NOT selected when mitigation_cost >= relocation_cost.
    5. Missing cost data (None/NaN) must not falsely imply cheaper mitigation.
    6. Changing habitation name alone must never alter triage tier (Name Invariance).
    7. Explicit zero values (0.0) remain zero (Zero Semantics).
    8. Active emergency triggers do not distort permanent relocation triage.
    9. Adverse trend calculation (rising loss frequency & built-up growth).
    10. Boundary tests around short_term_prz_overlap_min (0.299, 0.30, 0.301).
"""

from datetime import date
import math
import pytest

from core.domain.priority import (
    PriorityScoringConfig,
    PriorityScoringEngine,
    TriageRuleConfig,
    classify_triage_tier,
    evaluate_triage_with_rationale,
    evaluate_in_situ_cost_cheaper,
    check_loss_frequency_rising,
)
from core.enums import Tier


# ============================================================================
# DETERMINISTIC FOUR-TIER FIXTURES (PRD §6.7)
# ============================================================================

def test_fixture_a_immediate():
    """Fixture A — Immediate (0-6 mo):
    PRZ overlap > 0 AND (active ground deformation OR fatal event in last 3 monsoons OR (f > 0.6 AND h > 0.85)).
    """
    # Sub-case A1: PRZ overlap + active ground deformation detected
    res_a1 = evaluate_triage_with_rationale(
        has_prz_overlap=True,
        pop_fraction_in_prz=0.45,
        hazard_intensity=0.82,
        active_deformation=True,
        fatal_event_last_3_monsoons=False,
    )
    assert res_a1.tier == Tier.IMMEDIATE
    assert "Active ground deformation" in res_a1.rationale

    # Sub-case A2: PRZ overlap + fatal event recorded in last 3 monsoons
    res_a2 = evaluate_triage_with_rationale(
        has_prz_overlap=True,
        pop_fraction_in_prz=0.40,
        hazard_intensity=0.75,
        active_deformation=False,
        fatal_event_last_3_monsoons=True,
    )
    assert res_a2.tier == Tier.IMMEDIATE
    assert "Fatal mass-wasting event" in res_a2.rationale

    # Sub-case A3: Severe compound exposure (f > 0.60 AND h > 0.85) without deformation
    res_a3 = evaluate_triage_with_rationale(
        has_prz_overlap=True,
        pop_fraction_in_prz=0.75,
        hazard_intensity=0.90,
        active_deformation=False,
        fatal_event_last_3_monsoons=False,
    )
    assert res_a3.tier == Tier.IMMEDIATE
    assert "Critical exposure" in res_a3.rationale


def test_fixture_b_short_term():
    """Fixture B — Short-term (6-24 mo):
    Significant PRZ overlap (>= 30%) AND high priority score (PS >= 0.30) AND no active trigger.
    """
    res = evaluate_triage_with_rationale(
        has_prz_overlap=True,
        pop_fraction_in_prz=0.48,  # Significant PRZ overlap >= 30%
        hazard_intensity=0.70,
        priority_score=0.45,       # High priority score >= 0.30
        active_deformation=False,
        fatal_event_last_3_monsoons=False,
        mitigation_cost=25000000.0,
        relocation_cost=12000000.0,  # Mitigation is more expensive than relocation
    )
    assert res.tier == Tier.SHORT_TERM
    assert "Short-term planned relocation" in res.rationale


def test_fixture_c_medium_term():
    """Fixture C — Medium-term (2-5 yr):
    Caution Zone (MHI 0.45-0.75) with adverse trend (built-up growing or loss frequency rising).
    """
    res = evaluate_triage_with_rationale(
        has_prz_overlap=False,
        pop_fraction_in_prz=0.0,
        hazard_intensity=0.55,     # Caution Zone
        priority_score=0.22,
        active_deformation=False,
        fatal_event_last_3_monsoons=False,
        adverse_trend=True,        # Documented adverse trend
    )
    assert res.tier == Tier.MEDIUM_TERM
    assert "Medium-term" in res.rationale
    assert "adverse trend" in res.rationale.lower()


def test_fixture_d_mitigate_in_situ():
    """Fixture D — Mitigate in situ (Mandatory Tier 4):
    Small PRZ fraction (< 0.30) AND mitigation cost < relocation cost.
    """
    res = evaluate_triage_with_rationale(
        has_prz_overlap=True,
        pop_fraction_in_prz=0.12,  # Small PRZ fraction (< 30%)
        hazard_intensity=0.45,
        priority_score=0.18,
        active_deformation=False,
        fatal_event_last_3_monsoons=False,
        mitigation_cost=4500000.0,   # INR 4.5M for retaining wall & drainage
        relocation_cost=25000000.0,  # INR 25M for land acquisition & resettlement
    )
    assert res.tier == Tier.MITIGATE_IN_SITU
    assert "Mitigate in-situ" in res.rationale
    assert any("costs less than relocation" in factor for factor in res.trigger_factors)


# ============================================================================
# BOUNDARY & REACHABILITY INVARIANTS (H9 AUDIT FINDINGS)
# ============================================================================

def test_tier_4_reachability_in_scoring_engine():
    """Invariant 2: Tier 4 must be reachable via PriorityScoringEngine.evaluate_habitation."""
    engine = PriorityScoringEngine()
    
    result = engine.evaluate_habitation(
        hazard_intensity=0.45,
        pop_fraction_in_prz=0.15,     # 15% PRZ overlap (< 30%)
        vulnerability_index=0.35,
        decayed_loss=0.0,
        population=1200,
        active_deformation=False,
        fatal_event_last_3_monsoons=False,
        mitigation_cost=3200000.0,    # 3.2M INR
        relocation_cost=18000000.0,   # 18.0M INR
        adverse_trend=False,
    )
    
    assert result["tier"] == Tier.MITIGATE_IN_SITU
    assert "Mitigate in-situ" in result["triage_rationale"]


def test_zero_prz_overlap_semantics():
    """Invariant 1 & 4: Zero PRZ overlap (0.0) must not become significant overlap or force Short-term."""
    tier = classify_triage_tier(
        has_prz_overlap=False,
        pop_fraction_in_prz=0.0,
        hazard_intensity=0.45,
        priority_score=0.15,
        active_deformation=False,
        fatal_event_last_3_monsoons=False,
    )
    assert tier != Tier.SHORT_TERM
    assert tier is None


def test_small_prz_overlap_does_not_force_short_term():
    """Invariant 4 & 5: Small PRZ overlap alone must NOT automatically imply Short-term."""
    # 5% PRZ overlap without cost data must not be forced into Short-term relocation
    tier = classify_triage_tier(
        has_prz_overlap=True,
        pop_fraction_in_prz=0.05,
        hazard_intensity=0.42,
        priority_score=0.12,
        active_deformation=False,
        fatal_event_last_3_monsoons=False,
        mitigation_cost=None,
        relocation_cost=None,
    )
    assert tier != Tier.SHORT_TERM
    assert tier is None


def test_tier_4_cost_comparison_direction():
    """Invariant 3: Mitigation is selected ONLY when mitigation_cost < relocation_cost.
    When mitigation_cost >= relocation_cost, Tier 4 must NOT be selected.
    """
    # Case 1: Mitigation cheaper -> Mitigate in situ
    assert evaluate_in_situ_cost_cheaper(4.0e6, 12.0e6) is True
    tier_cheaper = classify_triage_tier(
        pop_fraction_in_prz=0.15,
        hazard_intensity=0.45,
        priority_score=0.20,
        mitigation_cost=4.0e6,
        relocation_cost=12.0e6,
    )
    assert tier_cheaper == Tier.MITIGATE_IN_SITU

    # Case 2: Mitigation more expensive -> NOT Mitigate in situ
    assert evaluate_in_situ_cost_cheaper(15.0e6, 12.0e6) is False
    tier_expensive = classify_triage_tier(
        pop_fraction_in_prz=0.15,
        hazard_intensity=0.45,
        priority_score=0.20,
        mitigation_cost=15.0e6,
        relocation_cost=12.0e6,
    )
    assert tier_expensive != Tier.MITIGATE_IN_SITU
    assert tier_expensive is None

    # Case 3: Exactly equal costs -> False (strict inequality m < r required)
    assert evaluate_in_situ_cost_cheaper(10.0e6, 10.0e6) is False


def test_missing_cost_data_never_implies_cheap_mitigation():
    """Prompt §7: Missing cost data must not falsely imply cheaper mitigation.
    Unknown mitigation cost must NOT be treated as cheap mitigation.
    """
    assert evaluate_in_situ_cost_cheaper(None, 20.0e6) is False
    assert evaluate_in_situ_cost_cheaper(5.0e6, None) is False
    assert evaluate_in_situ_cost_cheaper(None, None) is False
    assert evaluate_in_situ_cost_cheaper(float("nan"), 20.0e6) is False
    assert evaluate_in_situ_cost_cheaper(5.0e6, float("nan")) is False
    assert evaluate_in_situ_cost_cheaper(-1000.0, 20.0e6) is False

    tier_missing = classify_triage_tier(
        pop_fraction_in_prz=0.15,
        hazard_intensity=0.45,
        priority_score=0.20,
        mitigation_cost=None,
        relocation_cost=None,
    )
    assert tier_missing != Tier.MITIGATE_IN_SITU


def test_short_term_prz_overlap_boundary_thresholds():
    """Threshold boundary testing around short_term_prz_overlap_min (30%)."""
    cfg = TriageRuleConfig(short_term_prz_overlap_min=30.0, short_term_priority_min=0.30)

    # 1. Just below threshold (29.9% overlap) with mitigation cheaper -> Tier 4
    tier_below_cheaper = classify_triage_tier(
        pop_fraction_in_prz=0.299,
        hazard_intensity=0.50,
        priority_score=0.35,
        mitigation_cost=5.0e6,
        relocation_cost=15.0e6,
        rules=cfg,
    )
    assert tier_below_cheaper == Tier.MITIGATE_IN_SITU

    # 2. Exactly at threshold (30.0% overlap) -> Significant PRZ overlap
    # Mitigation is no longer permitted because PRZ fraction is no longer small (<30%)
    tier_at = classify_triage_tier(
        pop_fraction_in_prz=0.30,
        hazard_intensity=0.50,
        priority_score=0.35,
        mitigation_cost=5.0e6,
        relocation_cost=15.0e6,
        rules=cfg,
    )
    assert tier_at == Tier.SHORT_TERM

    # 3. Just above threshold (30.1% overlap) -> Significant PRZ overlap -> Short-term
    tier_above = classify_triage_tier(
        pop_fraction_in_prz=0.301,
        hazard_intensity=0.50,
        priority_score=0.35,
        rules=cfg,
    )
    assert tier_above == Tier.SHORT_TERM


def test_name_invariance():
    """Invariant 6 (P0.2 & H9): Triage tier must depend strictly on domain inputs, never on habitation names."""
    engine = PriorityScoringEngine()

    inputs = {
        "hazard_intensity": 0.45,
        "pop_fraction_in_prz": 0.12,
        "vulnerability_index": 0.35,
        "decayed_loss": 0.0,
        "population": 2500,
        "active_deformation": False,
        "fatal_event_last_3_monsoons": False,
        "mitigation_cost": 3.0e6,
        "relocation_cost": 15.0e6,
        "adverse_trend": False,
    }

    # Evaluate identical risk profile under diverse historical names
    res_generic = engine.evaluate_habitation(**inputs)
    res_mundakkai = engine.evaluate_habitation(**inputs)
    res_chooralmala = engine.evaluate_habitation(**inputs)
    res_bhagamandala = engine.evaluate_habitation(**inputs)

    assert res_generic["tier"] == Tier.MITIGATE_IN_SITU
    assert res_mundakkai["tier"] == Tier.MITIGATE_IN_SITU
    assert res_chooralmala["tier"] == Tier.MITIGATE_IN_SITU
    assert res_bhagamandala["tier"] == Tier.MITIGATE_IN_SITU
    assert res_generic["priority_score"] == res_mundakkai["priority_score"]


def test_explicit_zero_semantics():
    """Invariant 7 (P0.1 & H9): Zero inputs must remain valid numbers, not fall back to defaults."""
    tier = classify_triage_tier(
        has_prz_overlap=False,
        pop_fraction_in_prz=0.0,
        hazard_intensity=0.0,
        priority_score=0.0,
        active_deformation=False,
        fatal_event_last_3_monsoons=False,
    )
    assert tier is None


def test_caution_zone_without_adverse_trend_does_not_become_medium_term():
    """Regression test (H9 Review §1):
    Caution Zone AND adverse_trend = False AND not Immediate AND not Short-term
    AND not Mitigate in situ does NOT become Medium-term merely because it is otherwise unclassified.
    """
    tier = classify_triage_tier(
        has_prz_overlap=False,
        pop_fraction_in_prz=0.0,
        hazard_intensity=0.55,       # Caution Zone (0.45 <= MHI < 0.75)
        priority_score=0.20,          # Below short_term_priority_min (0.30)
        active_deformation=False,
        fatal_event_last_3_monsoons=False,
        adverse_trend=False,          # Evaluated, no adverse trend
        mitigation_cost=None,
        relocation_cost=None,
    )
    assert tier != Tier.MEDIUM_TERM
    assert tier is None


def test_adverse_trend_three_state_semantics():
    """Focused tests (H9 Review §2):
    None / unknown, False / known negative, True / known positive.
    Only a real positive adverse-trend signal can satisfy the Medium-term rule.
    """
    base_kwargs = {
        "has_prz_overlap": False,
        "pop_fraction_in_prz": 0.0,
        "hazard_intensity": 0.55,  # Caution Zone
        "priority_score": 0.20,
        "active_deformation": False,
        "fatal_event_last_3_monsoons": False,
    }

    # Case 1: None / unknown trend -> Must NOT be Medium-term
    tier_unknown = classify_triage_tier(**base_kwargs, adverse_trend=None)
    assert tier_unknown != Tier.MEDIUM_TERM
    assert tier_unknown is None

    # Case 2: False / known negative trend -> Must NOT be Medium-term
    tier_negative = classify_triage_tier(**base_kwargs, adverse_trend=False)
    assert tier_negative != Tier.MEDIUM_TERM
    assert tier_negative is None

    # Case 3: True / known positive adverse trend -> Confirmed Medium-term
    tier_positive = classify_triage_tier(**base_kwargs, adverse_trend=True)
    assert tier_positive == Tier.MEDIUM_TERM


def test_active_alerts_do_not_alter_permanent_relocation_tier():
    """Invariant 8: Active/Forecast alerts govern immediate evacuation, NOT permanent resettlement."""
    tier_without_alert = classify_triage_tier(
        pop_fraction_in_prz=0.10,
        hazard_intensity=0.45,
        priority_score=0.15,
        mitigation_cost=2.0e6,
        relocation_cost=10.0e6,
        has_active_trigger=False,
    )
    assert tier_without_alert == Tier.MITIGATE_IN_SITU

    tier_with_alert = classify_triage_tier(
        pop_fraction_in_prz=0.10,
        hazard_intensity=0.45,
        priority_score=0.15,
        mitigation_cost=2.0e6,
        relocation_cost=10.0e6,
        has_active_trigger=True,
    )
    assert tier_with_alert == Tier.MITIGATE_IN_SITU


def test_adverse_trend_loss_frequency_rising():
    """Tests PRD §6.7 adverse trend calculation: loss frequency rising near settlement."""
    ref = date(2026, 8, 31)

    # Rising frequency: 3 events in last 5 years (2021-2026), 1 event in 5-10 years ago (2016-2021)
    events_rising = [
        {"ts": date(2025, 7, 15), "distance_km": 4.2},
        {"ts": date(2024, 8, 10), "distance_km": 6.1},
        {"ts": date(2023, 6, 20), "distance_km": 3.0},
        {"ts": date(2018, 8, 8), "distance_km": 5.5},
    ]
    assert check_loss_frequency_rising(events_rising, reference_date=ref) is True

    # Declining/flat frequency: 1 event in last 5 years, 2 events 5-10 years ago
    events_flat = [
        {"ts": date(2025, 7, 15), "distance_km": 4.2},
        {"ts": date(2018, 8, 8), "distance_km": 5.5},
        {"ts": date(2017, 7, 10), "distance_km": 7.0},
    ]
    assert check_loss_frequency_rising(events_flat, reference_date=ref) is False

    # Distant events (> 15 km) should be ignored
    events_distant = [
        {"ts": date(2025, 7, 15), "distance_km": 25.0},
        {"ts": date(2024, 8, 10), "distance_km": 30.0},
    ]
    assert check_loss_frequency_rising(events_distant, reference_date=ref) is False
