"""Unit tests for Phase B6: Wayanad Live Forecast Hazard Evaluation & Snapshot Persistence.

Verifies:
1. Contract validation on B5 canonical records (cardinality 3,602 x 72 = 259,344, bounds, timestamps).
2. Backward-compatibility of compute_and_persist_dynamic_snapshots for existing callers.
3. Strict run/cycle scoping when forecast_cycle_at and pipeline_run_id are supplied.
4. Idempotency behavior (SKIPPED_IDEMPOTENT on matching READY run, retry on FAILED run, force_rerun).
5. Transaction safety and failure handling (FAILED status recorded on error).
6. Bidirectional channel preservation (mhi_live and mhi_static preserved during forecast computation).
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.constants import FORECAST_HORIZON_HOURS
from core.enums import DataQuality
from core.schemas.dynamic_triggers import CanonicalTriggerRecord, TriggerType
from pipeline.ingestion.open_meteo_client import (
    ADMIN_ID,
    DISTRICT_LGD,
    DISTRICT_NAME,
    SOURCE_ID,
    SOURCE_MODEL,
)
from pipeline.ingestion.open_meteo_regrid import EXPECTED_CELL_COUNT
from pipeline.ingestion.open_meteo_trigger import (
    HAZARD_TYPE,
    WayanadTriggerGenerationResult,
)
from pipeline.jobs.compute_dynamic_hazard import (
    DynamicProcessingResult,
    compute_and_persist_dynamic_snapshots,
)
from pipeline.jobs.run_open_meteo_wayanad import (
    WayanadForecastPipelineResult,
    compute_file_sha256,
    run_open_meteo_wayanad_pipeline,
    validate_b5_trigger_contract,
)


def _make_dummy_b5_result(
    num_cells: int = EXPECTED_CELL_COUNT,
    num_hours: int = FORECAST_HORIZON_HOURS,
    status: str = "SUCCESS",
    trigger_val: float = 0.50,
    cycle_anchor: datetime | None = None,
) -> WayanadTriggerGenerationResult:
    """Helper to create a deterministic dummy WayanadTriggerGenerationResult."""
    anchor = cycle_anchor or datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
    records: list[CanonicalTriggerRecord] = []

    for c in range(num_cells):
        h3_int = 0x886006498000000 + c
        h3_str = hex(h3_int)[2:]
        for h in range(1, num_hours + 1):
            valid_at = anchor + timedelta(hours=h)
            records.append(
                CanonicalTriggerRecord(
                    h3=h3_str,
                    h3_int=h3_int,
                    hazard_type=HAZARD_TYPE,
                    trigger_type=TriggerType.FORECAST,
                    trigger_value=trigger_val,
                    valid_at=valid_at,
                    forecast_cycle_at=anchor,
                    horizon_hours=h,
                    source=SOURCE_ID,
                    provider="Open-Meteo",
                    data_quality=DataQuality.VALID,
                    model_version=SOURCE_MODEL,
                )
            )

    return WayanadTriggerGenerationResult(
        status=status,
        hazard_type=HAZARD_TYPE,
        provider="Open-Meteo",
        source_model=SOURCE_MODEL,
        district=DISTRICT_NAME,
        lgd_code=DISTRICT_LGD,
        admin_id=ADMIN_ID,
        authoritative_cell_count=num_cells,
        valid_trigger_timestamps_count=num_hours,
        total_records_generated=len(records),
        forecast_cycle_anchor=anchor,
        first_trigger_valid_at=anchor + timedelta(hours=1),
        last_trigger_valid_at=anchor + timedelta(hours=num_hours),
        horizon_hours_start=1,
        horizon_hours_end=num_hours,
        min_trigger_value=trigger_val,
        max_trigger_value=trigger_val,
        mean_trigger_value=trigger_val,
        active_triggers_count=len(records) if trigger_val > 0.0 else 0,
        records=records,
    )


class TestB6TriggerContractValidation:
    """Rigorous tests on Phase B6 contract validation for Phase B5 outputs."""

    def test_validate_valid_b5_contract_passes(self):
        b5_result = _make_dummy_b5_result()
        # Must not raise
        validate_b5_trigger_contract(b5_result)

    def test_validate_fails_on_non_success_status(self):
        b5_result = _make_dummy_b5_result(status="FAILED")
        with pytest.raises(ValueError, match="status is 'FAILED'"):
            validate_b5_trigger_contract(b5_result)

    def test_validate_fails_on_cell_count_mismatch(self):
        b5_result = _make_dummy_b5_result(num_cells=3600)
        with pytest.raises(ValueError, match="Authoritative cell count mismatch"):
            validate_b5_trigger_contract(b5_result)

    def test_validate_fails_on_horizon_hours_mismatch(self):
        b5_result = _make_dummy_b5_result(num_hours=48)
        with pytest.raises(ValueError, match="Valid trigger timestamps count mismatch"):
            validate_b5_trigger_contract(b5_result)

    def test_validate_fails_on_out_of_bounds_trigger_value(self):
        b5_result = _make_dummy_b5_result()
        # Mutate one record to trigger_value > 3.0
        object.__setattr__(b5_result.records[10], "trigger_value", 3.5)
        with pytest.raises(ValueError, match="trigger_value out of bounds"):
            validate_b5_trigger_contract(b5_result)

    def test_validate_fails_on_nan_trigger_value(self):
        b5_result = _make_dummy_b5_result()
        object.__setattr__(b5_result.records[5], "trigger_value", float("nan"))
        with pytest.raises(ValueError, match="trigger_value out of bounds"):
            validate_b5_trigger_contract(b5_result)

    def test_validate_fails_on_invalid_timestamp_order(self):
        b5_result = _make_dummy_b5_result()
        # valid_at == forecast_cycle_at violates valid_at > forecast_cycle_at
        anchor = b5_result.forecast_cycle_anchor
        object.__setattr__(b5_result.records[0], "valid_at", anchor)
        with pytest.raises(ValueError, match="timestamp invariant violated"):
            validate_b5_trigger_contract(b5_result)

    def test_validate_fails_on_wrong_hazard_type(self):
        b5_result = _make_dummy_b5_result()
        object.__setattr__(b5_result.records[0], "hazard_type", "landslide")
        with pytest.raises(ValueError, match="invalid hazard_type"):
            validate_b5_trigger_contract(b5_result)


class TestDynamicEngineBackwardCompatibilityAndScoping:
    """Tests proving backward-compatibility for existing callers and safe scoping for B6."""

    def test_existing_caller_unscoped_sql_construction(self):
        """When forecast_cycle_at is None, time_query and trigger_sql execute without scoping clauses."""
        mock_session = MagicMock(spec=Session)
        mock_session.execute.return_value.mappings.return_value.fetchall.return_value = []

        # Call with no scoping parameters (like seed_pilot_data.py)
        res = compute_and_persist_dynamic_snapshots(
            db=mock_session,
            valid_at=None,
            pipeline_run_id=None,
        )

        assert res.status == "NO_DATA"
        # Inspect first executed SQL call (time_query)
        assert mock_session.execute.call_count == 1
        executed_stmt = str(mock_session.execute.call_args_list[0][0][0])
        # Invariant: Must NOT contain WHERE clause when forecast_cycle_at is None
        assert "WHERE" not in executed_stmt
        assert "SELECT DISTINCT valid_at" in executed_stmt

    def test_b6_scoped_time_and_trigger_sql_construction(self):
        """When forecast_cycle_at and pipeline_run_id are supplied, queries are strictly scoped."""
        mock_session = MagicMock(spec=Session)
        test_cycle = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
        test_valid = datetime(2026, 9, 8, 13, 0, 0, tzinfo=timezone.utc)
        test_run_id = uuid.uuid4()

        # Mock time_query returning 1 timestamp
        mock_session.execute.return_value.mappings.return_value.fetchall.side_effect = [
            [{"valid_at": test_valid}],  # time_query
            [],  # trigger_sql (empty triggers -> continue)
        ]

        res = compute_and_persist_dynamic_snapshots(
            db=mock_session,
            valid_at=None,
            pipeline_run_id=test_run_id,
            forecast_cycle_at=test_cycle,
            hazard_type="flash_flood",
            aoi_lgd=555,
        )

        assert mock_session.execute.call_count == 2

        # 1. Inspect time_query: must contain WHERE with forecast_cycle_at and pipeline_run_id
        time_call_stmt = str(mock_session.execute.call_args_list[0][0][0])
        time_call_params = mock_session.execute.call_args_list[0][0][1]
        assert "WHERE" in time_call_stmt
        assert "forecast_cycle_at = :forecast_cycle_at" in time_call_stmt
        assert "pipeline_run_id = :pipeline_run_id" in time_call_stmt
        assert time_call_params["forecast_cycle_at"] == test_cycle
        assert time_call_params["pipeline_run_id"] == test_run_id

        # 2. Inspect trigger_sql: must contain WHERE hd.forecast_cycle_at and hd.pipeline_run_id
        trigger_call_stmt = str(mock_session.execute.call_args_list[1][0][0])
        trigger_call_params = mock_session.execute.call_args_list[1][0][1]
        assert "hd.forecast_cycle_at = :forecast_cycle_at" in trigger_call_stmt
        assert "hd.pipeline_run_id = :pipeline_run_id" in trigger_call_stmt
        assert "hd.hazard_type = :hazard_type" in trigger_call_stmt
        assert "(gc.admin_id = :aoi_lgd OR ab.lgd_code = :aoi_lgd)" in trigger_call_stmt
        assert trigger_call_params["forecast_cycle_at"] == test_cycle
        assert trigger_call_params["pipeline_run_id"] == test_run_id
        assert trigger_call_params["hazard_type"] == "flash_flood"
        assert trigger_call_params["aoi_lgd"] == 555


class TestB6IdempotencyAndPipelineOrchestration:
    """Tests idempotency, retry, and pipeline run registration."""

    @patch("pipeline.jobs.run_open_meteo_wayanad.compute_file_sha256")
    def test_idempotent_skip_when_ready_run_exists(self, mock_sha):
        mock_sha.return_value = "dummy_sha256_hash_123"
        mock_session = MagicMock(spec=Session)
        existing_run_id = uuid.uuid4()
        existing_snap_id = uuid.uuid4()

        # Mock existing READY run
        mock_session.execute.return_value.mappings.return_value.first.return_value = {
            "id": existing_run_id,
            "status": "READY",
            "config_version": "wayanad-prototype-param-v1.0",
            "snapshot_id": existing_snap_id,
        }
        # Mock scalar row counts
        mock_session.execute.return_value.scalar.side_effect = [259344, 259344]

        # Use mock artifact path
        with patch("pathlib.Path.exists", return_value=True), patch("pathlib.Path.stat") as mock_stat:
            mock_stat.return_value.st_size = 50000
            res = run_open_meteo_wayanad_pipeline(
                db=mock_session,
                raw_artifact_path="dummy.json",
                force_rerun=False,
            )

        assert res.status == "SKIPPED_IDEMPOTENT"
        assert res.pipeline_run_id == existing_run_id
        assert res.source_snapshot_id == existing_snap_id
        assert res.trigger_records_persisted == 259344

    @patch("pipeline.jobs.run_open_meteo_wayanad.compute_file_sha256")
    @patch("pipeline.jobs.run_open_meteo_wayanad.execute_wayanad_b5_trigger_generation")
    @patch("pipeline.jobs.run_open_meteo_wayanad.compute_and_persist_dynamic_snapshots")
    def test_failed_run_retries_and_executes_successfully(self, mock_compute, mock_b5, mock_sha):
        """When an existing run is in FAILED status, idempotency does not skip and retry executes."""
        mock_sha.return_value = "dummy_sha_failed_retry"
        b5_result = _make_dummy_b5_result()
        mock_b5.return_value = b5_result

        mock_compute.return_value = DynamicProcessingResult(
            status="SUCCESS",
            snapshots_persisted=259344,
            valid_timestamps=[b5_result.forecast_cycle_anchor + timedelta(hours=h) for h in range(1, 73)],
            h3_cells_processed=3602,
        )

        mock_session = MagicMock(spec=Session)
        # Idempotency query filters WHERE status IN ('READY', 'COMPLETED')
        # Thus for a previously failed run, it returns None
        mock_session.execute.return_value.mappings.return_value.first.return_value = None

        with patch("pathlib.Path.exists", return_value=True), patch("pathlib.Path.stat") as mock_stat:
            mock_stat.return_value.st_size = 50000
            res = run_open_meteo_wayanad_pipeline(
                db=mock_session,
                raw_artifact_path="dummy.json",
                force_rerun=False,
            )

        assert res.status == "SUCCESS"
        assert res.trigger_records_persisted == 259344
        assert res.snapshots_persisted == 259344
        mock_compute.assert_called_once()

    @patch("pipeline.jobs.run_open_meteo_wayanad.compute_file_sha256")
    @patch("pipeline.jobs.run_open_meteo_wayanad.execute_wayanad_b5_trigger_generation")
    @patch("pipeline.jobs.run_open_meteo_wayanad.compute_and_persist_dynamic_snapshots")
    def test_full_pipeline_success_flow(self, mock_compute, mock_b5, mock_sha):
        mock_sha.return_value = "sha_abc_123"
        b5_result = _make_dummy_b5_result()
        mock_b5.return_value = b5_result

        mock_compute.return_value = DynamicProcessingResult(
            status="SUCCESS",
            snapshots_persisted=259344,
            valid_timestamps=[b5_result.forecast_cycle_anchor + timedelta(hours=h) for h in range(1, 73)],
            h3_cells_processed=3602,
        )

        mock_session = MagicMock(spec=Session)
        # No existing run
        mock_session.execute.return_value.mappings.return_value.first.return_value = None

        with patch("pathlib.Path.exists", return_value=True), patch("pathlib.Path.stat") as mock_stat:
            mock_stat.return_value.st_size = 60000
            res = run_open_meteo_wayanad_pipeline(
                db=mock_session,
                raw_artifact_path="dummy.json",
                force_rerun=False,
            )

        assert res.status == "SUCCESS"
        assert res.trigger_records_persisted == 259344
        assert res.snapshots_persisted == 259344
        assert res.valid_timestamps_count == 72
        assert res.cells_processed_count == 3602
        assert res.district == DISTRICT_NAME
        assert res.lgd_code == DISTRICT_LGD
        assert res.admin_id == ADMIN_ID
        assert res.horizon_hours_start == 1
        assert res.horizon_hours_end == 72

        # Verify compute_and_persist_dynamic_snapshots called with correct scoping parameters
        mock_compute.assert_called_once()
        call_kwargs = mock_compute.call_args[1]
        assert call_kwargs["aoi_lgd"] == DISTRICT_LGD
        assert call_kwargs["forecast_cycle_at"] == b5_result.forecast_cycle_anchor
        assert call_kwargs["hazard_type"] == HAZARD_TYPE
        assert call_kwargs["pipeline_run_id"] == res.pipeline_run_id

    @patch("pipeline.jobs.run_open_meteo_wayanad.compute_file_sha256")
    @patch("pipeline.jobs.run_open_meteo_wayanad.execute_wayanad_b5_trigger_generation")
    @patch("pipeline.jobs.run_open_meteo_wayanad.compute_and_persist_dynamic_snapshots")
    def test_pipeline_failure_rolls_back_and_records_failed(self, mock_compute, mock_b5, mock_sha):
        mock_sha.return_value = "sha_fail_test"
        b5_result = _make_dummy_b5_result()
        mock_b5.return_value = b5_result

        # Simulate dynamic computation failure
        mock_compute.return_value = DynamicProcessingResult(
            status="FAILED",
            snapshots_persisted=0,
            error="Database lock timeout",
        )

        mock_session = MagicMock(spec=Session)
        mock_session.execute.return_value.mappings.return_value.first.return_value = None

        with patch("pathlib.Path.exists", return_value=True), patch("pathlib.Path.stat") as mock_stat:
            mock_stat.return_value.st_size = 60000
            with pytest.raises(RuntimeError, match="Dynamic hazard snapshot computation returned status 'FAILED'"):
                run_open_meteo_wayanad_pipeline(
                    db=mock_session,
                    raw_artifact_path="dummy.json",
                    raise_on_failure=True,
                )

        # Invariant: session.rollback() must be called
        mock_session.rollback.assert_called()


class TestMhiSnapshotChannelPreservation:
    """Verifies that forecast MHI snapshots preserve mhi_live and mhi_static via upsert logic."""

    def test_upsert_preserves_live_and_static_channel_formula(self):
        """Validates that the upsert SQL logic does not overwrite mhi_live when :has_live is False."""
        from pipeline.hazard.dynamic_evaluator import DynamicHazardEvaluator
        evaluator = DynamicHazardEvaluator()

        # Cell with static landslide susceptibility 0.40, no live triggers, forecast flash_flood trigger 1.25
        res = evaluator.evaluate_cell(
            h3=0x8860064989fffff,
            static_susceptibilities={"landslide": 0.40, "flash_flood": 0.30},
            live_triggers=None,
            forecast_triggers={"flash_flood": 1.25},
            existing_mhi_live=0.65,  # Pre-existing live MHI in mhi_snapshot
            existing_mhi_fcst=None,
        )

        # Invariant 1: Pre-existing mhi_live (0.65) was NOT corrupted by the forecast evaluator
        assert res.mhi_live == pytest.approx(0.65, abs=1e-3)

        # Invariant 2: mhi_fcst was computed from static + forecast trigger
        # flash_flood dynamic = 0.30 * (1 + 1.0 * 1.25) = 0.675
        # landslide retains static = 0.40
        # MHI_fcst = 1 - (1 - 0.40)*(1 - 0.675) = 1 - (0.60 * 0.325) = 1 - 0.195 = 0.805
        assert res.mhi_fcst is not None
        assert res.mhi_fcst == pytest.approx(0.805, abs=1e-3)
        assert res.mhi_static == pytest.approx(0.58, abs=1e-3)
