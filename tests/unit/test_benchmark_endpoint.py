"""Unit and integration tests for the external recommendation and allocation benchmark endpoints."""

from __future__ import annotations

import json
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api.main import app
from core.config import settings


def test_plan_external_recommendations_endpoint():
    """GET /plan/external-recommendations?district=Barpeta returns all 14 external proposals."""
    client = TestClient(app)
    res = client.get("/plan/external-recommendations?district=Barpeta")
    assert res.status_code == 200
    data = res.json()
    assert data["district"] == "Barpeta"
    assert data["total_count"] == 14
    assert data["total_households_recommended"] == 5348
    assert len(data["items"]) == 14
    first = data["items"][0]
    assert first["origin_type"] == "external"
    assert first["decision_status"] == "recommendation"
    assert "Screening Grade" in first["screening_grade"]


def test_plan_benchmark_external_only_state():
    """GET /plan/benchmark?district=Barpeta returns external_only status when no canonical allocation exists."""
    client = TestClient(app)
    res = client.get("/plan/benchmark?district=Barpeta")
    assert res.status_code == 200
    data = res.json()
    assert data["district"] == "Barpeta"
    assert data["status"] == "external_only"
    assert data["setu_allocation_available"] is False
    assert data["total_external_recommended_households"] == 5348
    assert data["total_setu_allocated_households"] == 0
    assert data["external_recommendations_count"] == 14
    assert data["setu_allocations_count"] == 0
    assert len(data["comparisons"]) == 14

    for c in data["comparisons"]:
        assert c["external_recommendation"] is not None
        assert c["setu_canonical_allocation"] is None
        assert c["site_match"] is False
        assert any("SETU canonical allocation has not been run" in n for n in c["methodology_divergence_notes"])


def test_habitation_external_recommendations_endpoint():
    """GET /habitations/{id}/external-recommendations returns recommendations for the target habitation."""
    eng = create_engine(settings.get_sqlalchemy_url())
    with eng.connect() as conn:
        hab_id = conn.execute(
            text("SELECT id FROM habitation WHERE source_habitation_id = 'barpeta_10' LIMIT 1")
        ).scalar()

    assert hab_id is not None
    client = TestClient(app)
    res = client.get(f"/habitations/{hab_id}/external-recommendations")
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 1
    assert items[0]["external_habitation_key"] == "barpeta_10"
    assert items[0]["external_site_key"] == "baghbor_29"
    assert items[0]["households"] == 132
