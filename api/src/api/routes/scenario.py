"""FastAPI Route Handlers for Scenario Simulation & Sensitivity Analysis (L5).

Endpoint:
- POST /scenario
Section refs: docs/PRD1.md §6.10 (FR-9.4), §9.6
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
from api.services.scenario_service import ScenarioService
from core.db_models import AppUser
from core.domain.authorization import Permission
from core.schemas.scenario import ScenarioWeightOverrideRequest, ScenarioResponse

router = APIRouter(prefix="/scenario", tags=["Scenario & Decision Analysis"])


@router.post(
    "",
    response_model=ScenarioResponse,
    responses=error_responses(401, 403, 422, 500, 503),
    summary="Evaluate hypothetical policy and hazard weight scenarios without mutating baseline data",
    description=(
        "Executes a pure, stateless scenario evaluation over habitation baselines. "
        "Allows decision-makers to adjust hazard weights w_h and loss history amplifier gamma, "
        "recomputing priority scores, rank deltas, and triage tier shifts. "
        "Optionally simulates min-cost flow relocation allocation without modifying database records. "
        "Requires authenticated user with 'scenario.run' permission (Government Official) and authorized jurisdiction scope."
    ),
)
def evaluate_scenario(
    payload: ScenarioWeightOverrideRequest = Body(
        ...,
        description="Scenario assumptions and parameters (hazard weights, priority gamma, sort mode).",
    ),
    db: Session = Depends(get_db),
    _current_user: AppUser = Depends(require_permission(Permission.SCENARIO_RUN)),
    _sv: uuid.UUID = Depends(require_serving_version),
) -> ScenarioResponse:
    effective_admin_id = resolve_effective_admin_id(_current_user, payload.admin_id)
    service = ScenarioService(db)
    return service.evaluate_scenario(payload, admin_id=effective_admin_id)
