"""Day 0 Unit Tests — Foundation, Configuration, Enums, Errors, and Health Checks."""

import pytest
from fastapi.testclient import TestClient

from core.enums import Hazard, ZoneClass, Tier, TenureType, BindingConstraint, SortMode
from core.constants import (
    HAZARD_WEIGHTS,
    BETA,
    PRZ_MHI_STATIC,
    PRZ_ANY_SUSCEPTIBILITY,
    CAUTION_MHI_MIN,
    ACTIVE_ALERT_MHI_LIVE,
    FORECAST_HORIZON_HOURS,
    AREA_PER_HOUSEHOLD_M2,
)
from core.errors import (
    ErrorCode,
    AppError,
    InvalidH3IndexError,
    HabitationNotFoundError,
    SiteNotFoundError,
)
from core.config import settings
from api.main import app


def test_core_enums():
    """Verify all required domain enums are well-defined."""
    assert Hazard.LANDSLIDE == "landslide"
    assert Hazard.FLASH_FLOOD == "flash_flood"
    assert ZoneClass.PERMANENT_RED == "permanent_red"
    assert ZoneClass.ACTIVE_ALERT == "active_alert"
    assert ZoneClass.FORECAST_ALERT == "forecast_alert"
    assert Tier.IMMEDIATE == "immediate"
    assert Tier.MITIGATE_IN_SITU == "mitigate_in_situ"
    assert TenureType.GOVERNMENT_REVENUE == "government_revenue"
    assert BindingConstraint.WATER == "water"
    assert SortMode.CASELOAD == "caseload"


def test_domain_constants():
    """Verify core numerical constants match PRD §14.1."""
    assert HAZARD_WEIGHTS[Hazard.LANDSLIDE] == 1.0
    assert HAZARD_WEIGHTS[Hazard.FLASH_FLOOD] == 1.0
    assert HAZARD_WEIGHTS[Hazard.STORM_SURGE] == 0.9
    assert HAZARD_WEIGHTS[Hazard.RIVERINE_FLOOD] == 0.8
    assert HAZARD_WEIGHTS[Hazard.COASTAL_EROSION] == 0.7
    assert BETA == 1.0
    assert PRZ_MHI_STATIC == 0.75
    assert PRZ_ANY_SUSCEPTIBILITY == 0.85
    assert CAUTION_MHI_MIN == 0.45
    assert ACTIVE_ALERT_MHI_LIVE == 0.75
    assert FORECAST_HORIZON_HOURS == 72
    assert AREA_PER_HOUSEHOLD_M2 == pytest.approx(126.0)


def test_error_envelope_formatting():
    """Verify standard error envelope JSON structure."""
    err = InvalidH3IndexError("invalid_h3_123")
    formatted = err.to_dict(request_id="req-test-999")

    assert "error" in formatted
    assert formatted["error"]["code"] == ErrorCode.INVALID_H3
    assert formatted["error"]["request_id"] == "req-test-999"
    assert "invalid_h3_123" in formatted["error"]["message"]
    assert formatted["error"]["details"]["h3_index"] == "invalid_h3_123"


def test_settings_loading():
    """Verify central settings load with defaults."""
    assert settings.DEMO_MODE in (True, False)
    assert settings.LOG_LEVEL in ["DEBUG", "INFO", "WARNING", "ERROR"]
    assert settings.MODEL_VERSION == "v1.0.0"
    assert "postgresql" in settings.get_sqlalchemy_url()


def test_fastapi_root_and_liveness():
    """Verify FastAPI service starts and responds on root & liveness endpoints."""
    client = TestClient(app)

    # 1. Root info
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "SETU-DRR API"
    assert "X-Request-ID" in res.headers

    # 2. Liveness check
    res = client.get("/health/live")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["service"] == "setu-drr-api"
