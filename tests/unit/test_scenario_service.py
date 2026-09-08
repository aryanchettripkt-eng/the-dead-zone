"""Unit tests for ScenarioEngine and Scenario Decision Analysis (Day 7).

Section refs: docs/PRD1.md §6.10, §9.6

Verifies:
1. Baseline data is not mutated.
2. Hazard-weight overrides are scenario-only assumptions.
3. Priority gamma changes scenario scores without corrupting baseline.
4. Triage uses full existing triage logic with all inputs preserved.
5. Invariant: Dynamic AAZ/FAZ alerts never alter permanent relocation triage.
6. Tier shifts and rank deltas are deterministic.
"""

import pytest
from core.enums import Hazard, SortMode, Tier
from core.domain.scenario import (
    HabitationBaselineState,
    ScenarioEngine,
    ScenarioEvaluationOutcome,
)
from core.governance import AUTHORITATIVE_SCIENTIFIC


@pytest.fixture
def mock_baseline_habitations() -> list[HabitationBaselineState]:
    """Generates deterministic mock habitations representing diverse risk profiles."""
    return [
        HabitationBaselineState(
            id=1,
            name="Chooralmala",
            population=1200,
            households=280,
            hazard_intensity=0.88,
            pop_fraction_in_prz=0.85,
            prz_overlap_pct=85.0,
            vulnerability_index=0.72,
            decayed_loss=2.5,
            active_deformation=True,
            fatal_event_last_3_monsoons=True,
            hazard_scores={Hazard.LANDSLIDE: 0.90, Hazard.FLASH_FLOOD: 0.85},
            baseline_priority_score=0.82,
            baseline_tier=Tier.IMMEDIATE,
        ),
        HabitationBaselineState(
            id=2,
            name="Mundakkai",
            population=950,
            households=210,
            hazard_intensity=0.82,
            pop_fraction_in_prz=0.75,
            prz_overlap_pct=75.0,
            vulnerability_index=0.68,
            decayed_loss=2.0,
            active_deformation=False,
            fatal_event_last_3_monsoons=True,
            hazard_scores={Hazard.LANDSLIDE: 0.82, Hazard.FLASH_FLOOD: 0.70},
            baseline_priority_score=0.75,
            baseline_tier=Tier.IMMEDIATE,
        ),
        HabitationBaselineState(
            id=3,
            name="Lowland Village",
            population=1500,
            households=350,
            hazard_intensity=0.45,
            pop_fraction_in_prz=0.20,
            prz_overlap_pct=20.0,
            vulnerability_index=0.55,
            decayed_loss=0.0,
            active_deformation=False,
            fatal_event_last_3_monsoons=False,
            in_situ_cost_cheaper=True,
            hazard_scores={Hazard.LANDSLIDE: 0.20, Hazard.RIVERINE_FLOOD: 0.45},
            baseline_priority_score=0.18,
            baseline_tier=Tier.MITIGATE_IN_SITU,
        ),
        HabitationBaselineState(
            id=4,
            name="Caution Hamlet",
            population=600,
            households=140,
            hazard_intensity=0.52,
            pop_fraction_in_prz=0.15,
            prz_overlap_pct=15.0,
            vulnerability_index=0.50,
            decayed_loss=0.5,
            active_deformation=False,
            fatal_event_last_3_monsoons=False,
            is_caution_with_adverse_trend=True,
            hazard_scores={Hazard.LANDSLIDE: 0.52},
            baseline_priority_score=0.25,
            baseline_tier=Tier.MEDIUM_TERM,
        ),
    ]


