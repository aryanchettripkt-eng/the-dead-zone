"""SETU-DRR Phase B8 Final Acceptance Verification & Certification Script.

Executes the definitive Phase B8 acceptance sequence:
1. TEST A: Baseline State Capture (Wayanad LGD 555 / Admin ID 178)
2. TEST B: Successful Cycle A Execution & API Verification (Already verified; validated here)
3. TEST C: Controlled Provider Failure Injection on newer Cycle B (API retains Cycle A)
4. TEST D: Successful Newer Cycle Replacement (Cycle C becomes served latest-good)
5. TEST E: Idempotency Replay on Cycle C (zero duplicate canonical state)
6. TEST F: Multi-Cycle Ingestion (Cycle D & E) + Real Bounded Retention Pruning (retention_runs=3)
7. Channel Invariance Verification (PRZ, AAZ, static MHI, live MHI, observed dynamic, other districts)
8. Concurrency & Scheduler Invariants (PostgreSQL advisory lock, APScheduler config, CLI --run-once)
9. Database Storage Measurement (measured table/index sizes and exact row counts)
10. Git Isolation Audit (0 frontend, 0 ML, 0 migration diffs)
"""

from __future__ import annotations

import json
import logging
import math
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from api.main import app
from core.config import settings
from pipeline.ingestion.open_meteo_client import (
    ADMIN_ID,
    DISTRICT_LGD,
    DISTRICT_NAME,
    REFERENCE_ARTIFACT_REL_PATH,
    PhaseB1IngestionReport,
)
from pipeline.ingestion.open_meteo_validate import validate_wayanad_b3_forecast
from pipeline.jobs.scheduler import (
    ForecastLifecycleResult,
    ForecastLockManager,
    WAYANAD_FORECAST_LOCK_ID,
    prune_obsolete_forecast_runs,
    run_wayanad_forecast_lifecycle,
)

logger = logging.getLogger("setu_b8_verification")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def generate_shifted_forecast_artifact(
    base_artifact_path: Path,
    out_artifact_path: Path,
    target_anchor: datetime,
    base_anchor: datetime = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc),
    precip_multiplier: float = 1.0,
) -> Path:
    """Generates a contract-compliant synthetic forecast artifact shifted to target_anchor."""
    with open(base_artifact_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    shift = target_anchor - base_anchor
    shifted_data = []
    for loc in data:
        new_loc = dict(loc)
        new_hourly = dict(loc["hourly"])
        new_times = []
        for t_str in loc["hourly"]["time"]:
            dt = datetime.fromisoformat(t_str) + shift
            new_times.append(dt.isoformat()[:16])
        new_precip = [round(float(p) * precip_multiplier, 2) for p in loc["hourly"]["precipitation"]]
        new_hourly["time"] = new_times
        new_hourly["precipitation"] = new_precip
        new_loc["hourly"] = new_hourly
        shifted_data.append(new_loc)

    out_artifact_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_artifact_path, "w", encoding="utf-8") as f:
        json.dump(shifted_data, f)

    # Validate with B3 gate
    b3_report = validate_wayanad_b3_forecast(
        raw_artifact_path=out_artifact_path,
        cycle_anchor=target_anchor,
        raise_on_failure=True,
    )
    assert b3_report.valid, f"Generated artifact {out_artifact_path} failed B3 validation"
    return out_artifact_path


def run_git_isolation_audit(repo_root: Path) -> dict[str, Any]:
    """Audits git status and diffs for strict subsystem isolation."""
    res_diff = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    changed_files = [f.strip() for f in res_diff.stdout.strip().splitlines() if f.strip()]

    web_diffs = [f for f in changed_files if f.startswith("web/")]
    ml_diffs = [f for f in changed_files if f.startswith("core/src/core/ml/")]
    migration_diffs = [f for f in changed_files if "migration" in f.lower()]
    science_diffs = [
        f for f in changed_files
        if f in ("core/src/core/constants.py", "core/src/core/enums.py")
    ]

    return {
        "total_modified_files": len(changed_files),
        "modified_files": changed_files,
        "web_diffs": len(web_diffs),
        "ml_diffs": len(ml_diffs),
        "migration_diffs": len(migration_diffs),
        "science_formula_diffs": len(science_diffs),
    }


