"""Tests asserting Wayanad and Kodagu pilot state is semantically untouched."""

from __future__ import annotations

import json
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api.main import app
from core.config import settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_existing_pilot_habitations_untouched():
    """Wayanad and Kodagu habitations must match baseline exactly."""
    baseline_path = REPO_ROOT / "data" / "baseline_pilot_state.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    expected_map = {h["id"]: h for h in baseline["habitations"]}

    eng = create_engine(settings.get_sqlalchemy_url())
    with eng.connect() as conn:
        rows = conn.execute(
            text("SELECT id, name, type, admin_id, population, households, risk_status FROM habitation WHERE id = ANY(:ids)"),
            {"ids": list(expected_map.keys())},
        ).mappings().fetchall()

        assert len(rows) == len(expected_map)
        for row in rows:
            exp = expected_map[row["id"]]
            assert row["name"] == exp["name"]
            assert row["type"] == exp["type"]
            assert row["admin_id"] == exp["admin_id"]
            assert row["population"] == exp["population"]
            assert row["households"] == exp["households"]
            assert row["risk_status"] == "scored"


def test_existing_pilot_candidate_sites_untouched():
    """Existing 8 pilot candidate sites must match baseline and have correct domain semantics."""
    baseline_path = REPO_ROOT / "data" / "baseline_pilot_state.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    expected_map = {s["id"]: s for s in baseline["candidate_sites"]}

    eng = create_engine(settings.get_sqlalchemy_url())
    with eng.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, area_ha, tenure, slope_mean, mhi_max, cc_land, cc_final,
                       binding_constraint, suitability, assessment_status, eligibility_status
                FROM candidate_site WHERE id = ANY(:ids)
            """),
            {"ids": list(expected_map.keys())},
        ).mappings().fetchall()

        assert len(rows) == len(expected_map)
        for row in rows:
            sid = row["id"]
            exp = expected_map[sid]
            assert round(float(row["area_ha"]), 1) == exp["area_ha"]
            assert row["tenure"] == exp["tenure"]
            assert round(float(row["mhi_max"]), 2) == exp["mhi_max"]
            assert row["cc_land"] == exp["cc_land"]
            assert row["cc_final"] == exp["cc_final"]
            assert row["binding_constraint"] == exp["binding_constraint"]
            assert row["suitability"] == exp["suitability"]

            if sid == 491:
                assert row["assessment_status"] == "partial"
                assert row["eligibility_status"] == "unknown"
            else:
                assert row["assessment_status"] == "fully_assessed"
                assert row["eligibility_status"] == "eligible"


def test_api_wayanad_candidate_sites_unaffected():
    """GET /habitations/724/sites (Chooralmala) must return eligible candidate sites without disruption."""
    client = TestClient(app)
    res = client.get("/habitations/724/sites")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] > 0
    # Site 491 (unknown) must be filtered out when include_screening is default False
    site_ids = [item["id"] for item in data["items"]]
    assert 491 not in site_ids
    for item in data["items"]:
        assert item["allocatable"] is True
        assert item["eligibility_status"] == "eligible"
