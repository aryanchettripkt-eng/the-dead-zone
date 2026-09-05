"""Integration tests for H1 + H2 + H3 + H6: Temporal & Dynamic API Read Correctness.

Verifies:
- H1: /zones?valid_at= accurately selects temporal snapshots, supports point-in-time as-of lookup, ensures temporal consistency across all cells, and returns 404 DATA_UNAVAILABLE when no snapshot exists.
- H2: /zones and /zones/{h3} preserve persisted mhi_live and mhi_fcst without discard, preserving 0.0 as 0.0 and NULL as None.
- H3: /alerts/forecast?horizon= actually filters on forecast horizon (tested with distinct 24h vs 48h persisted records), prevents duplicate rows, and uses truthful persisted forecast_cycle_at provenance without now_utc fabrication.
- H6: /habitations?tier= strictly returns only habitations with matching tier, excluding other tiers and unscored NULL tier rows.
"""

from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient

from api.main import app
from core.enums import Tier, ZoneClass
from core.h3_utils import h3_to_str


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.db
class TestTemporalDynamicReadCorrectness:
    """Rigorous end-to-end integration tests for H1, H2, H3, and H6."""

    # =========================================================================
    # H1: Temporal valid_at query & snapshot consistency
    # =========================================================================

    def test_h1_valid_at_temporal_selection_and_as_of_semantics(self, client, db_session):
        """H1: Proves valid_at selects the appropriate snapshot and supports as-of point-in-time lookup."""
        # Find a real grid cell from the seeded database at resolution 8
        cell_row = db_session.execute(text("SELECT h3, res FROM grid_cell WHERE res = 8 LIMIT 1;")).mappings().first()
        assert cell_row is not None, "Test database must contain res 8 grid cells"
        test_h3 = cell_row["h3"]
        test_h3_hex = h3_to_str(test_h3)

        # Clear existing snapshots for this cell to test isolated deterministic snapshots
        db_session.execute(text("DELETE FROM mhi_snapshot WHERE h3 = :h3;"), {"h3": test_h3})

        # Insert Snapshot A at T1 (historical past: 2026-08-20)
        t1 = datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.40, 0.35, NULL, 'landslide', 'none');
            """),
            {"h3": test_h3, "valid_at": t1},
        )

        # Insert Snapshot B at T2 (more recent: 2026-08-25)
        t2 = datetime(2026, 8, 25, 10, 0, 0, tzinfo=timezone.utc)
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.40, 0.88, NULL, 'landslide', 'active_alert');
            """),
            {"h3": test_h3, "valid_at": t2},
        )
        db_session.commit()

        t1_iso = t1.strftime("%Y-%m-%dT%H:%M:%SZ")
        t2_iso = t2.strftime("%Y-%m-%dT%H:%M:%SZ")

        # 1. Query with valid_at = T1 -> must return Snapshot A (mhi_live = 0.35, zone_class = none)
        res_t1 = client.get("/zones", params={"res": 8, "valid_at": t1_iso, "limit": 5000})
        assert res_t1.status_code == 200
        items_t1 = [x for x in res_t1.json() if x["h3"] == test_h3_hex]
        assert len(items_t1) == 1
        assert items_t1[0]["mhi_live"] == 0.35
        assert items_t1[0]["zone_class"] == "none"

        # 2. Query with valid_at = T2 -> must return Snapshot B (mhi_live = 0.88, zone_class = active_alert)
        res_t2 = client.get("/zones", params={"res": 8, "valid_at": t2_iso, "limit": 5000})
        assert res_t2.status_code == 200
        items_t2 = [x for x in res_t2.json() if x["h3"] == test_h3_hex]
        assert len(items_t2) == 1
        assert items_t2[0]["mhi_live"] == 0.88
        assert items_t2[0]["zone_class"] == "active_alert"

        # 3. Query with valid_at between T1 and T2 (e.g. 2026-08-22, Model A as-of semantics) -> must return Snapshot A
        t_mid = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        res_mid = client.get("/zones", params={"res": 8, "valid_at": t_mid.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": 5000})
        assert res_mid.status_code == 200
        items_mid = [x for x in res_mid.json() if x["h3"] == test_h3_hex]
        assert len(items_mid) == 1
        assert items_mid[0]["mhi_live"] == 0.35

        # 4. Query without valid_at -> must return latest snapshot (Snapshot B)
        res_latest = client.get("/zones", params={"res": 8, "limit": 5000})
        assert res_latest.status_code == 200
        items_latest = [x for x in res_latest.json() if x["h3"] == test_h3_hex]
        assert len(items_latest) == 1
        assert items_latest[0]["mhi_live"] == 0.88

        # 5. Query prior to any persisted snapshot (e.g. 2020-01-01) -> must return 404 DATA_UNAVAILABLE without fabricating data
        t_early = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        res_early = client.get("/zones", params={"res": 8, "valid_at": t_early.strftime("%Y-%m-%dT%H:%M:%SZ")})
        assert res_early.status_code == 404
        err_early = res_early.json()
        assert err_early["error"]["code"] == "DATA_UNAVAILABLE"

    # =========================================================================
    # H2: Preserve mhi_live and mhi_fcst through repository -> service -> DTO
    # =========================================================================

    def test_h2_preserve_mhi_live_fcst_and_explicit_zeros(self, client, db_session):
        """H2: Proves mhi_live and mhi_fcst are preserved, 0.0 remains 0.0, and NULL remains None."""
        cell_row = db_session.execute(text("SELECT h3, res FROM grid_cell WHERE res = 8 LIMIT 1;")).mappings().first()
        assert cell_row is not None
        test_h3 = cell_row["h3"]
        test_h3_hex = h3_to_str(test_h3)

        # Clear and insert a snapshot with mhi_live = 0.0, mhi_fcst = 0.95
        ts_now = datetime.now(timezone.utc)
        db_session.execute(text("DELETE FROM mhi_snapshot WHERE h3 = :h3;"), {"h3": test_h3})
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.30, 0.0, 0.95, 'flash_flood', 'forecast_alert');
            """),
            {"h3": test_h3, "valid_at": ts_now},
        )
        db_session.commit()

        # Check GET /zones summary list
        res_list = client.get("/zones", params={"res": 8, "limit": 5000})
        assert res_list.status_code == 200
        matches = [x for x in res_list.json() if x["h3"] == test_h3_hex]
        assert len(matches) == 1
        item = matches[0]
        # Invariant: 0.0 remains 0.0, not None
        assert item["mhi_live"] == 0.0
        assert item["mhi_fcst"] == 0.95

        # Check GET /zones/{h3} cell detail
        res_detail = client.get(f"/zones/{test_h3_hex}")
        assert res_detail.status_code == 200
        detail = res_detail.json()
        assert detail["mhi_live"] == 0.0
        assert detail["mhi_fcst"] == 0.95

        # Also test NULL forecast value remains None
        ts_later = ts_now + timedelta(hours=1)
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.30, 0.45, NULL, 'landslide', 'none');
            """),
            {"h3": test_h3, "valid_at": ts_later},
        )
        db_session.commit()

        res_null_fcst = client.get(f"/zones/{test_h3_hex}")
        assert res_null_fcst.status_code == 200
        detail_null = res_null_fcst.json()
        assert detail_null["mhi_live"] == 0.45
        assert detail_null["mhi_fcst"] is None

    # =========================================================================
    # H3: Forecast horizon filtering & truthful provenance
    # =========================================================================

    def test_h3_forecast_horizon_selection_and_no_duplication(self, client, db_session):
        """H3: Proves horizon parameter actually filters data, returns truthful provenance, and avoids duplicates."""
        # Select test cells from Kodagu to avoid polluting or interacting with Wayanad seeded demo alerts
        kodagu_id = db_session.execute(
            text("SELECT id FROM admin_boundary WHERE name = 'Kodagu' LIMIT 1;")
        ).scalar()
        cell_rows = db_session.execute(
            text("SELECT h3 FROM grid_cell WHERE admin_id = :aid LIMIT 2;"),
            {"aid": kodagu_id},
        ).mappings().all()
        assert len(cell_rows) >= 2
        cell_a = cell_rows[0]["h3"]
        cell_b = cell_rows[1]["h3"]

        cycle_time = datetime(2026, 8, 30, 0, 0, 0, tzinfo=timezone.utc)
        valid_24h = cycle_time + timedelta(hours=24)  # 2026-08-31 00:00:00 UTC
        valid_48h = cycle_time + timedelta(hours=48)  # 2026-09-01 00:00:00 UTC

        # Clean prior test rows strictly scoped to test cells
        db_session.execute(text("DELETE FROM hazard_dynamic WHERE h3 IN (:a, :b);"), {"a": cell_a, "b": cell_b})
        db_session.execute(text("DELETE FROM mhi_snapshot WHERE h3 IN (:a, :b);"), {"a": cell_a, "b": cell_b})

        # Cell A: 24h Horizon forecast crossing threshold (mhi_fcst = 0.82)
        db_session.execute(
            text("""
                INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, forecast_cycle_at, trigger_value, source)
                VALUES (:h3, 'landslide', :valid_at, :cycle, 1.2, 'ECMWF_OPEN');
            """),
            {"h3": cell_a, "valid_at": valid_24h, "cycle": cycle_time},
        )
        # Add a second trigger record for Cell A at same (h3, valid_at) to verify duplicate-row prevention
        db_session.execute(
            text("""
                INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, forecast_cycle_at, trigger_value, source)
                VALUES (:h3, 'flash_flood', :valid_at, :cycle, 1.0, 'ECMWF_OPEN');
            """),
            {"h3": cell_a, "valid_at": valid_24h, "cycle": cycle_time},
        )
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.40, 0.30, 0.82, 'landslide', 'forecast_alert');
            """),
            {"h3": cell_a, "valid_at": valid_24h},
        )

        # Cell B: 48h Horizon forecast crossing threshold (mhi_fcst = 0.91)
        db_session.execute(
            text("""
                INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, forecast_cycle_at, trigger_value, source)
                VALUES (:h3, 'landslide', :valid_at, :cycle, 1.5, 'ECMWF_OPEN');
            """),
            {"h3": cell_b, "valid_at": valid_48h, "cycle": cycle_time},
        )
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.35, 0.20, 0.91, 'landslide', 'forecast_alert');
            """),
            {"h3": cell_b, "valid_at": valid_48h},
        )
        db_session.commit()

        hex_a = h3_to_str(cell_a)
        hex_b = h3_to_str(cell_b)

        # 1. Query horizon=24 -> MUST return Cell A (0.82), MUST NOT return Cell B (0.91)
        cycle_iso = cycle_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        res_24 = client.get(f"/alerts/forecast?horizon=24&admin={kodagu_id}&limit=100")
        assert res_24.status_code == 200
        data_24 = res_24.json()
        assert data_24["horizon_hours"] == 24
        assert data_24["forecast_cycle_at"] == cycle_iso
        items_24_a = [x for x in data_24["items"] if x["h3"] == hex_a]
        items_24_b = [x for x in data_24["items"] if x["h3"] == hex_b]
        assert len(items_24_a) == 1, "Cell A must be returned exactly once (no duplicates)"
        assert len(items_24_b) == 0, "Cell B (48h) must NOT be returned in 24h horizon query"
        assert items_24_a[0]["mhi_fcst"] == 0.82
        assert items_24_a[0]["horizon_hours"] == 24
        assert items_24_a[0]["forecast_cycle_at"] == cycle_iso

        # 2. Query horizon=48 -> MUST return Cell B (0.91) AND Cell A (0.82) since 24h <= 48h (within horizon)
        res_48 = client.get(f"/alerts/forecast?horizon=48&admin={kodagu_id}&limit=100")
        assert res_48.status_code == 200
        data_48 = res_48.json()
        assert data_48["horizon_hours"] == 48
        items_48_a = [x for x in data_48["items"] if x["h3"] == hex_a]
        items_48_b = [x for x in data_48["items"] if x["h3"] == hex_b]
        assert len(items_48_b) == 1, "Cell B (48h) must be returned in 48h horizon query"
        assert len(items_48_a) == 1, "Cell A (24h) must be returned in 48h horizon query (within-horizon semantics)"
        assert items_48_b[0]["mhi_fcst"] == 0.91
        assert items_48_b[0]["horizon_hours"] == 48
        assert items_48_a[0]["mhi_fcst"] == 0.82
        assert items_48_a[0]["horizon_hours"] == 24

        # 3. Query horizon=72 -> MUST return both Cell A (24h) and Cell B (48h) since both are within 72h
        res_72 = client.get(f"/alerts/forecast?horizon=72&admin={kodagu_id}&limit=100")
        assert res_72.status_code == 200
        data_72 = res_72.json()
        items_72_a = [x for x in data_72["items"] if x["h3"] == hex_a]
        items_72_b = [x for x in data_72["items"] if x["h3"] == hex_b]
        assert len(items_72_a) == 1, "Cell A (24h) must be returned in 72h horizon query"
        assert len(items_72_b) == 1, "Cell B (48h) must be returned in 72h horizon query"

        # 4. Multi-cycle determinism: insert an updated, newer forecast cycle for Cell A with the same horizon (24h)
        cycle_newer = cycle_time + timedelta(hours=6)  # 2026-08-30 06:00:00 UTC
        valid_24h_newer = cycle_newer + timedelta(hours=24)  # 2026-08-31 06:00:00 UTC
        db_session.execute(
            text("""
                INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, forecast_cycle_at, trigger_value, source)
                VALUES (:h3, 'landslide', :valid_at, :cycle, 1.4, 'ECMWF_OPEN');
            """),
            {"h3": cell_a, "valid_at": valid_24h_newer, "cycle": cycle_newer},
        )
        db_session.execute(
            text("""
                INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class)
                VALUES (:h3, :valid_at, 0.40, 0.30, 0.89, 'landslide', 'forecast_alert');
            """),
            {"h3": cell_a, "valid_at": valid_24h_newer},
        )
        db_session.commit()

        # Query horizon=24 again: must deterministically return the newer cycle/snapshot (0.89), exactly once
        cycle_newer_iso = cycle_newer.strftime("%Y-%m-%dT%H:%M:%SZ")
        res_24_updated = client.get(f"/alerts/forecast?horizon=24&admin={kodagu_id}&limit=100")
        assert res_24_updated.status_code == 200
        data_24_updated = res_24_updated.json()
        items_24_a_updated = [x for x in data_24_updated["items"] if x["h3"] == hex_a]
        assert len(items_24_a_updated) == 1, "Cell A must still have exactly 1 record after multi-cycle insert"
        assert items_24_a_updated[0]["mhi_fcst"] == 0.89, "Must select latest snapshot deterministically"
        assert items_24_a_updated[0]["forecast_cycle_at"] == cycle_newer_iso, "Must reflect latest cycle provenance"

        # Teardown scoped strictly to test cells
        db_session.execute(text("DELETE FROM hazard_dynamic WHERE h3 IN (:a, :b);"), {"a": cell_a, "b": cell_b})
        db_session.execute(text("DELETE FROM mhi_snapshot WHERE h3 IN (:a, :b);"), {"a": cell_a, "b": cell_b})
        db_session.commit()

    # =========================================================================
    # H6: Triage tier filtering excludes unscored habitations
    # =========================================================================

    def test_h6_tier_filter_excludes_unscored_habitations(self, client, db_session):
        """H6: Proves ?tier= filter only includes matching scored habitations and excludes unscored NULL tier rows."""
        # Find three habitations from the database
        hab_rows = db_session.execute(text("SELECT id FROM habitation LIMIT 3;")).mappings().all()
        assert len(hab_rows) >= 3
        h_imm = hab_rows[0]["id"]
        h_short = hab_rows[1]["id"]
        h_unscored = hab_rows[2]["id"]

        # Clean prior habitation_risk for these three habitations
        db_session.execute(
            text("DELETE FROM habitation_risk WHERE habitation_id IN (:h1, :h2, :h3);"),
            {"h1": h_imm, "h2": h_short, "h3": h_unscored},
        )

        # Habitation 1: Scored as 'immediate'
        db_session.execute(
            text("""
                INSERT INTO habitation_risk (habitation_id, priority_score, caseload_score, tier, triage_rationale, prz_overlap_pct)
                VALUES (:hid, 0.85, 425.0, 'immediate', 'Test immediate risk', 0.8);
            """),
            {"hid": h_imm},
        )

        # Habitation 2: Scored as 'short_term'
        db_session.execute(
            text("""
                INSERT INTO habitation_risk (habitation_id, priority_score, caseload_score, tier, triage_rationale, prz_overlap_pct)
                VALUES (:hid, 0.55, 275.0, 'short_term', 'Test short-term risk', 0.2);
            """),
            {"hid": h_short},
        )

        # Habitation 3: Left UNSCORED (no row in habitation_risk -> hr.tier IS NULL)
        db_session.commit()

        # 1. Query tier=immediate -> MUST return Habitation 1, MUST NOT return Habitation 2 or Habitation 3
        res_imm = client.get("/habitations?tier=immediate&limit=200")
        assert res_imm.status_code == 200
        imm_ids = [x["id"] for x in res_imm.json()["items"]]
        assert h_imm in imm_ids, "Scored immediate habitation must be included"
        assert h_short not in imm_ids, "Different tier habitation must be excluded"
        assert h_unscored not in imm_ids, "Unscored NULL-tier habitation must be strictly excluded"

        # 2. Query tier=short_term -> MUST return Habitation 2, MUST NOT return Habitation 1 or Habitation 3
        res_short = client.get("/habitations?tier=short_term&limit=200")
        assert res_short.status_code == 200
        short_ids = [x["id"] for x in res_short.json()["items"]]
        assert h_short in short_ids, "Scored short_term habitation must be included"
        assert h_imm not in short_ids, "Different tier habitation must be excluded"
        assert h_unscored not in short_ids, "Unscored NULL-tier habitation must be strictly excluded"

        # 3. Query without tier filter -> ALL habitations (including unscored Habitation 3) must be present in queue
        res_all = client.get("/habitations?limit=200")
        assert res_all.status_code == 200
        all_ids = [x["id"] for x in res_all.json()["items"]]
        assert h_imm in all_ids
        assert h_short in all_ids
        assert h_unscored in all_ids, "Unscored habitation must still appear when tier filter is omitted"
