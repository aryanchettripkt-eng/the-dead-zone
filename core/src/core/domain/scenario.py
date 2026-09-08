"""Pure domain logic for Decision Analysis and Scenario Simulation.

Section refs: docs/PRD1.md §6.10 (FR-9.4), §9.6

Allows decision-makers to evaluate hypothetical policy assumptions, hazard weights,
and loss-history multipliers WITHOUT mutating authoritative baseline database records.
Strictly preserves full existing triage logic and domain rules.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from core.constants import (
    HAZARD_WEIGHTS,
    PRIORITY_GAMMA,
    PRZ_MHI_STATIC,
    PRZ_ANY_SUSCEPTIBILITY,
    PRZ_FATAL_EVENT_MHI,
    SCREENING_GRADE_NOTICE,
)
from core.enums import Hazard, SortMode, Tier
from core.domain.hazard import compute_mhi
from core.domain.priority import compute_priority_score, classify_triage_tier


@dataclass(frozen=True)
class HabitationBaselineState:
    """Immutable snapshot of a habitation's baseline risk state loaded from PostgreSQL."""
    id: int
    name: str
    population: int
    households: int
    hazard_intensity: float
    pop_fraction_in_prz: float
    prz_overlap_pct: float
    vulnerability_index: float
    decayed_loss: float
    active_deformation: bool = False
    fatal_event_last_3_monsoons: bool = False
    in_situ_cost_cheaper: bool = False
    is_caution_with_adverse_trend: bool = False
    hazard_scores: Mapping[Hazard, float] = field(default_factory=dict)
    baseline_priority_score: float = 0.0
    baseline_tier: Optional[Tier] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


@dataclass
class ScenarioHabitationResult:
    """Outcome of scenario simulation for a single habitation."""
    habitation_id: int
    name: str
    population: int
    households: int
    original_rank: int
    scenario_rank: int
    rank_delta: int  # original_rank - scenario_rank (positive = rose in urgency)
    original_priority_score: float
    scenario_priority_score: float
    original_tier: Optional[Tier]
    scenario_tier: Optional[Tier]
    tier_changed: bool
    scenario_hazard_intensity: float
    scenario_prz_overlap_pct: float
    lat: Optional[float] = None
    lon: Optional[float] = None


