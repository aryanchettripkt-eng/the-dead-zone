"""FastAPI route handlers for external relocation recommendations and benchmark comparisons.

Endpoints:
- GET /habitations/{id}/external-recommendations
- GET /plan/external-recommendations?district=Barpeta
- GET /plan/benchmark?district=Barpeta
"""

from __future__ import annotations

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from api.dependencies import get_db, require_serving_version
from api.routes.common import error_responses
from api.services.recommendations_service import RecommendationsService
from core.schemas.allocation import (
    AllocationBenchmarkResponse,
    ExternalRecommendationItem,
    ExternalRecommendationListResponse,
)

router = APIRouter(tags=["External Recommendations & Benchmark"])


@router.get(
    "/habitations/{id}/external-recommendations",
    response_model=list[ExternalRecommendationItem],
    responses=error_responses(404, 422, 500, 503),
    summary="Get external pipeline relocation recommendations for a habitation",
    description=(
        "Retrieves offline GIS candidate proposals for this habitation from partner pipelines. "
        "These are external evidence records and do not represent authoritative SETU allocation decisions."
    ),
)
def get_habitation_external_recommendations(
    id: int = Path(
        ...,
        description="Habitation ID (integer primary key).",
        examples=[1],
    ),
    db: Session = Depends(get_db),
    _sv: uuid.UUID = Depends(require_serving_version),
) -> list[ExternalRecommendationItem]:
    service = RecommendationsService(db)
    return service.get_recommendations_for_habitation(id)


@router.get(
    "/plan/external-recommendations",
    response_model=ExternalRecommendationListResponse,
    responses=error_responses(404, 422, 500, 503),
    summary="List external pipeline relocation recommendations for a district",
    description="Retrieves all external pipeline candidate relocation recommendations for the specified district.",
)
def get_district_external_recommendations(
    district: str = Query(
        "Barpeta",
        description="Administrative district name (e.g., 'Barpeta').",
    ),
    db: Session = Depends(get_db),
    _sv: uuid.UUID = Depends(require_serving_version),
) -> ExternalRecommendationListResponse:
    service = RecommendationsService(db)
    return service.get_recommendations_for_district(district)


@router.get(
    "/plan/benchmark",
    response_model=AllocationBenchmarkResponse,
    responses=error_responses(404, 422, 500, 503),
    summary="Benchmark external pipeline recommendations against authoritative SETU relocation plan",
    description=(
        "Performs side-by-side comparative evaluation between partner pipeline proposals and SETU's min-cost flow optimizer. "
        "If SETU allocation has not been executed, returns 'external_only' status with external proposals."
    ),
)
def get_allocation_benchmark(
    district: str = Query(
        "Barpeta",
        description="Administrative district name to benchmark.",
    ),
    db: Session = Depends(get_db),
    _sv: uuid.UUID = Depends(require_serving_version),
) -> AllocationBenchmarkResponse:
    service = RecommendationsService(db)
    return service.get_benchmark_comparison(district)
