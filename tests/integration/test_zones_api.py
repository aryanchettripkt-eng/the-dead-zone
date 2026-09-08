"""Integration tests for /zones and /zones/{h3} API endpoints."""

import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


class TestZonesApi:
    def test_query_zones_success(self):
        # Query Wayanad bounding box
        response = client.get(
            "/zones",
            params={
                "bbox": "75.8,11.5,76.3,11.9",
                "res": 8,
                "limit": 100,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        first = data[0]
        assert "h3" in first
        assert "res" in first
        assert "mhi" in first
        assert "zone_class" in first
        assert "dominant_hazard" in first
        assert "dataset_version" in first
        assert "screening_grade" not in first  # Summary is lightweight

    def test_query_zones_invalid_resolution(self):
        response = client.get("/zones", params={"res": 15})
        assert response.status_code in (400, 422)
        err = response.json()
        assert "error" in err

    def test_query_zones_invalid_bbox_format(self):
        response = client.get("/zones", params={"bbox": "invalid_coords"})
        assert response.status_code == 400
        err = response.json()
        assert err["error"]["code"] == "INVALID_BBOX"

    def test_query_zones_bbox_area_limit_exceeded(self):
        # Extremely large bounding box (10 x 10 degrees = 100 sq deg > 5.0 max)
        response = client.get("/zones", params={"bbox": "70.0,10.0,80.0,20.0"})
        assert response.status_code == 400
        err = response.json()
        assert err["error"]["code"] == "INVALID_BBOX"

    def test_get_zone_detail_success(self):
        # First retrieve a valid cell from /zones
        list_res = client.get("/zones", params={"bbox": "75.8,11.5,76.3,11.9", "limit": 1})
        assert list_res.status_code == 200
        items = list_res.json()
        assert len(items) > 0
        sample_h3 = items[0]["h3"]

        detail_res = client.get(f"/zones/{sample_h3}")
        assert detail_res.status_code == 200
        detail = detail_res.json()

        assert detail["h3"] == sample_h3
        assert "hazards" in detail
        assert "explanation" in detail
        assert "screening_grade" in detail
        assert detail["model_version"] == "baseline-v1"

        # Check explanation method
        for factor in detail["explanation"]:
            assert factor["method"] == "heuristic"

    def test_get_zone_detail_invalid_h3(self):
        response = client.get("/zones/invalid_h3_code")
        assert response.status_code == 400
        err = response.json()
        assert err["error"]["code"] == "INVALID_H3"

    def test_get_zone_detail_not_found(self):
        # Valid H3 index but in Paris (outside India pilot)
        paris_h3 = "881fb46625fffff"
        response = client.get(f"/zones/{paris_h3}")
        assert response.status_code == 404
        err = response.json()
        assert err["error"]["code"] == "DATA_UNAVAILABLE"