@dataclass
class ScenarioEvaluationOutcome:
    """Aggregated outcome of a scenario simulation run."""
    total_habitations_evaluated: int
    total_tier_shifts: int
    applied_scenario_weights: dict[str, float]
    baseline_hazard_weights: dict[str, float]
    applied_gamma: float
    sort_mode: SortMode
    items: list[ScenarioHabitationResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    policy_version: str = "scenario-v1.0"
    screening_grade: str = SCREENING_GRADE_NOTICE


class ScenarioEngine:
    """Pure, stateless engine that simulates decision scenarios on habitation baselines."""

    def __init__(self, baseline_weights: Optional[Mapping[Hazard, float]] = None) -> None:
        self.baseline_weights: dict[Hazard, float] = dict(baseline_weights if baseline_weights is not None else HAZARD_WEIGHTS)

    def evaluate(
        self,
        habitations: Sequence[HabitationBaselineState],
        hazard_weight_overrides: Optional[Mapping[Hazard, float]] = None,
        priority_gamma: Optional[float] = None,
        sort_mode: SortMode = SortMode.URGENCY,
    ) -> ScenarioEvaluationOutcome:
        """Executes pure scenario simulation on the provided habitation collection."""
        warnings: list[str] = []

        # 1. Validate & resolve hazard weights
        active_weights = dict(self.baseline_weights)
        applied_scenario_weights: dict[str, float] = {}

        if hazard_weight_overrides is not None:
            for h_key, w_val in hazard_weight_overrides.items():
                if not isinstance(h_key, Hazard):
                    try:
                        h_enum = Hazard(str(h_key))
                    except ValueError:
                        warnings.append(f"Ignored unrecognized hazard key '{h_key}' in scenario overrides.")
                        continue
                else:
                    h_enum = h_key

                if not math.isfinite(float(w_val)) or float(w_val) < 0.0:
                    warnings.append(f"Invalid non-finite or negative weight for {h_enum.value}: {w_val}. Clamped to 0.0.")
                    w_clamped = 0.0
                else:
                    w_clamped = round(float(w_val), 4)

                active_weights[h_enum] = w_clamped
                applied_scenario_weights[h_enum.value] = w_clamped

        # Fill any missing keys in applied_scenario_weights with baseline values for transparency
        for h_enum, w_val in self.baseline_weights.items():
            if h_enum.value not in applied_scenario_weights:
                applied_scenario_weights[h_enum.value] = round(float(w_val), 4)

        # Baseline weights string dictionary for output transparency
        baseline_weights_dict = {h.value: round(float(w), 4) for h, w in self.baseline_weights.items()}

        # 2. Validate & resolve priority gamma
        applied_gamma = PRIORITY_GAMMA
        if priority_gamma is not None:
            if not math.isfinite(float(priority_gamma)) or float(priority_gamma) < 0.0:
                warnings.append(f"Invalid non-finite or negative priority_gamma: {priority_gamma}. Using default {PRIORITY_GAMMA}.")
                applied_gamma = PRIORITY_GAMMA
            else:
                applied_gamma = round(float(priority_gamma), 4)

        if not habitations:
            return ScenarioEvaluationOutcome(
                total_habitations_evaluated=0,
                total_tier_shifts=0,
                applied_scenario_weights=applied_scenario_weights,
                baseline_hazard_weights=baseline_weights_dict,
                applied_gamma=applied_gamma,
                sort_mode=sort_mode,
                items=[],
                warnings=warnings,
            )

        # 3. Sort baseline habitations to establish deterministic original ranks
        def baseline_sort_key(h: HabitationBaselineState) -> tuple[float, int]:
            if sort_mode == SortMode.CASELOAD:
                score = h.baseline_priority_score * h.population
            else:
                score = h.baseline_priority_score
            return (-score, h.id)

        sorted_baseline = sorted(habitations, key=baseline_sort_key)
        original_rank_map = {h.id: idx + 1 for idx, h in enumerate(sorted_baseline)}

        # 4. Evaluate each habitation under scenario assumptions
        scenario_eval_records = []
        for h in habitations:
            # Recompute hazard intensity if hazard scores are present and weights were overridden
            if h.hazard_scores and hazard_weight_overrides is not None:
                new_mhi = compute_mhi(h.hazard_scores, weights=active_weights)
                scenario_h_intensity = round(new_mhi, 4)
                
                # Check PRZ condition change under new MHI
                any_high_sus = any(s >= PRZ_ANY_SUSCEPTIBILITY for s in h.hazard_scores.values())
                is_prz = (new_mhi >= PRZ_MHI_STATIC) or any_high_sus
                
                # Adjust PRZ overlap proportionally if MHI crossed the PRZ threshold
                if is_prz and h.prz_overlap_pct <= 0.0:
                    scenario_prz_overlap = 50.0
                elif not is_prz and h.hazard_intensity >= PRZ_MHI_STATIC:
                    scenario_prz_overlap = 0.0
                else:
                    scenario_prz_overlap = h.prz_overlap_pct
            else:
                scenario_h_intensity = h.hazard_intensity
                scenario_prz_overlap = h.prz_overlap_pct

            scenario_pop_frac = scenario_prz_overlap / 100.0

            # Recompute priority score with scenario gamma & scenario hazard
            scenario_ps = compute_priority_score(
                hazard_intensity=scenario_h_intensity,
                pop_fraction_in_prz=scenario_pop_frac,
                vulnerability_index=h.vulnerability_index,
                decayed_loss=h.decayed_loss,
                gamma=applied_gamma,
            )

            # Re-evaluate triage tier using full approved domain rules (PRD §6.7)
            # INVARIANT: Dynamic alerts NEVER alter permanent relocation triage
            scenario_tier = classify_triage_tier(
                has_prz_overlap=(scenario_prz_overlap > 0.0),
                active_deformation=h.active_deformation,
                fatal_event_last_3_monsoons=h.fatal_event_last_3_monsoons,
                pop_fraction_in_prz=scenario_pop_frac,
                hazard_intensity=scenario_h_intensity,
                priority_score=scenario_ps,
                in_situ_cost_cheaper=h.in_situ_cost_cheaper,
                is_caution_with_adverse_trend=h.is_caution_with_adverse_trend,
            )

            scenario_eval_records.append({
                "habitation": h,
                "scenario_ps": scenario_ps,
                "scenario_tier": scenario_tier,
                "scenario_h_intensity": scenario_h_intensity,
                "scenario_prz_overlap": scenario_prz_overlap,
            })

        # 5. Sort under scenario score to establish scenario rank
        def scenario_sort_key(item: dict[str, Any]) -> tuple[float, int]:
            h = item["habitation"]
            ps = item["scenario_ps"]
            if sort_mode == SortMode.CASELOAD:
                score = ps * h.population
            else:
                score = ps
            return (-score, h.id)

        sorted_scenario = sorted(scenario_eval_records, key=scenario_sort_key)

        # 6. Build final items with rank deltas and tier shift tracking
        final_items: list[ScenarioHabitationResult] = []
        total_tier_shifts = 0

        for scenario_rank_idx, item in enumerate(sorted_scenario, start=1):
            h: HabitationBaselineState = item["habitation"]
            orig_rank = original_rank_map[h.id]
            rank_delta = orig_rank - scenario_rank_idx
            tier_changed = (h.baseline_tier != item["scenario_tier"])

            if tier_changed:
                total_tier_shifts += 1

            final_items.append(
                ScenarioHabitationResult(
                    habitation_id=h.id,
                    name=h.name,
                    population=h.population,
                    households=h.households,
                    original_rank=orig_rank,
                    scenario_rank=scenario_rank_idx,
                    rank_delta=rank_delta,
                    original_priority_score=round(h.baseline_priority_score, 4),
                    scenario_priority_score=round(item["scenario_ps"], 4),
                    original_tier=h.baseline_tier,
                    scenario_tier=item["scenario_tier"],
                    tier_changed=tier_changed,
                    scenario_hazard_intensity=item["scenario_h_intensity"],
                    scenario_prz_overlap_pct=item["scenario_prz_overlap"],
                    lat=h.lat,
                    lon=h.lon,
                )
            )

        return ScenarioEvaluationOutcome(
            total_habitations_evaluated=len(final_items),
            total_tier_shifts=total_tier_shifts,
            applied_scenario_weights=applied_scenario_weights,
            baseline_hazard_weights=baseline_weights_dict,
            applied_gamma=applied_gamma,
            sort_mode=sort_mode,
            items=final_items,
            warnings=warnings,
        )
