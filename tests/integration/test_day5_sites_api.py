"""Integration tests for Candidate Sites & Capacity Serving API (Day 5).

Endpoints tested:
- GET /habitations/{id}/sites
- GET /sites/{id}
- POST /sites/{id}/capacity
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app


from core.config import settings


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def officer_client():
    c = TestClient(app)
    c.post("/auth/login", json={
        "email": "officer@setu.gov.in",
        "password": settings.DEMO_OFFICER_PASSWORD,
    })
    return c


class TestCandidateSitesAPI:
    """Integration test suite for candidate relocation sites and capacity endpoints."""

    def test_get_candidate_sites_for_habitation_success(self, client):
        # 1. Fetch habitations list to obtain a valid habitation ID
        hab_res = client.get("/habitations?limit=1")
        assert hab_res.status_code == 200
        hab_data = hab_res.json()
        assert len(hab_data["items"]) > 0
        hab_id = hab_data["items"][0]["id"]

        # 2. Query candidate relocation sites within 25 km
        res = client.get(f"/habitations/{hab_id}/sites?radius_km=25")
        assert res.status_code == 200
        data = res.json()

        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert isinstance(data["items"], list)

        if data["total"] > 0:
            site = data["items"][0]
            # Validate site card schema
            assert "id" in site
            assert "distance_km" in site
            assert "area_ha" in site
            assert "tenure" in site
            assert site["tenure"] in ("government_revenue", "private", "tenure_unverified")
            assert "slope_mean" in site
            assert "mhi_max" in site
            assert "suitability" in site
            if site["suitability"] is not None:
                assert 0 <= site["suitability"] <= 100
            assert "centroid" in site
            assert len(site["centroid"]) == 2
            assert "screening_grade" in site

            # Validate capacity breakdown
            cap = site["capacity"]
            assert "cc_land" in cap
            assert "cc_final" in cap
            assert "binding_constraint" in cap
            assert cap["binding_constraint"] in ("land", "water", "school", "health")

            # Validate augmented capacity if present
            if site.get("augmented"):
                aug = site["augmented"]
                assert "relieved_constraint" in aug
                assert "augmented_capacity" in aug
                assert aug["augmented_capacity"] >= cap["cc_final"]

    def test_get_candidate_sites_zero_candidates_behavior(self, client):
        """Zero-candidate response is valid HTTP 200 with empty items and no fallback fabrications."""
        hab_res = client.get("/habitations?limit=1")
        hab_id = hab_res.json()["items"][0]["id"]

        # Query with tiny radius (0.001 km = 1 meter) where no sites exist
        res = client.get(f"/habitations/{hab_id}/sites?radius_km=0.001")
        assert res.status_code == 200
        data = res.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["has_more"] is False

    def test_get_candidate_sites_radius_filtering(self, client):
        hab_res = client.get("/habitations?limit=1")
        hab_id = hab_res.json()["items"][0]["id"]

        # Small radius vs large radius
        res_small = client.get(f"/habitations/{hab_id}/sites?radius_km=1")
        assert res_small.status_code == 200
        res_large = client.get(f"/habitations/{hab_id}/sites?radius_km=50")
        assert res_large.status_code == 200

        assert res_small.json()["total"] <= res_large.json()["total"]

    def test_get_candidate_sites_suitability_filter(self, client):
        hab_res = client.get("/habitations?limit=1")
        hab_id = hab_res.json()["items"][0]["id"]

        res = client.get(f"/habitations/{hab_id}/sites?min_suitability=90&radius_km=50")
        assert res.status_code == 200
        for item in res.json()["items"]:
            assert item["suitability"] >= 90

    def test_get_candidate_sites_nonexistent_habitation_404(self, client):
        res = client.get("/habitations/99999999/sites")
        assert res.status_code == 404
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] == "HABITATION_NOT_FOUND"

    def test_get_candidate_site_detail_success(self, client):
        # 1. Fetch a site ID
        hab_res = client.get("/habitations?limit=1")
        hab_id = hab_res.json()["items"][0]["id"]
        sites_res = client.get(f"/habitations/{hab_id}/sites?radius_km=50")
        if sites_res.json()["total"] == 0:
            pytest.skip("No candidate sites found in test database.")

        site_id = sites_res.json()["items"][0]["id"]

        # 2. Get site detail
        detail_res = client.get(f"/sites/{site_id}")
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["id"] == site_id
        assert "geometry" in detail
        assert "capacity" in detail
        assert "screening_grade" in detail

    def test_get_candidate_site_detail_nonexistent_404(self, client):
        res = client.get("/sites/99999999")
        assert res.status_code == 404
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] == "SITE_NOT_FOUND"

    def test_recompute_site_capacity_simulation(self, officer_client):
        # 1. Fetch site ID
        hab_res = officer_client.get("/habitations?limit=1")
        hab_id = hab_res.json()["items"][0]["id"]
        sites_res = officer_client.get(f"/habitations/{hab_id}/sites?radius_km=50")
        if sites_res.json()["total"] == 0:
            pytest.skip("No candidate sites found in test database.")

        site_id = sites_res.json()["items"][0]["id"]

        # 2. Recompute capacity with overrides
        payload = {
            "plot_area_m2": 60.0,  # denser plots
            "water_lpcd": 70,
            "daily_water_yield_liters": 150000.0,
            "spare_school_seats": 500,
            "spare_health_capacity_pop": 5000,
            "livelihood_multiplier": 1.0,
        }
        res = officer_client.post(f"/sites/{site_id}/capacity", json=payload)
        assert res.status_code == 200
        data = res.json()

        assert data["site_id"] == site_id
        assert "base_capacity" in data
        assert "scenario_capacity" in data
        assert "delta_households" in data
        assert "augmented_options" in data
        assert "screening_grade" in data

    def test_recompute_site_capacity_invalid_input_422(self, officer_client):
        # Negative plot area should fail validation with standard error envelope
        payload = {"plot_area_m2": -50.0}
        res = officer_client.post("/sites/1/capacity", json=payload)
        assert res.status_code == 422
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
