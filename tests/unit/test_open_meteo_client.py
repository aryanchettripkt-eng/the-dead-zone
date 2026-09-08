"""Unit tests for Open-Meteo ECMWF Ingestion Client (Phase B1).

Validates:
1. Successful ingestion lifecycle and contract compliance.
2. Raw-first persistence invariant (bytes written to disk before deserialization).
3. Payload validation rules (JSON validity, missing fields, length mismatch, negative/non-finite precipitation).
4. Temporal ordering and uniqueness of hourly timestamps.
5. Minimum future hourly coverage requirement (>= 72 future hours).
6. Scientific provenance and cycle semantics (derived_provider_run_anchor, cycle_anchor_verified=False).
7. SHA256 checksum calculation strictly from raw persisted bytes.
8. HTTP failures and network timeouts producing explicit failed runs.
9. Offline / DEMO_MODE execution with zero network access.
10. Idempotency on identical artifact digests.
11. Strict downstream isolation (zero writes to hazard_dynamic or mhi_snapshot).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from pipeline.ingestion.open_meteo_client import (
    OPEN_METEO_ECMWF_ENDPOINT,
    SOURCE_ID,
    SOURCE_MODEL,
    WAYANAD_PROTOTYPE_SAMPLE_POINTS,
    REFERENCE_ARTIFACT_REL_PATH,
    REFERENCE_ARTIFACT_SHA256,
    PhaseB1IngestionReport,
    derive_provider_run_anchor,
    validate_open_meteo_payload,
    fetch_open_meteo_ecmwf_wayanad,
)


@pytest.fixture
def sqlite_test_engine() -> Engine:
    """In-memory SQLite engine with minimal source_snapshot and pipeline_run tables."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
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
                    error TEXT,
                    FOREIGN KEY(source_snapshot_id) REFERENCES source_snapshot(id)
                );
            """)
        )
    return engine


def _generate_valid_mock_payload(
    num_locations: int = 12,
    anchor: datetime = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
    total_hours: int = 96,
) -> bytes:
    """Generates a valid Open-Meteo ECMWF multi-coordinate JSON response."""
    start_dt = anchor - timedelta(hours=12)
    times = [(start_dt + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(total_hours)]
    # precipitation in mm (varied, positive, deterministic)
    precip = [round(0.1 * (i % 10), 2) for i in range(total_hours)]

    locations = []
    for loc_id in range(num_locations):
        loc = {
            "latitude": 11.5 + (loc_id * 0.03),
            "longitude": 75.8 + (loc_id * 0.03),
            "generationtime_ms": 0.5,
            "utc_offset_seconds": 0,
            "timezone": "UTC",
            "timezone_abbreviation": "UTC",
            "elevation": 700.0,
            "location_id": loc_id,
            "hourly_units": {"time": "iso8601", "precipitation": "mm"},
            "hourly": {
                "time": list(times),
                "precipitation": list(precip),
            },
        }
        locations.append(loc)

    return json.dumps(locations).encode("utf-8")


# =============================================================================
# 1. SUCCESSFUL INGESTION CONTRACT
# =============================================================================

def test_successful_ingestion_lifecycle(tmp_path: Path, sqlite_test_engine: Engine):
    """Verifies complete B1 lifecycle with valid mocked provider payload."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    mock_bytes = _generate_valid_mock_payload(num_locations=12, anchor=anchor, total_hours=96)
    expected_sha = hashlib.sha256(mock_bytes).hexdigest()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(OPEN_METEO_ECMWF_ENDPOINT)
        return httpx.Response(200, content=mock_bytes)

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)

    report = fetch_open_meteo_ecmwf_wayanad(
        sample_points=WAYANAD_PROTOTYPE_SAMPLE_POINTS,
        db_engine=sqlite_test_engine,
        raw_output_dir=tmp_path,
        demo_mode=False,
        http_client=client,
    )

    assert report.status == "SUCCESS"
    assert report.http_status_code == 200
    assert report.source_snapshot_id is not None
    assert report.pipeline_run_id is not None
    assert report.sha256 == expected_sha
    assert report.size_bytes == len(mock_bytes)
    assert report.sample_points_count == 12
    assert report.total_hourly_steps_per_point == 96
    assert report.future_hourly_steps_available >= 72
    assert report.cycle_anchor_verified is False
    assert len(report.errors) == 0

    # Verify raw file exists on disk and matches exact bytes
    raw_file = Path(report.raw_artifact_path)
    assert raw_file.exists()
    assert raw_file.read_bytes() == mock_bytes

    # Verify source_snapshot record in DB
    with sqlite_test_engine.connect() as conn:
        snap = conn.execute(
            text("SELECT * FROM source_snapshot WHERE id = :id"),
            {"id": str(report.source_snapshot_id)},
        ).mappings().first()
        assert snap is not None
        assert snap["source_id"] == SOURCE_ID
        assert snap["sha256"] == expected_sha
        assert snap["size_bytes"] == len(mock_bytes)

        metadata = json.loads(snap["metadata"])
        assert metadata["provider"] == "Open-Meteo"
        assert metadata["source_model"] == SOURCE_MODEL
        assert metadata["native_resolution_km"] == 9.0
        assert metadata["district"] == "Wayanad"
        assert metadata["lgd_code"] == 555
        assert metadata["forecast_cycle_semantics"] == "derived_provider_run_anchor"
        assert metadata["cycle_anchor_verified"] is False

        # Verify pipeline_run record in DB
        run = conn.execute(
            text("SELECT * FROM pipeline_run WHERE id = :id"),
            {"id": str(report.pipeline_run_id)},
        ).mappings().first()
        assert run is not None
        assert run["status"] == "READY"
        assert run["run_type"] == "forecast_ingest"
        assert run["code_version"] == "phase-b1"
        assert run["model_version"] == SOURCE_MODEL
        assert run["source_snapshot_id"] == str(report.source_snapshot_id)
        assert run["error"] is None


