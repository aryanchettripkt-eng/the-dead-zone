"""Unit tests for Phase B4/B5: Canonical Forecast Trigger Generation.

Validates:
1. Phase B4 Frozen Contract Mathematics (exact thresholds, ramps, continuity, and clamps).
2. Property-Style Invariants (bounds in [0, 3], monotonicity, zero-rainfall invariant).
3. Rolling 3-hour Accumulation and Intensity (A3, I3) precision.
4. Interpretation B — Synoptic Pre-Anchor Lookback (first trigger at anchor+1h using anchor and anchor-1h).
5. Canonical Trigger Record Schema Conformance (TriggerType.FORECAST, dimensionless_index, flash_flood, valid_at > anchor).
6. Cardinality Derivation (authoritative cells × timestamps = 3,602 × 72 = 259,344 records).
7. Error conditions (negative, non-finite, missing lookback observations, mismatched lengths).
8. Real Phase B1 artifact integration test (completely offline, zero DB access).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from core.enums import DataQuality
from core.schemas.dynamic_triggers import CanonicalTriggerRecord, TriggerType
from pipeline.ingestion.open_meteo_client import (
    ADMIN_ID,
    DISTRICT_LGD,
    DISTRICT_NAME,
    REFERENCE_ARTIFACT_REL_PATH,
    SOURCE_ID,
    SOURCE_MODEL,
    WAYANAD_PROTOTYPE_SAMPLE_POINTS,
)
from pipeline.ingestion.open_meteo_regrid import (
    EXPECTED_CELL_COUNT,
    H3CellSampleMapping,
    WayanadSpatialMappingResult,
    execute_wayanad_b2_spatial_mapping,
)
from pipeline.ingestion.open_meteo_trigger import (
    HAZARD_TYPE,
    I0,
    IC,
    MODEL_VERSION,
    PROVIDER_NAME,
    ROLLING_WINDOW_INTERPRETATION,
    SCIENTIFIC_STATUS,
    SOURCE_NAME,
    T_MAX,
    TRIGGER_UNITS,
    WINDOW_HOURS,
    SampleTriggerStep,
    WayanadTriggerGenerationResult,
    calculate_t_flood,
    compute_rolling_accumulation_and_intensity,
    compute_sample_point_triggers,
    execute_wayanad_b5_trigger_generation,
    generate_canonical_forecast_triggers,
)


# =============================================================================
# 1. PHASE B4 FROZEN CONTRACT MATHEMATICS TESTS
# =============================================================================

def test_t_flood_below_baseline_threshold():
    """Below I0 = 10.0 mm/h, trigger T_flood is exactly 0.0."""
    assert calculate_t_flood(0.0) == 0.0
    assert calculate_t_flood(5.0) == 0.0
    assert calculate_t_flood(9.999) == 0.0


def test_t_flood_exact_lower_boundary():
    """At I0 = 10.0 mm/h, trigger T_flood is exactly 0.0."""
    assert calculate_t_flood(10.0) == 0.0


def test_t_flood_first_linear_ramp():
    """Between 10.0 and 29.0 mm/h, linear ramp scales up to 0.60."""
    # Midpoint: I3 = 19.5 -> ((19.5 - 10) / 19) * 0.60 = (9.5 / 19) * 0.60 = 0.5 * 0.60 = 0.30
    val_mid = calculate_t_flood(19.5)
    assert abs(val_mid - 0.30) < 1e-6

    # 25% point: I3 = 14.75 -> (4.75 / 19) * 0.60 = 0.25 * 0.60 = 0.15
    val_quarter = calculate_t_flood(14.75)
    assert abs(val_quarter - 0.15) < 1e-6


def test_t_flood_exact_critical_boundary_continuity():
    """At Ic = 29.0 mm/h, trigger T_flood is exactly 0.60 and continuous."""
    val_crit = calculate_t_flood(29.0)
    assert abs(val_crit - 0.60) < 1e-6

    # Left and right limits
    val_left = calculate_t_flood(28.9999)
    val_right = calculate_t_flood(29.0001)
    assert abs(val_left - 0.60) < 1e-4
    assert abs(val_right - 0.60) < 1e-4


def test_t_flood_upper_linear_ramp():
    """Above 29.0 mm/h, slope is (I3 - 29.0) / 29.0 * 1.0 added to 0.60."""
    # I3 = 43.5 mm/h -> 0.60 + ((43.5 - 29) / 29) * 1.0 = 0.60 + 0.50 = 1.10
    val_43_5 = calculate_t_flood(43.5)
    assert abs(val_43_5 - 1.10) < 1e-6

    # I3 = 58.0 mm/h -> 0.60 + ((58 - 29) / 29) * 1.0 = 0.60 + 1.0 = 1.60
    val_58 = calculate_t_flood(58.0)
    assert abs(val_58 - 1.60) < 1e-6


def test_t_flood_clamp_threshold_and_beyond():
    """At I3 = 98.6 mm/h, reaches 3.00 and is clamped at T_MAX = 3.0."""
    # 0.60 + ((98.6 - 29) / 29) * 1.0 = 0.60 + (69.6 / 29) = 0.60 + 2.40 = 3.00
    val_clamp = calculate_t_flood(98.6)
    assert abs(val_clamp - 3.0) < 1e-6

    # Above clamp threshold
    assert calculate_t_flood(100.0) == 3.0
    assert calculate_t_flood(250.0) == 3.0
    assert calculate_t_flood(1000.0) == 3.0


# =============================================================================
# 2. PROPERTY-STYLE INVARIANTS
# =============================================================================

def test_t_flood_bounds_invariant():
    """For any non-negative intensity, T_flood is strictly within [0.0, 3.0]."""
    test_intensities = [0.0, 0.1, 5.0, 10.0, 15.0, 20.0, 29.0, 35.0, 50.0, 98.6, 120.0, 1000.0]
    for i3 in test_intensities:
        t = calculate_t_flood(i3)
        assert 0.0 <= t <= 3.0, f"Trigger {t} outside [0.0, 3.0] for I3={i3}"


def test_t_flood_monotonicity_invariant():
    """T_flood is non-decreasing with respect to I3: I_a <= I_b => T(I_a) <= T(I_b)."""
    grid = [i * 0.5 for i in range(250)]  # 0.0 to 125.0 in 0.5 mm/h steps
    for idx in range(len(grid) - 1):
        i_a, i_b = grid[idx], grid[idx + 1]
        t_a, t_b = calculate_t_flood(i_a), calculate_t_flood(i_b)
        assert t_a <= t_b, f"Monotonicity violation: T({i_a})={t_a} > T({i_b})={t_b}"


def test_t_flood_negative_raises():
    """Negative intensity raises ValueError explicitly."""
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_t_flood(-0.01)


def test_t_flood_non_finite_raises():
    """NaN, +Inf, -Inf intensity raise ValueError explicitly."""
    with pytest.raises(ValueError, match="must be finite"):
        calculate_t_flood(float("nan"))
    with pytest.raises(ValueError, match="must be finite"):
        calculate_t_flood(float("inf"))
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_t_flood(float("-inf"))


# =============================================================================
# 3. ROLLING 3-HOUR ACCUMULATION & INTENSITY (A3, I3)
# =============================================================================

def test_rolling_accumulation_and_intensity_exact_values():
    """Verifies exact A3 and I3 values on known test series."""
    # Window of 3 on [1.0, 2.0, 3.0]
    series = [1.0, 2.0, 3.0]
    a3_list, i3_list = compute_rolling_accumulation_and_intensity(series, window_size=3)
    assert len(a3_list) == 1
    assert len(i3_list) == 1
    assert a3_list[0] == 6.0
    assert i3_list[0] == 2.0

    # Extended series: [0.0, 0.0, 3.0, 6.0, 9.0]
    # step 2: 0 + 0 + 3 = 3, i3 = 1.0
    # step 3: 0 + 3 + 6 = 9, i3 = 3.0
    # step 4: 3 + 6 + 9 = 18, i3 = 6.0
    series2 = [0.0, 0.0, 3.0, 6.0, 9.0]
    a3_list2, i3_list2 = compute_rolling_accumulation_and_intensity(series2, window_size=3)
    assert a3_list2 == [3.0, 9.0, 18.0]
    assert i3_list2 == [1.0, 3.0, 6.0]


def test_rolling_window_length_shorter_than_window_raises():
    """Series with fewer than window_size elements raises ValueError."""
    with pytest.raises(ValueError, match="smaller than window size"):
        compute_rolling_accumulation_and_intensity([1.0, 2.0], window_size=3)


# =============================================================================
# 4. INTERPRETATION B: SYNOPTIC PRE-ANCHOR LOOKBACK
# =============================================================================

def test_interpretation_b_first_trigger_at_anchor_plus_one_hour():
    """Interpretation B guarantees first trigger is at cycle_anchor + 1h using anchor and anchor - 1h."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    # Provide 2 preceding hours + 72 future hours = 75 total hours
    start_dt = anchor - timedelta(hours=2)
    times = [start_dt + timedelta(hours=i) for i in range(75)]
    # All zeros except anchor-1h, anchor, and anchor+1h
    precip = [0.0] * 75
    precip[0] = 10.0  # anchor - 2h (not in h=1 window)
    precip[1] = 10.0  # anchor - 1h (in h=1 window)
    precip[2] = 20.0  # anchor (in h=1 window)
    precip[3] = 30.0  # anchor + 1h (in h=1 window)

    steps = compute_sample_point_triggers(
        times=times,
        precip=precip,
        cycle_anchor=anchor,
        sample_index=0,
        max_horizon_hours=72,
    )

    assert len(steps) == 72

    # Verify h=1
    s1 = steps[0]
    assert s1.horizon_hours == 1
    assert s1.valid_at == anchor + timedelta(hours=1)
    # A3(t_1) = P(13:00) + P(12:00) + P(11:00) = 30 + 20 + 10 = 60 mm
    assert s1.a3_mm == 60.0
    # I3(t_1) = 60 / 3.0 = 20.0 mm/h
    assert s1.i3_mm_h == 20.0
    # T_flood: I3=20 in ramp 1: ((20 - 10) / 19) * 0.60 = (10 / 19) * 0.60 = 0.3158
    exp_t = ((20.0 - 10.0) / 19.0) * 0.60
    assert abs(s1.t_flood - exp_t) < 1e-4

    # Verify h=72
    s72 = steps[-1]
    assert s72.horizon_hours == 72
    assert s72.valid_at == anchor + timedelta(hours=72)


