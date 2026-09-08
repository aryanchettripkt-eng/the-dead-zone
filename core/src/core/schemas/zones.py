"""Pydantic v2 schemas for H3 Hazard Zones and Cell Details.

Endpoints: GET /zones, GET /zones/{h3}
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import Field
from core.enums import ZoneClass, Hazard
from core.schemas.common import BaseSchema, SCREENING_GRADE_NOTICE

from core.schemas.explanation import FeatureContributionDTO

class HazardDetailDTO(BaseSchema):
    hazard_type: str = Field(description="Hazard type (landslide, flash_flood, etc.).")
    susceptibility: float = Field(ge=0.0, le=1.0, description="Static terrain susceptibility S_h.")
    confidence: float = Field(ge=0.0, le=1.0, description="Model confidence in [0, 1].")
    trigger_value: Optional[float] = Field(default=None, description="Dynamic observed trigger T_h (null if unavailable).")
    forecast_trigger: Optional[float] = Field(default=None, description="Forecast trigger T_fcst (null if unavailable).")
    score: float = Field(ge=0.0, le=1.0, description="Composed hazard score H_h.")


class ZoneCellSummary(BaseSchema):
    """Summary record returned in spatial query list (GET /zones)."""
    h3: str = Field(description="H3 index as hexadecimal string.")
    h3_int: Optional[int] = Field(default=None, description="H3 index as 64-bit integer.")
    res: int = Field(description="H3 resolution (6, 7, 8, 9).")
    mhi: float = Field(ge=0.0, le=1.0, description="Active Multi-Hazard Index in [0, 1].")
    mhi_static: float = Field(ge=0.0, le=1.0, description="Static Multi-Hazard Index in [0, 1].")
    mhi_live: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    mhi_fcst: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    dominant_hazard: str
    zone_class: ZoneClass
    dataset_version: str = Field(default="demo-day2-v1", description="Published dataset version.")
    model_version: str = Field(default="baseline-v1", description="ML model version.")
    data_quality: str = Field(default="synthetic", description="Provenance / screening grade quality.")
    population: float = Field(default=0.0, ge=0.0)
    built_area_m2: float = Field(default=0.0, ge=0.0)
    centroid: list[float] = Field(description="[longitude, latitude]")


class ZoneCellDetail(BaseSchema):
    """Full cell detail with SHAP/heuristic explanation (GET /zones/{h3})."""
    h3: str
    h3_int: Optional[int] = None
    res: int
    dataset_version: str = "demo-day2-v1"
    model_version: str = "baseline-v1"
    data_quality: str = "synthetic"
    valid_at: datetime
    admin_id: Optional[int] = None
    admin_name: Optional[str] = None
    habitation_id: Optional[int] = None
    habitation_name: Optional[str] = None
    population: float = 0.0
    built_area_m2: float = 0.0
    centroid: list[float]
    
    # MHI and classification
    mhi_static: float
    mhi_live: Optional[float] = None
    mhi_fcst: Optional[float] = None
    dominant_hazard: str
    zone_class: ZoneClass
    confidence: float = 1.0

    # Hazards breakdown
    hazards: List[HazardDetailDTO] = Field(default_factory=list)

    # Explanation & Model metadata
    explanation: List[FeatureContributionDTO] = Field(default_factory=list)
    screening_grade: str = SCREENING_GRADE_NOTICE

