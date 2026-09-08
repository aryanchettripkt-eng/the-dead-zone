"""Unit tests for Phase B7: Wayanad Forecast API Read Path Verification.

Verifies:
1. alerts_repo: query_forecast_alerts scopes to the authoritative forecast cycle.
2. alerts_repo: get_latest_forecast_cycle supports admin-scoped and global resolution.
3. alerts_service: get_forecast_alerts exposes truthful cycle provenance and lead times.
4. alerts_service: input validation rejects horizon < 1 or horizon > 72 (FR-3.12).
5. alerts_service: correctly maps LGD code 555 / Admin ID 178 without leaking unrelated districts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from api.repositories.alerts_repo import AlertsRepository
from api.services.alerts_service import AlertsService
from core.constants import FORECAST_HORIZON_HOURS
from core.enums import DataQuality
from core.errors import InvalidParametersError
from core.schemas.alerts import ForecastAlertsResponse


class TestB7ForecastApiUnit:
    """Unit test suite for Phase B7 forecast query scoping and service layer."""

    def test_get_latest_forecast_cycle_admin_scoped(self):
        """Proves get_latest_forecast_cycle correctly scopes query when admin_id is provided."""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.mappings().first.return_value = {
            "max_cycle": datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
        }
        mock_db.execute.return_value = mock_result

        repo = AlertsRepository(mock_db)
        cycle = repo.get_latest_forecast_cycle(admin_id=555)

        assert cycle == datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
        executed_sql = str(mock_db.execute.call_args[0][0])
        assert "WHERE hd.forecast_cycle_at IS NOT NULL" in executed_sql
        assert "(g.admin_id = :admin_id OR a.lgd_code = :admin_id)" in executed_sql
        assert mock_db.execute.call_args[0][1] == {"admin_id": 555}

    def test_get_latest_forecast_cycle_global(self):
        """Proves get_latest_forecast_cycle queries globally when admin_id is None."""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.mappings().first.return_value = {
            "max_cycle": datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
        }
        mock_db.execute.return_value = mock_result

        repo = AlertsRepository(mock_db)
        cycle = repo.get_latest_forecast_cycle(admin_id=None)

        assert cycle == datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
        executed_sql = str(mock_db.execute.call_args[0][0])
        assert "admin_id" not in executed_sql

    def test_query_forecast_alerts_scopes_to_target_cycle(self):
        """Proves query_forecast_alerts binds target_cycle in SQL CTE to prevent cycle leakage."""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.mappings().fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        target_cycle = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
        repo = AlertsRepository(mock_db)

        records, total_cells, total_pop = repo.query_forecast_alerts(
            admin_id=555,
            min_mhi=0.75,
            horizon_hours=72,
            limit=50,
            offset=0,
            forecast_cycle_at=target_cycle,
        )

        assert records == []
        assert total_cells == 0
        assert total_pop == 0

        call_args = mock_db.execute.call_args
        executed_sql = str(call_args[0][0])
        params = call_args[0][1]

        assert "WHERE forecast_cycle_at = :target_cycle" in executed_sql
        assert params["target_cycle"] == target_cycle
        assert params["admin_id"] == 555
        assert params["horizon_hours"] == 72
        assert params["min_mhi"] == 0.75

    def test_service_horizon_validation_rejects_out_of_bounds(self):
        """Proves service layer enforces FR-3.12: horizon must be in [1, 72]."""
        mock_db = MagicMock()
        service = AlertsService(mock_db)

        with pytest.raises(InvalidParametersError, match="outside supported bounds"):
            service.get_forecast_alerts(horizon_hours=0)

        with pytest.raises(InvalidParametersError, match="outside supported bounds"):
            service.get_forecast_alerts(horizon_hours=73)

    def test_service_maps_wayanad_forecast_response_honestly(self):
        """Proves service layer preserves truthful provenance, cycle anchor, and H3-8 formatting."""
        mock_db = MagicMock()
        cycle_anchor = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
        valid_time = datetime(2026, 9, 8, 13, 0, 0, tzinfo=timezone.utc)

        fake_record = {
            "h3": 0x8860064a15fffff,
            "res": 8,
            "admin_id": 178,
            "admin_name": "Wayanad",
            "mhi_fcst": 0.9045,
            "mhi_static": 0.9045,
            "dominant_hazard": "flash_flood",
            "forecast_cycle_at": cycle_anchor,
            "valid_at": valid_time,
            "horizon_hours": 1,
            "source": "open_meteo_ecmwf",
            "population": 150.0,
            "lon": 76.1656,
            "lat": 11.5907,
            "full_count": 1,
            "full_exposed_pop": 150.0,
        }

        with patch.object(AlertsRepository, "query_forecast_alerts", return_value=([fake_record], 1, 150)):
            service = AlertsService(mock_db)
            resp = service.get_forecast_alerts(
                horizon_hours=72,
                admin_id=555,
                min_mhi=0.75,
            )

            assert isinstance(resp, ForecastAlertsResponse)
            assert resp.total_forecast_cells == 1
            assert resp.total_exposed_population == 150
            assert resp.forecast_cycle_at == cycle_anchor
            assert resp.horizon_hours == 72
            assert len(resp.items) == 1

            item = resp.items[0]
            assert item.h3 == "8860064a15fffff"
            assert item.h3_int == 0x8860064a15fffff
            assert item.res == 8
            assert item.admin_id == 178
            assert item.admin_name == "Wayanad"
            assert item.mhi_fcst == 0.9045
            assert item.mhi_static == 0.9045
            assert item.dominant_hazard == "flash_flood"
            assert item.forecast_cycle_at == cycle_anchor
            assert item.valid_at == valid_time
            assert item.horizon_hours == 1
            assert item.data_quality == DataQuality.VALID
            assert item.exposed_population == 150.0
            assert item.centroid == [76.1656, 11.5907]
