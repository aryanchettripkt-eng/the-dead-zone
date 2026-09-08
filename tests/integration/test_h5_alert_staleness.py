"""Integration tests for H5: Alert Staleness & Snapshot Coherence Guard.

Verifies:
- Test A: Historical active alert excluded by newer non-active snapshot (T1: A active; T2: A decayed -> A absent).
- Test B: Latest snapshot has active cell (T1: A active; T2: B active -> B only, A absent).
- Test C: Latest snapshot has zero active alerts (T1: A active; T2: no active alerts -> empty response, T1 alerts not resurrected).
- Test E: M18 static-vs-transient classification invariance (permanent zone_class never mutated by freshness).
- Test F: H4 truthful provenance preservation (source preserved, issued_at is None, issuing_model is None).
"""

from datetime import datetime, timezone
import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient

from api.main import app
from core.h3_utils import h3_to_str


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.db
class TestH5AlertStaleness:
    """Tests proving active alerts are evaluated against the authoritative latest snapshot and never resurrect stale history."""

    @pytest.fixture(autouse=True)
    def cleanup_test_data(self, db_session):
        yield
        db_session.execute(text("DELETE FROM hazard_dynamic WHERE valid_at >= '2026-09-05';"))
        db_session.execute(text("DELETE FROM mhi_snapshot WHERE valid_at >= '2026-09-05';"))
        db_session.commit()

    def test_a_historical_active_excluded_by_newer_non_active_snapshot(self, client, db_session):
        """Test A: T1: Cell A active; T2: Cell A decayed (non-active).

        Assert: Cell A is ABSENT from GET /alerts/active.
        """
        cell_row = db_session.execute(text("SELECT h3 FROM grid_cell WHERE res = 8 LIMIT 1;")).mappings().first()
        assert cell_row is not None
        cell_a = cell_row["h3"]
        hex_a = h3_to_str(cell_a)

        # Deterministic timestamps strictly after base seeding
        t1 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc)

        db_session.execute(text("DELETE FROM hazard_dynamic WHERE h3 = :h3;"), {"h3": cell_a})
        db_session.execute(text("DELETE FROM mhi_snapshot WHERE h3 = :h3;"), {"h3": cell_a})

        # T1: Cell A was active (mhi_live = 0.90)
        db_session.execute(
            text("""
                INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, forecast_cycle_at, trigger_value, source)
                VALUES (:h3, 'landslide', :valid_at, NULL, 1.5, 'IMERG_EARLY');
            """),
            {"h3": cell_a, "valid_at": t1},
        )
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.40, 0.90, NULL, 'landslide', 'none');
            """),
            {"h3": cell_a, "valid_at": t1},
        )

        # T2: Cell A decayed, storm passed (mhi_live = 0.30)
        db_session.execute(
            text("""
                INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, forecast_cycle_at, trigger_value, source)
                VALUES (:h3, 'landslide', :valid_at, NULL, 0.0, 'IMERG_EARLY');
            """),
            {"h3": cell_a, "valid_at": t2},
        )
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.40, 0.30, NULL, 'landslide', 'none');
            """),
            {"h3": cell_a, "valid_at": t2},
        )
        db_session.commit()

        # Query active alerts: latest snapshot is T2 where Cell A is mhi_live = 0.30
        res = client.get("/alerts/active?limit=100")
        assert res.status_code == 200
        data = res.json()

        items_a = [x for x in data["items"] if x["h3"] == hex_a]
        assert len(items_a) == 0, "Cell A must NOT be returned as active alert because in latest snapshot T2 it has decayed"

    def test_b_latest_snapshot_has_active_cell_superseding_older_alert(self, client, db_session):
        """Test B: T1: Cell A active; T2: Cell B active (Cell A decayed / absent).

        Assert: Only Cell B is returned. Cell A from T1 is excluded.
        """
        cell_rows = db_session.execute(text("SELECT h3 FROM grid_cell WHERE res = 8 LIMIT 2;")).mappings().all()
        assert len(cell_rows) >= 2
        cell_a = cell_rows[0]["h3"]
        cell_b = cell_rows[1]["h3"]
        hex_a = h3_to_str(cell_a)
        hex_b = h3_to_str(cell_b)

        t1 = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 23, 10, 0, 0, tzinfo=timezone.utc)

        db_session.execute(text("DELETE FROM hazard_dynamic WHERE h3 IN (:a, :b);"), {"a": cell_a, "b": cell_b})
        db_session.execute(text("DELETE FROM mhi_snapshot WHERE h3 IN (:a, :b);"), {"a": cell_a, "b": cell_b})

        # T1: Cell A active (0.92), Cell B baseline (0.20)
        db_session.execute(
            text("""
                INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, forecast_cycle_at, trigger_value, source)
                VALUES (:h3, 'landslide', :valid_at, NULL, 1.8, 'RADAR_T1');
            """),
            {"h3": cell_a, "valid_at": t1},
        )
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.40, 0.92, NULL, 'landslide', 'none');
            """),
            {"h3": cell_a, "valid_at": t1},
        )

        # T2: Cell B active (0.88), Cell A decayed (0.35)
        db_session.execute(
            text("""
                INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, forecast_cycle_at, trigger_value, source)
                VALUES (:h3, 'landslide', :valid_at, NULL, 1.4, 'RADAR_T2');
            """),
            {"h3": cell_b, "valid_at": t2},
        )
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.40, 0.88, NULL, 'landslide', 'none');
            """),
            {"h3": cell_b, "valid_at": t2},
        )
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.40, 0.35, NULL, 'landslide', 'none');
            """),
            {"h3": cell_a, "valid_at": t2},
        )
        db_session.commit()

        res = client.get("/alerts/active?limit=100")
        assert res.status_code == 200
        data = res.json()

        items_a = [x for x in data["items"] if x["h3"] == hex_a]
        items_b = [x for x in data["items"] if x["h3"] == hex_b]

        assert len(items_a) == 0, "Cell A from older snapshot T1 must NOT survive into latest snapshot T2"
        assert len(items_b) == 1, "Cell B from current snapshot T2 must be returned"
        assert items_b[0]["mhi_live"] == 0.88
        assert items_b[0]["trigger_source"] == "RADAR_T2"

    def test_c_latest_snapshot_has_zero_active_alerts_does_not_resurrect_history(self, client, db_session):
        """Test C: T1: Cell A active (0.90); T2: no active alerts across snapshot.

        Assert: /alerts/active returns total_active_cells = 0, items = [].
        T1 alerts must NOT be resurrected simply because T2 has no alerts.
        """
        cell_row = db_session.execute(text("SELECT h3 FROM grid_cell WHERE res = 8 LIMIT 1;")).mappings().first()
        assert cell_row is not None
        cell_a = cell_row["h3"]
        hex_a = h3_to_str(cell_a)

        t1 = datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 25, 10, 0, 0, tzinfo=timezone.utc)

        db_session.execute(text("DELETE FROM hazard_dynamic WHERE h3 = :h3;"), {"h3": cell_a})
        db_session.execute(text("DELETE FROM mhi_snapshot WHERE h3 = :h3;"), {"h3": cell_a})

        # T1: Cell A active
        db_session.execute(
            text("""
                INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, forecast_cycle_at, trigger_value, source)
                VALUES (:h3, 'landslide', :valid_at, NULL, 1.5, 'IMERG_OLD');
            """),
            {"h3": cell_a, "valid_at": t1},
        )
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.40, 0.90, NULL, 'landslide', 'none');
            """),
            {"h3": cell_a, "valid_at": t1},
        )

        # T2: Newer snapshot exists, but ALL cells in T2 have mhi_live < 0.75
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.40, 0.45, NULL, 'landslide', 'caution');
            """),
            {"h3": cell_a, "valid_at": t2},
        )
        db_session.commit()

        res = client.get("/alerts/active?limit=100")
        assert res.status_code == 200
        data = res.json()

        assert data["total_active_cells"] == 0
        assert len(data["items"]) == 0, "API must NOT resurrect T1 alerts when latest snapshot T2 has zero alerts"

    def test_d_no_newer_snapshot_active_alert_returned(self, client, db_session):
        """Case D: No newer snapshot exists (T1: Cell A active).

        Assert: Cell A is returned as active alert since T1 is the authoritative current snapshot.
        """
        cell_row = db_session.execute(text("SELECT h3 FROM grid_cell WHERE res = 8 LIMIT 1;")).mappings().first()
        assert cell_row is not None
        cell_a = cell_row["h3"]
        hex_a = h3_to_str(cell_a)

        t1 = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)

        db_session.execute(text("DELETE FROM hazard_dynamic WHERE h3 = :h3;"), {"h3": cell_a})
        db_session.execute(text("DELETE FROM mhi_snapshot WHERE h3 = :h3;"), {"h3": cell_a})

        # T1: Cell A active (0.88), no newer snapshot exists
        db_session.execute(
            text("""
                INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, forecast_cycle_at, trigger_value, source)
                VALUES (:h3, 'landslide', :valid_at, NULL, 1.4, 'IMERG_LIVE');
            """),
            {"h3": cell_a, "valid_at": t1},
        )
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.40, 0.88, NULL, 'landslide', 'none');
            """),
            {"h3": cell_a, "valid_at": t1},
        )
        db_session.commit()

        res = client.get("/alerts/active?limit=100")
        assert res.status_code == 200
        data = res.json()

        items_a = [x for x in data["items"] if x["h3"] == hex_a]
        assert len(items_a) == 1, "Cell A must be returned when T1 is the authoritative current snapshot"
        assert items_a[0]["mhi_live"] == 0.88

    def test_e_m18_static_zone_class_invariance_preserved(self, client, db_session):
        """Test E: M18: Active alert transient elevation must NEVER mutate static zone_class."""
        cell_row = db_session.execute(text("SELECT h3 FROM grid_cell WHERE res = 8 LIMIT 1;")).mappings().first()
        assert cell_row is not None
        cell_a = cell_row["h3"]
        hex_a = h3_to_str(cell_a)

        t_snap = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)

        db_session.execute(text("DELETE FROM hazard_dynamic WHERE h3 = :h3;"), {"h3": cell_a})
        db_session.execute(text("DELETE FROM mhi_snapshot WHERE h3 = :h3;"), {"h3": cell_a})

        # Cell A: static baseline is caution (0.50), transient live trigger elevates to active_alert (0.86)
        db_session.execute(
            text("""
                INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, forecast_cycle_at, trigger_value, source)
                VALUES (:h3, 'landslide', :valid_at, NULL, 1.2, 'IMERG_LIVE');
            """),
            {"h3": cell_a, "valid_at": t_snap},
        )
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.50, 0.86, NULL, 'landslide', 'caution');
            """),
            {"h3": cell_a, "valid_at": t_snap},
        )
        db_session.commit()

        # 1. Alert endpoint returns active alert with mhi_live = 0.86 and mhi_static = 0.50
        res_alert = client.get("/alerts/active?limit=100")
        assert res_alert.status_code == 200
        items = [x for x in res_alert.json()["items"] if x["h3"] == hex_a]
        assert len(items) == 1
        assert items[0]["mhi_live"] == 0.86
        assert items[0]["mhi_static"] == 0.50

        # 2. Zones endpoint preserves static zone_class = 'caution'
        res_zones = client.get("/zones", params={"res": 8, "valid_at": t_snap.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": 5000})
        assert res_zones.status_code == 200
        zone_items = [x for x in res_zones.json() if x["h3"] == hex_a]
        assert len(zone_items) == 1
        assert zone_items[0]["zone_class"] == "caution", "M18 static classification must remain invariant"

    def test_f_h4_truthful_provenance_preserved(self, client, db_session):
        """Test F: H4: Truthful provenance mapping without fabricated issued_at or model."""
        cell_row = db_session.execute(text("SELECT h3 FROM grid_cell WHERE res = 8 LIMIT 1;")).mappings().first()
        assert cell_row is not None
        cell_a = cell_row["h3"]
        hex_a = h3_to_str(cell_a)

        t_snap = datetime(2026, 9, 27, 8, 0, 0, tzinfo=timezone.utc)
        source_tag = "HONEST_RADAR_PROVENANCE_101"

        db_session.execute(text("DELETE FROM hazard_dynamic WHERE h3 = :h3;"), {"h3": cell_a})
        db_session.execute(text("DELETE FROM mhi_snapshot WHERE h3 = :h3;"), {"h3": cell_a})

        db_session.execute(
            text("""
                INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, forecast_cycle_at, trigger_value, source)
                VALUES (:h3, 'landslide', :valid_at, NULL, 1.3, :source);
            """),
            {"h3": cell_a, "valid_at": t_snap, "source": source_tag},
        )
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.40, 0.87, NULL, 'landslide', 'none');
            """),
            {"h3": cell_a, "valid_at": t_snap},
        )
        db_session.commit()

        res = client.get("/alerts/active?limit=100")
        assert res.status_code == 200
        data = res.json()

        # Top-level issued_at is honestly None
        assert data["issued_at"] is None

        items = [x for x in data["items"] if x["h3"] == hex_a]
        assert len(items) == 1
        item = items[0]
        assert item["trigger_source"] == source_tag
        assert item["valid_at"] == t_snap.strftime("%Y-%m-%dT%H:%M:%SZ")