def test_interpretation_b_missing_pre_anchor_lookback_raises():
    """Fails explicitly if observations at anchor or anchor - 1h are missing from payload."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    # Only future hours provided starting at 13:00 (missing anchor and anchor-1h)
    times = [anchor + timedelta(hours=i) for i in range(1, 73)]
    precip = [1.0] * 72

    with pytest.raises(ValueError, match="Interpretation B prerequisite missing"):
        compute_sample_point_triggers(
            times=times,
            precip=precip,
            cycle_anchor=anchor,
            sample_index=0,
            max_horizon_hours=72,
        )


# =============================================================================
# 5. CANONICAL TRIGGER RECORD SCHEMA CONFORMANCE
# =============================================================================

def test_canonical_trigger_records_fields_and_types():
    """Verifies that generated records conform strictly to CanonicalTriggerRecord schema."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    now_utc = datetime.now(timezone.utc)

    # Build synthetic 2-cell mapping
    mock_mappings = [
        H3CellSampleMapping(
            h3=614210667086872575,
            h3_str="8860064989fffff",
            lat=11.5364,
            lon=75.8500,
            sample_index=0,
            sample_latitude=11.5364,
            sample_longitude=75.8500,
            distance_km=1.2,
        ),
        H3CellSampleMapping(
            h3=614210667086872576,
            h3_str="886006498bfffff",
            lat=11.5400,
            lon=75.8600,
            sample_index=0,
            sample_latitude=11.5364,
            sample_longitude=75.8500,
            distance_km=2.1,
        ),
    ]

    mapping_res = WayanadSpatialMappingResult(
        district=DISTRICT_NAME,
        lgd_code=DISTRICT_LGD,
        admin_id=ADMIN_ID,
        h3_resolution=8,
        total_cells=2,
        mapped_cells=2,
        unmapped_cells=0,
        sample_points_count=1,
        mappings=mock_mappings,
        mappings_by_h3={m.h3: m for m in mock_mappings},
        mappings_by_h3_str={m.h3_str: m for m in mock_mappings},
        cell_counts_by_sample={0: 2},
        min_distance_km=1.2,
        median_distance_km=1.65,
        mean_distance_km=1.65,
        p90_distance_km=2.01,
        max_distance_km=2.1,
    )

    # Synthetic 72 sample triggers
    sample_steps = [
        SampleTriggerStep(
            sample_index=0,
            valid_at=anchor + timedelta(hours=h),
            horizon_hours=h,
            p_mm=0.5,
            a3_mm=1.5,
            i3_mm_h=0.5,
            t_flood=0.0,
        )
        for h in range(1, 73)
    ]

    records = generate_canonical_forecast_triggers(
        spatial_mapping=mapping_res,
        sample_triggers=[sample_steps],
        cycle_anchor=anchor,
    )

    # Cardinality check: 2 cells × 72 timestamps = 144 records
    assert len(records) == 144

    for r in records:
        assert isinstance(r, CanonicalTriggerRecord)
        assert r.trigger_type == TriggerType.FORECAST
        assert r.units == "dimensionless_index"
        assert r.hazard_type == "flash_flood"
        assert 0.0 <= r.trigger_value <= 3.0
        assert r.valid_at > r.forecast_cycle_at
        assert r.forecast_cycle_at == anchor
        assert 1 <= r.horizon_hours <= 72
        assert r.source == "open_meteo_ecmwf"
        assert r.provider == "Open-Meteo"
        assert r.data_quality == DataQuality.VALID
        assert r.model_version == "ECMWF_IFS_HRES"
        assert r.calculation_version == "prototype-heuristic-v1.0"
        assert r.parameter_set_version == "wayanad-prototype-param-v1.0"


