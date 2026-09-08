"""Service layer for Scenario Simulation and Sensitivity Analysis.

Section refs: docs/PRD1.md §6.10 (FR-9.4), §9.6

Coordinates stateless scenario evaluation:
1. Loads authoritative baseline habitation risk states from PostgreSQL.
2. Applies ScenarioEngine in-memory re-ranking and triage shifts.
3. Optionally simulates min-cost flow allocation without database persistence.
4. Returns comprehensive scenario response with provenance and warnings.
"""

from __future__ import annotations

import logging
import math
from typing import Optional
from sqlalchemy.orm import Session

from api.repositories.habitations_repo import HabitationsRepository
from api.services.allocation_service import AllocationService
from core.constants import (
    CAUTION_MHI_MIN,
    HAZARD_WEIGHTS,
    PRIORITY_GAMMA,
    PRZ_MHI_STATIC,
    SCREENING_GRADE_NOTICE,
)
from core.domain.allocation import HabitationDemand
from core.domain.priority import evaluate_in_situ_cost_cheaper
from core.domain.scenario import (
    HabitationBaselineState,
    ScenarioEngine,
    ScenarioEvaluationOutcome,
)
from core.enums import DataQuality, Hazard, SortMode, Tier
from core.errors import InvalidParametersError
from core.governance import (
    AUTHORITATIVE_SCIENTIFIC,
    DEFAULT_POLICY_PARAMS,
    DEFAULT_OPERATIONAL_CONFIG,
)
from core.schemas.scenario import (
    ScenarioAllocationSummaryDTO,
    ScenarioHabitationItem,
    ScenarioResponse,
    ScenarioWeightOverrideRequest,
)

logger = logging.getLogger("setu_api.scenario_service")


