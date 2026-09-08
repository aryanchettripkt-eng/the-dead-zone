"""Integration tests for /habitations and /habitations/{id}/risk API endpoints."""

import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


class TestHabitationsApi:
    def test_get_habitations_default_urgency_sort(self):
        response = client.get("/habitations", params={"limit": 10})
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert data["total"] > 0
        items = data["items"]

        # Check deterministic urgency ordering (priority_score DESC)
        for i in range(len(items) - 1):
            assert items[i]["priority_score"] >= items[i + 1]["priority_score"]

    def test_get_habitations_caseload_sort(self):
        response = client.get("/habitations", params={"sort": "caseload", "limit": 10})
        assert response.status_code == 200
        data = response.json()
        items = data["items"]

        # Check deterministic caseload ordering (caseload_score DESC)
        for i in range(len(items) - 1):
            assert items[i]["caseload_score"] >= items[i + 1]["caseload_score"]

    def test_get_habitations_tier_filter(self):
        response = client.get("/habitations", params={"tier": "immediate"})
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["tier"] == "immediate"

    def test_get_habitation_risk_dossier_success(self):
        # Retrieve first habitation from queue
        list_res = client.get("/habitations", params={"limit": 1})
        assert list_res.status_code == 200
        hab_id = list_res.json()["items"][0]["id"]

        response = client.get(f"/habitations/{hab_id}/risk")
        assert response.status_code == 200
        dossier = response.json()

        assert dossier["id"] == hab_id
        assert "name" in dossier
        assert "population" in dossier
        assert "vulnerability" in dossier
        assert "triage_rationale" in dossier
        assert "past_disasters" in dossier
        assert "top_contributing_factors" in dossier
        assert "screening_grade" in dossier

    def test_get_habitation_risk_dossier_not_found(self):
        response = client.get("/habitations/999999/risk")
        assert response.status_code == 404
        err = response.json()
        assert err["error"]["code"] == "HABITATION_NOT_FOUND"
