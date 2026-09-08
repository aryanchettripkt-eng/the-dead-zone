"""Unit and Boundary Security Tests for SETU-DRR API (Day 7).

Section refs: Prompt Section 10 & 14

Verifies robust handling of untrusted inputs:
1. Rejection of NaN, +Inf, -Inf numeric inputs.
2. Malformed H3 hexadecimal index validation.
3. Bounding box coordinates and area limits.
4. Pagination limit clamping.
5. Scenario parameter bounds.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.h3_utils import is_valid_h3, h3_to_int
from core.errors import InvalidH3IndexError, InvalidBboxError

client = TestClient(app)


@pytest.fixture(autouse=True)
def _authenticate_as_government_official_for_unit_tests():
    """Provides an authenticated Government Official user context for security boundary tests."""
    import uuid
    from datetime import datetime, timezone
    from api.dependencies import require_authenticated
    from core.db_models import AppUser
    from core.enums import Role

    mock_officer = AppUser(
        id=uuid.uuid4(),
        email="officer@setu.gov.in",
        password_hash="mock_hash",
        full_name="Test Officer",
        role=Role.GOVERNMENT_OFFICIAL.value,
        admin_id=158,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_authenticated] = lambda: mock_officer
    yield
    app.dependency_overrides.pop(require_authenticated, None)


class TestSecurityAndRobustness:
    """Security boundary checks and untrusted input validation."""

    def test_malformed_h3_index_rejected(self):
        """Malformed H3 string in /zones/{h3} returns structured 400/422 error."""
        invalid_indexes = [
            "not_an_h3_index",
            "8860064989fffff_extra",
            "000000000000000",
            "../../etc/passwd",
            "<script>alert(1)</script>",
        ]
        for invalid_h3 in invalid_indexes:
            assert not is_valid_h3(invalid_h3)
            res = client.get(f"/zones/{invalid_h3}")
            assert res.status_code in (400, 404, 422)

    def test_invalid_bbox_area_bounds_rejected(self):
        """BBox area exceeding max allowed (5.0 sq deg) is rejected with 400 error."""
        # Excessively large bbox (10 x 10 = 100 sq deg)
        res = client.get("/zones", params={"bbox": "70.0,10.0,80.0,20.0", "res": 8})
        assert res.status_code == 400
        assert "exceeds maximum allowed viewport" in res.json()["error"]["message"]

    def test_inverted_bbox_coordinates_rejected(self):
        """BBox with min_lon >= max_lon or min_lat >= max_lat is rejected with 400."""
        res = client.get("/zones", params={"bbox": "76.3,11.5,75.8,11.9", "res": 8})
        assert res.status_code == 400
        assert "min_lon/min_lat must be strictly less than max_lon/max_lat" in res.json()["error"]["message"]

    def test_out_of_bounds_bbox_coordinates_rejected(self):
        """BBox coordinates outside [-180, 180] or [-90, 90] are rejected."""
        res = client.get("/zones", params={"bbox": "-190.0,11.5,76.3,11.9", "res": 8})
        assert res.status_code == 400

    def test_scenario_nan_inf_rejected(self):
        """Scenario payload containing NaN or Inf string is rejected."""
        # Raw JSON NaN in gamma
        res_nan = client.post(
            "/scenario",
            content='{"priority_gamma": NaN}',
            headers={"Content-Type": "application/json"},
        )
        assert res_nan.status_code in (400, 422)

        # Raw JSON Infinity in gamma
        res_inf = client.post(
            "/scenario",
            content='{"priority_gamma": Infinity}',
            headers={"Content-Type": "application/json"},
        )
        assert res_inf.status_code in (400, 422)

        # Negative gamma
        res_neg = client.post("/scenario", json={"priority_gamma": -1.5})
        assert res_neg.status_code == 422


    def test_scenario_invalid_hazard_weight_rejected(self):
        """Scenario payload with invalid hazard type or negative weight is rejected."""
        # Unknown hazard
        res_unknown = client.post(
            "/scenario",
            json={"hazard_weights": {"meteorite_strike": 2.0}},
        )
        assert res_unknown.status_code == 422

        # Negative weight
        res_neg_weight = client.post(
            "/scenario",
            json={"hazard_weights": {"landslide": -0.5}},
        )
        assert res_neg_weight.status_code in (400, 422)

    def test_pagination_limit_clamping(self):
        """Limits above max allowed are safely clamped or rejected."""
        # Request limit = 10_000 (exceeds 5000 max)
        res = client.get("/zones", params={"bbox": "75.8,11.5,76.3,11.9", "res": 8, "limit": 10000})
        assert res.status_code == 422