class ScenarioService:
    """Orchestrates hypothetical decision scenario evaluations."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.hab_repo = HabitationsRepository(db)
        self.engine = ScenarioEngine(baseline_weights=AUTHORITATIVE_SCIENTIFIC.baseline_hazard_weights)

    def evaluate_scenario(
        self,
        request: ScenarioWeightOverrideRequest,
        admin_id: Optional[int] = None,
    ) -> ScenarioResponse:
        """Evaluates hypothetical scenario assumptions without mutating baseline data."""
        # 1. Parameter guards & boundary checks
        if request.priority_gamma is not None:
            if not math.isfinite(request.priority_gamma) or request.priority_gamma < 0.0:
                raise InvalidParametersError(f"priority_gamma must be a non-negative finite number, got {request.priority_gamma}")

        if request.hazard_weights:
            for h_key, w_val in request.hazard_weights.items():
                if not math.isfinite(w_val) or w_val < 0.0:
                    raise InvalidParametersError(f"Hazard weight for '{h_key}' must be non-negative and finite, got {w_val}")

        clamped_limit = min(max(1, request.limit), DEFAULT_OPERATIONAL_CONFIG.max_query_limit)
        clamped_offset = max(0, request.offset)

        # 2. Query baseline habitations
        # Fetch all habitations within the boundary to establish comprehensive ranking without truncation (M10)
        effective_admin_id = admin_id if admin_id is not None else request.admin_id
        raw_habs, total_count = self.hab_repo.query_habitations(
            admin_id=effective_admin_id,
            limit=None,
            offset=0,
            sort=request.sort_mode,
        )

        hab_ids = [int(r["id"]) for r in raw_habs]
        hab_hazard_scores = self.hab_repo.get_hazard_scores_for_habitations(hab_ids)

        baseline_states: list[HabitationBaselineState] = []
        for r in raw_habs:
            pop = int(r.get("population") if r.get("population") is not None else 0)
            hh = int(r.get("households") if r.get("households") is not None else max(1, pop // 4))
            h_id = int(r["id"])
            name = str(r.get("name") or f"Habitation-{h_id}")

            prz_overlap = float(r.get("prz_overlap_pct") if r.get("prz_overlap_pct") is not None else 0.0)
            pop_frac = prz_overlap / 100.0
            hazard_intensity = float(r.get("hazard_intensity") if r.get("hazard_intensity") is not None else 0.5)
            v_index = float(r.get("v_index") if r.get("v_index") is not None else 0.5)
            decayed_loss = float(r.get("decayed_loss") if r.get("decayed_loss") is not None else 0.0)

            # Resolve baseline tier
            raw_tier = r.get("tier")
            try:
                tier_enum = Tier(raw_tier) if raw_tier else Tier.SHORT_TERM
            except ValueError:
                tier_enum = Tier.SHORT_TERM

            base_ps = float(r.get("priority_score") if r.get("priority_score") is not None else 0.5)

            active_deformation = bool(r.get("active_deformation", False))
            fatal_event = bool(r.get("fatal_event_last_3_monsoons", False))

            # Map static hazard scores from persisted hazard_static data
            hazard_scores = hab_hazard_scores.get(h_id)
            if not hazard_scores:
                dom_str = r.get("dominant_hazard") or "landslide"
                try:
                    dom_hazard = Hazard(dom_str)
                except ValueError:
                    dom_hazard = Hazard.LANDSLIDE
                hazard_scores = {dom_hazard: hazard_intensity}

            m_cost = r.get("mitigation_cost")
            r_cost = r.get("relocation_cost")
            in_situ_cheaper = evaluate_in_situ_cost_cheaper(m_cost, r_cost)
            adv_trend = r.get("adverse_trend")
            is_caution = (CAUTION_MHI_MIN <= hazard_intensity < PRZ_MHI_STATIC) or (0.45 <= hazard_intensity < 0.75)
            caution_adverse = is_caution and (adv_trend is True)

            baseline_states.append(
                HabitationBaselineState(
                    id=h_id,
                    name=name,
                    population=pop,
                    households=hh,
                    hazard_intensity=hazard_intensity,
                    pop_fraction_in_prz=pop_frac,
                    prz_overlap_pct=prz_overlap,
                    vulnerability_index=v_index,
                    decayed_loss=decayed_loss,
                    active_deformation=active_deformation,
                    fatal_event_last_3_monsoons=fatal_event,
                    in_situ_cost_cheaper=in_situ_cheaper,
                    is_caution_with_adverse_trend=caution_adverse,
                    hazard_scores=hazard_scores,
                    baseline_priority_score=base_ps,
                    baseline_tier=tier_enum,
                    lat=r.get("centroid_lat") if r.get("centroid_lat") is not None else r.get("lat"),
                    lon=r.get("centroid_lon") if r.get("centroid_lon") is not None else r.get("lon"),
                )
            )

        # 3. Evaluate scenario through ScenarioEngine
        outcome: ScenarioEvaluationOutcome = self.engine.evaluate(
            habitations=baseline_states,
            hazard_weight_overrides=request.hazard_weights,
            priority_gamma=request.priority_gamma,
            sort_mode=request.sort_mode,
        )

        # 4. Optional simulation of allocation matching without persistence
        alloc_summary: Optional[ScenarioAllocationSummaryDTO] = None
        if request.include_allocation and outcome.items:
            alloc_service = AllocationService(self.db)
            
            # Determine target tiers for simulation
            target_tiers = [Tier.IMMEDIATE, Tier.SHORT_TERM]
            if request.allocation_params and request.allocation_params.target_tiers:
                target_tiers = request.allocation_params.target_tiers

            simulated_demands = [
                HabitationDemand(
                    id=item.habitation_id,
                    name=item.name,
                    demand_households=item.households,
                    priority_score=item.scenario_priority_score,
                    tier=item.scenario_tier,
                    lat=item.lat,
                    lon=item.lon,
                )
                for item in outcome.items
                if item.scenario_tier in target_tiers and item.households > 0
            ]

            max_radius = 15.0
            dist_weight = 1.0
            splits = True
            if request.allocation_params:
                max_radius = request.allocation_params.max_search_radius_km
                dist_weight = request.allocation_params.distance_penalty_weight
                splits = request.allocation_params.allow_group_splits

            try:
                alloc_res = alloc_service.simulate_allocation(
                    simulated_demands=simulated_demands,
                    max_search_radius_km=max_radius,
                    distance_penalty_weight=dist_weight,
                    allow_group_splits=splits,
                )
                alloc_summary = ScenarioAllocationSummaryDTO(
                    status=alloc_res.status,
                    total_demand_households=alloc_res.total_demand_households,
                    total_relocated_households=alloc_res.total_relocated_households,
                    unmet_demand_households=alloc_res.unmet_demand_households,
                    assignments_count=len(alloc_res.assignments),
                    solver_latency_ms=alloc_res.solver_latency_ms,
                    group_split_warnings=alloc_res.group_split_warnings,
                    policy_version=alloc_res.policy_version,
                )
            except Exception as e:
                logger.warning(f"Scenario allocation simulation failed: {e}")
                outcome.warnings.append(f"Allocation simulation could not complete: {e}")

        # 5. Paginate items
        paginated_items = outcome.items[clamped_offset : clamped_offset + clamped_limit]

        dto_items = [
            ScenarioHabitationItem(
                habitation_id=item.habitation_id,
                name=item.name,
                original_rank=item.original_rank,
                scenario_rank=item.scenario_rank,
                rank_delta=item.rank_delta,
                original_priority_score=item.original_priority_score,
                scenario_priority_score=item.scenario_priority_score,
                original_tier=item.original_tier,
                scenario_tier=item.scenario_tier,
                tier_changed=item.tier_changed,
                population=item.population,
                households=item.households,
                scenario_hazard_intensity=item.scenario_hazard_intensity,
                scenario_prz_overlap_pct=item.scenario_prz_overlap_pct,
            )
            for item in paginated_items
        ]

        return ScenarioResponse(
            admin_id=request.admin_id,
            total_habitations_evaluated=outcome.total_habitations_evaluated,
            total_tier_shifts=outcome.total_tier_shifts,
            applied_weights=outcome.applied_scenario_weights,
            applied_scenario_weights=outcome.applied_scenario_weights,
            baseline_hazard_weights=outcome.baseline_hazard_weights,
            applied_gamma=outcome.applied_gamma,
            sort_mode=outcome.sort_mode,
            items=dto_items,
            allocation_simulation=alloc_summary,
            scoring_version="priority-v1.0",
            policy_version="scenario-v1.0",
            dataset_version="demo-day2-v1",
            model_version="baseline-v1",
            data_quality=DataQuality.SYNTHETIC,
            warnings=outcome.warnings,
            screening_grade=outcome.screening_grade,
        )
