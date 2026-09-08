"""Integration test for Neon DB connectivity, PostGIS, and H3 functions."""

import pytest
from fastapi.testclient import TestClient
from api.main import app


def test_health_ready_endpoint():
    """Verify that /health/ready returns 200 OK and reports all extensions healthy."""
    client = TestClient(app)
    res = client.get("/health/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"] is True
    assert data["checks"]["extensions"]["postgis"] is True
    assert data["checks"]["extensions"]["h3"] is True
