"""FastAPI dependencies for database sessions, pagination, and request context."""

import uuid
from typing import Generator, Optional
from fastapi import Depends, Request
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from core.config import settings
from core.errors import PipelineNotReadyError

# Direct/Pooled database engine
# Using psycopg3 sync engine for stable Prepared Statement support with Neon & Martin
engine = create_engine(
    settings.get_sqlalchemy_url(direct=False),
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Yields a database session and ensures clean closure."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_request_id(request: Request) -> str:
    """Retrieves request_id attached by RequestIdAndLoggingMiddleware."""
    return getattr(request.state, "request_id", "unknown")


# --------------------------------------------------------------------------- #
# H13: Serving-version readiness gate
# --------------------------------------------------------------------------- #
# Per H13 specification, only 'READY' is a valid servable status.
# If the referenced pipeline_run has status != 'READY', the API must refuse to serve data.
_SERVING_READY_STATUS = "READY"


def require_serving_version(db: Session = Depends(get_db)) -> uuid.UUID:
    """Enforces that a valid, ready serving version exists before serving data.

    The ``serving_version`` table has ``dataset_name`` as its PRIMARY KEY,
    so exactly one row per dataset name — no ambiguous ``LIMIT 1`` is needed.

    Raises:
        PipelineNotReadyError: HTTP 503 when no valid serving version exists
            or the linked pipeline run status != 'READY'.

    Returns:
        The ``pipeline_run_id`` of the active serving version.
    """
    row = db.execute(
        text(
            "SELECT sv.pipeline_run_id, pr.status "
            "FROM serving_version sv "
            "JOIN pipeline_run pr ON sv.pipeline_run_id = pr.id "
            "WHERE sv.dataset_name = 'default';"
        )
    ).mappings().first()

    if row is None or row["status"] != _SERVING_READY_STATUS:
        raise PipelineNotReadyError("default")

    return row["pipeline_run_id"]


# --------------------------------------------------------------------------- #
# Authentication & Identity Dependencies (Part 1)
# --------------------------------------------------------------------------- #

def get_current_user_optional(request: Request, db: Session = Depends(get_db)):
    """Resolves authenticated user from session cookie if present, returning None otherwise."""
    from api.services.auth_service import AuthService
    from core.errors import UnauthenticatedError

    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        return None

    try:
        service = AuthService(db)
        return service.resolve_session(token)
    except UnauthenticatedError:
        return None


def require_authenticated(request: Request, db: Session = Depends(get_db)):
    """Enforces that a valid authenticated user session exists.
    
    Raises:
        UnauthenticatedError: HTTP 401 when session is missing, invalid, expired, revoked, or user inactive.
    """
    from api.services.auth_service import AuthService
    from core.errors import UnauthenticatedError

    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        raise UnauthenticatedError("Authentication required. Please log in.")

    service = AuthService(db)
    return service.resolve_session(token)


# --------------------------------------------------------------------------- #
# Authorization & Role Policy Dependencies (Part 2)
# --------------------------------------------------------------------------- #

def require_permission(permission: str):
    """Dependency factory enforcing that the authenticated user possesses the required permission.
    
    Raises:
        UnauthenticatedError: HTTP 401 if request has no valid session.
        ForbiddenError: HTTP 403 if authenticated user's role lacks the requested permission.
    """
    from core.db_models import AppUser
    from core.domain.authorization import Permission as PermissionEnum, has_permission
    from core.errors import ForbiddenError

    perm_obj = PermissionEnum(permission) if isinstance(permission, str) else permission

    def _permission_checker(current_user: AppUser = Depends(require_authenticated)) -> AppUser:
        if not has_permission(current_user.role, perm_obj):
            raise ForbiddenError(
                f"Permission '{perm_obj.value}' required. Role '{current_user.role}' is not authorized."
            )
        return current_user

    return _permission_checker


# --------------------------------------------------------------------------- #
# Jurisdiction & Spatial Administrative Scoping Dependencies (Part 3)
# --------------------------------------------------------------------------- #

def resolve_effective_admin_id(user, requested_admin_id: Optional[int]) -> int:
    """Resolves authorized canonical admin_boundary.id without mutating the request DTO.
    
    Rules:
    1. Privileged user must possess an assigned jurisdiction (user.admin_id is not None).
    2. If requested_admin_id is omitted (None), defaults authoritatively to user.admin_id.
    3. If requested_admin_id is supplied, validates via has_jurisdiction(user.admin_id, requested_admin_id).
       Note: Both must be canonical admin_boundary.id values. Mismatch or LGD confusion raises 403.
    """
    from core.domain.authorization import has_jurisdiction
    from core.errors import ForbiddenError

    if user.admin_id is None:
        raise ForbiddenError("User has no administrative jurisdiction assigned.")

    if requested_admin_id is None:
        return user.admin_id

    if not has_jurisdiction(user.admin_id, requested_admin_id):
        raise ForbiddenError("Operation outside assigned administrative jurisdiction.")

    return requested_admin_id


def get_site_district_admin_id(db: Session, site_id: int) -> Optional[int]:
    """Resolves the single authoritative district admin_boundary.id containing candidate site centroid.
    
    Enforces district boundary uniqueness:
    - Exactly 1 district: returns canonical admin_boundary.id
    - 0 districts: returns None (unmapped site)
    - >1 districts: raises ForbiddenError (ambiguous spatial boundary)
    """
    from core.errors import ForbiddenError

    stmt = text("""
        SELECT ab.id
        FROM candidate_site cs
        JOIN admin_boundary ab ON ab.level = 'district' AND ST_Intersects(ab.geom, cs.centroid)
        WHERE cs.id = :site_id;
    """)
    rows = db.execute(stmt, {"site_id": site_id}).scalars().all()
    if len(rows) == 1:
        return rows[0]
    elif len(rows) > 1:
        raise ForbiddenError(f"Candidate site {site_id} spans multiple conflicting district jurisdictions.")
    return None
