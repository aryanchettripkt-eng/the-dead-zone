"""Contract tests for OpenAPI schema generation and export."""

import json
from pathlib import Path
import pytest
from api.main import app


class TestOpenAPIContract:
    def test_committed_openapi_matches_app(self):
        """B4: Verifies that committed openapi.json accurately mirrors the FastAPI schema without mutative side-effects."""
        openapi_schema = app.openapi()
        assert openapi_schema is not None
        assert "paths" in openapi_schema
        assert "components" in openapi_schema

        root_path = Path(__file__).resolve().parents[2]
        openapi_file = root_path / "openapi.json"
        assert openapi_file.exists(), "openapi.json must exist in workspace root"
        assert openapi_file.stat().st_size > 1000

        with open(openapi_file, "r", encoding="utf-8") as f:
            committed_schema = json.load(f)

        assert committed_schema == openapi_schema, (
            "Committed openapi.json is out of date with current FastAPI schema. "
            "Run 'pnpm export:openapi' or 'uv run python scripts/export_openapi.py' to update it."
        )

    def test_error_schemas_contract(self):
        """B5: Verifies that OpenAPI contract documents custom ErrorEnvelope and eliminates stock HTTPValidationError."""
        schema = app.openapi()
        schemas = schema["components"]["schemas"]

        # Custom error schemas must be present
        assert "ErrorEnvelope" in schemas
        assert "ErrorDetail" in schemas

        # Stock FastAPI validation schemas must NOT be present
        assert "HTTPValidationError" not in schemas
        assert "ValidationError" not in schemas

        paths = schema["paths"]

        # 422 responses must reference ErrorEnvelope across all parameter endpoints
        for endpoint in ["/zones", "/zones/{h3}", "/habitations", "/habitations/{id}/risk",
                         "/habitations/{id}/sites", "/sites/{id}", "/sites/{id}/capacity",
                         "/alerts/active", "/alerts/forecast", "/plan/allocate", "/scenario"]:
            for method, op in paths[endpoint].items():
                responses = op["responses"]
                assert "422" in responses, f"Endpoint {method.upper()} {endpoint} missing 422 documentation"
                assert responses["422"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/ErrorEnvelope"

        # 400 Bad Request documented on applicable endpoints
        for endpoint in ["/zones", "/zones/{h3}"]:
            for method, op in paths[endpoint].items():
                assert "400" in op["responses"], f"{method.upper()} {endpoint} should document 400"
                assert op["responses"]["400"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/ErrorEnvelope"

        # 404 Not Found documented on entity lookup endpoints and /zones
        for endpoint in ["/zones", "/zones/{h3}", "/habitations/{id}/risk",
                         "/habitations/{id}/sites", "/sites/{id}", "/sites/{id}/capacity"]:
            for method, op in paths[endpoint].items():
                assert "404" in op["responses"], f"{method.upper()} {endpoint} should document 404"
                assert op["responses"]["404"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/ErrorEnvelope"

        # 404 should NOT be documented on /habitations list query (returns empty list if none match)
        assert "404" not in paths["/habitations"]["get"]["responses"], "/habitations should not document 404"

        # 500 Internal Error documented on all operational endpoints
        for endpoint in ["/zones", "/zones/{h3}", "/habitations", "/habitations/{id}/risk",
                         "/habitations/{id}/sites", "/sites/{id}", "/sites/{id}/capacity",
                         "/alerts/active", "/alerts/forecast", "/plan/allocate", "/scenario"]:
            for method, op in paths[endpoint].items():
                assert "500" in op["responses"], f"{method.upper()} {endpoint} should document 500"
                assert op["responses"]["500"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/ErrorEnvelope"

        # 503 documented on /health/ready referencing ReadinessResponse
        ready_responses = paths["/health/ready"]["get"]["responses"]
        assert "503" in ready_responses
        assert ready_responses["503"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/ReadinessResponse"

    def test_runtime_error_envelope_matches_contract(self):
        """B5: Verifies runtime error responses match the documented ErrorEnvelope schema across the HTTP boundary."""
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from core.schemas.common import ErrorEnvelope
        from api.routes.health import ReadinessResponse
        from core.errors import HabitationNotFoundError

        # Use raise_server_exceptions=False to test actual HTTP 500 response handling
        client = TestClient(app, raise_server_exceptions=False)

        # 1. Runtime 422 validation error
        res_422 = client.get("/zones?limit=99999")
        assert res_422.status_code == 422
        body_422 = res_422.json()
        validated_422 = ErrorEnvelope.model_validate(body_422)
        assert validated_422.error.code == "VALIDATION_ERROR"
        assert "errors" in validated_422.error.details

        # 2. Runtime 400 bad request error
        res_400 = client.get("/zones?bbox=invalid_bbox")
        assert res_400.status_code == 400
        body_400 = res_400.json()
        validated_400 = ErrorEnvelope.model_validate(body_400)
        assert validated_400.error.code == "INVALID_BBOX"

        # 3. Runtime 404 not found error
        with patch("api.services.habitations_service.HabitationsService.get_habitation_risk_dossier", side_effect=HabitationNotFoundError(999999)):
            res_404 = client.get("/habitations/999999/risk")
            assert res_404.status_code == 404
            body_404 = res_404.json()
            validated_404 = ErrorEnvelope.model_validate(body_404)
            assert validated_404.error.code == "HABITATION_NOT_FOUND"

        # 4. Runtime 500 internal server error crossing the HTTP response boundary
        with patch("api.services.zones_service.ZonesService.get_zones", side_effect=RuntimeError("Simulated database failure")):
            res_500 = client.get("/zones")
            assert res_500.status_code == 500
            body_500 = res_500.json()
            validated_500 = ErrorEnvelope.model_validate(body_500)
            assert validated_500.error.code == "INTERNAL_ERROR"

        # 5. Runtime 503 readiness probe response
        from api.dependencies import get_db
        from unittest.mock import MagicMock
        mock_db = MagicMock()
        mock_db.execute.side_effect = RuntimeError("DB connection dropped")
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            res_503 = client.get("/health/ready")
            assert res_503.status_code == 503
            body_503 = res_503.json()
            validated_503 = ReadinessResponse.model_validate(body_503)
            assert validated_503.status == "not_ready"
            assert validated_503.checks.database is False
            assert validated_503.error == "DB connection dropped"
        finally:
            app.dependency_overrides.pop(get_db, None)


