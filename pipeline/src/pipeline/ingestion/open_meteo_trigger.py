"""SETU-DRR Phase B4/B5: Prototype Forecast Trigger Generation.

Connects:
    B1: Open-Meteo ECMWF raw response (persisted & hashed)
            ↓
    B2: 12 forecast sample points → 3,602 existing H3-8 cells (spatial mapping)
            ↓
    B3: Rainfall & spatial validation gate (certified upstream input)
            ↓
    B4: Trigger contract freeze (constants & piecewise heuristic formula)
            ↓
    B5: Canonical trigger generation (THIS MODULE: in-memory transformation)
            ↓
    B6: Hazard evaluation & snapshot persistence (downstream execution)

Strict Scope Boundary (Phase B4/B5):
- Pure IN-MEMORY data transformation stage.
- ZERO database access (no SQL, no inserts, no updates, no migrations).
- ZERO network calls (no HTTP requests, offline only).
- ZERO modifications to core hazard engine, MHI, ML, frontend, or DB schemas.
- Consumes B2 spatial mapping as upstream input (never recomputes Haversine or grids).
- Consumes B3 validation as upstream gate (never duplicates rainfall validation).

Phase B4 Contract Freeze:
    Accumulation: A3(t) = P(t) + P(t-1) + P(t-2)   [mm / 3 hours]
    Intensity:    I3(t) = A3(t) / 3.0               [mm/h]
    Constants:    I0 = 10.0 mm/h, Ic = 29.0 mm/h, Tmax = 3.0
    Piecewise formula:
        if I3 < 10.0:
            T_flood = 0.0
        elif 10.0 <= I3 < 29.0:
            T_flood = ((I3 - 10.0) / 19.0) * 0.60
        else:
            T_flood = 0.60 + ((I3 - 29.0) / 29.0) * 1.0
        T_flood = min(T_flood, 3.0)

Approved Rolling-Window Contract:
    Interpretation B — Synoptic Pre-Anchor Lookback:
    - First forecast trigger is at forecast_cycle_at + 1 hour (h=1).
    - Uses the preceding two hourly observations available in the upstream forecast payload:
        h=1: P(anchor + 1h) + P(anchor) + P(anchor - 1h)
        h=2: P(anchor + 2h) + P(anchor + 1h) + P(anchor)
    - Exactly 72 forecast timestamps (h = 1 .. 72).
    - Expected Wayanad cardinality = 3,602 cells × 72 timestamps = 259,344 canonical records.

Scientific Status:
    Prototype Heuristic Calibration.
    NOT an empirically calibrated operational warning model or disaster prediction.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from core.constants import FORECAST_HORIZON_HOURS, SCREENING_GRADE_NOTICE
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
    EXPECTED_SAMPLE_COUNT,
    WayanadSpatialMappingResult,
    execute_wayanad_b2_spatial_mapping,
    load_b1_forecast_artifact,
)
from pipeline.ingestion.open_meteo_validate import (
    MIN_FUTURE_HOURS,
    PhaseB3ValidationReport,
    validate_wayanad_b3_forecast,
)

logger = logging.getLogger("setu_pipeline.open_meteo_trigger")

# =============================================================================
# PHASE B4: FROZEN PROTOTYPE TRIGGER CONTRACT CONSTANTS
# =============================================================================

I0: float = 10.0      # Baseline threshold in mm/h (below which T_flood = 0.0)
IC: float = 29.0      # Critical threshold in mm/h (at which T_flood reaches 0.60)
T_MAX: float = 3.0    # Maximum dimensionless trigger cap
WINDOW_HOURS: int = 3 # Rolling accumulation window in hours

HAZARD_TYPE: str = "flash_flood"
TRIGGER_UNITS: str = "dimensionless_index"
SOURCE_NAME: str = SOURCE_ID  # "open_meteo_ecmwf"
PROVIDER_NAME: str = "Open-Meteo"
MODEL_VERSION: str = SOURCE_MODEL  # "ECMWF_IFS_HRES"
CALCULATION_VERSION: str = "prototype-heuristic-v1.0"
PARAMETER_SET_VERSION: str = "wayanad-prototype-param-v1.0"

SCIENTIFIC_STATUS: str = "Prototype Heuristic Calibration"
ROLLING_WINDOW_INTERPRETATION: str = "Interpretation B - Synoptic Pre-Anchor Lookback"
SCIENTIFIC_DISCLAIMER: str = (
    "Prototype heuristic trigger calculation for Wayanad live ECMWF forecast integration. "
    "This heuristic is NOT an empirically calibrated operational warning model or a disaster prediction."
)


@dataclass(frozen=True)
class SampleTriggerStep:
    """Pre-computed hourly trigger step for a single forecast sample point."""
    sample_index: int
    valid_at: datetime
    horizon_hours: int
    p_mm: float
    a3_mm: float
    i3_mm_h: float
    t_flood: float


@dataclass(frozen=True)
class WayanadTriggerGenerationResult:
    """Auditable in-memory result produced by Phase B5 canonical trigger generation."""
    status: str
    hazard_type: str
    provider: str
    source_model: str
    district: str
    lgd_code: int
    admin_id: int
    authoritative_cell_count: int
    valid_trigger_timestamps_count: int
    total_records_generated: int
    forecast_cycle_anchor: datetime
    first_trigger_valid_at: datetime
    last_trigger_valid_at: datetime
    horizon_hours_start: int
    horizon_hours_end: int
    min_trigger_value: float
    max_trigger_value: float
    mean_trigger_value: float
    active_triggers_count: int
    rolling_window_hours: int = WINDOW_HOURS
    rolling_window_interpretation: str = ROLLING_WINDOW_INTERPRETATION
    scientific_status: str = SCIENTIFIC_STATUS
    records: list[CanonicalTriggerRecord] = field(default_factory=list)


# =============================================================================
# PHASE B4: PURE TRIGGER MATHEMATICS
# =============================================================================

def calculate_t_flood(i3: float) -> float:
    """Computes dimensionless flash flood trigger T_flood from 3-hour intensity I3 (mm/h).

    Mathematical Formulation (Phase B4 Contract Freeze):
        if I3 < 10.0:
            T_flood = 0.0
        elif 10.0 <= I3 < 29.0:
            T_flood = ((I3 - 10.0) / 19.0) * 0.60
        else:
            T_flood = 0.60 + ((I3 - 29.0) / 29.0) * 1.0
        T_flood = min(T_flood, 3.0)

    Continuity check:
        At I3 = 10.0: T_flood = 0.0
        At I3 = 19.5: T_flood = (9.5 / 19.0) * 0.60 = 0.30
        At I3 = 29.0: Ramp 1: (19.0 / 19.0) * 0.60 = 0.60; Ramp 2: 0.60 + 0 = 0.60 (continuous)
        At I3 = 58.0: T_flood = 0.60 + (29.0 / 29.0) * 1.0 = 1.60
        At I3 = 98.6: T_flood = 0.60 + (69.6 / 29.0) * 1.0 = 3.00 (clamp threshold)

    Raises:
        ValueError: if i3 < 0.0 or i3 is non-finite.
    """
    if i3 < 0.0:
        raise ValueError(f"Intensity I3 cannot be negative, got {i3}")
    if math.isnan(i3) or math.isinf(i3):
        raise ValueError(f"Intensity I3 must be finite, got {i3}")

    if i3 < I0:
        t_val = 0.0
    elif i3 < IC:
        t_val = ((i3 - I0) / (IC - I0)) * 0.60
    else:
        t_val = 0.60 + ((i3 - IC) / IC) * 1.0

    return min(t_val, T_MAX)


def compute_rolling_accumulation_and_intensity(
    hourly_precip: Sequence[float],
    window_size: int = WINDOW_HOURS,
) -> tuple[list[float], list[float]]:
    """Computes rolling accumulation A_w and average intensity I_w over a 1D precipitation sequence.

    For each index i >= window_size - 1:
        A[i] = sum(P[i - k] for k in range(window_size))
        I[i] = A[i] / float(window_size)

    Raises:
        ValueError: if len(hourly_precip) < window_size or any value is negative / non-finite.
    """
    if len(hourly_precip) < window_size:
        raise ValueError(
            f"Precipitation series length {len(hourly_precip)} is smaller than window size {window_size}"
        )

    for idx, p in enumerate(hourly_precip):
        if p < 0.0 or math.isnan(p) or math.isinf(p):
            raise ValueError(f"Invalid precipitation value at index {idx}: {p}")

    accumulations: list[float] = []
    intensities: list[float] = []

    for i in range(window_size - 1, len(hourly_precip)):
        a_val = sum(hourly_precip[i - k] for k in range(window_size))
        i_val = a_val / float(window_size)
        accumulations.append(round(a_val, 4))
        intensities.append(round(i_val, 4))

    return accumulations, intensities


# =============================================================================
# PHASE B5: SAMPLE POINT & CANONICAL TRIGGER GENERATION
# =============================================================================

def compute_sample_point_triggers(
    times: Sequence[datetime | str],
    precip: Sequence[float],
    cycle_anchor: datetime,
    sample_index: int,
    max_horizon_hours: int = FORECAST_HORIZON_HOURS,
) -> list[SampleTriggerStep]:
    """Computes 72 hourly trigger steps for a single sample point under Interpretation B.

    Interpretation B Contract:
    - First forecast trigger is at cycle_anchor + 1h (horizon h=1).
    - Requires preceding 2 hourly observations (anchor, anchor - 1h) from upstream payload.
    - Computes:
        A3(t_h) = P(t_h) + P(t_{h-1}) + P(t_{h-2})
        I3(t_h) = A3(t_h) / 3.0
        T_flood(t_h) = calculate_t_flood(I3(t_h))
    - Generates exactly max_horizon_hours steps (h = 1 .. max_horizon_hours).
    """
    anchor_utc = cycle_anchor if cycle_anchor.tzinfo is not None else cycle_anchor.replace(tzinfo=timezone.utc)

    # Normalize timestamps to UTC
    parsed_dts: list[datetime] = []
    for t_val in times:
        if isinstance(t_val, datetime):
            dt = t_val if t_val.tzinfo is not None else t_val.replace(tzinfo=timezone.utc)
        else:
            iso_str = t_val.replace("Z", "+00:00") if t_val.endswith("Z") else t_val
            dt = datetime.fromisoformat(iso_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        parsed_dts.append(dt.astimezone(timezone.utc))

    if len(parsed_dts) != len(precip):
        raise ValueError(
            f"Sample {sample_index} length mismatch: len(times)={len(parsed_dts)} != len(precip)={len(precip)}"
        )

    # Build lookup map of valid_dt -> precipitation
    precip_by_dt: dict[datetime, float] = {}
    for dt, p in zip(parsed_dts, precip):
        p_val = float(p)
        if p_val < 0.0 or math.isnan(p_val) or math.isinf(p_val):
            raise ValueError(f"Sample {sample_index} invalid precipitation value at {dt.isoformat()}: {p_val}")
        precip_by_dt[dt] = p_val

    # Interpretation B requires observations at anchor and anchor - 1h
    t_minus_1 = anchor_utc
    t_minus_2 = anchor_utc - timedelta(hours=1)

    if t_minus_1 not in precip_by_dt:
        raise ValueError(
            f"Sample {sample_index} Interpretation B prerequisite missing: observation at anchor "
            f"{t_minus_1.isoformat()} not found in payload"
        )
    if t_minus_2 not in precip_by_dt:
        raise ValueError(
            f"Sample {sample_index} Interpretation B prerequisite missing: observation at anchor-1h "
            f"{t_minus_2.isoformat()} not found in payload"
        )

    steps: list[SampleTriggerStep] = []

    for h in range(1, max_horizon_hours + 1):
        t_curr = anchor_utc + timedelta(hours=h)
        t_prev1 = anchor_utc + timedelta(hours=h - 1)
        t_prev2 = anchor_utc + timedelta(hours=h - 2)

        if t_curr not in precip_by_dt:
            raise ValueError(
                f"Sample {sample_index} missing forecast observation for horizon hour h={h} ({t_curr.isoformat()})"
            )

        p_curr = precip_by_dt[t_curr]
        p_prev1 = precip_by_dt[t_prev1]
        p_prev2 = precip_by_dt[t_prev2]

        # Exact 3-hour accumulation and intensity under Interpretation B
        a3 = p_curr + p_prev1 + p_prev2
        i3 = a3 / 3.0
        t_flood = calculate_t_flood(i3)

        steps.append(
            SampleTriggerStep(
                sample_index=sample_index,
                valid_at=t_curr,
                horizon_hours=h,
                p_mm=round(p_curr, 4),
                a3_mm=round(a3, 4),
                i3_mm_h=round(i3, 4),
                t_flood=round(t_flood, 4),
            )
        )

    return steps


def generate_canonical_forecast_triggers(
    spatial_mapping: WayanadSpatialMappingResult,
    sample_triggers: Sequence[Sequence[SampleTriggerStep]],
    cycle_anchor: datetime,
    source: str = SOURCE_NAME,
    provider: str = PROVIDER_NAME,
    model_version: str = MODEL_VERSION,
    calculation_version: str = CALCULATION_VERSION,
    parameter_set_version: str = PARAMETER_SET_VERSION,
) -> list[CanonicalTriggerRecord]:
    """Transforms pre-computed sample triggers into canonical trigger records for all mapped H3 cells.

    Cardinality is derived as:
        len(spatial_mapping.mappings) * len(sample_triggers[0])
    For Wayanad:
        3,602 cells * 72 timestamps = 259,344 records.

    Enforces all CanonicalTriggerRecord schema invariants:
        - trigger_type == TriggerType.FORECAST
        - units == "dimensionless_index"
        - hazard_type == "flash_flood"
        - 0.0 <= trigger_value <= 3.0
        - valid_at > forecast_cycle_at
    """
    anchor_utc = cycle_anchor if cycle_anchor.tzinfo is not None else cycle_anchor.replace(tzinfo=timezone.utc)
    now_utc = datetime.now(timezone.utc)

    num_cells = len(spatial_mapping.mappings)
    if num_cells == 0:
        raise ValueError("Spatial mapping contains 0 mapped cells")

    num_samples = len(sample_triggers)
    if num_samples != spatial_mapping.sample_points_count:
        raise ValueError(
            f"Sample triggers count ({num_samples}) does not match spatial mapping "
            f"sample count ({spatial_mapping.sample_points_count})"
        )

    timestamps_per_sample = len(sample_triggers[0])
    expected_total_records = num_cells * timestamps_per_sample

    logger.info(
        f"Generating canonical forecast triggers: {num_cells} cells x {timestamps_per_sample} timestamps "
        f"= {expected_total_records} records..."
    )

    records: list[CanonicalTriggerRecord] = []

    # Map pre-computed sample triggers to H3 cells using B2 assignments
    for m in spatial_mapping.mappings:
        sample_idx = m.sample_index
        sample_series = sample_triggers[sample_idx]

        for step in sample_series:
            record = CanonicalTriggerRecord(
                h3=m.h3_str,
                h3_int=m.h3,
                hazard_type=HAZARD_TYPE,
                trigger_type=TriggerType.FORECAST,
                trigger_value=step.t_flood,
                units=TRIGGER_UNITS,
                valid_at=step.valid_at,
                forecast_cycle_at=anchor_utc,
                horizon_hours=step.horizon_hours,
                source=source,
                provider=provider,
                data_quality=DataQuality.VALID,
                fallback_source=None,
                model_version=model_version,
                calculation_version=calculation_version,
                parameter_set_version=parameter_set_version,
                generated_at=now_utc,
                screening_grade=SCREENING_GRADE_NOTICE,
            )
            records.append(record)

    if len(records) != expected_total_records:
        raise ValueError(
            f"Generated record cardinality mismatch: expected {expected_total_records}, produced {len(records)}"
        )

    return records


def execute_wayanad_b5_trigger_generation(
    raw_artifact_path: Optional[Path | str] = None,
    spatial_mapping: Optional[WayanadSpatialMappingResult] = None,
    cycle_anchor: Optional[datetime] = None,
    max_horizon_hours: int = FORECAST_HORIZON_HOURS,
    expected_cell_count: int = EXPECTED_CELL_COUNT,
) -> WayanadTriggerGenerationResult:
    """End-to-end execution of Phase B5 canonical trigger generation for Wayanad.

    Algorithm:
        1. Load validated raw artifact (Phase B1 / B3).
        2. Validate rainfall and spatial mapping via Phase B3 validation gate.
        3. Load B2 spatial mapping (3,602 cells -> 12 sample points).
        4. Compute rolling A3, I3, and T_flood for all 12 sample points under Interpretation B.
        5. Map sample triggers to all 3,602 H3 cells, generating exactly 259,344 CanonicalTriggerRecords.
        6. Compute summary metrics and return auditable WayanadTriggerGenerationResult.

    Strict Invariants:
        - ZERO database access.
        - ZERO external network requests.
        - ZERO modifications to upstream or downstream systems.
    """
    logger.info("Starting Phase B5 Wayanad canonical trigger generation...")

    # 1. Resolve raw artifact path
    if raw_artifact_path is None:
        repo_root = Path(__file__).resolve().parents[4]
        raw_artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    # 2. Consume B3 Validation Gate
    validation_report = validate_wayanad_b3_forecast(
        raw_artifact_path=raw_artifact_path,
        cycle_anchor=cycle_anchor,
        min_future_hours=max_horizon_hours,
        raise_on_failure=True,
    )

    if not validation_report.valid:
        raise ValueError(f"B3 validation failed with {len(validation_report.errors)} errors")

    # 3. Determine Synoptic Anchor
    anchor = datetime.fromisoformat(validation_report.derived_provider_run_anchor)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)

    # 4. Load Raw Payload
    _, _, payload, _ = load_b1_forecast_artifact(
        raw_artifact_path=raw_artifact_path,
        expected_sample_count=EXPECTED_SAMPLE_COUNT,
    )

    # 5. Consume B2 Spatial Mapping
    mapping = spatial_mapping
    if mapping is None:
        mapping = execute_wayanad_b2_spatial_mapping(raw_artifact_path=raw_artifact_path)

    if mapping.mapped_cells != expected_cell_count:
        raise ValueError(
            f"Authoritative cell count invariant failed: {mapping.mapped_cells} != {expected_cell_count}"
        )

    # 6. Compute 12 Sample Point Triggers under Interpretation B
    sample_triggers: list[list[SampleTriggerStep]] = []
    for loc_idx, loc in enumerate(payload):
        hourly = loc["hourly"]
        steps = compute_sample_point_triggers(
            times=hourly["time"],
            precip=hourly["precipitation"],
            cycle_anchor=anchor,
            sample_index=loc_idx,
            max_horizon_hours=max_horizon_hours,
        )
        sample_triggers.append(steps)

    # 7. Generate Canonical Trigger Records
    records = generate_canonical_forecast_triggers(
        spatial_mapping=mapping,
        sample_triggers=sample_triggers,
        cycle_anchor=anchor,
    )

    # 8. Compute Summary Statistics
    trigger_values = [r.trigger_value for r in records]
    min_t = min(trigger_values)
    max_t = max(trigger_values)
    mean_t = sum(trigger_values) / len(trigger_values)
    active_count = sum(1 for t in trigger_values if t > 0.0)

    total_records = len(records)
    timestamps_count = len(sample_triggers[0])

    first_ts = sample_triggers[0][0].valid_at
    last_ts = sample_triggers[0][-1].valid_at

    result = WayanadTriggerGenerationResult(
        status="SUCCESS",
        hazard_type=HAZARD_TYPE,
        provider=PROVIDER_NAME,
        source_model=MODEL_VERSION,
        district=DISTRICT_NAME,
        lgd_code=DISTRICT_LGD,
        admin_id=ADMIN_ID,
        authoritative_cell_count=mapping.mapped_cells,
        valid_trigger_timestamps_count=timestamps_count,
        total_records_generated=total_records,
        forecast_cycle_anchor=anchor,
        first_trigger_valid_at=first_ts,
        last_trigger_valid_at=last_ts,
        horizon_hours_start=1,
        horizon_hours_end=max_horizon_hours,
        min_trigger_value=round(min_t, 4),
        max_trigger_value=round(max_t, 4),
        mean_trigger_value=round(mean_t, 4),
        active_triggers_count=active_count,
        rolling_window_hours=WINDOW_HOURS,
        rolling_window_interpretation=ROLLING_WINDOW_INTERPRETATION,
        scientific_status=SCIENTIFIC_STATUS,
        records=records,
    )

    logger.info(
        f"Phase B5 Trigger Generation complete: {total_records} records generated "
        f"({mapping.mapped_cells} cells x {timestamps_count} timestamps). "
        f"T_flood range: [{result.min_trigger_value}, {result.max_trigger_value}], "
        f"active (T>0): {result.active_triggers_count}/{total_records}"
    )

    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    res = execute_wayanad_b5_trigger_generation()

    print("\n" + "=" * 75)
    print("SETU-DRR Phase B4/B5: Canonical Forecast Trigger Generation")
    print(f"Status:                         {res.status}")
    print(f"Hazard Type:                    {res.hazard_type}")
    print(f"Provider / Model:               {res.provider} / {res.source_model}")
    print(f"District:                       {res.district} (LGD {res.lgd_code}, Admin ID {res.admin_id})")
    print(f"Authoritative Cells:            {res.authoritative_cell_count}")
    print(f"Valid Trigger Timestamps:       {res.valid_trigger_timestamps_count}")
    print(f"Total Records Generated:        {res.total_records_generated}")
    print(f"Forecast Cycle Anchor:          {res.forecast_cycle_anchor.isoformat()}")
    print(f"First Trigger Valid At:         {res.first_trigger_valid_at.isoformat()} (h={res.horizon_hours_start})")
    print(f"Last Trigger Valid At:          {res.last_trigger_valid_at.isoformat()} (h={res.horizon_hours_end})")
    print(f"T_flood Range:                  [{res.min_trigger_value:.4f}, {res.max_trigger_value:.4f}]")
    print(f"T_flood Mean:                   {res.mean_trigger_value:.4f}")
    print(f"Active Triggers (T > 0):        {res.active_triggers_count} / {res.total_records_generated}")
    print(f"Window Interpretation:          {res.rolling_window_interpretation}")
    print(f"Scientific Status:              {res.scientific_status}")
    print("=" * 75 + "\n")
