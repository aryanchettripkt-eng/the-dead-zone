"""SETU-DRR Phase B6: Wayanad Live Forecast Hazard Evaluation & Snapshot Persistence.

Orchestrates:
    Phase B5 canonical forecast trigger records (259,344 in-memory records)
            ↓
    Contract validation & integrity check
            ↓
    Idempotency check (source_snapshot & pipeline_run)
            ↓
    Register PipelineRun (status: RUNNING)
            ↓
    Bulk persist forecast triggers into hazard_dynamic
            ↓
    Invoke authoritative dynamic hazard engine (compute_and_persist_dynamic_snapshots)
    with explicit scoping: aoi_lgd=555, pipeline_run_id, forecast_cycle_at, hazard_type='flash_flood'
            ↓
    Verify forecast MHI snapshots (mhi_snapshot.mhi_fcst)
            ↓
    Finalize PipelineRun (status: READY)

Strict Scope Rules (Phase B6):
- Consumes Phase B5 canonical trigger records (never modifies B1-B5).
- Invokes existing authoritative DynamicHazardEvaluator via compute_and_persist_dynamic_snapshots.
- Preserves existing mhi_live and mhi_static via atomic database upsert.
- Zero schema modifications, zero migrations, zero API changes, zero frontend changes, zero ML changes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from core.config import settings
from core.constants import FORECAST_HORIZON_HOURS
from core.schemas.dynamic_triggers import CanonicalTriggerRecord
from pipeline.ingestion.open_meteo_client import (
    ADMIN_ID,
    DISTRICT_LGD,
    DISTRICT_NAME,
    REFERENCE_ARTIFACT_REL_PATH,
    SOURCE_ID,
    SOURCE_MODEL,
)
from pipeline.ingestion.open_meteo_regrid import (
    EXPECTED_CELL_COUNT,
    WayanadSpatialMappingResult,
)
from pipeline.ingestion.open_meteo_trigger import (
    HAZARD_TYPE,
    WayanadTriggerGenerationResult,
    execute_wayanad_b5_trigger_generation,
)
from pipeline.jobs.compute_dynamic_hazard import (
    DynamicProcessingResult,
    compute_and_persist_dynamic_snapshots,
)

logger = logging.getLogger("setu_pipeline.run_open_meteo_wayanad")

PIPELINE_CODE_VERSION = "b6-wayanad-v1.0"
PIPELINE_CONFIG_VERSION = "wayanad-prototype-param-v1.0"
PIPELINE_MODEL_VERSION = SOURCE_MODEL  # "ECMWF_IFS_HRES"


@dataclass(frozen=True)
class WayanadForecastPipelineResult:
    """Outcome report for the Wayanad live ECMWF forecast pipeline execution."""
    status: str  # 'SUCCESS', 'SKIPPED_IDEMPOTENT', 'FAILED'
    pipeline_run_id: uuid.UUID
    source_snapshot_id: Optional[uuid.UUID]
    district: str
    lgd_code: int
    admin_id: int
    hazard_type: str
    forecast_cycle_anchor: datetime
    trigger_records_persisted: int
    snapshots_persisted: int
    valid_timestamps_count: int
    cells_processed_count: int
    horizon_hours_start: int
    horizon_hours_end: int
    error: Optional[str] = None


def compute_file_sha256(file_path: Path | str) -> str:
    """Computes SHA-256 hex digest of a file in streaming chunks."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _chunker(seq: Sequence[Any], size: int = 1000) -> Iterable[Sequence[Any]]:
    """Yield successive chunks of size from sequence."""
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def validate_b5_trigger_contract(
    b5_result: WayanadTriggerGenerationResult,
    expected_cell_count: int = EXPECTED_CELL_COUNT,
    expected_horizon_hours: int = FORECAST_HORIZON_HOURS,
) -> None:
    """Rigorous contract validation on Phase B5 output before database persistence.

    Validates:
        - B5 execution status is 'SUCCESS'
        - Cardinality == expected_cell_count * expected_horizon_hours
        - Horizon hours in 1..expected_horizon_hours
        - Every trigger_value is finite and in [0.0, 3.0]
        - Every valid_at is strictly greater than forecast_cycle_at
        - Hazard type matches 'flash_flood'
        - Source matches 'open_meteo_ecmwf'
    """
    if b5_result.status != "SUCCESS":
        raise ValueError(f"B5 trigger generation result status is '{b5_result.status}', expected 'SUCCESS'")

    if b5_result.authoritative_cell_count != expected_cell_count:
        raise ValueError(
            f"Authoritative cell count mismatch: {b5_result.authoritative_cell_count} != {expected_cell_count}"
        )

    if b5_result.valid_trigger_timestamps_count != expected_horizon_hours:
        raise ValueError(
            f"Valid trigger timestamps count mismatch: {b5_result.valid_trigger_timestamps_count} != {expected_horizon_hours}"
        )

    expected_total = expected_cell_count * expected_horizon_hours
    actual_total = len(b5_result.records)
    if actual_total != expected_total:
        raise ValueError(f"Total B5 records mismatch: expected {expected_total}, got {actual_total}")

    if b5_result.horizon_hours_start != 1 or b5_result.horizon_hours_end != expected_horizon_hours:
        raise ValueError(
            f"Horizon range invalid: [{b5_result.horizon_hours_start}, {b5_result.horizon_hours_end}], "
            f"expected [1, {expected_horizon_hours}]"
        )

    cycle_anchor = b5_result.forecast_cycle_anchor
    for idx, rec in enumerate(b5_result.records):
        if rec.hazard_type != HAZARD_TYPE:
            raise ValueError(f"Record {idx} invalid hazard_type: '{rec.hazard_type}', expected '{HAZARD_TYPE}'")

        if rec.source != SOURCE_ID:
            raise ValueError(f"Record {idx} invalid source: '{rec.source}', expected '{SOURCE_ID}'")

        t_val = rec.trigger_value
        if math.isnan(t_val) or math.isinf(t_val) or t_val < 0.0 or t_val > 3.0:
            raise ValueError(f"Record {idx} trigger_value out of bounds [0.0, 3.0]: {t_val}")

        if rec.forecast_cycle_at is None:
            raise ValueError(f"Record {idx} forecast_cycle_at is None")

        if rec.valid_at <= rec.forecast_cycle_at:
            raise ValueError(
                f"Record {idx} timestamp invariant violated: valid_at ({rec.valid_at}) <= "
                f"forecast_cycle_at ({rec.forecast_cycle_at})"
            )

        if rec.horizon_hours is None or rec.horizon_hours < 1 or rec.horizon_hours > expected_horizon_hours:
            raise ValueError(f"Record {idx} horizon_hours out of range [1, {expected_horizon_hours}]: {rec.horizon_hours}")