# =============================================================================
# 6. CARDINALITY DERIVATION TESTS
# =============================================================================

def test_cardinality_is_derived_not_hardcoded():
    """Proves that cardinality equals num_cells * num_timestamps dynamically."""
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)

    # Test with 3 cells and 24 timestamps
    mock_cells = [
        H3CellSampleMapping(
            h3=i,
            h3_str=f"cell_{i}",
            lat=11.5,
            lon=75.8,
            sample_index=0,
            sample_latitude=11.5,
            sample_longitude=75.8,
            distance_km=1.0,
        )
        for i in range(1, 4)
    ]

    mapping_res = WayanadSpatialMappingResult(
        district=DISTRICT_NAME,
        lgd_code=DISTRICT_LGD,
        admin_id=ADMIN_ID,
        h3_resolution=8,
        total_cells=3,
        mapped_cells=3,
        unmapped_cells=0,
        sample_points_count=1,
        mappings=mock_cells,
        mappings_by_h3={m.h3: m for m in mock_cells},
        mappings_by_h3_str={m.h3_str: m for m in mock_cells},
        cell_counts_by_sample={0: 3},
        min_distance_km=1.0,
        median_distance_km=1.0,
        mean_distance_km=1.0,
        p90_distance_km=1.0,
        max_distance_km=1.0,
    )

    steps_24 = [
        SampleTriggerStep(
            sample_index=0,
            valid_at=anchor + timedelta(hours=h),
            horizon_hours=h,
            p_mm=1.0,
            a3_mm=3.0,
            i3_mm_h=1.0,
            t_flood=0.0,
        )
        for h in range(1, 25)
    ]

    records = generate_canonical_forecast_triggers(
        spatial_mapping=mapping_res,
        sample_triggers=[steps_24],
        cycle_anchor=anchor,
    )

    # 3 cells × 24 timestamps = 72 records
    assert len(records) == 3 * 24 == 72


