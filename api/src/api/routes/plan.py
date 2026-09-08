"""FastAPI Route Handlers for Relocation Plan Optimization (Day 6).

Endpoint:
- POST /plan/allocate
"""

import uuid
from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session

from api.dependencies import (
    get_db,
    require_serving_version,
    require_permission,
    resolve_effective_admin_id,
)
from api.routes.common import error_responses
from api.services.allocation_service import AllocationService
from core.db_models import AppUser
from core.domain.authorization import Permission
from core.schemas.allocation import AllocationPlanRequest, AllocationPlanResponse

router = APIRouter(prefix="/plan", tags=["Relocation Planning & Allocation"])


@router.post(
    "/allocate",
    response_model=AllocationPlanResponse,
    responses=error_responses(401, 403, 422, 500, 503),
    summary="Solve optimal habitation-to-site relocation allocation via min-cost flow",
    description=(
        "Executes exact min-cost flow optimization (Google OR-Tools) to assign vulnerable habitations to candidate relocation sites. "
        "Respects carrying capacity constraints (Day 5), maximizes composite suitability/priority benefit, minimizes distance penalty, "
        "and explicitly reports any village household group splits requiring social sign-off. "
        "Requires authenticated user with 'allocation.run' permission (Government Official) and authorized jurisdiction scope."
    ),
)
def generate_allocation_plan(
    payload: AllocationPlanRequest = Body(
        ...,
        description="Configuration and constraints for the min-cost-flow allocation solver.",
    ),
    db: Session = Depends(get_db),
    _current_user: AppUser = Depends(require_permission(Permission.ALLOCATION_RUN)),
    _sv: uuid.UUID = Depends(require_serving_version),
) -> AllocationPlanResponse:
    effective_admin_id = resolve_effective_admin_id(_current_user, payload.admin_id)
    service = AllocationService(db)
    return service.generate_allocation_plan(payload, admin_id=effective_admin_id)
