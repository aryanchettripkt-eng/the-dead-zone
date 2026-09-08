"""Unit tests for SETU-DRR Phase B3: Rainfall & Spatial Mapping Validation Gate.

Validates:
1. Complete happy path validation using recorded B1 artifact and B2 spatial mapping.
2. Forecast horizon boundary testing (72 future hours PASS, 71 future hours FAIL, 83 future hours PASS).
3. Timestamp integrity (duplicate, non-monotonic, missing hour, 30-min gap, 2-hr gap, naïve vs aware).
4. Numeric precipitation validation (missing/null, negative, NaN, +Inf, -Inf, non-numeric strings/booleans).
5. Spatial mapping integrity (3,602 cells PASS, 3,601 cells FAIL, unmapped cells FAIL, invalid H3 index/resolution FAIL).
6. Scientific provenance tracking (provider, source model, native resolution, SHA256 integrity).
7. Explicit rainfall semantics contract (hourly accumulation in mm, NOT intensity, NOT running total).
8. Real B1 reference artifact regression test.
9. Offline execution with zero external network access.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from core.h3_utils import is_valid_h3
from pipeline.ingestion.open_meteo_client import (
    ADMIN_ID,
    DISTRICT_LGD,
    DISTRICT_NAME,
    NATIVE_RESOLUTION_KM,
    REFERENCE_ARTIFACT_REL_PATH,
    REFERENCE_ARTIFACT_SHA256,
    SOURCE_MODEL,
    WAYANAD_PROTOTYPE_SAMPLE_POINTS,
)
from pipeline.ingestion.open_meteo_regrid import (
    EXPECTED_CELL_COUNT,
    EXPECTED_SAMPLE_COUNT,
    H3CellSampleMapping,
    WayanadSpatialMappingResult,
    execute_wayanad_b2_spatial_mapping,
)
from pipeline.ingestion.open_meteo_validate import (
    DECISION_GEOMETRY,
    FORECAST_CYCLE_SEMANTICS,
    MIN_FUTURE_HOURS,
    RAINFALL_INTERPRETATION,
    RAINFALL_UNIT,
    PhaseB3ValidationReport,
    RainfallValidationError,
    validate_forecast_horizon,
    validate_forecast_timestamps,
    validate_precipitation_values,
    validate_provenance,
    validate_rainfall_semantics,
    validate_spatial_mapping,
    validate_wayanad_b3_forecast,
)


def _build_mock_payload(
    num_locations: int = 12,
    anchor: datetime = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
    future_hours: int = 72,
    past_hours: int = 12,
) -> list[dict[str, Any]]:
    """Builds a synthetic in-memory Open-Meteo multi-location response payload."""
    # total_hours includes past_hours (before anchor), anchor itself, and future_hours (after anchor)
    total_hours = past_hours + 1 + future_hours
    start_dt = anchor - timedelta(hours=past_hours)

    times = [(start_dt + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(total_hours)]
    # Deterministic positive precipitation values in mm
    precip = [round(0.15 * (i % 8), 2) for i in range(total_hours)]

    locations = []
    for loc_idx in range(num_locations):
        sample_coord = WAYANAD_PROTOTYPE_SAMPLE_POINTS[loc_idx] if loc_idx < len(WAYANAD_PROTOTYPE_SAMPLE_POINTS) else (11.5, 75.8)
        loc = {
            "latitude": sample_coord[0],
            "longitude": sample_coord[1],
            "elevation": 750.0,
            "timezone": "GMT",
            "utc_offset_seconds": 0,
            "hourly_units": {
                "time": "iso8601",
                "precipitation": "mm",
            },
            "hourly": {
                "time": list(times),
                "precipitation": list(precip),
            },
        }
        locations.append(loc)
    return locations


# =============================================================================
# 1. HAPPY PATH VALIDATION (MOCK & RECORDED ARTIFACT)
# =============================================================================

def test_happy_path_mock_forecast():
    """Verifies that a valid forecast payload with 72 future hours passes all checks."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    payload = _build_mock_payload(num_locations=12, anchor=anchor, future_hours=72, past_hours=12)

    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    # Execute with precomputed mapping from existing B2
    mapping_res = execute_wayanad_b2_spatial_mapping(raw_artifact_path=artifact_path)

    report = validate_wayanad_b3_forecast(
        raw_payload=payload,
        mapping_result=mapping_res,
        cycle_anchor=anchor,
        min_future_hours=72,
    )

    assert report.valid is True
    assert len(report.errors) == 0
    assert report.forecast_hours_available == 85
    assert report.future_hours_available == 72
    assert report.mapped_cells == 3602
    assert report.unmapped_cells == 0
    assert report.timestamps_strictly_increasing is True
    assert report.timestamps_hourly is True
    assert report.duplicate_timestamps == 0
    assert report.missing_timestamps == 0
    assert report.missing_precipitation_values == 0
    assert report.negative_precipitation_values == 0
    assert report.non_finite_values == 0
    assert report.non_numeric_values == 0
    assert report.rainfall_unit == "mm"
    assert report.forecast_cycle_semantics == "derived_provider_run_anchor"
    assert report.cycle_anchor_verified is False


