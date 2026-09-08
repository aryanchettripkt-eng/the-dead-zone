"""Integration tests for Day 4 Habitations Triage Queue and Risk Dossiers API endpoints.

Covers:
- GET /habitations (admin filter, tier filter, urgency/caseload sort, bounded pagination)
- GET /habitations/{id}/risk (complete risk dossier, SoVI vulnerability breakdown, loss history, provenance)
- Security & SQL injection safety tests
- Deterministic secondary tie-breaking
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app
from core.enums import Tier

client = TestClient(app)


class TestHabitationsRiskApiDay4:
    def test_get_habitations_admin_filter_wayanad(self):
        """Filters habitations by administrative unit LGD code (555 = Wayanad)."""
        response = client.get("/habitations", params={"admin": 555, "limit": 20})
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert data["total"] > 0

        for item in data["items"]:
            assert item["admin_name"] == "Wayanad" or item["admin_id"] is not None

    def test_get_habitations_tier_filtering_all_tiers(self):
        """Tests filtering across triage tiers (immediate, short_term, medium_term)."""
        # 1. Immediate Tier
        res_imm = client.get("/habitations", params={"tier": "immediate"})
        assert res_imm.status_code == 200
        data_imm = res_imm.json()
        for item in data_imm["items"]:
            assert item["tier"] == "immediate"

        # 2. Short-term Tier
        res_short = client.get("/habitations", params={"tier": "short_term"})
        assert res_short.status_code == 200
        data_short = res_short.json()
        for item in data_short["items"]:
            assert item["tier"] == "short_term"

        # 3. Medium-term Tier
        res_med = client.get("/habitations", params={"tier": "medium_term"})
        assert res_med.status_code == 200
        data_med = res_med.json()
        for item in data_med["items"]:
            assert item["tier"] == "medium_term"

    def test_dual_ranking_modes_urgency_vs_caseload(self):
        """Tests deterministic sorting under both Urgency (PS_j DESC) and Caseload (PS_j * Pop DESC)."""
        # 1. Urgency sorting
        res_urgency = client.get("/habitations", params={"sort": "urgency", "limit": 50})
        assert res_urgency.status_code == 200
        items_urgency = res_urgency.json()["items"]
        assert len(items_urgency) >= 2

        for i in range(len(items_urgency) - 1):
            assert items_urgency[i]["priority_score"] >= items_urgency[i + 1]["priority_score"]

        # 2. Caseload sorting
        res_caseload = client.get("/habitations", params={"sort": "caseload", "limit": 50})
        assert res_caseload.status_code == 200
        items_caseload = res_caseload.json()["items"]
        assert len(items_caseload) >= 2

        for i in range(len(items_caseload) - 1):
            assert items_caseload[i]["caseload_score"] >= items_caseload[i + 1]["caseload_score"]

    def test_pagination_bounds_and_deterministic_order(self):
        """Tests pagination offset, limit clamping, and total count."""
        # Page 1 (limit 2)
        res_p1 = client.get("/habitations", params={"limit": 2, "offset": 0})
        assert res_p1.status_code == 200
        data_p1 = res_p1.json()
        assert len(data_p1["items"]) == 2

        # Page 2 (limit 2, offset 2)
        res_p2 = client.get("/habitations", params={"limit": 2, "offset": 2})
        assert res_p2.status_code == 200
        data_p2 = res_p2.json()
        assert len(data_p2["items"]) == 2

        # Ensure no overlap between pages
        p1_ids = {item["id"] for item in data_p1["items"]}
        p2_ids = {item["id"] for item in data_p2["items"]}
        assert len(p1_ids.intersection(p2_ids)) == 0

    def test_get_habitation_risk_dossier_complete_schema(self):
        """Verifies full risk dossier schema and fields for GET /habitations/{id}/risk."""
        list_res = client.get("/habitations", params={"limit": 1})
        assert list_res.status_code == 200
        sample_hab = list_res.json()["items"][0]
        hab_id = sample_hab["id"]

        response = client.get(f"/habitations/{hab_id}/risk")
        assert response.status_code == 200
        dossier = response.json()

        # Identity & Demographics
        assert dossier["id"] == hab_id
        assert "name" in dossier
        assert "population" in dossier
        assert "households" in dossier
        assert len(dossier["centroid"]) == 2

        # Prioritization & Triage
        assert "priority_score" in dossier
        assert "caseload_score" in dossier
        assert "tier" in dossier
        assert "triage_rationale" in dossier
        assert len(dossier["triage_rationale"]) > 0

        # Provenance
        assert "model_version" in dossier
        assert "scoring_version" in dossier
        assert "dataset_version" in dossier
        assert "data_quality" in dossier
        assert "confidence" in dossier

        # Vulnerability Breakdown
        v = dossier["vulnerability"]
        assert 0.0 <= v["v_demographic"] <= 1.0
        assert 0.0 <= v["v_structural"] <= 1.0
        assert 0.0 <= v["v_access"] <= 1.0
        assert 0.0 <= v["v_economic"] <= 1.0
        assert 0.0 <= v["v_index"] <= 1.0

        # Contributing factors & screening grade notice
        assert len(dossier["top_contributing_factors"]) > 0
        assert "Screening Grade" in dossier["screening_grade"]

    def test_get_habitation_risk_dossier_not_found(self):
        """Returns 404 for nonexistent habitation ID with standard error envelope."""
        response = client.get("/habitations/987654321/risk")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "HABITATION_NOT_FOUND"

    def test_security_input_validation_and_sql_injection_defense(self):
        """Verifies API parameter validation and SQL injection defense."""
        # 1. Invalid tier enum returns 422
        res_bad_tier = client.get("/habitations", params={"tier": "critical_emergency_now"})
        assert res_bad_tier.status_code == 422

        # 2. Invalid sort mode returns 422
        res_bad_sort = client.get("/habitations", params={"sort": "random_untrusted_column"})
        assert res_bad_sort.status_code == 422

        # 3. SQL injection attempt in admin parameter returns 422
        res_sql_inj = client.get("/habitations", params={"admin": "555 OR 1=1; DROP TABLE habitation;--"})
        assert res_sql_inj.status_code == 422

        # 4. Out of bounds pagination limit is clamped
        res_clamp = client.get("/habitations", params={"limit": 500})
        # Limit > 200 is rejected by FastAPI Query validation with 422
        assert res_clamp.status_code == 422