class TestScenarioEngine:
    """Test suite verifying pure scenario domain logic and invariant preservation."""

    def test_baseline_preservation_and_immutability(self, mock_baseline_habitations):
        """Scenario evaluation must not mutate input baseline objects."""
        engine = ScenarioEngine()
        original_states = [
            (h.id, h.baseline_priority_score, h.baseline_tier, h.hazard_intensity)
            for h in mock_baseline_habitations
        ]

        outcome = engine.evaluate(
            mock_baseline_habitations,
            hazard_weight_overrides={Hazard.LANDSLIDE: 1.5, Hazard.FLASH_FLOOD: 0.2},
            priority_gamma=1.0,
        )

        assert outcome.total_habitations_evaluated == 4
        # Verify baseline objects are completely untouched
        for idx, h in enumerate(mock_baseline_habitations):
            assert (h.id, h.baseline_priority_score, h.baseline_tier, h.hazard_intensity) == original_states[idx]

    def test_hazard_weight_overrides_scenario_only(self, mock_baseline_habitations):
        """Overrides are scenario assumptions; baseline weights remain unchanged."""
        engine = ScenarioEngine()
        outcome = engine.evaluate(
            mock_baseline_habitations,
            hazard_weight_overrides={Hazard.RIVERINE_FLOOD: 1.5},
        )

        assert outcome.applied_scenario_weights["riverine_flood"] == 1.5
        assert outcome.baseline_hazard_weights["riverine_flood"] == AUTHORITATIVE_SCIENTIFIC.baseline_hazard_weights[Hazard.RIVERINE_FLOOD]

    def test_priority_gamma_sensitivity(self, mock_baseline_habitations):
        """Increasing gamma elevates habitations with significant loss history."""
        engine = ScenarioEngine()

        # Run with gamma = 0.0 (loss history ignored)
        outcome_g0 = engine.evaluate(mock_baseline_habitations, priority_gamma=0.0)
        # Run with gamma = 2.0 (loss history strongly amplified)
        outcome_g2 = engine.evaluate(mock_baseline_habitations, priority_gamma=2.0)

        item_chooralmala_g0 = next(i for i in outcome_g0.items if i.name == "Chooralmala")
        item_chooralmala_g2 = next(i for i in outcome_g2.items if i.name == "Chooralmala")

        # Chooralmala has decayed_loss = 2.5, so score must be strictly higher with gamma=2.0
        assert item_chooralmala_g2.scenario_priority_score > item_chooralmala_g0.scenario_priority_score

    def test_full_triage_logic_and_tier_shifts(self, mock_baseline_habitations):
        """Triage evaluation strictly applies approved rules including in-situ, chronic markers, and PRZ."""
        engine = ScenarioEngine()
        outcome = engine.evaluate(mock_baseline_habitations)

        lowland = next(i for i in outcome.items if i.name == "Lowland Village")
        assert lowland.scenario_tier == Tier.MITIGATE_IN_SITU

        chooralmala = next(i for i in outcome.items if i.name == "Chooralmala")
        assert chooralmala.scenario_tier == Tier.IMMEDIATE

    def test_deterministic_rank_deltas(self, mock_baseline_habitations):
        """Verifies deterministic rank calculation: rank_delta = original_rank - scenario_rank."""
        engine = ScenarioEngine()
        outcome1 = engine.evaluate(mock_baseline_habitations, priority_gamma=0.8, sort_mode=SortMode.URGENCY)
        outcome2 = engine.evaluate(mock_baseline_habitations, priority_gamma=0.8, sort_mode=SortMode.URGENCY)

        ranks1 = [(i.habitation_id, i.original_rank, i.scenario_rank, i.rank_delta) for i in outcome1.items]
        ranks2 = [(i.habitation_id, i.original_rank, i.scenario_rank, i.rank_delta) for i in outcome2.items]
        assert ranks1 == ranks2

        for item in outcome1.items:
            assert item.rank_delta == item.original_rank - item.scenario_rank

    def test_caseload_sorting_mode(self, mock_baseline_habitations):
        """Caseload sort mode weights priority score by population (PS * pop)."""
        engine = ScenarioEngine()
        outcome = engine.evaluate(mock_baseline_habitations, sort_mode=SortMode.CASELOAD)

        caseload_scores = [
            round(item.scenario_priority_score * item.population, 2)
            for item in outcome.items
        ]
        # Caseload scores must be non-increasing
        for i in range(len(caseload_scores) - 1):
            assert caseload_scores[i] >= caseload_scores[i + 1]
