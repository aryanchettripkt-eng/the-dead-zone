"""Integration tests for Dynamic Alerts, Forecasts & Relocation Allocation APIs (Day 6).

Endpoints tested:
- GET /alerts/active
- GET /alerts/forecast
- POST /plan/allocate
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app
from core.enums import Tier


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def officer_client():
    from core.config import settings
    c = TestClient(app)
    c.post("/auth/login", json={
        "email": "officer@setu.gov.in",
        "password": settings.DEMO_OFFICER_PASSWORD,
    })
    return c


class TestDay6AlertsAndAllocationAPI:
    """Integration test suite for Day 6 dynamic serving and allocation endpoints."""

    def test_get_active_alerts_structure(self, client):
        res = client.get("/alerts/active?limit=10")
        assert res.status_code == 200
        data = res.json()

        assert "total_active_cells" in data
        assert "total_exposed_population" in data
        assert "issued_at" in data
        assert "items" in data
        assert isinstance(data["items"], list)

        assert data["total_active_cells"] >= 1
        assert len(data["items"]) >= 1
        item = data["items"][0]
        assert "h3" in item
        assert "mhi_live" in item
        assert item["mhi_live"] >= 0.75
        assert "mhi_static" in item
        assert item["mhi_static"] < 0.75
        assert "dominant_hazard" in item
        assert "centroid" in item
        assert len(item["centroid"]) == 2
        assert "screening_grade" in item

    def test_get_forecast_alerts_structure_and_72h_validation(self, client):
        # 1. Valid 48h horizon query
        res = client.get("/alerts/forecast?horizon=48&limit=10")
        assert res.status_code == 200
        data = res.json()

        assert "total_forecast_cells" in data
        assert "total_exposed_population" in data
        assert "issuing_model" in data
        assert data["issuing_model"] is None or isinstance(data["issuing_model"], str)
        assert data["horizon_hours"] == 48
        assert "items" in data

        assert data["total_forecast_cells"] >= 1
        assert len(data["items"]) >= 1
        item = data["items"][0]
        assert "h3" in item
        assert "mhi_fcst" in item
        assert item["mhi_fcst"] >= 0.75
        assert "mhi_static" in item
        assert item["mhi_static"] < 0.75
        assert "horizon_hours" in item
        assert 1 <= item["horizon_hours"] <= 48
        assert "screening_grade" in item

        # 2. Reject horizon > 72h (FR-3.12 constraint)
        res_invalid_high = client.get("/alerts/forecast?horizon=96")
        assert res_invalid_high.status_code == 422

        # 3. Reject horizon < 1h
        res_invalid_low = client.get("/alerts/forecast?horizon=0")
        assert res_invalid_low.status_code == 422

    def test_forecast_horizon_boundary_semantics(self, client):
        """H3 boundary test: verifies within-horizon semantics and boundary conditions on seeded alerts.
        
        Seeded forecasts exist at 24h, 48h, and 72h lead times.
        - horizon=23: immediately outside 24h boundary -> excludes 24h (total 0)
        - horizon=24: at 24h boundary -> includes 24h, excludes 48h (total 1)
        - horizon=47: immediately outside 48h boundary -> includes 24h, excludes 48h (total 1)
        - horizon=48: at 48h boundary -> includes 24h and 48h, excludes 72h (total 2)
        - horizon=71: immediately outside 72h boundary -> includes 24h and 48h, excludes 72h (total 2)
        - horizon=72: at 72h boundary -> includes 24h, 48h, and 72h (total 3)
        """
        # Horizon 23: excludes 24h
        res_23 = client.get("/alerts/forecast?horizon=23")
        assert res_23.status_code == 200
        assert res_23.json()["total_forecast_cells"] == 0

        # Horizon 24: includes 24h, excludes 48h and 72h
        res_24 = client.get("/alerts/forecast?horizon=24")
        assert res_24.status_code == 200
        data_24 = res_24.json()
        assert data_24["total_forecast_cells"] == 1
        assert [x["horizon_hours"] for x in data_24["items"]] == [24]

        # Horizon 47: includes 24h, excludes 48h
        res_47 = client.get("/alerts/forecast?horizon=47")
        assert res_47.status_code == 200
        assert res_47.json()["total_forecast_cells"] == 1

        # Horizon 48: includes 24h and 48h, excludes 72h
        res_48 = client.get("/alerts/forecast?horizon=48")
        assert res_48.status_code == 200
        data_48 = res_48.json()
        assert data_48["total_forecast_cells"] == 2
        horizons_48 = {x["horizon_hours"] for x in data_48["items"]}
        assert horizons_48 == {24, 48}

        # Horizon 71: includes 24h and 48h, excludes 72h
        res_71 = client.get("/alerts/forecast?horizon=71")
        assert res_71.status_code == 200
        assert res_71.json()["total_forecast_cells"] == 2

        # Horizon 72: includes 24h, 48h, and 72h
        res_72 = client.get("/alerts/forecast?horizon=72")
        assert res_72.status_code == 200
        data_72 = res_72.json()
        assert data_72["total_forecast_cells"] == 3
        horizons_72 = {x["horizon_hours"] for x in data_72["items"]}
        assert horizons_72 == {24, 48, 72}

    def test_post_plan_allocate_success(self, officer_client):
        payload = {
            "max_search_radius_km": 25.0,
            "target_tiers": ["immediate", "short_term"],
            "allow_group_splits": True,
            "distance_penalty_weight": 1.0,
        }
        res = officer_client.post("/plan/allocate", json=payload)
        assert res.status_code == 200
        data = res.json()

        assert "allocation_run_id" in data
        assert "status" in data
        assert data["status"] == "COMPLETED"
        assert "total_demand_households" in data
        assert "total_relocated_households" in data
        assert "unmet_demand_households" in data
        assert "solver_latency_ms" in data
        assert "assignments" in data
        assert "group_split_warnings" in data
        assert "screening_grade" in data

        # Validate assignment schemas if habitations were allocated
        if data["total_relocated_households"] > 0 and len(data["assignments"]) > 0:
            a = data["assignments"][0]
            assert "habitation_id" in a
            assert "habitation_name" in a
            assert "site_id" in a
            assert "site_distance_km" in a
            assert "households" in a
            assert a["households"] > 0
            assert "tier" in a
            assert "priority_score" in a
            assert "site_suitability" in a
            assert "has_group_split" in a

    def test_post_plan_allocate_invalid_radius_rejection(self, officer_client):
        # Negative search radius
        res = officer_client.post("/plan/allocate", json={"max_search_radius_km": -5.0})
        assert res.status_code == 422

        # Excessively large search radius (> 100km)
        res2 = officer_client.post("/plan/allocate", json={"max_search_radius_km": 500.0})
        assert res2.status_code == 422

    def test_post_plan_allocate_empty_tiers_rejection(self, officer_client):
        res = officer_client.post("/plan/allocate", json={"target_tiers": []})
        assert res.status_code in (400, 422)

    def test_security_sql_injection_defense(self, client):
        # Query active alerts with malicious SQL payload
        res = client.get("/alerts/active?hazard=landslide'%20OR%20'1'='1")
        assert res.status_code == 200
        data = res.json()
        # Should return 0 records cleanly rather than dumping the database
        assert data["total_active_cells"] == 0