def test_happy_path_real_b1_artifact():
    """Regression test: validates against the actual recorded Phase B1 artifact."""
    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    assert artifact_path.exists(), f"Reference artifact missing at {artifact_path}"
    raw_bytes = artifact_path.read_bytes()
    computed_sha = hashlib.sha256(raw_bytes).hexdigest()
    assert computed_sha == REFERENCE_ARTIFACT_SHA256

    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    report = validate_wayanad_b3_forecast(
        raw_artifact_path=artifact_path,
        cycle_anchor=anchor,
        min_future_hours=72,
    )

    assert report.valid is True
    assert len(report.errors) == 0
    assert report.provider == "Open-Meteo"
    assert report.source_model == "ECMWF_IFS_HRES"
    assert report.district == "Wayanad"
    assert report.lgd == 555
    assert report.admin_id == 178
    assert report.h3_resolution == 8
    assert report.expected_cells == 3602
    assert report.mapped_cells == 3602
    assert report.unmapped_cells == 0
    assert report.sample_points_present == 12
    assert report.forecast_hours_available == 96
    assert report.future_hours_available == 83  # 83 strictly after 12:00Z
    assert report.future_hours_available >= 72
    assert report.raw_artifact_sha256 == REFERENCE_ARTIFACT_SHA256


# =============================================================================
# 2. FORECAST HORIZON BOUNDARY TESTING
# =============================================================================

def test_forecast_horizon_exactly_72_hours():
    """Boundary test: exactly 72 future hours passes."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    # Start anchor at 12:00, 72 subsequent hourly steps starting at 13:00
    times = [anchor + timedelta(hours=i + 1) for i in range(72)]
    is_valid, errors, future_cnt = validate_forecast_horizon(times, anchor, min_future_hours=72)
    assert is_valid is True
    assert future_cnt == 72
    assert len(errors) == 0


def test_forecast_horizon_71_hours_fails():
    """Boundary test: 71 future hours fails with explicit diagnostic."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    times = [anchor + timedelta(hours=i + 1) for i in range(71)]  # Only 71 future!
    is_valid, errors, future_cnt = validate_forecast_horizon(times, anchor, min_future_hours=72)
    assert is_valid is False
    assert future_cnt == 71
    assert any("future_hours_available=71 required=72" in e for e in errors)


