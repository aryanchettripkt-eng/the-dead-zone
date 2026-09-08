"""FastAPI Route Handlers for Authentication, User Verification & Server-Side Sessions.

Section refs: SETU-DRR Auth Part 1 — Identity + Password Verification + Server-Side Sessions.
Endpoints:
- POST /auth/login
- GET  /auth/me
- POST /auth/logout
- POST /auth/register
"""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from api.dependencies import get_db, require_authenticated, get_login_rate_limiter
from api.routes.common import error_responses
from api.services.auth_service import AuthService
from core.config import settings
from core.db_models import AppUser
from core.domain.rate_limit import LoginRateLimiter
from core.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    UserResponse,
    LogoutResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication & Identity"])


def _extract_client_ip(request: Request) -> str:
    """Extracts client IP from direct socket connection.

    Uses transport-level client host rather than spoofable X-Forwarded-For headers
    since the application runs standalone without a trusted reverse proxy.
    """
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


@router.post(
    "/login",
    response_model=UserResponse,
    responses=error_responses(400, 401, 422, 429, 500),
    summary="Authenticate user with email and password",
    description=(
        "Verifies credentials using Argon2id, creates a secure server-side session, "
        "and sets an HTTP-only session cookie. Returns the safe authenticated identity. "
        "Protected by configurable sliding-window rate limiting."
    ),
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    rate_limiter: LoginRateLimiter = Depends(get_login_rate_limiter),
) -> UserResponse:
    client_ip = _extract_client_ip(request)
    service = AuthService(db, rate_limiter=rate_limiter)
    user, raw_token = service.login(payload.email, payload.password, client_ip=client_ip)

    # Set HTTP-only, SameSite session cookie
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=settings.SESSION_DURATION_DAYS * 86400,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/",
    )

    return UserResponse.model_validate(user)


@router.get(
    "/me",
    response_model=UserResponse,
    responses=error_responses(401, 500),
    summary="Get authenticated user identity",
    description=(
        "Resolves the current authenticated user identity from the session cookie. "
        "Returns 401 if unauthenticated, expired, or revoked."
    ),
)
def get_me(
    current_user: AppUser = Depends(require_authenticated),
) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    responses=error_responses(200, 500),
    summary="Revoke session and log out",
    description="Revokes the active server-side session and clears the session cookie.",
)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LogoutResponse:
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if token:
        service = AuthService(db)
        service.logout(token)

    # Clear session cookie
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
    )

    return LogoutResponse(message="Logged out successfully.")


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(400, 422, 500),
    summary="Register a new civilian user",
    description=(
        "Public self-registration for civilian users. Privileged roles (GOVERNMENT_OFFICIAL, SYSTEM_ADMIN) "
        "cannot be selected and are strictly rejected."
    ),
)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
) -> UserResponse:
    service = AuthService(db)
    user = service.register_civilian(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
    )
    return UserResponse.model_validate(user)
