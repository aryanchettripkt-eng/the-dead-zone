"""Integration tests for H4: Alert Provenance Semantics (No Fabrication, No Relabelling).

Verifies:
- Test 1: Active alert provenance comes from persistence (trigger_source, valid_at match persisted records; issued_at is honestly None).
- Test 2: Forecast alert provenance comes from persistence (forecast_cycle_at, valid_at match persisted records; source is NOT relabelled as issuing_model; issuing_model is honestly None).
- Test 3: No runtime fabrication (provenance timestamps do not drift across repeated reads, issued_at remains None).
- Test 4: Existing B6/M18 invariants remain intact (transient alert does not mutate static classification, real values returned).
"""

from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient

from api.main import app
from core.enums import ZoneClass
from core.h3_utils import h3_to_str


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.db
class TestH4AlertProvenance:
    """Rigorous tests proving alert provenance is derived from persisted records only without semantic relabelling."""

    @pytest.fixture(autouse=True)
    def cleanup_test_data(self, db_session):
        yield
        db_session.execute(text("DELETE FROM hazard_dynamic WHERE valid_at >= '2026-09-05';"))
        db_session.execute(text("DELETE FROM mhi_snapshot WHERE valid_at >= '2026-09-05';"))
        db_session.commit()

    def test_active_alert_provenance_comes_from_persistence(self, client, db_session):
        """Test 1: Proves GET /alerts/active derives trigger_source and valid_at strictly from persisted records.

        Also proves issued_at is honestly None rather than fabricating now_utc or relabelling valid_at as issued_at.
        """
        cell_row = db_session.execute(text("SELECT h3, res FROM grid_cell WHERE res = 8 LIMIT 1;")).mappings().first()
        assert cell_row is not None
        test_h3 = cell_row["h3"]
        test_hex = h3_to_str(test_h3)

        # Distinctive timestamps and source that could never match fabricated defaults
        distinct_source = "CUSTOM_RADAR_TEST_NETWORK_99"
        distinct_valid_at = datetime(2026, 9, 10, 14, 30, 0, tzinfo=timezone.utc)
        valid_at_iso = distinct_valid_at.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Clear prior dynamic records for test cell
        db_session.execute(text("DELETE FROM hazard_dynamic WHERE h3 = :h3;"), {"h3": test_h3})
        db_session.execute(text("DELETE FROM mhi_snapshot WHERE h3 = :h3;"), {"h3": test_h3})

        # Insert active live trigger with distinctive provenance into hazard_dynamic
        db_session.execute(
            text("""
                INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, forecast_cycle_at, trigger_value, source)
                VALUES (:h3, 'landslide', :valid_at, NULL, 1.20, :source);
            """),
            {"h3": test_h3, "valid_at": distinct_valid_at, "source": distinct_source},
        )
        # Insert corresponding active snapshot into mhi_snapshot (mhi_live >= 0.75, mhi_static < 0.75)
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.40, 0.88, NULL, 'landslide', 'none');
            """),
            {"h3": test_h3, "valid_at": distinct_valid_at},
        )
        db_session.commit()

        # Query active alerts
        res = client.get("/alerts/active?limit=100")
        assert res.status_code == 200
        data = res.json()

        # Find our test cell item
        items = [x for x in data["items"] if x["h3"] == test_hex]
        assert len(items) == 1, "Test cell must be returned in active alerts"
        item = items[0]

        # Verify truthful persisted provenance
        assert item["trigger_source"] == distinct_source, (
            f"Expected persisted trigger_source '{distinct_source}', got '{item['trigger_source']}'"
        )
        assert item["valid_at"] == valid_at_iso, (
            f"Expected persisted valid_at '{valid_at_iso}', got '{item['valid_at']}'"
        )
        assert item["mhi_live"] == 0.88
        assert item["mhi_static"] == 0.40

        # Verify response-level issued_at is honestly None (valid_at is NOT relabelled as issued_at)
        assert data["issued_at"] is None, (
            f"Expected issued_at to be None (unpersisted), got '{data['issued_at']}'"
        )

    def test_forecast_alert_provenance_comes_from_persistence(self, client, db_session):
        """Test 2: Proves GET /alerts/forecast derives forecast_cycle_at and valid_at from persistence.

        Also proves that provider source is NOT silently relabelled as issuing_model,
        and no hardcoded 'ECMWF Open Data' default is fabricated.
        """
        cell_row = db_session.execute(text("SELECT h3, res FROM grid_cell WHERE res = 8 LIMIT 1;")).mappings().first()
        assert cell_row is not None
        test_h3 = cell_row["h3"]
        test_hex = h3_to_str(test_h3)

        distinct_feed_source = "OPEN_DATA_FEED_GPM_42"
        distinct_cycle = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)
        horizon = 36
        distinct_valid_at = distinct_cycle + timedelta(hours=horizon)
        cycle_iso = distinct_cycle.strftime("%Y-%m-%dT%H:%M:%SZ")
        valid_at_iso = distinct_valid_at.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Clear prior dynamic records for test cell
        db_session.execute(text("DELETE FROM hazard_dynamic WHERE h3 = :h3;"), {"h3": test_h3})
        db_session.execute(text("DELETE FROM mhi_snapshot WHERE h3 = :h3;"), {"h3": test_h3})

        # Insert forecast trigger with feed source provenance into hazard_dynamic
        db_session.execute(
            text("""
                INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, forecast_cycle_at, trigger_value, source)
                VALUES (:h3, 'landslide', :valid_at, :cycle, 1.30, :source);
            """),
            {"h3": test_h3, "valid_at": distinct_valid_at, "cycle": distinct_cycle, "source": distinct_feed_source},
        )
        # Insert corresponding snapshot
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.35, 0.20, 0.86, 'landslide', 'none');
            """),
            {"h3": test_h3, "valid_at": distinct_valid_at},
        )
        db_session.commit()

        # Query forecast alerts for horizon=36
        res = client.get(f"/alerts/forecast?horizon={horizon}&limit=100")
        assert res.status_code == 200
        data = res.json()

        assert data["horizon_hours"] == horizon
        assert data["forecast_cycle_at"] == cycle_iso

        # Critical verification: source is NOT relabelled as issuing_model, and no hardcoded fallback exists
        assert data["issuing_model"] is None, (
            f"Expected top-level issuing_model to be None (unpersisted), got '{data['issuing_model']}'"
        )
        assert data["issuing_model"] != distinct_feed_source, "Feed source must not be relabelled as model"
        assert data["issuing_model"] != "ECMWF Open Data", "Hardcoded model name must not be fabricated"

        items = [x for x in data["items"] if x["h3"] == test_hex]
        assert len(items) == 1, "Test cell must be returned in forecast alerts"
        item = items[0]

        assert item["issuing_model"] is None, (
            f"Expected item issuing_model to be None (unpersisted), got '{item['issuing_model']}'"
        )
        assert item["issuing_model"] != distinct_feed_source, "Item feed source must not be relabelled as model"
        assert item["forecast_cycle_at"] == cycle_iso
        assert item["valid_at"] == valid_at_iso
        assert item["horizon_hours"] == horizon
        assert item["mhi_fcst"] == 0.86

    def test_no_runtime_fabrication_timestamps_stable_across_reads(self, client, db_session):
        """Test 3: Proves repeated reads return identical persisted timestamps without drifting with wall-clock time."""
        cell_row = db_session.execute(text("SELECT h3, res FROM grid_cell WHERE res = 8 LIMIT 1;")).mappings().first()
        assert cell_row is not None
        test_h3 = cell_row["h3"]
        test_hex = h3_to_str(test_h3)

        test_time = datetime(2026, 9, 11, 8, 0, 0, tzinfo=timezone.utc)
        test_time_iso = test_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        db_session.execute(text("DELETE FROM hazard_dynamic WHERE h3 = :h3;"), {"h3": test_h3})
        db_session.execute(text("DELETE FROM mhi_snapshot WHERE h3 = :h3;"), {"h3": test_h3})

        db_session.execute(
            text("""
                INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, forecast_cycle_at, trigger_value, source)
                VALUES (:h3, 'landslide', :valid_at, NULL, 1.10, 'STABLE_RADAR');
            """),
            {"h3": test_h3, "valid_at": test_time},
        )
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.40, 0.85, NULL, 'landslide', 'none');
            """),
            {"h3": test_h3, "valid_at": test_time},
        )
        db_session.commit()

        # Call active alerts twice
        res1 = client.get("/alerts/active?limit=100")
        res2 = client.get("/alerts/active?limit=100")

        assert res1.status_code == 200
        assert res2.status_code == 200

        data1 = res1.json()
        data2 = res2.json()

        # issued_at is honestly None across reads (never drifting with wall-clock time)
        assert data1["issued_at"] is None
        assert data2["issued_at"] is None

        item1 = next(x for x in data1["items"] if x["h3"] == test_hex)
        item2 = next(x for x in data2["items"] if x["h3"] == test_hex)

        # Both calls must yield exactly identical valid_at timestamp matching persisted test_time
        assert item1["valid_at"] == item2["valid_at"] == test_time_iso

    def test_b6_m18_invariants_preserved(self, client, db_session):
        """Test 4: Proves B6 real alert values and M18 static-vs-transient zone_class separation remain intact."""
        cell_row = db_session.execute(text("SELECT h3, res FROM grid_cell WHERE res = 8 LIMIT 1;")).mappings().first()
        assert cell_row is not None
        test_h3 = cell_row["h3"]
        test_hex = h3_to_str(test_h3)

        t_alert = datetime(2026, 9, 12, 4, 0, 0, tzinfo=timezone.utc)
        db_session.execute(text("DELETE FROM hazard_dynamic WHERE h3 = :h3;"), {"h3": test_h3})
        db_session.execute(text("DELETE FROM mhi_snapshot WHERE h3 = :h3;"), {"h3": test_h3})

        # M18: zone_class represents persistent classification ('caution' because mhi_static = 0.50),
        # while transient mhi_live = 0.88 creates active alert state independently without mutating zone_class.
        db_session.execute(
            text("""
                INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, forecast_cycle_at, trigger_value, source)
                VALUES (:h3, 'landslide', :valid_at, NULL, 1.0, 'IMERG_EARLY');
            """),
            {"h3": test_h3, "valid_at": t_alert},
        )
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.50, 0.88, NULL, 'landslide', 'caution');
            """),
            {"h3": test_h3, "valid_at": t_alert},
        )
        db_session.commit()

        # Verify active alerts endpoint returns the cell with mhi_live = 0.88 (B6)
        res = client.get("/alerts/active?limit=100")
        assert res.status_code == 200
        items = [x for x in res.json()["items"] if x["h3"] == test_hex]
        assert len(items) == 1
        assert items[0]["mhi_live"] == 0.88
        assert items[0]["mhi_static"] == 0.50
        assert items[0]["trigger_source"] == "IMERG_EARLY"

        # Verify /zones endpoint preserves static zone_class ('caution') per M18
        res_zones = client.get("/zones", params={"res": 8, "valid_at": t_alert.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": 5000})
        assert res_zones.status_code == 200
        zone_items = [x for x in res_zones.json() if x["h3"] == test_hex]
        assert len(zone_items) == 1
        assert zone_items[0]["zone_class"] == "caution", "M18 static zone_class must remain invariant"
        assert zone_items[0]["mhi_live"] == 0.88