def test_forecast_horizon_extra_hours_accepted():
    """Boundary test: 83 or 96 future hours passes comfortably."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    times = [anchor + timedelta(hours=i + 1) for i in range(83)]
    is_valid, errors, future_cnt = validate_forecast_horizon(times, anchor, min_future_hours=72)
    assert is_valid is True
    assert future_cnt == 83
    assert len(errors) == 0


# =============================================================================
# 3. TEMPORAL INTEGRITY TESTING
# =============================================================================

def test_timestamp_duplicate_fails():
    """Fails if duplicate timestamps exist."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    times = [
        "2026-09-08T12:00",
        "2026-09-08T13:00",
        "2026-09-08T13:00",  # duplicate!
        "2026-09-08T14:00",
    ]
    coord = (11.5364, 75.8500)
    is_valid, errors, _, counts = validate_forecast_timestamps(times, coord, loc_idx=0)
    assert is_valid is False
    assert counts["duplicate_timestamps"] == 1
    assert any("duplicate timestamp detected" in e for e in errors)
    assert any("sample_point=(11.5364,75.8500)" in e for e in errors)


def test_timestamp_non_monotonic_fails():
    """Fails if timestamps go backwards in time."""
    times = [
        "2026-09-08T12:00",
        "2026-09-08T14:00",
        "2026-09-08T13:00",  # backward!
        "2026-09-08T15:00",
    ]
    coord = (11.5364, 75.8500)
    is_valid, errors, _, counts = validate_forecast_timestamps(times, coord, loc_idx=0)
    assert is_valid is False
    assert counts["strictly_increasing"] is False
    assert any("non-monotonic timestamp" in e for e in errors)


def test_timestamp_missing_hour_fails():
    """Fails if an hourly timestamp is omitted (2-hour gap)."""
    times = [
        "2026-09-08T12:00",
        "2026-09-08T13:00",
        # 14:00 missing!
        "2026-09-08T15:00",
        "2026-09-08T16:00",
    ]
    coord = (11.5364, 75.8500)
    is_valid, errors, _, counts = validate_forecast_timestamps(times, coord, loc_idx=0)
    assert is_valid is False
    assert counts["missing_timestamps"] == 1
    assert any("missing hourly timestamp (2h gap" in e for e in errors)


def test_timestamp_30_min_gap_fails():
    """Fails if timestamps have an unexpected interval (e.g. 30 minutes)."""
    times = [
        "2026-09-08T12:00",
        "2026-09-08T12:30",  # 30 min interval!
        "2026-09-08T13:00",
    ]
    coord = (11.5364, 75.8500)
    is_valid, errors, _, counts = validate_forecast_timestamps(times, coord, loc_idx=0)
    assert is_valid is False
    assert counts["hourly_spacing"] is False
    assert any("unexpected interval (1800.0s gap" in e for e in errors)


def test_timestamp_explicit_offset_normalized():
    """Normalizes explicit timezone offset (e.g. +05:30) to UTC."""
    times = [
        "2026-09-08T17:30:00+05:30",  # 12:00 UTC
        "2026-09-08T18:30:00+05:30",  # 13:00 UTC
    ]
    coord = (11.5364, 75.8500)
    is_valid, errors, parsed, _ = validate_forecast_timestamps(times, coord, loc_idx=0)
    assert is_valid is True
    assert len(parsed) == 2
    assert parsed[0] == datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    assert parsed[1] == datetime(2026, 9, 8, 13, 0, tzinfo=timezone.utc)


def test_timestamp_naive_rejected_when_explicit_tz_required():
    """Rejects naive timestamp if require_explicit_tz is enforced."""
    times = ["2026-09-08T12:00", "2026-09-08T13:00"]
    coord = (11.5364, 75.8500)
    is_valid, errors, _, _ = validate_forecast_timestamps(times, coord, loc_idx=0, default_tz=None)
    assert is_valid is False
    assert any("naive without timezone" in e for e in errors)


# =============================================================================
# 4. PRECIPITATION NUMERIC & INTEGRITY TESTING
# =============================================================================

