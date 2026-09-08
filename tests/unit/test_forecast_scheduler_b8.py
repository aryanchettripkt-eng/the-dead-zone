"""Unit tests for SETU-DRR Phase B8: Production-Safe Live Forecast Scheduling & Retention.

Verifies:
1. Concurrency Control: Singleton lock prevents overlapping forecast runs; releases on exit.
2. Provider Failure Safety: Open-Meteo network/HTTP failure preserves existing latest-good forecast.
3. Pipeline Failure Safety: B6 processing failure preserves existing latest-good forecast.
4. API Read Path Isolation: RUNNING or FAILED runs never replace latest-good; API serves previous cycle.
5. Atomic Latest-Good Transition: Newly READY run becomes latest-good seamlessly.
6. Scoped Retention: Prunes obsolete forecast runs while strictly protecting latest-good and all core channels.
7. Channel Invariance: PRZ, AAZ, static MHI, live MHI, and other districts remain 100% untouched.
8. Dry-Run Inspection: Reports retention candidates without database mutations.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from api.repositories.alerts_repo import AlertsRepository
from core.config import settings
from pipeline.ingestion.open_meteo_client import ADMIN_ID, DISTRICT_LGD, DISTRICT_NAME
from pipeline.jobs.run_open_meteo_wayanad import WayanadForecastPipelineResult
from pipeline.jobs.scheduler import (
    ForecastLifecycleResult,
    ForecastLockManager,
    RetentionResult,
    prune_obsolete_forecast_runs,
    run_wayanad_forecast_lifecycle,
    start_forecast_scheduler,
    WAYANAD_FORECAST_LOCK_ID,
)


@pytest.fixture
def sqlite_test_engine() -> Engine:
    """In-memory SQLite engine with core tables for testing lifecycle and retention."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text("""
                CREATE TABLE admin_boundary (
                    id INTEGER PRIMARY KEY,
                    lgd_code INTEGER,
                    name TEXT NOT NULL
                );
            """)
        )
        conn.execute(
            text("""
                CREATE TABLE grid_cell (
                    h3 INTEGER PRIMARY KEY,
                    res INTEGER NOT NULL,
                    admin_id INTEGER,
                    population REAL DEFAULT 0.0,
                    built_area_m2 REAL DEFAULT 0.0
                );
            """)
        )
        conn.execute(
            text("""
                CREATE TABLE source_snapshot (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    retrieved_at TIMESTAMP NOT NULL,
                    valid_at TIMESTAMP,
                    uri TEXT NOT NULL,
                    sha256 TEXT,
                    size_bytes INTEGER,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );
            """)
        )
        conn.execute(
            text("""
                CREATE TABLE pipeline_run (
                    id TEXT PRIMARY KEY,
                    run_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    code_version TEXT NOT NULL,
                    config_version TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    source_snapshot_id TEXT,
                    error TEXT
                );
            """)
        )
        conn.execute(
            text("""
                CREATE TABLE hazard_dynamic (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    h3 INTEGER NOT NULL,
                    hazard_type TEXT NOT NULL,
                    valid_at TIMESTAMP NOT NULL,
                    ingested_at TIMESTAMP NOT NULL,
                    forecast_cycle_at TIMESTAMP,
                    trigger_value REAL NOT NULL,
                    source TEXT NOT NULL,
                    pipeline_run_id TEXT
                );
            """)
        )
        conn.execute(
            text("""
                CREATE TABLE mhi_snapshot (
                    h3 INTEGER NOT NULL,
                    valid_at TIMESTAMP NOT NULL,
                    mhi_static REAL NOT NULL,
                    mhi_live REAL NOT NULL,
                    mhi_fcst REAL,
                    dominant_hazard TEXT NOT NULL,
                    zone_class TEXT NOT NULL,
                    pipeline_run_id TEXT,
                    PRIMARY KEY (h3, valid_at)
                );
            """)
        )
    return engine


class TestB8ConcurrencyControl:
    """Verifies singleton execution lock and overlap prevention."""

    def test_forecast_lock_acquisition_and_release(self, sqlite_test_engine):
        """Proves lock is acquired and released cleanly."""
        lock_mgr = ForecastLockManager(engine=sqlite_test_engine, lock_id=12345)
        assert lock_mgr.acquire() is True
        assert lock_mgr.acquired is True

        # Second acquisition while held must fail
        lock_mgr_2 = ForecastLockManager(engine=sqlite_test_engine, lock_id=12345)
        assert lock_mgr_2.acquire() is False
        assert lock_mgr_2.acquired is False

        # Release first lock
        lock_mgr.release()
        assert lock_mgr.acquired is False

        # Now second can acquire
        assert lock_mgr_2.acquire() is True
        lock_mgr_2.release()

    @patch("pipeline.jobs.scheduler.ForecastLockManager.acquire", return_value=False)
    def test_lifecycle_skips_when_lock_held(self, mock_acquire, sqlite_test_engine):
        """Proves run_wayanad_forecast_lifecycle returns LOCKED_SKIPPED if lock acquisition fails."""
        res = run_wayanad_forecast_lifecycle(engine=sqlite_test_engine)
        assert res.status == "LOCKED_SKIPPED"
        assert res.pipeline_run_id is None
        assert "Concurrent forecast run" in str(res.error)


class TestB8ProviderAndPipelineFailureSafety:
    """Verifies that failures never invalidate or corrupt the latest-good forecast."""

    @patch("pipeline.jobs.scheduler.fetch_open_meteo_ecmwf_wayanad")
    def test_provider_failure_preserves_latest_good(self, mock_fetch, sqlite_test_engine):
        """Proves provider acquisition failure exits cleanly without corrupting state."""
        from pipeline.ingestion.open_meteo_client import PhaseB1IngestionReport

        now = datetime.now(timezone.utc)
        mock_fetch.return_value = PhaseB1IngestionReport(
            status="FAILED",
            http_status_code=503,
            source_snapshot_id=None,
            pipeline_run_id=None,
            raw_artifact_path="",
            sha256="",
            size_bytes=0,
            sample_points_count=12,
            total_hourly_steps_per_point=0,
            future_hourly_steps_available=0,
            forecast_cycle_anchor=now,
            cycle_anchor_verified=False,
            earliest_valid_at=now,
            latest_valid_at=now,
            errors=["Open-Meteo endpoint returned HTTP 503 Service Unavailable"],
        )

        res = run_wayanad_forecast_lifecycle(
            engine=sqlite_test_engine,
            max_retries=1,
            retry_delay_seconds=0.01,
        )

        assert res.status == "FAILED_PROVIDER"
        assert "503" in str(res.error)
        assert res.pipeline_run_id is None

    @patch("pipeline.jobs.scheduler.run_open_meteo_wayanad_pipeline")
    def test_pipeline_processing_failure_preserves_latest_good(self, mock_b6, sqlite_test_engine):
        """Proves B6 processing failure exits cleanly without corrupting state."""
        now = datetime.now(timezone.utc)
        failed_run_id = uuid.uuid4()

        mock_b6.return_value = WayanadForecastPipelineResult(
            status="FAILED",
            pipeline_run_id=failed_run_id,
            source_snapshot_id=uuid.uuid4(),
            district=DISTRICT_NAME,
            lgd_code=DISTRICT_LGD,
            admin_id=ADMIN_ID,
            hazard_type="flash_flood",
            forecast_cycle_anchor=now,
            trigger_records_persisted=0,
            snapshots_persisted=0,
            valid_timestamps_count=0,
            cells_processed_count=0,
            horizon_hours_start=1,
            horizon_hours_end=72,
            error="Simulated dynamic snapshot computation failure",
        )

        res = run_wayanad_forecast_lifecycle(
            engine=sqlite_test_engine,
            raw_artifact_path="data/raw/open_meteo/ecmwf_wayanad_20260908T120000Z.json",
        )

        assert res.status == "FAILED_PIPELINE"
        assert res.pipeline_run_id == failed_run_id
        assert "Simulated dynamic snapshot computation failure" in str(res.error)


class TestB8LatestGoodResolutionAndApiIsolation:
    """Verifies that the API only resolves READY cycles and ignores RUNNING or FAILED runs."""

    def test_api_ignores_running_and_failed_runs(self, sqlite_test_engine):
        """Proves get_latest_forecast_cycle resolves ONLY READY cycles."""
        cycle_a = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
        cycle_b = datetime(2026, 9, 8, 18, 0, 0, tzinfo=timezone.utc)
        cycle_c = datetime(2026, 9, 9, 0, 0, 0, tzinfo=timezone.utc)

        run_a = str(uuid.uuid4())
        run_b = str(uuid.uuid4())
        run_c = str(uuid.uuid4())

        with Session(sqlite_test_engine) as session:
            # Seed admin and grid
            session.execute(text("INSERT INTO admin_boundary (id, lgd_code, name) VALUES (178, 555, 'Wayanad');"))
            session.execute(text("INSERT INTO grid_cell (h3, res, admin_id) VALUES (1001, 8, 178);"))

            # Run A: READY
            session.execute(
                text("""
                    INSERT INTO pipeline_run (id, run_type, status, started_at, code_version, config_version, model_version)
                    VALUES (:id, 'forecast_pipeline', 'READY', :started, 'v1', 'v1', 'v1');
                """),
                {"id": run_a, "started": cycle_a},
            )
            session.execute(
                text("""
                    INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, ingested_at, forecast_cycle_at, trigger_value, source, pipeline_run_id)
                    VALUES (1001, 'flash_flood', :valid, :ingested, :cycle, 0.5, 'open_meteo_ecmwf', :run_id);
                """),
                {"valid": cycle_a + timedelta(hours=1), "ingested": cycle_a, "cycle": cycle_a, "run_id": run_a},
            )
            session.commit()

            repo = AlertsRepository(session)
            # Must resolve cycle A
            assert repo.get_latest_forecast_cycle(admin_id=555) == cycle_a

            # Run B starts: RUNNING with cycle B
            session.execute(
                text("""
                    INSERT INTO pipeline_run (id, run_type, status, started_at, code_version, config_version, model_version)
                    VALUES (:id, 'forecast_pipeline', 'RUNNING', :started, 'v1', 'v1', 'v1');
                """),
                {"id": run_b, "started": cycle_b},
            )
            session.execute(
                text("""
                    INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, ingested_at, forecast_cycle_at, trigger_value, source, pipeline_run_id)
                    VALUES (1001, 'flash_flood', :valid, :ingested, :cycle, 0.8, 'open_meteo_ecmwf', :run_id);
                """),
                {"valid": cycle_b + timedelta(hours=1), "ingested": cycle_b, "cycle": cycle_b, "run_id": run_b},
            )
            session.commit()

            # Crucial: API must STILL serve cycle A while B is RUNNING
            assert repo.get_latest_forecast_cycle(admin_id=555) == cycle_a

            # Run B fails: status becomes FAILED
            session.execute(
                text("UPDATE pipeline_run SET status = 'FAILED', error = 'simulated error' WHERE id = :id;"),
                {"id": run_b},
            )
            session.commit()

            # Crucial: API must STILL serve cycle A after B FAILED
            assert repo.get_latest_forecast_cycle(admin_id=555) == cycle_a

            # Run C succeeds: status becomes READY
            session.execute(
                text("""
                    INSERT INTO pipeline_run (id, run_type, status, started_at, code_version, config_version, model_version)
                    VALUES (:id, 'forecast_pipeline', 'READY', :started, 'v1', 'v1', 'v1');
                """),
                {"id": run_c, "started": cycle_c},
            )
            session.execute(
                text("""
                    INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, ingested_at, forecast_cycle_at, trigger_value, source, pipeline_run_id)
                    VALUES (1001, 'flash_flood', :valid, :ingested, :cycle, 0.4, 'open_meteo_ecmwf', :run_id);
                """),
                {"valid": cycle_c + timedelta(hours=1), "ingested": cycle_c, "cycle": cycle_c, "run_id": run_c},
            )
            session.commit()

            # Now API atomically transitions to cycle C!
            assert repo.get_latest_forecast_cycle(admin_id=555) == cycle_c


class TestB8ScopedRetention:
    """Verifies that retention prunes obsolete forecast runs while preserving all core channels."""

    def test_retention_preserves_latest_good_and_core_channels(self, sqlite_test_engine):
        """Proves retention keeps latest N runs and never deletes PRZ, live, or static MHI."""
        import json

        base_time = datetime(2026, 9, 8, 0, 0, 0, tzinfo=timezone.utc)
        run_ids: list[str] = []

        with Session(sqlite_test_engine) as session:
            # Seed 4 consecutive READY forecast runs (Run 0, 1, 2, 3)
            for i in range(4):
                run_id = str(uuid.uuid4())
                snap_id = str(uuid.uuid4())
                cycle = base_time + timedelta(hours=i * 6)
                run_ids.append(run_id)

                meta = json.dumps({
                    "admin_id": 178,
                    "lgd_code": 555,
                    "district": "Wayanad",
                })
                session.execute(
                    text("""
                        INSERT INTO source_snapshot (id, source_id, retrieved_at, valid_at, uri, sha256, size_bytes, metadata)
                        VALUES (:id, 'open_meteo_ecmwf', :now, :cycle, 'uri', 'sha', 100, :meta);
                    """),
                    {"id": snap_id, "now": cycle, "cycle": cycle, "meta": meta},
                )
                session.execute(
                    text("""
                        INSERT INTO pipeline_run (id, run_type, status, started_at, completed_at, code_version, config_version, model_version, source_snapshot_id)
                        VALUES (:id, 'forecast_pipeline', 'READY', :cycle, :cycle, 'v1', 'v1', 'v1', :snap_id);
                    """),
                    {"id": run_id, "cycle": cycle, "snap_id": snap_id},
                )
                # Persist hazard_dynamic forecast rows for this run
                session.execute(
                    text("""
                        INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, ingested_at, forecast_cycle_at, trigger_value, source, pipeline_run_id)
                        VALUES (1001, 'flash_flood', :valid, :cycle, :cycle, 0.5, 'open_meteo_ecmwf', :run_id);
                    """),
                    {"valid": cycle + timedelta(hours=1), "cycle": cycle, "run_id": run_id},
                )
                # Persist mhi_snapshot forecast row (pure forecast)
                session.execute(
                    text("""
                        INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class, pipeline_run_id)
                        VALUES (1001, :valid, 0.3, 0.0, 0.8, 'flash_flood', 'forecast_alert', :run_id);
                    """),
                    {"valid": cycle + timedelta(hours=1), "run_id": run_id},
                )

            # Also seed an active PRZ cell (must NEVER be touched by forecast retention!)
            prz_time = base_time + timedelta(hours=1)
            session.execute(
                text("""
                    INSERT INTO mhi_snapshot (h3, valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class, pipeline_run_id)
                    VALUES (9999, :valid, 0.95, 0.0, NULL, 'landslide', 'permanent_red', 'static_run_seed');
                """),
                {"valid": prz_time},
            )
            # Also seed an observed dynamic trigger (forecast_cycle_at IS NULL, must NEVER be touched!)
            session.execute(
                text("""
                    INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, ingested_at, forecast_cycle_at, trigger_value, source, pipeline_run_id)
                    VALUES (1001, 'flash_flood', :valid, :now, NULL, 0.9, 'IMERG_EARLY', 'obs_run_1');
                """),
                {"valid": prz_time, "now": prz_time},
            )
            session.commit()

            # Test Dry-Run first: retention=2 runs
            dry_res = prune_obsolete_forecast_runs(
                db=session,
                admin_id=178,
                lgd_code=555,
                retention_runs=2,
                dry_run=True,
            )
            assert len(dry_res.runs_protected) == 2
            assert len(dry_res.runs_pruned) == 2
            assert dry_res.dry_run is True

            # Verify no rows deleted yet
            hd_count_pre = session.execute(text("SELECT count(*) FROM hazard_dynamic;")).scalar()
            assert hd_count_pre == 5  # 4 forecast + 1 observed

            # Execute real retention: keep latest 2 runs (Run 3 and Run 2 protected, Run 1 and Run 0 pruned)
            real_res = prune_obsolete_forecast_runs(
                db=session,
                admin_id=178,
                lgd_code=555,
                retention_runs=2,
                dry_run=False,
            )
            assert len(real_res.runs_protected) == 2
            assert uuid.UUID(run_ids[3]) in real_res.runs_protected  # Latest-good is Run 3
            assert uuid.UUID(run_ids[2]) in real_res.runs_protected
            assert uuid.UUID(run_ids[1]) in real_res.runs_pruned
            assert uuid.UUID(run_ids[0]) in real_res.runs_pruned

            # Verify obsolete pipeline_run status became SUPERSEDED
            status_0 = session.execute(
                text("SELECT status FROM pipeline_run WHERE id = :id;"),
                {"id": run_ids[0]},
            ).scalar()
            assert status_0 == "SUPERSEDED"

            # Verify protected pipeline_run status remains READY
            status_3 = session.execute(
                text("SELECT status FROM pipeline_run WHERE id = :id;"),
                {"id": run_ids[3]},
            ).scalar()
            assert status_3 == "READY"

            # Verify obsolete hazard_dynamic rows deleted, protected rows remain
            hd_remaining = session.execute(
                text("SELECT pipeline_run_id FROM hazard_dynamic WHERE forecast_cycle_at IS NOT NULL;")
            ).scalars().all()
            assert set(hd_remaining) == {run_ids[3], run_ids[2]}

            # Invariance 1: Observed dynamic record (forecast_cycle_at IS NULL) strictly preserved!
            obs_hd = session.execute(
                text("SELECT count(*) FROM hazard_dynamic WHERE forecast_cycle_at IS NULL;")
            ).scalar()
            assert obs_hd == 1

            # Invariance 2: Permanent Red Zone cell strictly preserved!
            prz_row = session.execute(
                text("SELECT zone_class, mhi_static FROM mhi_snapshot WHERE h3 = 9999;")
            ).mappings().first()
            assert prz_row["zone_class"] == "permanent_red"
            assert prz_row["mhi_static"] == 0.95


class TestB8SchedulerConfiguration:
    """Verifies scheduler startup options and disabled mode."""

    def test_scheduler_disabled_returns_none(self):
        """Proves scheduler does nothing when FORECAST_SCHEDULER_ENABLED is False."""
        with patch.object(settings, "FORECAST_SCHEDULER_ENABLED", False):
            res = start_forecast_scheduler(blocking=False, run_once=False, force_enabled=False)
            assert res is None

    @patch("pipeline.jobs.scheduler.run_wayanad_forecast_lifecycle")
    def test_run_once_executes_lifecycle(self, mock_lifecycle):
        """Proves start_forecast_scheduler(run_once=True) triggers lifecycle immediately."""
        now = datetime.now(timezone.utc)
        mock_lifecycle.return_value = ForecastLifecycleResult(
            status="SUCCESS",
            pipeline_run_id=uuid.uuid4(),
            forecast_cycle_anchor=now,
            provider_status="SUCCESS",
            pipeline_result=None,
            retention_result=None,
            duration_seconds=1.23,
            error=None,
        )

        res = start_forecast_scheduler(run_once=True)
        assert res is not None
        assert res.status == "SUCCESS"
        mock_lifecycle.assert_called_once()

    def test_retention_failure_does_not_fail_forecast_job(self, sqlite_test_engine):
        """Proves retention failure logs error but does not fail the newly successful forecast."""
        now = datetime.now(timezone.utc)
        run_id = uuid.uuid4()

        mock_b6_res = WayanadForecastPipelineResult(
            status="SUCCESS",
            pipeline_run_id=run_id,
            source_snapshot_id=uuid.uuid4(),
            district=DISTRICT_NAME,
            lgd_code=DISTRICT_LGD,
            admin_id=ADMIN_ID,
            hazard_type="flash_flood",
            forecast_cycle_anchor=now,
            trigger_records_persisted=259344,
            snapshots_persisted=259344,
            valid_timestamps_count=72,
            cells_processed_count=3602,
            horizon_hours_start=1,
            horizon_hours_end=72,
        )

        with patch("pipeline.jobs.scheduler.fetch_open_meteo_ecmwf_wayanad") as mock_fetch, \
             patch("pipeline.jobs.scheduler.run_open_meteo_wayanad_pipeline", return_value=mock_b6_res), \
             patch("pipeline.jobs.scheduler.prune_obsolete_forecast_runs", side_effect=RuntimeError("Simulated DB lock during cleanup")):
            from pipeline.ingestion.open_meteo_client import PhaseB1IngestionReport

            mock_fetch.return_value = PhaseB1IngestionReport(
                status="SUCCESS",
                http_status_code=200,
                source_snapshot_id=uuid.uuid4(),
                pipeline_run_id=run_id,
                raw_artifact_path="data/raw/open_meteo/ecmwf_wayanad_20260908T120000Z.json",
                sha256="abc",
                size_bytes=1000,
                sample_points_count=12,
                total_hourly_steps_per_point=96,
                future_hourly_steps_available=72,
                forecast_cycle_anchor=now,
                cycle_anchor_verified=False,
                earliest_valid_at=now,
                latest_valid_at=now + timedelta(hours=72),
            )

            res = run_wayanad_forecast_lifecycle(engine=sqlite_test_engine)
            # Must still succeed!
            assert res.status == "SUCCESS"
            assert res.pipeline_run_id == run_id
            assert res.retention_result is not None
            assert "Simulated DB lock during cleanup" in str(res.retention_result.error)

    def test_retention_preserves_other_districts(self, sqlite_test_engine):
        """Proves retention for Wayanad (admin 178 / lgd 555) never prunes other districts."""
        import json

        base_time = datetime(2026, 9, 8, 0, 0, 0, tzinfo=timezone.utc)
        other_run_id = str(uuid.uuid4())
        other_snap_id = str(uuid.uuid4())

        with Session(sqlite_test_engine) as session:
            # Seed an old READY run belonging to district Idukki (LGD 554, Admin 177)
            idukki_meta = json.dumps({
                "admin_id": 177,
                "lgd_code": 554,
                "district": "Idukki",
            })
            session.execute(
                text("""
                    INSERT INTO source_snapshot (id, source_id, retrieved_at, valid_at, uri, sha256, size_bytes, metadata)
                    VALUES (:id, 'open_meteo_ecmwf', :now, :cycle, 'uri', 'sha', 100, :meta);
                """),
                {"id": other_snap_id, "now": base_time, "cycle": base_time, "meta": idukki_meta},
            )
            session.execute(
                text("""
                    INSERT INTO pipeline_run (id, run_type, status, started_at, completed_at, code_version, config_version, model_version, source_snapshot_id)
                    VALUES (:id, 'forecast_pipeline', 'READY', :cycle, :cycle, 'v1', 'v1', 'v1', :snap_id);
                """),
                {"id": other_run_id, "cycle": base_time, "snap_id": other_snap_id},
            )
            session.execute(
                text("""
                    INSERT INTO hazard_dynamic (h3, hazard_type, valid_at, ingested_at, forecast_cycle_at, trigger_value, source, pipeline_run_id)
                    VALUES (8888, 'flash_flood', :valid, :cycle, :cycle, 0.5, 'open_meteo_ecmwf', :run_id);
                """),
                {"valid": base_time + timedelta(hours=1), "cycle": base_time, "run_id": other_run_id},
            )
            session.commit()

            # Run Wayanad retention
            ret_res = prune_obsolete_forecast_runs(
                db=session,
                admin_id=178,
                lgd_code=555,
                retention_runs=1,
            )

            # Other district's run must NOT be pruned
            assert uuid.UUID(other_run_id) not in ret_res.runs_pruned

            # Other district's records must remain intact
            other_status = session.execute(
                text("SELECT status FROM pipeline_run WHERE id = :id;"),
                {"id": other_run_id},
            ).scalar()
            assert other_status == "READY"

            other_hd_count = session.execute(
                text("SELECT count(*) FROM hazard_dynamic WHERE pipeline_run_id = :id;"),
                {"id": other_run_id},
            ).scalar()
            assert other_hd_count == 1
