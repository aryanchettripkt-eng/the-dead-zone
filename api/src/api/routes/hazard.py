"""FastAPI route handlers for static hazard layers (vector map source).

Endpoints:
- GET /hazard/layers
- GET /hazard/cells?hazard_type=&res=&bbox=&admin=&min_susceptibility=&limit=
- GET /hazard/cells/{h3}?hazard_type=

Distinct from /zones: those endpoints compose the Multi-Hazard Index from `mhi_snapshot`,
which the flood pipeline does not write. These read `hazard_static` directly, so a layer
is servable the moment Milestone E loads it.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from api.dependencies import get_db
from api.routes.common import error_responses
from api.services.hazard_service import HazardService
from core.enums import Hazard
from core.schemas.hazard import (
    HazardCellDetailDTO,
    HazardLayerResponse,
    HazardLayerSummaryDTO,
)

router = APIRouter(
    prefix="/hazard",
    tags=["Hazard Layers"],
    responses=error_responses(400, 404, 422, 500, 503),
)


@router.get(
    "/layers",
    response_model=List[HazardLayerSummaryDTO],
    summary="List published static hazard layers",
    description=(
        "Enumerates every `hazard_static` layer with its cell count, susceptibility range "
        "and confidence ceiling, so the client can build a layer switcher without guessing."
    ),
)
def list_hazard_layers(db: Session = Depends(get_db)) -> List[HazardLayerSummaryDTO]:
    return HazardService(db).list_layers()


@router.get(
    "/cells",
    response_model=HazardLayerResponse,
    summary="Query a static hazard layer for the map viewport",
    description=(
        "Returns H3 cells with susceptibility, confidence and coverage provenance, plus the "
        "quantile class breaks and confidence ceiling required to render them faithfully.\n\n"
        "Geometry is omitted by design — the client derives hexagon boundaries from the H3 "
        "index (deck.gl `H3HexagonLayer`), which is roughly 7x smaller on the wire."
    ),
)
def get_hazard_cells(
    hazard_type: str = Query(
        Hazard.RIVERINE_FLOOD.value,
        description="Hazard layer to serve.",
        examples=["riverine_flood"],
    ),
    res: int = Query(8, ge=6, le=9, description="H3 grid resolution."),
    bbox: Optional[str] = Query(
        None,
        description="Viewport as 'min_lon,min_lat,max_lon,max_lat'. Omit for the full layer.",
        examples=["90.70,26.05,91.45,26.75"],
    ),
    admin: Optional[int] = Query(
        None, description="Filter by admin_boundary id or LGD code (e.g. 277 for Barpeta)."
    ),
    min_susceptibility: float = Query(
        0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Optional susceptibility floor. Left at 0.0 the response still includes "
            "hard-zero and no-coverage cells, which the map must distinguish."
        ),
    ),
    limit: int = Query(20000, ge=1, le=30000, description="Maximum cells to return."),
    db: Session = Depends(get_db),
) -> HazardLayerResponse:
    return HazardService(db).get_layer(
        hazard_type=hazard_type,
        res=res,
        bbox=bbox,
        admin=admin,
        min_susceptibility=min_susceptibility,
        limit=limit,
    )


@router.get(
    "/cells/{h3}",
    response_model=HazardCellDetailDTO,
    summary="Get one cell's hazard dossier and physical drivers",
    description=(
        "Returns the cell's score with its inundation frequency, HAND, slope and cropland "
        "drivers from `hazard_static_flood`, plus confidence already normalised against the "
        "layer ceiling."
    ),
)
def get_hazard_cell_detail(
    h3: str = Path(
        ...,
        description="H3 index as hexadecimal string.",
        examples=["883ce00201fffff"],
    ),
    hazard_type: str = Query(Hazard.RIVERINE_FLOOD.value, description="Hazard layer to read."),
    db: Session = Depends(get_db),
) -> HazardCellDetailDTO:
    return HazardService(db).get_cell_detail(h3, hazard_type=hazard_type)
