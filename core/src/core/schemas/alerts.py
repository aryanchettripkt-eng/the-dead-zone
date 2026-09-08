"""Pydantic v2 schemas for Active and Forecast Alert Zones.

Endpoints: GET /alerts/active, GET /alerts/forecast
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import Field
from core.enums import DataQuality, ZoneClass
from core.schemas.common import BaseSchema, SCREENING_GRADE_NOTICE


class ActiveAlertItem(BaseSchema):
    """Dynamic alert zone item currently exceeding threshold (GET /alerts/active)."""
    h3: str
    h3_int: int
    res: int
    admin_id: Optional[int] = None
    admin_name: Optional[str] = None
    mhi_live: float = Field(ge=0.0, le=1.0, description="Active live MHI in [0, 1].")
    mhi_static: float = Field(ge=0.0, le=1.0, description="Static baseline MHI.")
    dominant_hazard: str
    trigger_source: Optional[str] = None
    valid_at: Optional[datetime] = None
    age_hours: Optional[float] = Field(default=None, description="Age of dynamic trigger observation in hours.")
    data_quality: Optional[DataQuality] = Field(default=None, description="Data quality / provenance classification.")
    exposed_population: float = 0.0
    exposed_built_area_m2: float = 0.0
    centroid: list[float] = Field(description="[longitude, latitude]")
    screening_grade: str = SCREENING_GRADE_NOTICE


class ForecastAlertItem(BaseSchema):
    """Forecast alert zone item predicted to cross threshold within 72 hours (GET /alerts/forecast)."""
    h3: str
    h3_int: int
    res: int
    admin_id: Optional[int] = None
    admin_name: Optional[str] = None
    mhi_fcst: float = Field(ge=0.0, le=1.0, description="Forecast MHI in [0, 1].")
    mhi_static: float = Field(ge=0.0, le=1.0, description="Static baseline MHI.")
    dominant_hazard: str
    issuing_model: Optional[str] = None
    forecast_cycle_at: Optional[datetime] = None
    valid_at: Optional[datetime] = None
    horizon_hours: int = Field(ge=1, le=72)
    data_quality: Optional[DataQuality] = Field(default=None, description="Data quality / provenance classification.")
    exposed_population: float = 0.0
    centroid: list[float]
    screening_grade: str = SCREENING_GRADE_NOTICE


class ActiveAlertsResponse(BaseSchema):
    total_active_cells: int
    total_exposed_population: int
    issued_at: Optional[datetime] = None
    items: List[ActiveAlertItem] = Field(default_factory=list)


class ForecastAlertsResponse(BaseSchema):
    total_forecast_cells: int
    total_exposed_population: int
    issuing_model: Optional[str] = None
    forecast_cycle_at: Optional[datetime] = None
    horizon_hours: int
    items: List[ForecastAlertItem] = Field(default_factory=list)