def test_precipitation_null_missing_fails():
    """Fails if any precipitation value is null / None."""
    times = ["2026-09-08T12:00", "2026-09-08T13:00"]
    precip = [0.5, None]
    coord = (11.6091, 76.0500)
    is_valid, errors, stats = validate_precipitation_values(precip, times, coord, loc_idx=3)
    assert is_valid is False
    assert stats["missing_precipitation_values"] == 1
    assert any("sample_point=(11.6091,76.0500)" in e for e in errors)
    assert any("field=hourly.precipitation reason=missing value" in e for e in errors)


def test_precipitation_negative_fails():
    """Fails if precipitation contains negative values."""
    times = ["2026-09-08T12:00", "2026-09-08T13:00"]
    precip = [0.5, -0.1]
    coord = (11.6091, 76.0500)
    is_valid, errors, stats = validate_precipitation_values(precip, times, coord, loc_idx=3)
    assert is_valid is False
    assert stats["negative_precipitation_values"] == 1
    assert any("reason=negative precipitation -0.1" in e for e in errors)


def test_precipitation_nan_fails():
    """Fails if precipitation contains NaN."""
    times = ["2026-09-08T12:00"]
    precip = [float("nan")]
    coord = (11.6091, 76.0500)
    is_valid, errors, stats = validate_precipitation_values(precip, times, coord, loc_idx=3)
    assert is_valid is False
    assert stats["non_finite_values"] == 1
    assert any("reason=non-finite value nan" in e for e in errors)


def test_precipitation_infinity_fails():
    """Fails if precipitation contains +Inf or -Inf."""
    times = ["2026-09-08T12:00", "2026-09-08T13:00"]
    precip = [float("inf"), float("-inf")]
    coord = (11.6091, 76.0500)
    is_valid, errors, stats = validate_precipitation_values(precip, times, coord, loc_idx=3)
    assert is_valid is False
    assert stats["non_finite_values"] == 2
    assert any("reason=non-finite value inf" in e for e in errors)
    assert any("reason=non-finite value -inf" in e for e in errors)


def test_precipitation_non_numeric_string_fails():
    """Fails if precipitation is a non-numeric string (e.g. 'heavy')."""
    times = ["2026-09-08T12:00"]
    precip = ["heavy_rain"]
    coord = (11.6091, 76.0500)
    is_valid, errors, stats = validate_precipitation_values(precip, times, coord, loc_idx=3)
    assert is_valid is False
    assert stats["non_numeric_values"] == 1
    assert any("reason=non-numeric precipitation value 'heavy_rain'" in e for e in errors)


def test_precipitation_boolean_fails():
    """Fails if precipitation is a boolean (e.g. True/False)."""
    times = ["2026-09-08T12:00"]
    precip = [True]
    coord = (11.6091, 76.0500)
    is_valid, errors, stats = validate_precipitation_values(precip, times, coord, loc_idx=3)
    assert is_valid is False
    assert stats["non_numeric_values"] == 1
    assert any("reason=non-numeric precipitation value 'True'" in e for e in errors)


# =============================================================================
# 5. SPATIAL MAPPING INTEGRITY TESTING
# =============================================================================