# =============================================================================
# 2. RAW-FIRST PERSISTENCE INVARIANT
# =============================================================================

def test_raw_first_persistence_even_when_validation_fails(tmp_path: Path, sqlite_test_engine: Engine):
    """Proves that raw bytes are written to disk and SHA256 computed BEFORE validation."""
    malformed_json = b"[{'bad_json': true}]"  # Invalid JSON syntax
    expected_sha = hashlib.sha256(malformed_json).hexdigest()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=malformed_json)

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))

    report = fetch_open_meteo_ecmwf_wayanad(
        sample_points=WAYANAD_PROTOTYPE_SAMPLE_POINTS,
        db_engine=sqlite_test_engine,
        raw_output_dir=tmp_path,
        demo_mode=False,
        http_client=client,
    )

    # Ingestion must fail validation
    assert report.status == "FAILED"
    assert len(report.errors) > 0

    # But raw file MUST have been written to disk first!
    raw_file = Path(report.raw_artifact_path)
    assert raw_file.exists()
    assert raw_file.read_bytes() == malformed_json
    assert report.sha256 == expected_sha

    # And pipeline_run must record FAILED status honestly
    with sqlite_test_engine.connect() as conn:
        run = conn.execute(
            text("SELECT * FROM pipeline_run WHERE id = :id"),
            {"id": str(report.pipeline_run_id)},
        ).mappings().first()
        assert run is not None
        assert run["status"] == "FAILED"
        assert "JSON deserialization failed" in run["error"]


# =============================================================================
# 3. PAYLOAD VALIDATION CHECKS
# =============================================================================

def test_validation_missing_hourly():
    """Fails if 'hourly' dictionary is absent."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    payload = json.dumps([{"latitude": 11.5, "longitude": 75.8}]).encode("utf-8")
    is_valid, errors, _ = validate_open_meteo_payload(payload, anchor, expected_sample_count=1)
    assert not is_valid
    assert any("missing 'hourly'" in e for e in errors)


def test_validation_length_mismatch():
    """Fails if len(time) != len(precipitation)."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    times = [(anchor + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(80)]
    precip = [0.1] * 70  # mismatch!
    payload = json.dumps([{"hourly": {"time": times, "precipitation": precip}}]).encode("utf-8")
    is_valid, errors, _ = validate_open_meteo_payload(payload, anchor, expected_sample_count=1)
    assert not is_valid
    assert any("length mismatch" in e for e in errors)