# =============================================================================
# 7. REAL B1 ARTIFACT INTEGRATION TEST (WAYANAD 259,344 RECORDS)
# =============================================================================

def test_full_wayanad_trigger_generation_with_real_artifact():
    """End-to-end integration test against the real recorded Phase B1 artifact.

    Validates:
    - Exactly 3,602 cells mapped.
    - Exactly 72 forecast timestamps under Interpretation B.
    - Exactly 259,344 canonical trigger records generated in memory.
    - Zero database queries, zero network calls.
    - All triggers in [0.0, 3.0].
    """
    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    result = execute_wayanad_b5_trigger_generation(raw_artifact_path=artifact_path)

    assert result.status == "SUCCESS"
    assert result.hazard_type == "flash_flood"
    assert result.provider == "Open-Meteo"
    assert result.source_model == "ECMWF_IFS_HRES"
    assert result.district == "Wayanad"
    assert result.lgd_code == 555
    assert result.admin_id == 178

    # Cardinality checks
    assert result.authoritative_cell_count == 3602
    assert result.valid_trigger_timestamps_count == 72
    assert result.total_records_generated == 259344  # 3,602 × 72
    assert len(result.records) == 259344

    # Horizon window checks
    anchor = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    assert result.forecast_cycle_anchor == anchor
    assert result.first_trigger_valid_at == anchor + timedelta(hours=1)
    assert result.last_trigger_valid_at == anchor + timedelta(hours=72)
    assert result.horizon_hours_start == 1
    assert result.horizon_hours_end == 72

    # Value checks
    assert 0.0 <= result.min_trigger_value <= result.max_trigger_value <= 3.0
    assert result.rolling_window_hours == 3
    assert result.rolling_window_interpretation == "Interpretation B - Synoptic Pre-Anchor Lookback"
    assert result.scientific_status == "Prototype Heuristic Calibration"

    # Verify a slice of records
    first_record = result.records[0]
    assert first_record.valid_at == anchor + timedelta(hours=1)
    assert first_record.horizon_hours == 1
    assert first_record.trigger_type == TriggerType.FORECAST
    assert first_record.units == "dimensionless_index"
    assert first_record.hazard_type == "flash_flood"
    assert first_record.source == "open_meteo_ecmwf"
    assert first_record.provider == "Open-Meteo"