def test_spatial_mapping_3601_cells_fails():
    """Fails if mapped cell count is 3,601 instead of authoritative 3,602."""
    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH
    real_mapping = execute_wayanad_b2_spatial_mapping(raw_artifact_path=artifact_path)

    # Simulate an under-coverage mapping by removing one cell
    truncated_mappings = real_mapping.mappings[:-1]
    truncated_by_h3 = {m.h3: m for m in truncated_mappings}

    bad_mapping = WayanadSpatialMappingResult(
        district=real_mapping.district,
        lgd_code=real_mapping.lgd_code,
        admin_id=real_mapping.admin_id,
        h3_resolution=real_mapping.h3_resolution,
        total_cells=3601,
        mapped_cells=3601,
        unmapped_cells=1,
        sample_points_count=real_mapping.sample_points_count,
        mappings=truncated_mappings,
        mappings_by_h3=truncated_by_h3,
        mappings_by_h3_str={m.h3_str: m for m in truncated_mappings},
        cell_counts_by_sample=real_mapping.cell_counts_by_sample,
        min_distance_km=real_mapping.min_distance_km,
        median_distance_km=real_mapping.median_distance_km,
        mean_distance_km=real_mapping.mean_distance_km,
        p90_distance_km=real_mapping.p90_distance_km,
        max_distance_km=real_mapping.max_distance_km,
        mapping_method=real_mapping.mapping_method,
    )

    is_valid, errors = validate_spatial_mapping(bad_mapping, expected_cell_count=3602)
    assert is_valid is False
    assert any("mapped_cells=3601 expected_cells=3602 unmapped_cells=1" in e for e in errors)


def test_spatial_mapping_unknown_sample_point_fails():
    """Fails if a cell mapping targets a sample index outside [0..11]."""
    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH
    real_mapping = execute_wayanad_b2_spatial_mapping(raw_artifact_path=artifact_path)

    # Mutate one cell to target sample_index=99
    corrupted_mappings = list(real_mapping.mappings)
    first_m = corrupted_mappings[0]
    corrupted_mappings[0] = H3CellSampleMapping(
        h3=first_m.h3,
        h3_str=first_m.h3_str,
        lat=first_m.lat,
        lon=first_m.lon,
        sample_index=99,  # invalid!
        sample_latitude=99.0,
        sample_longitude=99.0,
        distance_km=10.0,
    )

    bad_mapping = WayanadSpatialMappingResult(
        district=real_mapping.district,
        lgd_code=real_mapping.lgd_code,
        admin_id=real_mapping.admin_id,
        h3_resolution=real_mapping.h3_resolution,
        total_cells=real_mapping.total_cells,
        mapped_cells=real_mapping.mapped_cells,
        unmapped_cells=0,
        sample_points_count=real_mapping.sample_points_count,
        mappings=corrupted_mappings,
        mappings_by_h3={m.h3: m for m in corrupted_mappings},
        mappings_by_h3_str={m.h3_str: m for m in corrupted_mappings},
        cell_counts_by_sample=real_mapping.cell_counts_by_sample,
        min_distance_km=real_mapping.min_distance_km,
        median_distance_km=real_mapping.median_distance_km,
        mean_distance_km=real_mapping.mean_distance_km,
        p90_distance_km=real_mapping.p90_distance_km,
        max_distance_km=real_mapping.max_distance_km,
        mapping_method=real_mapping.mapping_method,
    )

    is_valid, errors = validate_spatial_mapping(bad_mapping, expected_cell_count=3602)
    assert is_valid is False
    assert any("mapped to unknown sample point index 99" in e for e in errors)


def test_spatial_mapping_incorrect_resolution_fails():
    """Fails if mapping resolution is not 8."""
    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH
    real_mapping = execute_wayanad_b2_spatial_mapping(raw_artifact_path=artifact_path)

    bad_mapping = WayanadSpatialMappingResult(
        district=real_mapping.district,
        lgd_code=real_mapping.lgd_code,
        admin_id=real_mapping.admin_id,
        h3_resolution=7,  # invalid resolution!
        total_cells=real_mapping.total_cells,
        mapped_cells=real_mapping.mapped_cells,
        unmapped_cells=0,
        sample_points_count=real_mapping.sample_points_count,
        mappings=real_mapping.mappings,
        mappings_by_h3=real_mapping.mappings_by_h3,
        mappings_by_h3_str=real_mapping.mappings_by_h3_str,
        cell_counts_by_sample=real_mapping.cell_counts_by_sample,
        min_distance_km=real_mapping.min_distance_km,
        median_distance_km=real_mapping.median_distance_km,
        mean_distance_km=real_mapping.mean_distance_km,
        p90_distance_km=real_mapping.p90_distance_km,
        max_distance_km=real_mapping.max_distance_km,
        mapping_method=real_mapping.mapping_method,
    )

    is_valid, errors = validate_spatial_mapping(bad_mapping, target_res=8)
    assert is_valid is False
    assert any("h3_resolution=7 expected=8" in e for e in errors)