def test_validation_negative_precipitation():
    """Fails if precipitation contains negative values."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    times = [(anchor + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(80)]
    precip = [0.5] * 79 + [-1.2]  # negative!
    payload = json.dumps([{"hourly": {"time": times, "precipitation": precip}}]).encode("utf-8")
    is_valid, errors, _ = validate_open_meteo_payload(payload, anchor, expected_sample_count=1)
    assert not is_valid
    assert any("negative precipitation" in e for e in errors)


def test_validation_non_monotonic_timestamps():
    """Fails if timestamps are not strictly increasing."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    times = [
        "2026-09-08T12:00",
        "2026-09-08T14:00",
        "2026-09-08T13:00",  # went backwards!
    ] + [(anchor + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(3, 80)]
    precip = [0.0] * len(times)
    payload = json.dumps([{"hourly": {"time": times, "precipitation": precip}}]).encode("utf-8")
    is_valid, errors, _ = validate_open_meteo_payload(payload, anchor, expected_sample_count=1)
    assert not is_valid
    assert any("non-monotonic timestamp" in e for e in errors)


def test_validation_duplicate_timestamps():
    """Fails if duplicate timestamps exist."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    times = [
        "2026-09-08T12:00",
        "2026-09-08T13:00",
        "2026-09-08T13:00",  # duplicate!
    ] + [(anchor + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(3, 80)]
    precip = [0.0] * len(times)
    payload = json.dumps([{"hourly": {"time": times, "precipitation": precip}}]).encode("utf-8")
    is_valid, errors, _ = validate_open_meteo_payload(payload, anchor, expected_sample_count=1)
    assert not is_valid
    assert any("duplicate timestamp" in e for e in errors)


def test_validation_insufficient_future_coverage():
    """Fails if fewer than 72 future hours exist after cycle anchor."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    # Only 50 hours after anchor
    times = [(anchor + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(1, 51)]
    precip = [0.0] * 50
    payload = json.dumps([{"hourly": {"time": times, "precipitation": precip}}]).encode("utf-8")
    is_valid, errors, _ = validate_open_meteo_payload(payload, anchor, expected_sample_count=1, min_future_hours=72)
    assert not is_valid
    assert any("Insufficient future hourly values" in e for e in errors)


# =============================================================================
# 4. CANONICAL REFERENCE ARTIFACT VERIFICATION
# =============================================================================

def test_canonical_reference_artifact_checksum():
    """Verifies that the reference artifact ecmwf_wayanad_20260908T120000Z.json matches exact expected SHA256."""
    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    assert artifact_path.exists(), f"Reference artifact missing at {artifact_path}"
    raw_bytes = artifact_path.read_bytes()
    computed_sha = hashlib.sha256(raw_bytes).hexdigest()

    assert computed_sha == REFERENCE_ARTIFACT_SHA256, (
        f"Checksum mismatch: expected {REFERENCE_ARTIFACT_SHA256}, got {computed_sha}"
    )
    assert len(raw_bytes) == 30921, f"Expected 30921 bytes, got {len(raw_bytes)}"


# =============================================================================
# 5. OFFLINE / DEMO MODE INTEGRATION
# =============================================================================

def test_demo_mode_offline_execution(tmp_path: Path, sqlite_test_engine: Engine):
    """Verifies DEMO_MODE runs with zero live network calls from the recorded artifact."""
    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    # Execute in DEMO_MODE
    report = fetch_open_meteo_ecmwf_wayanad(
        sample_points=WAYANAD_PROTOTYPE_SAMPLE_POINTS,
        db_engine=sqlite_test_engine,
        raw_output_dir=tmp_path,
        demo_mode=True,
        recorded_artifact_path=artifact_path,
    )

    assert report.status == "SUCCESS"
    assert report.http_status_code == 200
    assert report.sha256 == REFERENCE_ARTIFACT_SHA256
    assert report.size_bytes == 30921
    assert report.sample_points_count == 12
    assert report.total_hourly_steps_per_point == 96
    assert report.cycle_anchor_verified is False


# =============================================================================
# 6. IDEMPOTENCY HANDLING
# =============================================================================

def test_idempotency_prevents_duplicate_runs(tmp_path: Path, sqlite_test_engine: Engine):
    """Repeated execution with identical artifact returns SKIPPED_IDEMPOTENT."""
    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    # First run
    report1 = fetch_open_meteo_ecmwf_wayanad(
        sample_points=WAYANAD_PROTOTYPE_SAMPLE_POINTS,
        db_engine=sqlite_test_engine,
        raw_output_dir=tmp_path,
        demo_mode=True,
        recorded_artifact_path=artifact_path,
    )
    assert report1.status == "SUCCESS"

    # Second run (same DB, force=False)
    report2 = fetch_open_meteo_ecmwf_wayanad(
        sample_points=WAYANAD_PROTOTYPE_SAMPLE_POINTS,
        db_engine=sqlite_test_engine,
        raw_output_dir=tmp_path,
        demo_mode=True,
        recorded_artifact_path=artifact_path,
        force=False,
    )
    assert report2.status == "SKIPPED_IDEMPOTENT"
    assert report2.source_snapshot_id == report1.source_snapshot_id
    assert report2.pipeline_run_id == report1.pipeline_run_id

    # Verify no duplicate pipeline_run rows created
    with sqlite_test_engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM pipeline_run")).scalar()
        assert count == 1


# =============================================================================
# 7. HTTP FAILURES AND TIMEOUTS
# =============================================================================

def test_http_failure_500(tmp_path: Path, sqlite_test_engine: Engine):
    """HTTP 500 server error produces explicit failed report and failed pipeline_run."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))

    report = fetch_open_meteo_ecmwf_wayanad(
        sample_points=WAYANAD_PROTOTYPE_SAMPLE_POINTS,
        db_engine=sqlite_test_engine,
        raw_output_dir=tmp_path,
        demo_mode=False,
        http_client=client,
    )

    assert report.status == "FAILED"
    assert report.http_status_code == 500
    assert any("HTTP 500" in e for e in report.errors)

    with sqlite_test_engine.connect() as conn:
        run = conn.execute(
            text("SELECT * FROM pipeline_run WHERE id = :id"),
            {"id": str(report.pipeline_run_id)},
        ).mappings().first()
        assert run is not None
        assert run["status"] == "FAILED"


def test_http_network_timeout(tmp_path: Path, sqlite_test_engine: Engine):
    """Network timeout produces explicit failed report and failed pipeline_run."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("Connection timed out")

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))

    report = fetch_open_meteo_ecmwf_wayanad(
        sample_points=WAYANAD_PROTOTYPE_SAMPLE_POINTS,
        db_engine=sqlite_test_engine,
        raw_output_dir=tmp_path,
        demo_mode=False,
        http_client=client,
    )

    assert report.status == "FAILED"
    assert report.http_status_code == 0
    assert any("Connection timed out" in e for e in report.errors)