def run_open_meteo_wayanad_pipeline(
    db: Optional[Session | Engine | Connection] = None,
    raw_artifact_path: Optional[Path | str] = None,
    spatial_mapping: Optional[WayanadSpatialMappingResult] = None,
    cycle_anchor: Optional[datetime] = None,
    max_horizon_hours: int = FORECAST_HORIZON_HOURS,
    expected_cell_count: int = EXPECTED_CELL_COUNT,
    force_rerun: bool = False,
    raise_on_failure: bool = True,
) -> WayanadForecastPipelineResult:
    """Executes the complete Phase B6 Wayanad live forecast pipeline.

    Flow:
        1. Resolve database session & raw forecast artifact.
        2. Check idempotency: if artifact already ingested in a READY run and not force_rerun, skip.
        3. Execute Phase B5 canonical trigger generation (in-memory).
        4. Validate B5 output contracts and invariants.
        5. Stage 1: Register SourceSnapshot and PipelineRun (status='RUNNING').
        6. Stage 2: Bulk persist 259,344 trigger records into hazard_dynamic.
        7. Stage 3: Invoke authoritative compute_and_persist_dynamic_snapshots with explicit scoping:
           (aoi_lgd=555, pipeline_run_id=id, forecast_cycle_at=anchor, hazard_type='flash_flood').
        8. Stage 4: Verify snapshot counts and mark PipelineRun as 'READY'.
        9. Handle failure cleanly with transaction rollback and 'FAILED' audit status.
    """
    logger.info("Starting Phase B6 Wayanad live forecast pipeline...")

    # 1. Resolve raw artifact path
    if raw_artifact_path is None:
        repo_root = Path(__file__).resolve().parents[4]
        raw_artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH
    else:
        raw_artifact_path = Path(raw_artifact_path)

    if not raw_artifact_path.exists():
        raise FileNotFoundError(f"Raw forecast artifact not found: '{raw_artifact_path}'")

    sha256 = compute_file_sha256(raw_artifact_path)
    file_size = raw_artifact_path.stat().st_size
    now_utc = datetime.now(timezone.utc)

    # 2. Resolve database session / connection
    session_managed = False
    if db is None:
        engine = create_engine(settings.get_sqlalchemy_url(direct=True))
        session = Session(engine)
        session_managed = True
    elif isinstance(db, Session):
        session = db
    elif isinstance(db, Engine):
        session = Session(db)
        session_managed = True
    elif isinstance(db, Connection):
        session = Session(bind=db)
        session_managed = True
    else:
        raise ValueError(f"Unsupported db type: {type(db)}")

    try:
        # 3. Check Idempotency
        existing_run = session.execute(
            text("""
                SELECT r.id, r.status, r.config_version, s.id as snapshot_id
                FROM pipeline_run r
                JOIN source_snapshot s ON r.source_snapshot_id = s.id
                WHERE s.sha256 = :sha256 AND r.status IN ('READY', 'COMPLETED')
                ORDER BY r.started_at DESC LIMIT 1;
            """),
            {"sha256": sha256},
        ).mappings().first()

        if existing_run and not force_rerun:
            run_id = existing_run["id"]
            snap_id = existing_run["snapshot_id"]
            logger.info(f"Idempotency check passed: artifact already ingested in READY PipelineRun {run_id}. Skipping.")

            # Count existing records for auditable return
            hd_count = session.execute(
                text("SELECT count(*) FROM hazard_dynamic WHERE pipeline_run_id = :run_id;"),
                {"run_id": run_id},
            ).scalar() or 0

            mhi_count = session.execute(
                text("SELECT count(*) FROM mhi_snapshot WHERE pipeline_run_id = :run_id;"),
                {"run_id": run_id},
            ).scalar() or 0

            return WayanadForecastPipelineResult(
                status="SKIPPED_IDEMPOTENT",
                pipeline_run_id=run_id,
                source_snapshot_id=snap_id,
                district=DISTRICT_NAME,
                lgd_code=DISTRICT_LGD,
                admin_id=ADMIN_ID,
                hazard_type=HAZARD_TYPE,
                forecast_cycle_anchor=cycle_anchor or now_utc,
                trigger_records_persisted=hd_count,
                snapshots_persisted=mhi_count,
                valid_timestamps_count=max_horizon_hours,
                cells_processed_count=expected_cell_count,
                horizon_hours_start=1,
                horizon_hours_end=max_horizon_hours,
            )

        # 4. Generate Phase B5 Canonical Trigger Records
        logger.info("Executing Phase B5 canonical trigger generation...")
        b5_result = execute_wayanad_b5_trigger_generation(
            raw_artifact_path=raw_artifact_path,
            spatial_mapping=spatial_mapping,
            cycle_anchor=cycle_anchor,
            max_horizon_hours=max_horizon_hours,
            expected_cell_count=expected_cell_count,
        )

        # 5. Contract Validation
        validate_b5_trigger_contract(
            b5_result=b5_result,
            expected_cell_count=expected_cell_count,
            expected_horizon_hours=max_horizon_hours,
        )

        pipeline_run_id = uuid.uuid4()
        snapshot_id = uuid.uuid4()
        anchor_utc = b5_result.forecast_cycle_anchor

        logger.info(f"Registering PipelineRun {pipeline_run_id} and SourceSnapshot {snapshot_id}...")

        # 6. Record Source Snapshot
        metadata_json = json.dumps({
            "district": DISTRICT_NAME,
            "lgd_code": DISTRICT_LGD,
            "admin_id": ADMIN_ID,
            "hazard_type": HAZARD_TYPE,
            "forecast_cycle_anchor": anchor_utc.isoformat(),
            "authoritative_cells": b5_result.authoritative_cell_count,
            "horizon_hours": max_horizon_hours,
            "total_trigger_records": len(b5_result.records),
            "source_model": b5_result.source_model,
        })

        session.execute(
            text("""
                INSERT INTO source_snapshot (
                    id, source_id, retrieved_at, valid_at, uri, sha256, size_bytes, metadata
                ) VALUES (
                    :id, :source_id, :now, :valid_at, :uri, :sha256, :size_bytes, CAST(:metadata AS jsonb)
                );
            """),
            {
                "id": snapshot_id,
                "source_id": SOURCE_ID,
                "now": now_utc,
                "valid_at": anchor_utc,
                "uri": str(raw_artifact_path),
                "sha256": sha256,
                "size_bytes": file_size,
                "metadata": metadata_json,
            },
        )

        # 7. Record PipelineRun in RUNNING state
        session.execute(
            text("""
                INSERT INTO pipeline_run (
                    id, run_type, status, started_at,
                    code_version, config_version, model_version, source_snapshot_id
                ) VALUES (
                    :id, 'forecast_pipeline', 'RUNNING', :now,
                    :code_ver, :config_ver, :model_ver, :snapshot_id
                );
            """),
            {
                "id": pipeline_run_id,
                "now": now_utc,
                "code_ver": PIPELINE_CODE_VERSION,
                "config_ver": PIPELINE_CONFIG_VERSION,
                "model_ver": PIPELINE_MODEL_VERSION,
                "snapshot_id": snapshot_id,
            },
        )
        session.commit()

        # 8. Bulk Persist Forecast Triggers into hazard_dynamic
        logger.info(f"Persisting {len(b5_result.records)} forecast triggers into hazard_dynamic...")

        dynamic_rows = []
        for r in b5_result.records:
            dynamic_rows.append({
                "h3": r.h3_int,
                "hazard_type": r.hazard_type,
                "valid_at": r.valid_at,
                "ingested_at": now_utc,
                "forecast_cycle_at": r.forecast_cycle_at,
                "trigger_value": r.trigger_value,
                "source": r.source,
                "pipeline_run_id": pipeline_run_id,
            })

        insert_sql = text("""
            INSERT INTO hazard_dynamic (
                h3, hazard_type, valid_at, ingested_at, forecast_cycle_at, trigger_value, source, pipeline_run_id
            ) VALUES (
                :h3, :hazard_type, :valid_at, :ingested_at, :forecast_cycle_at, :trigger_value, :source, :pipeline_run_id
            );
        """)

        for chunk in _chunker(dynamic_rows, size=1000):
            session.execute(insert_sql, chunk)

        session.commit()
        logger.info(f"Successfully persisted {len(dynamic_rows)} triggers into hazard_dynamic.")

        # 9. Invoke Existing Dynamic Hazard Pipeline with Safe Run Scoping
        logger.info("Invoking authoritative dynamic hazard snapshot computation...")

        dynamic_res = compute_and_persist_dynamic_snapshots(
            db=session,
            aoi_lgd=DISTRICT_LGD,
            pipeline_run_id=pipeline_run_id,
            forecast_cycle_at=anchor_utc,
            hazard_type=HAZARD_TYPE,
        )

        if dynamic_res.status != "SUCCESS":
            raise RuntimeError(f"Dynamic hazard snapshot computation returned status '{dynamic_res.status}': {dynamic_res.error}")

        if dynamic_res.snapshots_persisted == 0:
            raise RuntimeError("Dynamic hazard snapshot computation persisted 0 snapshots")

        # 10. Mark PipelineRun as READY
        completed_at = datetime.now(timezone.utc)
        session.execute(
            text("""
                UPDATE pipeline_run
                SET status = 'READY', completed_at = :completed_at
                WHERE id = :run_id;
            """),
            {"run_id": pipeline_run_id, "completed_at": completed_at},
        )
        session.commit()

        logger.info(
            f"Successfully completed Phase B6 forecast pipeline run {pipeline_run_id}: "
            f"{len(dynamic_rows)} triggers persisted, {dynamic_res.snapshots_persisted} snapshots evaluated."
        )

        return WayanadForecastPipelineResult(
            status="SUCCESS",
            pipeline_run_id=pipeline_run_id,
            source_snapshot_id=snapshot_id,
            district=DISTRICT_NAME,
            lgd_code=DISTRICT_LGD,
            admin_id=ADMIN_ID,
            hazard_type=HAZARD_TYPE,
            forecast_cycle_anchor=anchor_utc,
            trigger_records_persisted=len(dynamic_rows),
            snapshots_persisted=dynamic_res.snapshots_persisted,
            valid_timestamps_count=len(dynamic_res.valid_timestamps),
            cells_processed_count=dynamic_res.h3_cells_processed,
            horizon_hours_start=1,
            horizon_hours_end=max_horizon_hours,
        )

    except Exception as e:
        session.rollback()
        logger.error(f"Phase B6 Wayanad forecast pipeline failed: {e}", exc_info=True)

        # Record failure status on pipeline_run if it was created
        try:
            if 'pipeline_run_id' in locals():
                session.execute(
                    text("""
                        UPDATE pipeline_run
                        SET status = 'FAILED', completed_at = :completed_at, error = :error
                        WHERE id = :run_id;
                    """),
                    {
                        "run_id": pipeline_run_id,
                        "completed_at": datetime.now(timezone.utc),
                        "error": str(e)[:500],
                    },
                )
                session.commit()
        except Exception as update_err:
            logger.error(f"Failed to record FAILED status on pipeline_run: {update_err}")

        if raise_on_failure:
            raise

        return WayanadForecastPipelineResult(
            status="FAILED",
            pipeline_run_id=locals().get("pipeline_run_id", uuid.uuid4()),
            source_snapshot_id=locals().get("snapshot_id"),
            district=DISTRICT_NAME,
            lgd_code=DISTRICT_LGD,
            admin_id=ADMIN_ID,
            hazard_type=HAZARD_TYPE,
            forecast_cycle_anchor=cycle_anchor or now_utc,
            trigger_records_persisted=0,
            snapshots_persisted=0,
            valid_timestamps_count=0,
            cells_processed_count=0,
            horizon_hours_start=1,
            horizon_hours_end=max_horizon_hours,
            error=str(e),
        )

    finally:
        if session_managed:
            session.close()