# =============================================================================
# 6. PROVENANCE INTEGRITY TESTING
# =============================================================================

def test_provenance_wrong_model_fails():
    """Fails if source_model is not ECMWF_IFS_HRES."""
    prov = {
        "provider": "Open-Meteo",
        "source_model": "GFS_CONUS",  # wrong!
        "native_resolution_km": 9.0,
        "district": "Wayanad",
        "lgd_code": 555,
        "raw_artifact_sha256": "a" * 64,
    }
    is_valid, errors = validate_provenance(prov)
    assert is_valid is False
    assert any("source_model='GFS_CONUS' expected 'ECMWF_IFS_HRES'" in e for e in errors)


def test_provenance_corrupted_sha256_fails():
    """Fails if computed SHA256 of raw bytes disagrees with recorded hash."""
    prov = {
        "provider": "Open-Meteo",
        "source_model": "ECMWF_IFS_HRES",
        "native_resolution_km": 9.0,
        "district": "Wayanad",
        "lgd_code": 555,
        "raw_artifact_sha256": "0" * 64,  # bad sha!
    }
    raw_bytes = b"[{\"valid\": true}]"
    is_valid, errors = validate_provenance(prov, raw_bytes=raw_bytes)
    assert is_valid is False
    assert any("raw artifact SHA256 mismatch" in e for e in errors)


def test_provenance_cycle_semantics_must_be_derived():
    """Fails if cycle_anchor_verified is claimed True without proof."""
    prov = {
        "provider": "Open-Meteo",
        "source_model": "ECMWF_IFS_HRES",
        "native_resolution_km": 9.0,
        "district": "Wayanad",
        "lgd_code": 555,
        "raw_artifact_sha256": "a" * 64,
        "cycle_anchor_verified": True,  # illegitimate upgrade!
    }
    is_valid, errors = validate_provenance(prov)
    assert is_valid is False
    assert any("cycle_anchor_verified must be False" in e for e in errors)


# =============================================================================
# 7. RAINFALL SEMANTICS CONTRACT
# =============================================================================

def test_rainfall_semantics_explicit_contract():
    """Verifies that rainfall semantics is explicitly affirmed as hourly accumulation in mm."""
    assert RAINFALL_UNIT == "mm"
    assert "hourly precipitation accumulation in millimetres" in RAINFALL_INTERPRETATION
    assert "instantaneous rainfall intensity" in RAINFALL_INTERPRETATION
    assert "cumulative running total" in RAINFALL_INTERPRETATION

    # Test validator checking hourly_units
    bad_units = {"time": "iso8601", "precipitation": "inch"}
    errors = validate_rainfall_semantics(bad_units, (11.5, 75.8), 0)
    assert any("expected precipitation unit 'mm', got 'inch'" in e for e in errors)


# =============================================================================
# 8. RAISE ON FAILURE BEHAVIOR
# =============================================================================

def test_raise_on_failure_raises_rainfall_validation_error():
    """Verifies that raise_on_failure=True raises RainfallValidationError with diagnostic."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    # Payload with only 1 location instead of 12
    bad_payload = _build_mock_payload(num_locations=1, anchor=anchor, future_hours=72)

    with pytest.raises(RainfallValidationError) as excinfo:
        validate_wayanad_b3_forecast(
            raw_payload=bad_payload,
            cycle_anchor=anchor,
            raise_on_failure=True,
        )

    assert "Phase B3 Rainfall Validation failed" in str(excinfo.value)
    assert "location count mismatch" in str(excinfo.value)