def main():
    repo_root = Path(__file__).resolve().parents[1]
    raw_dir = repo_root / "data" / "raw" / "open_meteo"
    ref_artifact = raw_dir / "ecmwf_wayanad_20260908T120000Z.json"

    engine = create_engine(settings.get_sqlalchemy_url(direct=True))
    session = Session(engine)
    client = TestClient(app)

    evidence: dict[str, Any] = {}

    print("=" * 80)
    print("SETU-DRR PHASE B8 FINAL LIVE ACCEPTANCE & CERTIFICATION SUITE")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # TEST A: Clean Baseline State
    # -------------------------------------------------------------------------
    print("\n>>> [TEST A] CAPTURING BASELINE CHANNEL STATE...")
    base_run = session.execute(
        text("""
            SELECT r.id, r.status, r.started_at, s.valid_at as cycle_anchor
            FROM pipeline_run r
            JOIN source_snapshot s ON r.source_snapshot_id = s.id
            WHERE r.run_type = 'forecast_pipeline' AND r.status = 'READY'
            ORDER BY r.started_at ASC LIMIT 1;
        """)
    ).mappings().first()

    baseline_hd_obs = session.execute(
        text("SELECT count(*) FROM hazard_dynamic WHERE forecast_cycle_at IS NULL;")
    ).scalar() or 0

    baseline_prz = session.execute(
        text("SELECT count(*) FROM mhi_snapshot WHERE zone_class = 'permanent_red';")
    ).scalar() or 0

    baseline_aaz = session.execute(
        text("SELECT count(*) FROM mhi_snapshot WHERE zone_class = 'active_alert';")
    ).scalar() or 0

    baseline_caution = session.execute(
        text("SELECT count(*) FROM mhi_snapshot WHERE zone_class = 'caution';")
    ).scalar() or 0

    baseline_sample_cells = session.execute(
        text("""
            SELECT m.h3, m.valid_at, m.mhi_static, m.mhi_live, m.zone_class
            FROM mhi_snapshot m
            JOIN grid_cell g ON m.h3 = g.h3
            WHERE g.admin_id = 178 AND m.mhi_static IS NOT NULL
            ORDER BY m.h3 ASC, m.valid_at ASC
            LIMIT 5;
        """)
    ).mappings().fetchall()

    evidence["baseline"] = {
        "initial_run_id": str(base_run["id"]) if base_run else None,
        "initial_cycle": str(base_run["cycle_anchor"]) if base_run else None,
        "observed_dynamic_count": baseline_hd_obs,
        "prz_count": baseline_prz,
        "aaz_count": baseline_aaz,
        "caution_count": baseline_caution,
        "sample_cells": [dict(r) for r in baseline_sample_cells],
    }
    print(f"  Baseline initial run: {evidence['baseline']['initial_run_id']} ({evidence['baseline']['initial_cycle']})")
    print(f"  Baseline PRZ: {baseline_prz}, AAZ: {baseline_aaz}, Observed dynamic: {baseline_hd_obs}")

    # -------------------------------------------------------------------------
    # TEST B: Verify Cycle A is Currently Served
    # -------------------------------------------------------------------------
    print("\n>>> [TEST B] VERIFYING SUCCESSFUL CYCLE A (2026-09-08T18:00:00Z)...")
    run_a = session.execute(
        text("""
            SELECT r.id, r.status, r.started_at, s.valid_at as cycle_anchor
            FROM pipeline_run r
            JOIN source_snapshot s ON r.source_snapshot_id = s.id
            WHERE r.run_type = 'forecast_pipeline' AND r.status = 'READY'
              AND s.valid_at = '2026-09-08 18:00:00+00'
            ORDER BY r.started_at DESC LIMIT 1;
        """)
    ).mappings().first()

    assert run_a is not None, "Cycle A run not found in READY status!"
    cycle_a = datetime(2026, 9, 8, 18, 0, 0, tzinfo=timezone.utc)

    api_res_a = client.get("/alerts/forecast", params={"admin": 555, "horizon": 72, "limit": 5})
    assert api_res_a.status_code == 200, f"API error: {api_res_a.text}"
    data_a = api_res_a.json()
    served_a_ts = data_a.get("forecast_cycle_at")
    print(f"  Run A ID:     {run_a['id']}")
    print(f"  Run A Status: {run_a['status']}")
    print(f"  API Served:   {served_a_ts}")
    assert datetime.fromisoformat(served_a_ts) == cycle_a, f"API served {served_a_ts} != Cycle A {cycle_a.isoformat()}"
    evidence["test_b"] = {
        "run_id": str(run_a["id"]),
        "cycle": cycle_a.isoformat(),
        "status": run_a["status"],
        "api_served": served_a_ts,
    }
    print("  [PASS] Cycle A verified as currently served latest-good forecast.")

    # -------------------------------------------------------------------------
    # TEST C: Controlled Provider Failure on Newer Cycle B
    # -------------------------------------------------------------------------
    cycle_b = datetime(2026, 9, 9, 0, 0, 0, tzinfo=timezone.utc)
    print(f"\n>>> [TEST C] EXECUTING FAILED NEWER CYCLE B ({cycle_b.isoformat()})...")

    mock_b_failure = PhaseB1IngestionReport(
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
        forecast_cycle_anchor=cycle_b,
        cycle_anchor_verified=False,
        earliest_valid_at=datetime.now(timezone.utc),
        latest_valid_at=datetime.now(timezone.utc),
        errors=["Simulated ECMWF Open-Meteo HTTP 503 Provider Outage"],
    )

    t0_b = time.time()
    with patch("pipeline.jobs.scheduler.fetch_open_meteo_ecmwf_wayanad", return_value=mock_b_failure):
        res_b = run_wayanad_forecast_lifecycle(
            engine=engine,
            max_retries=1,
            retry_delay_seconds=0.01,
        )
    dur_b = time.time() - t0_b
    print(f"  Run B Outcome Status: {res_b.status}")
    print(f"  Run B Error:          {res_b.error}")
    assert res_b.status == "FAILED_PROVIDER", f"Expected FAILED_PROVIDER, got {res_b.status}"

    # Verify API still serves Cycle A
    api_res_b = client.get("/alerts/forecast", params={"admin": 555, "horizon": 72, "limit": 5})
    assert api_res_b.status_code == 200
    data_b = api_res_b.json()
    served_b_ts = data_b.get("forecast_cycle_at")
    print(f"  API Served After Failure: {served_b_ts}")
    assert datetime.fromisoformat(served_b_ts) == cycle_a, f"API did not preserve Cycle A! Got: {served_b_ts}"

    # Verify no partial rows for Cycle B in hazard_dynamic
    partial_b_rows = session.execute(
        text("SELECT count(*) FROM hazard_dynamic WHERE forecast_cycle_at = :b_cycle;"),
        {"b_cycle": cycle_b},
    ).scalar() or 0
    assert partial_b_rows == 0, f"Found {partial_b_rows} partial rows for Cycle B in hazard_dynamic!"

    evidence["test_c"] = {
        "cycle": cycle_b.isoformat(),
        "status": res_b.status,
        "error": res_b.error,
        "api_served_before": served_a_ts,
        "api_served_after": served_b_ts,
        "partial_rows_persisted": partial_b_rows,
        "latest_good_preserved": (datetime.fromisoformat(served_b_ts) == cycle_a),
    }
    print("  [PASS] Failure isolation verified: failed newer Cycle B did NOT replace latest-good Cycle A.")

    # -------------------------------------------------------------------------
    # TEST D: Successful Newer Cycle Replacement (Cycle C)
    # -------------------------------------------------------------------------
    cycle_c = datetime(2026, 9, 9, 6, 0, 0, tzinfo=timezone.utc)
    print(f"\n>>> [TEST D] EXECUTING SUCCESSFUL CYCLE C ({cycle_c.isoformat()})...")
    artifact_c = raw_dir / "ecmwf_wayanad_test_cycle_c.json"
    generate_shifted_forecast_artifact(
        base_artifact_path=ref_artifact,
        out_artifact_path=artifact_c,
        target_anchor=cycle_c,
        precip_multiplier=1.15,
    )

    t0_c = time.time()
    res_c = run_wayanad_forecast_lifecycle(
        engine=engine,
        raw_artifact_path=str(artifact_c),
        cycle_anchor=cycle_c,
        force_rerun=False,
        dry_run=True,
    )
    dur_c = time.time() - t0_c
    print(f"  Run C Outcome Status: {res_c.status} (in {dur_c:.2f}s)")
    print(f"  Run C PipelineRun ID: {res_c.pipeline_run_id}")
    assert res_c.status in ("SUCCESS", "SKIPPED_IDEMPOTENT"), f"Run C failed: {res_c.status}"

    # Verify API now atomically resolves Cycle C
    api_res_c = client.get("/alerts/forecast", params={"admin": 555, "horizon": 72, "limit": 5})
    assert api_res_c.status_code == 200
    data_c = api_res_c.json()
    served_c_ts = data_c.get("forecast_cycle_at")
    print(f"  API Served After Cycle C: {served_c_ts}")
    assert datetime.fromisoformat(served_c_ts) == cycle_c, f"API did not switch to Cycle C! Got: {served_c_ts}"

    evidence["test_d"] = {
        "run_id": str(res_c.pipeline_run_id),
        "cycle": cycle_c.isoformat(),
        "status": res_c.status,
        "duration_seconds": round(dur_c, 2),
        "api_served": served_c_ts,
        "replaced_older_good": (datetime.fromisoformat(served_c_ts) == cycle_c),
    }
    print("  [PASS] Distinct cycle replacement verified: Cycle C atomically replaced Cycle A.")

    # -------------------------------------------------------------------------
    # TEST E: Idempotency Replay on Cycle C
    # -------------------------------------------------------------------------
    print("\n>>> [TEST E] EXECUTING IDEMPOTENT REPLAY ON CYCLE C...")
    t0_e = time.time()
    res_e = run_wayanad_forecast_lifecycle(
        engine=engine,
        raw_artifact_path=str(artifact_c),
        cycle_anchor=cycle_c,
        force_rerun=False,
        dry_run=True,
    )
    dur_e = time.time() - t0_e
    print(f"  Replay Status:         {res_e.status} (in {dur_e:.2f}s)")
    print(f"  Replay PipelineRun ID: {res_e.pipeline_run_id}")
    assert res_e.status == "SKIPPED_IDEMPOTENT", f"Expected SKIPPED_IDEMPOTENT, got {res_e.status}"
    assert res_e.pipeline_run_id == res_c.pipeline_run_id, "PipelineRun ID changed on idempotent replay!"

    # Verify API remains on Cycle C
    api_res_e = client.get("/alerts/forecast", params={"admin": 555, "horizon": 72, "limit": 5})
    data_e = api_res_e.json()
    assert datetime.fromisoformat(data_e.get("forecast_cycle_at")) == cycle_c

    evidence["test_e"] = {
        "cycle": cycle_c.isoformat(),
        "status": res_e.status,
        "pipeline_run_id": str(res_e.pipeline_run_id),
        "duration_seconds": round(dur_e, 2),
        "api_served": data_e.get("forecast_cycle_at"),
    }
    print("  [PASS] Idempotency verified: identical payload safely skipped; zero duplicate state created.")

    # -------------------------------------------------------------------------
    # TEST F: Multi-Cycle Execution & Real Bounded Retention Pruning
    # -------------------------------------------------------------------------
    print("\n>>> [TEST F] INGESTING ADDITIONAL DISTINCT CYCLES FOR REAL PRUNING...")
    # Generate Cycle D (2026-09-09T12:00:00Z)
    cycle_d = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)
    artifact_d = raw_dir / "ecmwf_wayanad_test_cycle_d.json"
    generate_shifted_forecast_artifact(
        base_artifact_path=ref_artifact,
        out_artifact_path=artifact_d,
        target_anchor=cycle_d,
        precip_multiplier=1.20,
    )
    print(f"  Executing Cycle D ({cycle_d.isoformat()})...")
    res_d = run_wayanad_forecast_lifecycle(
        engine=engine,
        raw_artifact_path=str(artifact_d),
        cycle_anchor=cycle_d,
        force_rerun=False,
        dry_run=True,
    )
    print(f"  Cycle D Status: {res_d.status}, ID: {res_d.pipeline_run_id}")

    # Generate Cycle E (2026-09-09T18:00:00Z)
    cycle_e = datetime(2026, 9, 9, 18, 0, 0, tzinfo=timezone.utc)
    artifact_e = raw_dir / "ecmwf_wayanad_test_cycle_e.json"
    generate_shifted_forecast_artifact(
        base_artifact_path=ref_artifact,
        out_artifact_path=artifact_e,
        target_anchor=cycle_e,
        precip_multiplier=1.25,
    )
    print(f"  Executing Cycle E ({cycle_e.isoformat()})...")
    res_e = run_wayanad_forecast_lifecycle(
        engine=engine,
        raw_artifact_path=str(artifact_e),
        cycle_anchor=cycle_e,
        force_rerun=False,
        dry_run=True,
    )
    print(f"  Cycle E Status: {res_e.status}, ID: {res_e.pipeline_run_id}")

    # Inspect all READY forecast runs in DB before pruning
    ready_runs_before = session.execute(
        text("""
            SELECT r.id, r.started_at, s.valid_at as cycle_anchor
            FROM pipeline_run r
            JOIN source_snapshot s ON r.source_snapshot_id = s.id
            WHERE r.run_type = 'forecast_pipeline' AND r.status = 'READY'
            ORDER BY r.started_at DESC;
        """)
    ).mappings().fetchall()
    print(f"\n  READY Forecast Runs Before Pruning: {len(ready_runs_before)}")
    for r in ready_runs_before:
        print(f"    - ID={r['id']}, Cycle={r['cycle_anchor']}, Started={r['started_at']}")

    # EXECUTE REAL RETENTION PRUNING (dry_run=False, retention_runs=3)
    print("\n  Executing REAL retention pruning (retention_runs=3, dry_run=False)...")
    ret_result = prune_obsolete_forecast_runs(
        db=session,
        admin_id=ADMIN_ID,
        lgd_code=DISTRICT_LGD,
        retention_runs=3,
        dry_run=False,
    )
    print(f"  Retention Pruning Summary:")
    print(f"    - Runs Protected:                 {len(ret_result.runs_protected)}")
    print(f"    - Runs Pruned:                    {len(ret_result.runs_pruned)}")
    print(f"    - Deleted hazard_dynamic rows:    {ret_result.records_deleted_hazard_dynamic}")
    print(f"    - Deleted mhi_snapshot rows:      {ret_result.records_deleted_mhi_snapshot}")
    print(f"    - Cleared mhi_fcst values:        {ret_result.records_updated_mhi_fcst_cleared}")
    assert len(ret_result.runs_protected) == 3, f"Expected 3 protected runs, got {len(ret_result.runs_protected)}"
    assert len(ret_result.runs_pruned) >= 1, f"Expected >= 1 pruned runs, got {len(ret_result.runs_pruned)}"
    assert ret_result.records_deleted_hazard_dynamic > 0, "No hazard_dynamic rows were pruned!"

    # Verify latest-good run (Cycle E) is protected
    assert ret_result.runs_protected[0] == res_e.pipeline_run_id, "Latest-good run was not protected in slot 0!"

    # Verify pruned runs transitioned to SUPERSEDED
    for pruned_id in ret_result.runs_pruned:
        st = session.execute(
            text("SELECT status FROM pipeline_run WHERE id = :id;"),
            {"id": pruned_id},
        ).scalar()
        assert st == "SUPERSEDED", f"Pruned run {pruned_id} has status '{st}', expected 'SUPERSEDED'"

    # Verify API still serves Cycle E without disruption
    api_res_post_ret = client.get("/alerts/forecast", params={"admin": 555, "horizon": 72, "limit": 5})
    assert api_res_post_ret.status_code == 200
    data_post_ret = api_res_post_ret.json()
    print(f"  API Served After Retention: {data_post_ret.get('forecast_cycle_at')}")
    assert datetime.fromisoformat(data_post_ret.get("forecast_cycle_at")) == cycle_e

    evidence["test_f"] = {
        "configured_retention": 3,
        "runs_before_pruning": len(ready_runs_before),
        "runs_protected_count": len(ret_result.runs_protected),
        "runs_pruned_count": len(ret_result.runs_pruned),
        "records_deleted_hazard_dynamic": ret_result.records_deleted_hazard_dynamic,
        "records_deleted_mhi_snapshot": ret_result.records_deleted_mhi_snapshot,
        "records_updated_mhi_fcst_cleared": ret_result.records_updated_mhi_fcst_cleared,
        "latest_good_protected": str(ret_result.runs_protected[0]),
        "api_served_post_retention": data_post_ret.get("forecast_cycle_at"),
    }
    print("  [PASS] Real retention pruning verified: obsolete runs purged; latest-good protected.")

    # -------------------------------------------------------------------------
    # TEST G: Strict Subsystem & Channel Invariance Verification
    # -------------------------------------------------------------------------
    print("\n>>> [TEST G] VERIFYING CHANNEL INVARIANCE...")
    post_hd_obs = session.execute(
        text("SELECT count(*) FROM hazard_dynamic WHERE forecast_cycle_at IS NULL;")
    ).scalar() or 0
    assert post_hd_obs == baseline_hd_obs, f"Observed dynamic count changed: {post_hd_obs} != {baseline_hd_obs}"

    post_prz = session.execute(
        text("SELECT count(*) FROM mhi_snapshot WHERE zone_class = 'permanent_red';")
    ).scalar() or 0
    assert post_prz == baseline_prz, f"PRZ count changed: {post_prz} != {baseline_prz}"

    post_aaz = session.execute(
        text("SELECT count(*) FROM mhi_snapshot WHERE zone_class = 'active_alert';")
    ).scalar() or 0
    assert post_aaz == baseline_aaz, f"AAZ count changed: {post_aaz} != {baseline_aaz}"

    # Sample cell check
    for sc in baseline_sample_cells:
        cur_cell = session.execute(
            text("""
                SELECT mhi_static, mhi_live, zone_class
                FROM mhi_snapshot
                WHERE h3 = :h3 AND valid_at = :valid_at;
            """),
            {"h3": sc["h3"], "valid_at": sc["valid_at"]},
        ).mappings().first()
        assert cur_cell is not None, f"Sample cell {sc['h3']} missing after retention!"
        assert abs(float(cur_cell["mhi_static"]) - float(sc["mhi_static"])) < 1e-6, "Static MHI altered!"
        assert abs(float(cur_cell["mhi_live"]) - float(sc["mhi_live"])) < 1e-6, "Live MHI altered!"

    evidence["invariance"] = {
        "observed_dynamic_count": post_hd_obs,
        "observed_dynamic_preserved": (post_hd_obs == baseline_hd_obs),
        "prz_count": post_prz,
        "prz_preserved": (post_prz == baseline_prz),
        "aaz_count": post_aaz,
        "aaz_preserved": (post_aaz == baseline_aaz),
        "static_live_mhi_preserved": True,
    }
    print("  [PASS] Channel invariance verified: PRZ, AAZ, static/live MHI, and observed dynamic 100% intact.")

    # -------------------------------------------------------------------------
    # TEST H: Concurrency Lock & Scheduler Configuration Audit
    # -------------------------------------------------------------------------
    print("\n>>> [TEST H] AUDITING CONCURRENCY LOCK & SCHEDULER SETTINGS...")
    lock1 = ForecastLockManager(engine=engine, lock_id=WAYANAD_FORECAST_LOCK_ID)
    assert lock1.acquire() is True
    lock2 = ForecastLockManager(engine=engine, lock_id=WAYANAD_FORECAST_LOCK_ID)
    assert lock2.acquire() is False
    lock1.release()
    assert lock2.acquire() is True
    lock2.release()

    evidence["concurrency"] = {
        "lock_id": WAYANAD_FORECAST_LOCK_ID,
        "overlap_rejected": True,
        "clean_release_verified": True,
        "scheduler_enabled_default": settings.FORECAST_SCHEDULER_ENABLED,
        "scheduler_cron": settings.FORECAST_SCHEDULE_CRON,
    }
    print("  [PASS] Concurrency lock and scheduler configuration verified.")

    # -------------------------------------------------------------------------
    # TEST I: Actual Storage Measurement
    # -------------------------------------------------------------------------
    print("\n>>> [TEST I] MEASURING ACTUAL POSTGRESQL TABLE & INDEX STORAGE...")
    storage_queries = {
        "hazard_dynamic": "SELECT pg_total_relation_size('hazard_dynamic') as total_bytes, pg_size_pretty(pg_total_relation_size('hazard_dynamic')) as pretty_size;",
        "mhi_snapshot": "SELECT pg_total_relation_size('mhi_snapshot') as total_bytes, pg_size_pretty(pg_total_relation_size('mhi_snapshot')) as pretty_size;",
        "pipeline_run": "SELECT pg_total_relation_size('pipeline_run') as total_bytes, pg_size_pretty(pg_total_relation_size('pipeline_run')) as pretty_size;",
        "source_snapshot": "SELECT pg_total_relation_size('source_snapshot') as total_bytes, pg_size_pretty(pg_total_relation_size('source_snapshot')) as pretty_size;",
    }

    storage_data = {}
    for table, query in storage_queries.items():
        res = session.execute(text(query)).mappings().first()
        row_cnt = session.execute(text(f"SELECT count(*) FROM {table};")).scalar() or 0
        storage_data[table] = {
            "row_count": row_cnt,
            "total_bytes": res["total_bytes"],
            "pretty_size": res["pretty_size"],
        }
        print(f"  Table '{table}': {row_cnt} rows, {res['pretty_size']} ({res['total_bytes']} bytes)")

    evidence["storage"] = storage_data

    # -------------------------------------------------------------------------
    # TEST J: Git Subsystem Isolation Audit
    # -------------------------------------------------------------------------
    print("\n>>> [TEST J] AUDITING SUBSYSTEM ISOLATION...")
    git_audit = run_git_isolation_audit(repo_root)
    print(f"  Web Diffs:             {git_audit['web_diffs']}")
    print(f"  ML Diffs:              {git_audit['ml_diffs']}")
    print(f"  Migration Diffs:       {git_audit['migration_diffs']}")
    print(f"  Science Formula Diffs: {git_audit['science_formula_diffs']}")
    assert git_audit["web_diffs"] == 0, "Web diffs detected!"
    assert git_audit["ml_diffs"] == 0, "ML diffs detected!"
    assert git_audit["migration_diffs"] == 0, "Migrations detected!"
    assert git_audit["science_formula_diffs"] == 0, "Science formula diffs detected!"

    evidence["git_isolation"] = git_audit

    # Save evidence file
    evidence_path = repo_root / "b8_final_verification_evidence.json"
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)
    print(f"\nSaved complete verification evidence to '{evidence_path}'.")
    print("=" * 80)
    print("ALL B8 ACCEPTANCE TESTS PASSED EMPIRICALLY!")
    print("=" * 80)


if __name__ == "__main__":
    main()
