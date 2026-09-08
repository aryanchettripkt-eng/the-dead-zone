"""FastAPI main entrypoint for SETU-DRR serving layer (L5)."""

import logging
from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from api.config import api_settings
from api.middleware import RequestIdAndLoggingMiddleware
from api.routes.health import router as health_router
from api.routes.zones import router as zones_router
from api.routes.hazard import router as hazard_router
from api.routes.habitations import router as habitations_router
from api.routes.sites import router as sites_router
from api.routes.alerts import router as alerts_router
from api.routes.plan import router as plan_router
from api.routes.recommendations import router as recommendations_router
from api.routes.scenario import router as scenario_router
from api.routes.auth import router as auth_router
from core.errors import ErrorCode

logging.basicConfig(
    level=getattr(logging, api_settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("setu_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("Starting SETU-DRR API service...")
    logger.info(
        f"Database URL configured: {api_settings.DATABASE_URL.split('@')[-1] if '@' in api_settings.DATABASE_URL else 'localhost'}"
    )
    logger.info(f"DEMO_MODE: {api_settings.DEMO_MODE}")
    yield
    logger.info("Shutting down SETU-DRR API service.")


app = FastAPI(
    title="SETU-DRR API",
    version=api_settings.MODEL_VERSION,
    description="Hazard Red Zone Identification, Carrying Capacity Assessment & Relocation Decision Support Platform.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# 1. Request ID & Logging Middleware
app.add_middleware(RequestIdAndLoggingMiddleware)

# 2. CORS Middleware
#
# Registered last so it is the OUTERMOST layer. RequestIdAndLoggingMiddleware catches AppError
# and builds its own JSONResponse; when CORS sat outside-in of that, those error responses left
# without Access-Control-* headers and a browser saw every 401/403/404 as an opaque network
# failure rather than a readable error envelope. CORS must wrap the error handler, not sit
# inside it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=api_settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sanitize_validation_errors(obj: Any) -> Any:
    """Recursively converts non-finite floats (NaN, Inf) into strings so Starlette JSONResponse doesn't crash."""
    import math
    if isinstance(obj, float) and not math.isfinite(obj):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_validation_errors(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_validation_errors(x) for x in obj]
    return obj


# 3. Custom Validation Error Handler (conforms to standard error envelope)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    error_dict = {
        "error": {
            "code": ErrorCode.VALIDATION_ERROR.value,
            "message": "Request parameter validation failed.",
            "request_id": request_id,
            "details": {"errors": _sanitize_validation_errors(exc.errors())},
        }
    }
    return JSONResponse(status_code=422, content=error_dict)



# 4. Include Routers
app.include_router(health_router)
app.include_router(zones_router)
app.include_router(hazard_router)
app.include_router(habitations_router)
app.include_router(sites_router)
app.include_router(alerts_router)
app.include_router(plan_router)
app.include_router(recommendations_router)
app.include_router(scenario_router)
app.include_router(auth_router)


@app.get("/", tags=["General"])
def root_info() -> dict[str, Any]:
    """Root metadata endpoint."""
    return {
        "name": "SETU-DRR API",
        "description": "Hazard Red Zone & Relocation Decision Support Platform",
        "version": api_settings.MODEL_VERSION,
        "docs": "/docs",
        "health": "/health/live",
    }
