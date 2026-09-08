"""FastAPI Route Handlers for H3 Zones and Cell Dossiers (L5).

Endpoints:
- GET /zones?bbox=&res=&valid_at=&admin=&limit=
- GET /zones/{h3}
"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session

from api.dependencies import get_db, require_serving_version
from api.routes.common import error_responses
from api.services.zones_service import ZonesService
from core.schemas.zones import ZoneCellSummary, ZoneCellDetail

router = APIRouter(prefix="/zones", tags=["Hazard Zones"])


@router.get(
    "",
    response_model=List[ZoneCellSummary],
    responses=error_responses(400, 404, 422, 500, 503),
    summary="Query H3 hazard zones within spatial viewport",
    description=(
        "Retrieves active Multi-Hazard Index and dominant hazard classifications "
        "for H3 hexagonal grid cells within the specified bounding box."
    ),
)
def get_zones(
    bbox: Optional[str] = Query(
        None,
        description="Bounding box as 'min_lon,min_lat,max_lon,max_lat' (e.g. '75.8,11.5,76.3,11.9')",
        examples=["75.8,11.5,76.3,11.9"],
    ),
    res: int = Query(
        8,
        description="H3 grid resolution (6=Overview, 7=National, 8=Pilot, 9=Site)",
        ge=6,
        le=9,
    ),
    valid_at: Optional[datetime] = Query(
        None,
        description="Historical timestamp to evaluate (ISO 8601). Defaults to latest.",
    ),
    admin: Optional[int] = Query(
        None,
        description="Filter by Administrative Unit ID or LGD Code (e.g. 555 for Wayanad)",
    ),
    limit: int = Query(
        1000,
        description="Maximum number of cells to return (max 5000).",
        ge=1,
        le=5000,
    ),
    db: Session = Depends(get_db),
    _sv: uuid.UUID = Depends(require_serving_version),
) -> List[ZoneCellSummary]:
    service = ZonesService(db)
    return service.get_zones(
        bbox=bbox,
        res=res,
        valid_at=valid_at,
        admin=admin,
        limit=limit,
    )


@router.get(
    "/{h3}",
    response_model=ZoneCellDetail,
    responses=error_responses(400, 404, 422, 500, 503),
    summary="Get full cell detail and SHAP/heuristic explanation",
    description="Retrieves multi-hazard breakdown, static/live MHI, and feature attributions for a single H3 cell.",
)
def get_zone_detail(
    h3: str = Path(
        ...,
        description="H3 index as hexadecimal string (e.g. '8860064989fffff')",
        examples=["8860064989fffff"],
    ),
    db: Session = Depends(get_db),
    _sv: uuid.UUID = Depends(require_serving_version),
) -> ZoneCellDetail:
    service = ZonesService(db)
    return service.get_zone_detail(h3)
