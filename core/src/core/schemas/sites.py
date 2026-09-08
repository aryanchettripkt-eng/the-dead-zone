"""Pydantic v2 schemas for Candidate Relocation Sites and Carrying Capacity.

Endpoints: GET /habitations/{id}/sites, GET /sites/{id}, POST /sites/{id}/capacity
"""

from typing import Optional, List, Dict, Any
from pydantic import Field
from core.enums import BindingConstraint, TenureType
from core.schemas.common import BaseSchema, SCREENING_GRADE_NOTICE


class CapacityBreakdownDTO(BaseSchema):
    """Structured breakdown of independent resource capacity dimensions."""
    cc_land: int = Field(ge=0, description="Households supportable by developable land area.")
    land_screening_capacity: int = Field(
        default=0, ge=0, description="Households supportable by developable land area (screening-only capacity)."
    )
    cc_water: Optional[int] = Field(
        default=None, ge=0, description="Households supportable by sustainable potable water yield (None if unmeasured)."
    )
    cc_school: Optional[int] = Field(
        default=None, ge=0, description="Households supportable by spare school capacity (None if unmeasured)."
    )
    cc_health: Optional[int] = Field(
        default=None, ge=0, description="Households supportable by spare primary health capacity (None if unmeasured)."
    )
    livelihood_multiplier: float = Field(ge=0.0, le=1.0, description="Multiplier for economic connectivity.")
    cc_final: Optional[int] = Field(
        default=None, ge=0, description="Binding minimum carrying capacity in households (None if lifelines unassessed)."
    )
    binding_constraint: Optional[BindingConstraint] = Field(
        default=None, description="The primary limiting capacity bottleneck (None if lifelines unassessed)."
    )
    tied_constraints: List[BindingConstraint] = Field(
        default_factory=list,
        description="All resource constraints matching the minimum bottleneck value.",
    )
    assessment_status: str = Field(
        default="screening_only",
        description="Assessment completeness: 'fully_assessed', 'partial', or 'screening_only'.",
    )
    data_quality: str = Field(
        default="complete",
        description="Data quality state: 'complete', 'partial', or 'unavailable'.",
    )
    policy_version: str = Field(
        default="capacity-norms-v1.0",
        description="Audit version of the capacity policy norms applied.",
    )
    calculation_version: str = Field(
        default="calc-v1.0",
        description="Audit version of the mathematical calculation implementation.",
    )


class AugmentedCapacityDTO(BaseSchema):
    """Augmentation relief assessment for relieving the primary binding constraint."""
    relieved_constraint: BindingConstraint
    augmented_capacity: int = Field(ge=0, description="Augmented carrying capacity in households.")
    next_binding_constraint: Optional[BindingConstraint] = Field(
        default=None,
        description="The secondary resource constraint that limits the site after relief.",
    )
    indicative_intervention: str = Field(description="Recommended engineering or policy intervention.")
    indicative_cost_inr_lakhs: Optional[float] = Field(
        default=None,
        description="Estimated intervention cost in Lakhs INR (None if unverified).",
    )


class CandidateSiteItem(BaseSchema):
    """Candidate site card in ranked destination list (GET /habitations/{id}/sites)."""
    id: int
    distance_km: float = Field(ge=0.0, description="Geodesic distance from source habitation in km.")
    area_ha: float = Field(ge=0.0, description="Total contiguous developable area in hectares.")
    tenure: TenureType = Field(description="Tenure status (government_revenue, private, tenure_unverified).")
    slope_mean: float = Field(default=0.0, description="Mean terrain slope in degrees.")
    mhi_max: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Maximum static multi-hazard index inside site (None if unmeasured)."
    )
    suitability: Optional[int] = Field(
        default=None, ge=0, le=100, description="Composite suitability score (0-100, None if unassigned/provisional), separate from capacity."
    )
    capacity: CapacityBreakdownDTO = Field(description="Full resource capacity breakdown.")
    augmented: Optional[AugmentedCapacityDTO] = Field(
        default=None,
        description="Capacity outcome if binding bottleneck is relieved.",
    )
    centroid: List[float] = Field(description="[longitude, latitude] coordinates.")
    assessment_status: str = Field(
        default="screening_only",
        description="Assessment status: 'fully_assessed', 'partial', or 'screening_only'.",
    )
    eligibility_status: str = Field(
        default="unknown",
        description="Eligibility status: 'eligible', 'ineligible', or 'unknown'.",
    )
    allocatable: bool = Field(
        default=False,
        description="True only if site is fully eligible under canonical CandidateSitePolicy.",
    )
    rejection_reasons: List[str] = Field(
        default_factory=list,
        description="Reasons why site is not currently allocatable.",
    )
    source_site_id: Optional[str] = Field(
        default=None,
        description="External source record identifier if imported.",
    )
    screening_grade: str = Field(
        default=SCREENING_GRADE_NOTICE,
        description="Persistent decision-support disclaimer notice.",
    )


class CandidateSiteDetail(CandidateSiteItem):
    """Complete candidate site detail including GeoJSON geometry."""
    geometry: Optional[Dict[str, Any]] = Field(
        default=None,
        description="GeoJSON MultiPolygon boundary of the candidate relocation site.",
    )


class SiteCapacityOverrideRequest(BaseSchema):
    """Request payload for capacity scenario simulation (POST /sites/{id}/capacity)."""
    plot_area_m2: Optional[float] = Field(default=None, gt=0.0, le=1000.0, description="Override plot area per HH.")
    water_lpcd: Optional[int] = Field(default=None, gt=0, le=500, description="Override LPCD norm (55 rural, 135 urban).")
    daily_water_yield_liters: Optional[float] = Field(default=None, gt=0.0, description="Override sustainable water yield.")
    spare_school_seats: Optional[int] = Field(default=None, ge=0, description="Override spare school seats.")
    spare_health_capacity_pop: Optional[int] = Field(default=None, ge=0, description="Override spare PHC population.")
    livelihood_multiplier: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Override livelihood multiplier.")


class SiteCapacityOverrideResponse(BaseSchema):
    """Response payload for capacity scenario simulation (POST /sites/{id}/capacity)."""
    site_id: int
    base_capacity: CapacityBreakdownDTO
    scenario_capacity: CapacityBreakdownDTO
    delta_households: int = Field(description="Change in final household capacity under override scenario.")
    augmented_options: List[AugmentedCapacityDTO] = Field(default_factory=list)
    screening_grade: str = Field(
        default=SCREENING_GRADE_NOTICE,
        description="Persistent decision-support disclaimer notice.",
    )
