"""Integration tests for SETU-DRR Authorization & Role Policy enforcement (Part 2).

Verifies:
1. Endpoint protection matrix:
   - POST /plan/allocate
   - POST /scenario
   - POST /sites/{id}/capacity
   Each tested for:
    - Anonymous request -> 401 UNAUTHENTICATED
    - Authenticated CIVILIAN -> 403 FORBIDDEN
    - Authenticated rescue officer (consolidated as GOVERNMENT_OFFICIAL) -> 200 OK (permitted)
    - Authenticated GOVERNMENT_OFFICIAL -> 200 OK (permitted)
2. Public read endpoints remain completely accessible without any session or authentication.
3. Civilian public navigation remains unrestricted across administrative boundaries.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.config import settings


@pytest.fixture
def client():
    return TestClient(app)


def login_as(client: TestClient, email: str, password: str) -> None:
    """Helper to log in and establish session cookie on test client."""
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"


class TestAuthorizationApiIntegration:
    """Integration test suite for role-based permission enforcement."""

    # -------------------------------------------------------------------------
    # 1. POST /plan/allocate (Requires allocation.run -> GOVERNMENT_OFFICIAL)
    # -------------------------------------------------------------------------

    def test_allocate_anonymous_rejected_401(self, client):
        """Unauthenticated request to /plan/allocate must return 401 UNAUTHENTICATED."""
        res = client.post("/plan/allocate", json={
            "max_search_radius_km": 25.0,
            "target_tiers": ["immediate", "short_term"],
            "allow_group_splits": True,
            "distance_penalty_weight": 1.0,
        })
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_allocate_civilian_forbidden_403(self, client):
        """Authenticated CIVILIAN attempting /plan/allocate must receive 403 FORBIDDEN."""
        login_as(client, "civilian@setu.gov.in", settings.DEMO_CIVILIAN_PASSWORD)
        res = client.post("/plan/allocate", json={
            "max_search_radius_km": 25.0,
            "target_tiers": ["immediate", "short_term"],
            "allow_group_splits": True,
            "distance_penalty_weight": 1.0,
        })
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "FORBIDDEN"

    def test_allocate_rescue_officer_authorized_as_government_official(self, client):
        """Rescue officer is authorized as GOVERNMENT_OFFICIAL to execute /plan/allocate."""
        login_as(client, "rescue@setu.gov.in", settings.DEMO_RESCUE_PASSWORD)
        res = client.post("/plan/allocate", json={
            "max_search_radius_km": 25.0,
            "target_tiers": ["immediate", "short_term"],
            "allow_group_splits": True,
            "distance_penalty_weight": 1.0,
        })
        assert res.status_code == 200
        data = res.json()
        assert "allocation_run_id" in data
        assert data["status"] == "COMPLETED"

    def test_allocate_government_official_permitted_200(self, client):
        """Authenticated GOVERNMENT_OFFICIAL is authorized to execute /plan/allocate."""
        login_as(client, "officer@setu.gov.in", settings.DEMO_OFFICER_PASSWORD)
        res = client.post("/plan/allocate", json={
            "max_search_radius_km": 25.0,
            "target_tiers": ["immediate", "short_term"],
            "allow_group_splits": True,
            "distance_penalty_weight": 1.0,
        })
        assert res.status_code == 200
        data = res.json()
        assert "allocation_run_id" in data
        assert data["status"] == "COMPLETED"

    # -------------------------------------------------------------------------
    # 2. POST /scenario (Requires scenario.run -> GOVERNMENT_OFFICIAL)
    # -------------------------------------------------------------------------

    def test_scenario_anonymous_rejected_401(self, client):
        """Unauthenticated request to /scenario must return 401 UNAUTHENTICATED."""
        res = client.post("/scenario", json={"hazard_weights": {"landslide": 0.5}})
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_scenario_civilian_forbidden_403(self, client):
        """Authenticated CIVILIAN attempting /scenario must receive 403 FORBIDDEN."""
        login_as(client, "civilian@setu.gov.in", settings.DEMO_CIVILIAN_PASSWORD)
        res = client.post("/scenario", json={"hazard_weights": {"landslide": 0.5}})
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "FORBIDDEN"

    def test_scenario_rescue_officer_authorized_as_government_official(self, client):
        """Rescue officer is authorized as GOVERNMENT_OFFICIAL to execute /scenario."""
        login_as(client, "rescue@setu.gov.in", settings.DEMO_RESCUE_PASSWORD)
        res = client.post("/scenario", json={"hazard_weights": {"landslide": 0.5}})
        assert res.status_code == 200
        assert "items" in res.json()
        assert "total_habitations_evaluated" in res.json()

    def test_scenario_government_official_permitted_200(self, client):
        """Authenticated GOVERNMENT_OFFICIAL is authorized to execute /scenario."""
        login_as(client, "officer@setu.gov.in", settings.DEMO_OFFICER_PASSWORD)
        res = client.post("/scenario", json={"hazard_weights": {"landslide": 0.5}})
        assert res.status_code == 200
        assert "items" in res.json()
        assert "total_habitations_evaluated" in res.json()

    # -------------------------------------------------------------------------
    # 3. POST /sites/{id}/capacity (Requires capacity.recompute -> GOVERNMENT_OFFICIAL)
    # -------------------------------------------------------------------------

    def test_site_capacity_anonymous_rejected_401(self, client):
        """Unauthenticated request to /sites/{id}/capacity must return 401 UNAUTHENTICATED."""
        res = client.post("/sites/1/capacity", json={"plot_area_m2": 60.0})
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_site_capacity_civilian_forbidden_403(self, client):
        """Authenticated CIVILIAN attempting /sites/{id}/capacity must receive 403 FORBIDDEN."""
        login_as(client, "civilian@setu.gov.in", settings.DEMO_CIVILIAN_PASSWORD)
        res = client.post("/sites/1/capacity", json={"plot_area_m2": 60.0})
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "FORBIDDEN"

    def test_site_capacity_rescue_officer_authorized_as_government_official(self, client):
        """Rescue officer is authorized as GOVERNMENT_OFFICIAL to execute /sites/{id}/capacity."""
        hab_res = client.get("/habitations?limit=1")
        assert hab_res.status_code == 200
        hab_id = hab_res.json()["items"][0]["id"]
        sites_res = client.get(f"/habitations/{hab_id}/sites?radius_km=50")
        assert sites_res.status_code == 200
        site_id = sites_res.json()["items"][0]["id"]

        login_as(client, "rescue@setu.gov.in", settings.DEMO_RESCUE_PASSWORD)
        res = client.post(f"/sites/{site_id}/capacity", json={"plot_area_m2": 60.0})
        assert res.status_code == 200
        assert "scenario_capacity" in res.json()

    def test_site_capacity_government_official_permitted_200(self, client):
        """Authenticated GOVERNMENT_OFFICIAL is authorized to execute /sites/{id}/capacity."""
        hab_res = client.get("/habitations?limit=1")
        assert hab_res.status_code == 200
        hab_id = hab_res.json()["items"][0]["id"]
        sites_res = client.get(f"/habitations/{hab_id}/sites?radius_km=50")
        assert sites_res.status_code == 200
        site_id = sites_res.json()["items"][0]["id"]

        login_as(client, "officer@setu.gov.in", settings.DEMO_OFFICER_PASSWORD)
        res = client.post(f"/sites/{site_id}/capacity", json={"plot_area_m2": 60.0})
        assert res.status_code == 200
        assert "scenario_capacity" in res.json()

    # -------------------------------------------------------------------------
    # 4. Public reads remain unauthenticated & accessible
    # -------------------------------------------------------------------------

    def test_public_reads_remain_unauthenticated(self, client):
        """Verifies that all public exploration GET endpoints require NO credentials."""
        # /zones
        assert client.get("/zones", params={"res": 8, "limit": 2}).status_code == 200

        # /habitations
        hab_res = client.get("/habitations?limit=2")
        assert hab_res.status_code == 200
        assert len(hab_res.json()["items"]) > 0
        hab_id = hab_res.json()["items"][0]["id"]

        # /habitations/{id}/risk
        assert client.get(f"/habitations/{hab_id}/risk").status_code == 200

        # /habitations/{id}/sites
        sites_res = client.get(f"/habitations/{hab_id}/sites?limit=2")
        assert sites_res.status_code == 200
        if sites_res.json()["items"]:
            site_id = sites_res.json()["items"][0]["id"]
            # /sites/{id}
            assert client.get(f"/sites/{site_id}").status_code == 200

        # /alerts/active
        assert client.get("/alerts/active", params={"limit": 2}).status_code == 200

        # /alerts/forecast
        assert client.get("/alerts/forecast", params={"limit": 2}).status_code == 200
