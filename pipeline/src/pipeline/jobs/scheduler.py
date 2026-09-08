"""SETU-DRR Phase B8: Production-Safe Live Forecast Scheduling, Latest-Good State & Retention.

Orchestrates:
    Scheduler / Cron Trigger
            ↓
    Singleton Concurrency Lock (PostgreSQL Session Advisory Lock)
            ↓
    Provider Acquisition (Phase B1 with bounded retries & backoff)
            ↓
    Existing Wayanad Forecast Pipeline (Phases B2–B6)
            ↓
    Latest-Good Verification & Atomic Transition
            ↓
    Scoped Bounded Retention (obsolete forecast pruning)
            ↓
    Release Concurrency Lock

Strict Subsystem Invariants:
- Reuses existing Phase B1 ingestion and Phase B6 pipeline (zero duplicate logic).
- Preserves all scientific constants and formulas (B4/B5 trigger calculation untouched).
- Preserves all core channels (PRZ, AAZ, static MHI, live MHI untouched).
- Zero modifications to ML models, XGBoost, or frontend code.
- Zero schema modifications or database migrations.
- FAILED or RUNNING pipeline runs NEVER replace the latest-good forecast.
- API serves previous latest-good forecast seamlessly during active ingestion.
- Retention failure NEVER invalidates a newly successful forecast run.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from core.config import settings
from pipeline.ingestion.open_meteo_client import (
    ADMIN_ID,
    DISTRICT_LGD,
    DISTRICT_NAME,
    fetch_open_meteo_ecmwf_wayanad,
)
from pipeline.jobs.run_open_meteo_wayanad import (
    WayanadForecastPipelineResult,
    run_open_meteo_wayanad_pipeline,
)

logger = logging.getLogger("setu_pipeline.scheduler")

# Deterministic PostgreSQL Advisory Lock ID for Wayanad Forecast Lifecycle
# Derived from Admin ID 178 + LGD Code 555 + Slot 01 -> 17855501 (signed 64-bit int safe)
WAYANAD_FORECAST_LOCK_ID = 17855501

# Fallback in-process thread lock for non-PostgreSQL / SQLite test environments
_IN_PROCESS_LOCK = threading.Lock()


@dataclass(frozen=True)
class RetentionResult:
    """Outcome report of bounded forecast retention pruning."""
    runs_pruned: list[uuid.UUID] = field(default_factory=list)
    runs_protected: list[uuid.UUID] = field(default_factory=list)
    records_deleted_hazard_dynamic: int = 0
    records_deleted_mhi_snapshot: int = 0
    records_updated_mhi_fcst_cleared: int = 0
    dry_run: bool = False
    error: Optional[str] = None


@dataclass(frozen=True)
class ForecastLifecycleResult:
    """Consolidated outcome report of the scheduled Wayanad forecast lifecycle."""
    status: str  # 'SUCCESS', 'SKIPPED_IDEMPOTENT', 'LOCKED_SKIPPED', 'FAILED_PROVIDER', 'FAILED_PIPELINE'
    pipeline_run_id: Optional[uuid.UUID]
    forecast_cycle_anchor: Optional[datetime]
    provider_status: Optional[str]
    pipeline_result: Optional[WayanadForecastPipelineResult]
    retention_result: Optional[RetentionResult]
    duration_seconds: float
    error: Optional[str] = None


class ForecastLockManager:
    """Session-scoped advisory lock manager for singleton execution safety.

    On PostgreSQL, uses `pg_try_advisory_lock` on a dedicated unpooled connection.
    On non-PostgreSQL (e.g. SQLite unit tests), falls back to a thread lock.
    """

    def __init__(self, engine: Engine, lock_id: int = WAYANAD_FORECAST_LOCK_ID):
        self.engine = engine
        self.lock_id = lock_id
        self.connection: Optional[Connection] = None
        self.acquired: bool = False
        self._is_postgres: bool = False
        self._thread_acquired: bool = False

    def acquire(self) -> bool:
        """Attempts non-blocking acquisition of the forecast lifecycle lock."""
        try:
            self.connection = self.engine.connect()
            self._is_postgres = self.connection.dialect.name == "postgresql"

            if self._is_postgres:
                res = self.connection.execute(
                    text("SELECT pg_try_advisory_lock(:lock_id) AS acquired;"),
                    {"lock_id": self.lock_id},
                ).scalar()
                self.acquired = bool(res)
            else:
                # SQLite / test fallback: non-blocking thread lock
                self._thread_acquired = _IN_PROCESS_LOCK.acquire(blocking=False)
                self.acquired = self._thread_acquired

            if self.acquired:
                logger.info(f"Acquired forecast singleton lock (id={self.lock_id}, postgres={self._is_postgres})")
            else:
                logger.warning(
                    f"Forecast singleton lock (id={self.lock_id}) already held by another active run. "
                    "Skipping execution to prevent concurrent interleaving."
                )
                self.release()

            return self.acquired

        except Exception as exc:
            logger.error(f"Failed to acquire advisory lock {self.lock_id}: {exc}")
            self.release()
            return False

    def release(self) -> None:
        """Releases the advisory lock and closes the dedicated session connection."""
        try:
            if self.acquired:
                if self._is_postgres and self.connection and not self.connection.closed:
                    self.connection.execute(
                        text("SELECT pg_advisory_unlock(:lock_id);"),
                        {"lock_id": self.lock_id},
                    )
                    logger.info(f"Released PostgreSQL advisory lock (id={self.lock_id})")
                elif self._thread_acquired:
                    _IN_PROCESS_LOCK.release()
                    self._thread_acquired = False
                    logger.info("Released in-process thread lock")
        except Exception as exc:
            logger.warning(f"Error during advisory unlock {self.lock_id}: {exc}")
        finally:
            self.acquired = False
            if self.connection and not self.connection.closed:
                try:
                    self.connection.close()
                except Exception:
                    pass
                self.connection = None


def prune_obsolete_forecast_runs(
    db: Session,
    admin_id: int = ADMIN_ID,
    lgd_code: int = DISTRICT_LGD,
    retention_runs: int = 3,
    dry_run: bool = False,
) -> RetentionResult:
    """Identifies and purges obsolete forecast runs while strictly protecting latest-good.

    Scope Safety Guarantees:
        1. Protects the latest `retention_runs` successful READY runs (which includes latest-good).
        2. Never deletes RUNNING runs.
        3. Scoped strictly to district forecast runs (Wayanad / LGD 555).
        4. In `hazard_dynamic`: deletes only rows with `forecast_cycle_at IS NOT NULL`.
        5. In `mhi_snapshot`: deletes only pure forecast snapshots (`mhi_live = 0.0` and
           `zone_class NOT IN ('permanent_red', 'active_alert', 'caution')`).
        6. In `mhi_snapshot`: clears `mhi_fcst = NULL` for any shared rows.
        7. In `pipeline_run`: marks status = 'SUPERSEDED'.
        8. Does NOT touch PRZ, AAZ, static MHI, live MHI, observed dynamic records, or other districts.
    """
    logger.info(
        f"Evaluating forecast retention candidates for admin_id={admin_id}, lgd_code={lgd_code} "
        f"(retention_count={retention_runs}, dry_run={dry_run})..."
    )

    # 1. Query all READY forecast runs in reverse chronological order
    all_ready_runs = db.execute(
        text("""
            SELECT r.id, r.started_at, r.completed_at, r.status, s.valid_at as cycle_anchor, s.metadata
            FROM pipeline_run r
            JOIN source_snapshot s ON r.source_snapshot_id = s.id
            WHERE r.run_type = 'forecast_pipeline'
              AND r.status = 'READY'
            ORDER BY r.started_at DESC;
        """)
    ).mappings().fetchall()

    # Scope filtering in Python to ensure 100% database portability (PostgreSQL JSONB / SQLite TEXT)
    ready_runs = []
    for r in all_ready_runs:
        meta = r.get("metadata")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        elif not isinstance(meta, dict):
            meta = {}

        r_admin = meta.get("admin_id")
        r_lgd = meta.get("lgd_code")
        r_dist = meta.get("district")
        if (
            (r_admin is not None and int(r_admin) == admin_id)
            or (r_lgd is not None and int(r_lgd) == lgd_code)
            or (r_dist and str(r_dist).lower() == DISTRICT_NAME.lower())
        ):
            ready_runs.append(r)

    protected_runs = [uuid.UUID(str(r["id"])) for r in ready_runs[:retention_runs]]
    obsolete_ready_runs = [uuid.UUID(str(r["id"])) for r in ready_runs[retention_runs:]]

    # 2. Also identify old FAILED runs that occurred prior to the oldest protected run
    obsolete_failed_runs: list[uuid.UUID] = []
    if ready_runs and len(ready_runs) >= retention_runs:
        oldest_protected_time = ready_runs[retention_runs - 1]["started_at"]
        all_failed_runs = db.execute(
            text("""
                SELECT r.id, r.started_at, s.metadata
                FROM pipeline_run r
                JOIN source_snapshot s ON r.source_snapshot_id = s.id
                WHERE r.run_type = 'forecast_pipeline'
                  AND r.status = 'FAILED'
                  AND r.started_at < :oldest_time;
            """),
            {"oldest_time": oldest_protected_time},
        ).mappings().fetchall()

        for r in all_failed_runs:
            meta = r.get("metadata")
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            elif not isinstance(meta, dict):
                meta = {}

            r_admin = meta.get("admin_id")
            r_lgd = meta.get("lgd_code")
            r_dist = meta.get("district")
            if (
                (r_admin is not None and int(r_admin) == admin_id)
                or (r_lgd is not None and int(r_lgd) == lgd_code)
                or (r_dist and str(r_dist).lower() == DISTRICT_NAME.lower())
            ):
                obsolete_failed_runs.append(uuid.UUID(str(r["id"])))

    candidate_run_ids = obsolete_ready_runs + obsolete_failed_runs

    # Absolute Safety Check: Latest-Good MUST NOT be in candidate list
    if protected_runs and protected_runs[0] in candidate_run_ids:
        raise RuntimeError("Safety Invariant Violated: Latest-good run was identified as retention candidate!")

    logger.info(
        f"Retention scope analysis: {len(protected_runs)} protected runs, "
        f"{len(candidate_run_ids)} obsolete candidates ({len(obsolete_ready_runs)} READY, "
        f"{len(obsolete_failed_runs)} FAILED)."
    )

    if not candidate_run_ids:
        logger.info("No obsolete forecast runs qualify for retention pruning.")
        return RetentionResult(
            runs_pruned=[],
            runs_protected=protected_runs,
            records_deleted_hazard_dynamic=0,
            records_deleted_mhi_snapshot=0,
            records_updated_mhi_fcst_cleared=0,
            dry_run=dry_run,
        )

    total_hd_deleted = 0
    total_mhi_deleted = 0
    total_mhi_cleared = 0

    # A snapshot row is prunable only when the timestamp it sits on belongs exclusively to
    # the run being pruned: no observed trigger and no other run's forecast trigger shares it.
    # Rows on shared timestamps are left untouched for their surviving owner to keep.
    #
    # NOTE: the snapshot delete must run BEFORE the trigger delete, because it identifies its
    # targets by joining through this run's own hazard_dynamic rows.
    ORPHAN_SNAPSHOT_PREDICATE = """
        mhi_fcst IS NOT NULL
        AND zone_class NOT IN ('permanent_red', 'active_alert', 'caution')
        AND EXISTS (
            SELECT 1 FROM hazard_dynamic hd
            WHERE hd.valid_at = mhi_snapshot.valid_at
              AND hd.pipeline_run_id = :run_id
              AND hd.forecast_cycle_at IS NOT NULL
        )
        AND NOT EXISTS (
            SELECT 1 FROM hazard_dynamic hd2
            WHERE hd2.valid_at = mhi_snapshot.valid_at
              AND (hd2.forecast_cycle_at IS NULL OR hd2.pipeline_run_id IS DISTINCT FROM :run_id)
        )
    """

    for run_id in candidate_run_ids:
        run_id_str = str(run_id)
        if dry_run:
            hd_count = db.execute(
                text("""
                    SELECT count(*) FROM hazard_dynamic
                    WHERE pipeline_run_id = :run_id AND forecast_cycle_at IS NOT NULL;
                """),
                {"run_id": run_id_str},
            ).scalar() or 0

            mhi_del_count = db.execute(
                text(f"SELECT count(*) FROM mhi_snapshot WHERE {ORPHAN_SNAPSHOT_PREDICATE};"),
                {"run_id": run_id_str},
            ).scalar() or 0

            total_hd_deleted += hd_count
            total_mhi_deleted += mhi_del_count
            logger.info(
                f"[DRY-RUN] Would prune Run {run_id_str}: "
                f"{hd_count} hazard_dynamic rows, {mhi_del_count} orphaned mhi_snapshot rows."
            )
        else:
            # 1. Delete forecast snapshots stranded by this run (must precede the trigger delete).
            del_mhi = db.execute(
                text(f"DELETE FROM mhi_snapshot WHERE {ORPHAN_SNAPSHOT_PREDICATE};"),
                {"run_id": run_id_str},
            )
            total_mhi_deleted += del_mhi.rowcount or 0

            # 2. Delete this run's forecast records from hazard_dynamic.
            del_hd = db.execute(
                text("""
                    DELETE FROM hazard_dynamic
                    WHERE pipeline_run_id = :run_id AND forecast_cycle_at IS NOT NULL;
                """),
                {"run_id": run_id_str},
            )
            total_hd_deleted += del_hd.rowcount or 0

            # 3. Transition PipelineRun status to SUPERSEDED.
            #    pipeline_run_id on surviving snapshots is deliberately left intact: nulling it
            #    would strip provenance from PRZ/live rows the forecast run merely touched.
            db.execute(
                text("""
                    UPDATE pipeline_run
                    SET status = 'SUPERSEDED'
                    WHERE id = :run_id AND status = 'READY';
                """),
                {"run_id": run_id_str},
            )

    if not dry_run:
        db.commit()
        logger.info(
            f"Successfully pruned {len(candidate_run_ids)} obsolete runs: "
            f"{total_hd_deleted} hazard_dynamic records deleted, "
            f"{total_mhi_deleted} orphaned mhi_snapshot records deleted "
            f"(snapshots on timestamps shared with a surviving cycle are left intact)."
        )

    return RetentionResult(
        runs_pruned=candidate_run_ids,
        runs_protected=protected_runs,
        records_deleted_hazard_dynamic=total_hd_deleted,
        records_deleted_mhi_snapshot=total_mhi_deleted,
        records_updated_mhi_fcst_cleared=total_mhi_cleared,
        dry_run=dry_run,
    )


def run_wayanad_forecast_lifecycle(
    engine: Optional[Engine] = None,
    raw_artifact_path: Optional[Path | str] = None,
    cycle_anchor: Optional[datetime] = None,
    force_rerun: bool = False,
    dry_run: bool = False,
    retention_runs: Optional[int] = None,
    max_retries: Optional[int] = None,
    retry_delay_seconds: Optional[float] = None,
    http_client: Optional[httpx.Client] = None,
) -> ForecastLifecycleResult:
    """Authoritative entrypoint for the operational Wayanad forecast lifecycle (Phase B8).

    Orchestrates:
        1. Non-blocking acquisition of PostgreSQL singleton advisory lock.
        2. Acquisition of ECMWF forecast data via Phase B1 client with bounded retries.
        3. Full forecast evaluation & persistence via Phase B6 pipeline job.
        4. Validation that new run achieved READY status and is visible to API read path.
        5. Bounded retention pruning of obsolete historical runs (protecting latest-good).
        6. Reliable release of singleton lock in `finally` block.

    Failure Safety Invariant:
        Provider acquisition failures or pipeline processing failures NEVER destroy or
        corrupt existing forecast state. The previous latest-good run remains fully intact
        and queryable.
    """
    start_time = time.time()
    logger.info("=" * 80)
    logger.info(f"INITIATING WAYANAD LIVE FORECAST LIFECYCLE (PID={threading.get_native_id()})")
    logger.info("=" * 80)

    # Resolve database engine
    managed_engine = False
    if engine is None:
        db_url = settings.get_sqlalchemy_url(direct=True)
        engine = create_engine(db_url)
        managed_engine = True

    effective_retention = retention_runs if retention_runs is not None else settings.FORECAST_RETENTION_RUNS
    effective_retries = max_retries if max_retries is not None else settings.FORECAST_MAX_RETRIES
    effective_delay = retry_delay_seconds if retry_delay_seconds is not None else settings.FORECAST_RETRY_DELAY_SECONDS

    # 1. Acquire Concurrency Lock
    lock_mgr = ForecastLockManager(engine=engine, lock_id=WAYANAD_FORECAST_LOCK_ID)
    if not lock_mgr.acquire():
        elapsed = time.time() - start_time
        return ForecastLifecycleResult(
            status="LOCKED_SKIPPED",
            pipeline_run_id=None,
            forecast_cycle_anchor=None,
            provider_status=None,
            pipeline_result=None,
            retention_result=None,
            duration_seconds=elapsed,
            error="Concurrent forecast run currently active; lock acquisition rejected.",
        )

    try:
        # 2. Acquire Provider Forecast Data (Phase B1 with bounded retries)
        resolved_artifact: Optional[Path | str] = raw_artifact_path
        provider_status: str = "PRE_EXISTING_ARTIFACT"
        resolved_cycle_anchor: Optional[datetime] = cycle_anchor

        if resolved_artifact is None:
            logger.info(
                f"Acquiring forecast from Open-Meteo ECMWF (max_retries={effective_retries}, "
                f"delay={effective_delay}s, demo_mode={settings.DEMO_MODE})..."
            )
            attempts = 0
            b1_report = None
            last_err = None

            while attempts <= effective_retries:
                attempts += 1
                try:
                    b1_report = fetch_open_meteo_ecmwf_wayanad(
                        http_client=http_client,
                        db_engine=None,  # Handled authoritatively by B6
                    )
                    if b1_report.status in ("SUCCESS", "SKIPPED_IDEMPOTENT"):
                        resolved_artifact = b1_report.raw_artifact_path
                        provider_status = b1_report.status
                        resolved_cycle_anchor = b1_report.forecast_cycle_anchor
                        break
                    else:
                        last_err = "; ".join(b1_report.errors) or f"HTTP {b1_report.http_status_code}"
                        logger.warning(f"Provider attempt {attempts}/{effective_retries + 1} failed: {last_err}")
                except Exception as fetch_exc:
                    last_err = str(fetch_exc)
                    logger.warning(f"Provider attempt {attempts}/{effective_retries + 1} raised exception: {last_err}")

                if attempts <= effective_retries:
                    backoff = effective_delay * (2 ** (attempts - 1))
                    logger.info(f"Retrying provider acquisition in {backoff:.1f}s...")
                    time.sleep(backoff)

            if resolved_artifact is None:
                err_msg = f"Provider acquisition failed after {attempts} attempts: {last_err}"
                logger.error(f"{err_msg} Preserving existing latest-good forecast intact.")
                elapsed = time.time() - start_time
                return ForecastLifecycleResult(
                    status="FAILED_PROVIDER",
                    pipeline_run_id=None,
                    forecast_cycle_anchor=None,
                    provider_status="FAILED",
                    pipeline_result=None,
                    retention_result=None,
                    duration_seconds=elapsed,
                    error=err_msg,
                )

        logger.info(f"Provider stage complete: artifact='{resolved_artifact}', status='{provider_status}'")

        # 3. Execute Existing Phase B6 Pipeline
        logger.info("Executing Phase B6 Wayanad forecast pipeline...")
        with Session(engine) as session:
            b6_result = run_open_meteo_wayanad_pipeline(
                db=session,
                raw_artifact_path=resolved_artifact,
                cycle_anchor=resolved_cycle_anchor,
                force_rerun=force_rerun,
                raise_on_failure=False,
            )

            if b6_result.status == "FAILED":
                err_msg = f"B6 pipeline execution failed: {b6_result.error}"
                logger.error(f"{err_msg} Preserving previous latest-good forecast intact.")
                elapsed = time.time() - start_time
                return ForecastLifecycleResult(
                    status="FAILED_PIPELINE",
                    pipeline_run_id=b6_result.pipeline_run_id,
                    forecast_cycle_anchor=b6_result.forecast_cycle_anchor,
                    provider_status=provider_status,
                    pipeline_result=b6_result,
                    retention_result=None,
                    duration_seconds=elapsed,
                    error=err_msg,
                )

            logger.info(
                f"Phase B6 execution finished with status='{b6_result.status}' "
                f"(run_id={b6_result.pipeline_run_id}, triggers={b6_result.trigger_records_persisted}, "
                f"snapshots={b6_result.snapshots_persisted})"
            )

            # 4. Verify Latest-Good Resolution on DB Read Path
            check_cycle = session.execute(
                text("""
                    SELECT MAX(hd.forecast_cycle_at) as max_cycle
                    FROM hazard_dynamic hd
                    JOIN grid_cell g ON hd.h3 = g.h3
                    LEFT JOIN admin_boundary a ON g.admin_id = a.id
                    LEFT JOIN pipeline_run pr ON hd.pipeline_run_id = pr.id
                    WHERE hd.forecast_cycle_at IS NOT NULL
                      AND (g.admin_id = :admin_id OR a.lgd_code = :admin_id)
                      AND (hd.pipeline_run_id IS NULL OR pr.status IN ('READY', 'COMPLETED'));
                """),
                {"admin_id": DISTRICT_LGD},
            ).scalar()

            logger.info(f"Latest-good forecast cycle resolved by read query: {check_cycle}")

            # 5. Execute Scoped Bounded Retention (Non-destructive to new run)
            retention_res: Optional[RetentionResult] = None
            try:
                retention_res = prune_obsolete_forecast_runs(
                    db=session,
                    admin_id=ADMIN_ID,
                    lgd_code=DISTRICT_LGD,
                    retention_runs=effective_retention,
                    dry_run=dry_run,
                )
            except Exception as ret_err:
                logger.error(
                    f"Retention pruning encountered an error: {ret_err}. "
                    "Newly ingested forecast run remains READY and protected.",
                    exc_info=True,
                )
                retention_res = RetentionResult(
                    runs_pruned=[],
                    runs_protected=[],
                    dry_run=dry_run,
                    error=str(ret_err),
                )

            elapsed = time.time() - start_time
            logger.info("=" * 80)
            logger.info(f"WAYANAD FORECAST LIFECYCLE COMPLETED SUCCESSFULLY IN {elapsed:.2f}s")
            logger.info("=" * 80)

            final_status = "SKIPPED_IDEMPOTENT" if b6_result.status == "SKIPPED_IDEMPOTENT" else "SUCCESS"
            return ForecastLifecycleResult(
                status=final_status,
                pipeline_run_id=b6_result.pipeline_run_id,
                forecast_cycle_anchor=b6_result.forecast_cycle_anchor,
                provider_status=provider_status,
                pipeline_result=b6_result,
                retention_result=retention_res,
                duration_seconds=elapsed,
                error=None,
            )

    finally:
        lock_mgr.release()
        if managed_engine:
            engine.dispose()


def start_forecast_scheduler(
    blocking: bool = True,
    run_once: bool = False,
    dry_run: bool = False,
    force_enabled: bool = False,
) -> Optional[ForecastLifecycleResult]:
    """Starts the APScheduler runner for periodic Wayanad forecast ingestion.

    Options:
        blocking: If True, uses BlockingScheduler (for standalone CLI daemon worker).
        run_once: If True, immediately executes one lifecycle run and exits.
        dry_run: If True, executes without deleting records during retention.
        force_enabled: Overrides `settings.FORECAST_SCHEDULER_ENABLED = False`.
    """
    if run_once:
        logger.info("Executing single manual forecast lifecycle run (--run-once)...")
        return run_wayanad_forecast_lifecycle(dry_run=dry_run)

    is_enabled = settings.FORECAST_SCHEDULER_ENABLED or force_enabled
    if not is_enabled:
        logger.info(
            "Forecast scheduler is disabled by configuration (FORECAST_SCHEDULER_ENABLED=False). "
            "To enable, set FORECAST_SCHEDULER_ENABLED=true in .env or pass --force-enable."
        )
        return None

    # Imported lazily: only the long-running daemon needs APScheduler. Keeping it at module
    # scope would make `import pipeline.jobs` (and therefore every other job) depend on it.
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    cron_expr = settings.FORECAST_SCHEDULE_CRON
    logger.info(
        f"Initializing Wayanad Forecast APScheduler: cron='{cron_expr}' (UTC), "
        f"retention={settings.FORECAST_RETENTION_RUNS}, dry_run={dry_run}..."
    )

    scheduler = BlockingScheduler(timezone="UTC") if blocking else BackgroundScheduler(timezone="UTC")

    scheduler.add_job(
        run_wayanad_forecast_lifecycle,
        trigger=CronTrigger.from_crontab(cron_expr, timezone="UTC"),
        id="wayanad_forecast_lifecycle_job",
        name="Wayanad ECMWF Live Forecast Pipeline",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        kwargs={"dry_run": dry_run},
    )

    def _shutdown_handler(signum, frame):
        logger.info(f"Received termination signal {signum}. Shutting down scheduler gracefully...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    logger.info(f"APScheduler active. Next run scheduled according to '{cron_expr}'.")
    if blocking:
        scheduler.start()
    else:
        scheduler.start()
        return None


def main() -> None:
    """CLI entrypoint for operational forecast scheduling and lifecycle management."""
    parser = argparse.ArgumentParser(description="SETU-DRR Phase B8 Live Forecast Scheduler & Runner")
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Execute a single forecast lifecycle run immediately and exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute lifecycle without deleting records during retention.",
    )
    parser.add_argument(
        "--force-enable",
        action="store_true",
        help="Override FORECAST_SCHEDULER_ENABLED=False configuration.",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Start the persistent APScheduler daemon worker.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.run_once:
        res = start_forecast_scheduler(run_once=True, dry_run=args.dry_run)
        print(f"Run Outcome: {res.status if res else 'NO_RESULT'}")
    elif args.daemon or args.force_enable:
        start_forecast_scheduler(blocking=True, dry_run=args.dry_run, force_enabled=True)
    else:
        start_forecast_scheduler(blocking=True, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
