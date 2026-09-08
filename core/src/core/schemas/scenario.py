"""Pydantic v2 schemas for Scenario Simulation and Sensitivity Analysis.

Endpoint: POST /scenario
Section refs: docs/PRD1.md §6.10 (FR-9.4), §9.6
"""

from typing import Optional, List, Dict, Any
from pydantic import Field
from core.enums import Hazard, Tier, SortMode, DataQuality
from core.schemas.common import BaseSchema, SCREENING_GRADE_NOTICE


class ScenarioAllocationParams(BaseSchema):
    """Optional configuration for simulated allocation execution."""
    max_search_radius_km: float = Field(default=15.0, gt=0.0, le=100.0)
    distance_penalty_weight: float = Field(default=1.0, ge=0.0, le=10.0)
    allow_group_splits: bool = Field(default=True)
    target_tiers: Optional[List[Tier]] = Field(
        default=None,
        description="Filter simulated allocation to specific tiers (defaults to immediate + short_term).",
    )


class ScenarioWeightOverrideRequest(BaseSchema):
    """Request payload for scenario simulation with custom weights and parameters (POST /scenario)."""
    admin_id: Optional[int] = Field(default=None, description="Scope simulation to specific administrative boundary.")
    hazard_weights: Optional[Dict[Hazard, float]] = Field(
        default=None,
        description="Scenario hazard weight overrides w_h (treated as hypothetical assumptions, not calibration).",
    )
    priority_gamma: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=10.0,
        description="Scenario loss history amplifier gamma (default 0.5).",
    )
    sort_mode: SortMode = Field(
        default=SortMode.URGENCY,
        description="Sort by urgency (PS_j) or caseload (PS_j * pop).",
    )
    limit: int = Field(default=50, ge=1, le=200, description="Max habitations to return in paginated response.")
    offset: int = Field(default=0, ge=0, description="Offset for pagination.")
    include_allocation: bool = Field(
        default=False,
        description="If True, executes pure in-memory OR-Tools allocation simulation without database mutation.",
    )
    allocation_params: Optional[ScenarioAllocationParams] = Field(
        default=None,
        description="Custom parameters for the simulated allocation solver.",
    )


class ScenarioHabitationItem(BaseSchema):
    habitation_id: int
    name: str
    original_rank: int
    scenario_rank: int
    rank_delta: int = Field(description="Positive means rose in urgency, negative dropped.")
    original_priority_score: float
    scenario_priority_score: float
    original_tier: Optional[Tier] = None
    scenario_tier: Optional[Tier] = None
    tier_changed: bool
    population: int
    households: int = Field(default=0)
    scenario_hazard_intensity: Optional[float] = None
    scenario_prz_overlap_pct: Optional[float] = None


class ScenarioAllocationSummaryDTO(BaseSchema):
    """Outcome summary of non-persisting OR-Tools allocation simulation."""
    status: str
    total_demand_households: int
    total_relocated_households: int
    unmet_demand_households: int
    assignments_count: int
    solver_latency_ms: float
    group_split_warnings: List[str] = Field(default_factory=list)
    policy_version: str = "allocation-v1.0"


class ScenarioResponse(BaseSchema):
    """Response payload for scenario simulation (POST /scenario)."""
    admin_id: Optional[int] = None
    total_habitations_evaluated: int
    total_tier_shifts: int
    applied_weights: Dict[str, float] = Field(description="Active weights applied in the scenario (alias for applied_scenario_weights).")
    applied_scenario_weights: Dict[str, float] = Field(default_factory=dict, description="Hypothetical scenario weights applied.")
    baseline_hazard_weights: Dict[str, float] = Field(default_factory=dict, description="Authoritative scientific baseline weights.")
    applied_gamma: float
    sort_mode: SortMode
    items: List[ScenarioHabitationItem] = Field(default_factory=list)
    allocation_simulation: Optional[ScenarioAllocationSummaryDTO] = None
    scoring_version: str = "priority-v1.0"
    policy_version: str = "scenario-v1.0"
    dataset_version: str = "demo-day2-v1"
    model_version: str = "baseline-v1"
    data_quality: DataQuality = DataQuality.SYNTHETIC
    warnings: List[str] = Field(default_factory=list)
    screening_grade: str = SCREENING_GRADE_NOTICE