# =============================================================================
# 8. DOWNSTREAM ISOLATION (ZERO HAZARD WRITES)
# =============================================================================

def test_b1_zero_hazard_dynamic_writes(tmp_path: Path, sqlite_test_engine: Engine):
    """Ensures B1 strictly never attempts writes to hazard_dynamic or mhi_snapshot."""
    with sqlite_test_engine.begin() as conn:
        conn.execute(text("CREATE TABLE hazard_dynamic (id INTEGER PRIMARY KEY, trigger_value REAL);"))
        conn.execute(text("CREATE TABLE mhi_snapshot (id INTEGER PRIMARY KEY, mhi_fcst REAL);"))

    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    report = fetch_open_meteo_ecmwf_wayanad(
        sample_points=WAYANAD_PROTOTYPE_SAMPLE_POINTS,
        db_engine=sqlite_test_engine,
        raw_output_dir=tmp_path,
        demo_mode=True,
        recorded_artifact_path=artifact_path,
    )

    assert report.status == "SUCCESS"

    with sqlite_test_engine.connect() as conn:
        dynamic_count = conn.execute(text("SELECT count(*) FROM hazard_dynamic")).scalar()
        mhi_count = conn.execute(text("SELECT count(*) FROM mhi_snapshot")).scalar()
        assert dynamic_count == 0, "hazard_dynamic must have ZERO writes in Phase B1!"
        assert mhi_count == 0, "mhi_snapshot must have ZERO writes in Phase B1!"
