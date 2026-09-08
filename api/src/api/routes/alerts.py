"""FastAPI Route Handlers for Active and Forecast Alert Zones (Day 6).

Endpoints:
- GET /alerts/active
- GET /alerts/forecast
"""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.dependencies import get_db, require_serving_version
from api.routes.common import error_responses
from api.services.alerts_service import AlertsService
from core.constants import FORECAST_HORIZON_HOURS
from core.schemas.alerts import ActiveAlertsResponse, ForecastAlertsResponse

router = APIRouter(prefix="/alerts", tags=["Dynamic Alerts & Forecasts"])


@router.get(
    "/active",
    response_model=ActiveAlertsResponse,
    responses=error_responses(422, 500, 503),
    summary="Get active hazard alert zones exceeding emergency threshold",
    description=(
        "Retrieves H3 grid cells currently in Active Alert Zone state (MHI_live >= 0.75 and MHI_static < 0.75). "
        "Alerts are transient, driven by observed meteorological/hydrological triggers, and do not mutate permanent PRZ classifications."
    ),
)
def get_active_alerts(
    admin: Optional[int] = Query(
        None,
        description="Filter by Administrative Unit ID or LGD Code (e.g. 555 for Wayanad)",
    ),
    min_mhi: float = Query(
        0.75,
        ge=0.0,
        le=1.0,
        description="Minimum active MHI threshold (default 0.75).",
    ),
    hazard: Optional[str] = Query(
        None,
        description="Filter by dominant hazard type (landslide, flash_flood, riverine_flood).",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Maximum records to return.",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Pagination offset.",
    ),
    db: Session = Depends(get_db),
    _sv: uuid.UUID = Depends(require_serving_version),
) -> ActiveAlertsResponse:
    service = AlertsService(db)
    return service.get_active_alerts(
        admin_id=admin,
        min_mhi=min_mhi,
        dominant_hazard=hazard,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/forecast",
    response_model=ForecastAlertsResponse,
    responses=error_responses(422, 500, 503),
    summary="Get forecast alert zones predicted to cross threshold within 72 hours",
    description=(
        "Retrieves H3 grid cells predicted to cross the hazard threshold (MHI_fcst >= 0.75) within a configurable horizon (1-72h). "
        "Represents meteorological forecast threshold crossing (ECMWF Open Data) and does not predict disasters or alter permanent relocation triage."
    ),
)
def get_forecast_alerts(
    horizon: int = Query(
        72,
        ge=1,
        le=FORECAST_HORIZON_HOURS,
        description="Forecast horizon in hours (maximum 72 hours).",
    ),
    admin: Optional[int] = Query(
        None,
        description="Filter by Administrative Unit ID or LGD Code (e.g. 555 for Wayanad)",
    ),
    min_mhi: float = Query(
        0.75,
        ge=0.0,
        le=1.0,
        description="Minimum forecast MHI threshold (default 0.75).",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Maximum records to return.",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Pagination offset.",
    ),
    db: Session = Depends(get_db),
    _sv: uuid.UUID = Depends(require_serving_version),
) -> ForecastAlertsResponse:
    service = AlertsService(db)
    return service.get_forecast_alerts(
        horizon_hours=horizon,
        admin_id=admin,
        min_mhi=min_mhi,
        limit=limit,
        offset=offset,
    )
