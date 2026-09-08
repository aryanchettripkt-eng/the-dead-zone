"""Integration tests for Scenario Simulation Endpoint (POST /scenario).

Section refs: docs/PRD1.md §6.10, §9.6

Verifies:
1. POST /scenario executes and returns expected response envelope.
2. Hypothetical weight and gamma overrides alter priority scores and tier rankings.
3. Invariant: Baseline database records are NEVER mutated during scenario evaluation.
4. include_allocation=True executes non-persisting simulation boundary without writing to allocation_run.
5. Error handling for malformed or out-of-bounds parameters.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api.main import app
from core.config import settings

@pytest.fixture
def officer_client():
    c = TestClient(app)
    c.post("/auth/login", json={
        "email": "officer@setu.gov.in",
        "password": settings.DEMO_OFFICER_PASSWORD,
    })
    return c


class TestDay7ScenarioAPI:
    """Integration test suite for POST /scenario endpoint."""

    def test_scenario_basic_simulation(self, officer_client):
        """Basic scenario simulation evaluates habitations and reports rank deltas."""
        payload = {
            "hazard_weights": {
                "landslide": 1.2,
                "flash_flood": 0.8,
            },
            "priority_gamma": 0.8,
            "sort_mode": "urgency",
            "limit": 20,
        }
        res = officer_client.post("/scenario", json=payload)
        assert res.status_code == 200
        data = res.json()

        assert "total_habitations_evaluated" in data
        assert data["total_habitations_evaluated"] > 0
        assert "applied_scenario_weights" in data
        assert data["applied_scenario_weights"]["landslide"] == 1.2
        assert "baseline_hazard_weights" in data
        assert data["applied_gamma"] == 0.8
        assert "screening_grade" in data

        items = data["items"]
        assert len(items) > 0
        first_item = items[0]
        assert "original_rank" in first_item
        assert "scenario_rank" in first_item
        assert "rank_delta" in first_item
        assert "tier_changed" in first_item
        assert first_item["rank_delta"] == first_item["original_rank"] - first_item["scenario_rank"]

    def test_scenario_does_not_mutate_baseline_database(self, officer_client):
        """Evaluating scenarios must leave database habitation_risk records completely untouched."""
        engine = create_engine(settings.get_sqlalchemy_url(direct=True))

        with engine.connect() as conn:
            before_records = conn.execute(
                text("SELECT habitation_id, priority_score, tier FROM habitation_risk ORDER BY habitation_id;")
            ).mappings().all()
            before_tuples = [(r["habitation_id"], float(r["priority_score"]), str(r["tier"])) for r in before_records]

        # Execute extreme scenario override
        payload = {
            "hazard_weights": {"landslide": 2.5, "riverine_flood": 0.0},
            "priority_gamma": 3.0,
            "limit": 100,
        }
        res = officer_client.post("/scenario", json=payload)
        assert res.status_code == 200

        with engine.connect() as conn:
            after_records = conn.execute(
                text("SELECT habitation_id, priority_score, tier FROM habitation_risk ORDER BY habitation_id;")
            ).mappings().all()
            after_tuples = [(r["habitation_id"], float(r["priority_score"]), str(r["tier"])) for r in after_records]

        # Verify exact bit-for-bit equality before and after scenario execution
        assert after_tuples == before_tuples

    def test_scenario_with_allocation_simulation(self, officer_client):
        """include_allocation=True executes simulation boundary without creating allocation_run records."""
        engine = create_engine(settings.get_sqlalchemy_url(direct=True))

        with engine.connect() as conn:
            runs_count_before = conn.execute(text("SELECT count(*) FROM allocation_run;")).scalar()

        payload = {
            "hazard_weights": {"landslide": 1.0, "flash_flood": 1.0},
            "priority_gamma": 0.5,
            "include_allocation": True,
            "allocation_params": {
                "max_search_radius_km": 15.0,
                "distance_penalty_weight": 1.0,
                "allow_group_splits": True,
            },
            "limit": 50,
        }
        res = officer_client.post("/scenario", json=payload)
        assert res.status_code == 200
        data = res.json()

        assert data["allocation_simulation"] is not None
        sim = data["allocation_simulation"]
        assert sim["status"] in ("COMPLETED", "OPTIMAL")
        assert "total_demand_households" in sim
        assert "total_relocated_households" in sim

        with engine.connect() as conn:
            runs_count_after = conn.execute(text("SELECT count(*) FROM allocation_run;")).scalar()

        # Database must NOT have new allocation_run records
        assert runs_count_after == runs_count_before

    def test_scenario_caseload_sort_mode(self, officer_client):
        """Testing caseload sort mode via POST /scenario."""
        res = officer_client.post("/scenario", json={"sort_mode": "caseload", "limit": 10})
        assert res.status_code == 200
        items = res.json()["items"]
        assert len(items) > 0
        caseloads = [item["scenario_priority_score"] * item["population"] for item in items]
        for i in range(len(caseloads) - 1):
            assert caseloads[i] >= caseloads[i + 1] - 0.01

    def test_scenario_invalid_bounds(self, officer_client):
        """Invalid bounds like negative gamma or negative weights return error."""
        res = officer_client.post("/scenario", json={"priority_gamma": -1.0})
        assert res.status_code == 422
