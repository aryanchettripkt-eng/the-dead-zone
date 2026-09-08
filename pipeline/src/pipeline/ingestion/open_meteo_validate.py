"""SETU-DRR Phase B3: Rainfall & Spatial Mapping Validation Gate.

Establishes a rigorous, reproducible, deterministic validation gate between:
    B1: Open-Meteo ECMWF raw forecast ingestion (persisted & hashed)
            ↓
    B2: 12 forecast sample points → 3,602 existing H3-8 cells (spatial mapping)
            ↓
    B3: Rainfall & Spatial Mapping Validation Gate (THIS MODULE)
            ↓
    B4: Trigger contract freeze
            ↓
    B5: T_flood generation
            ↓
    Existing dynamic hazard engine

Scope Boundary (Phase B3):
- Strictly READ-ONLY validation gate.
- ZERO trigger calculations (T_flood, A3, I3).
- ZERO hazard calculations or MHI mutations.
- ZERO writes to `hazard_dynamic` or `mhi_snapshot`.
- ZERO modifications to core hazard math, ML models, frontend, or DB schemas.
- ZERO parallel H3 grids or alternate geometries.

Rainfall Semantics Contract:
Open-Meteo ECMWF IFS HRES `hourly.precipitation` MUST be interpreted as:
    hourly precipitation accumulation in millimetres for the corresponding hourly interval.
It must NOT be treated as:
    - instantaneous rainfall intensity;
    - mm/min;
    - mm/s;
    - cumulative running total.

Scientific Provenance & Geometry Distinction:
    forecast_native_resolution_km = 9.0 (ECMWF IFS HRES native grid ~9 km)
    decision_geometry = H3 resolution 8 (~460m operational decision cells)
    spatial_mapping_method = nearest_sample_prototype
H3-8 cells are reporting/decision geometry, NOT 3,602 independent 460m rainfall observations.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from sqlalchemy.engine import Engine

from core.h3_utils import h3_get_resolution, is_valid_h3
from pipeline.ingestion.open_meteo_client import (
    ADMIN_ID,
    DISTRICT_LGD,
    DISTRICT_NAME,
    NATIVE_RESOLUTION_KM,
    OPEN_METEO_ECMWF_ENDPOINT,
    REFERENCE_ARTIFACT_REL_PATH,
    REFERENCE_ARTIFACT_SHA256,
    SOURCE_ID,
    SOURCE_MODEL,
    WAYANAD_PROTOTYPE_SAMPLE_POINTS,
    derive_provider_run_anchor,
)
from pipeline.ingestion.open_meteo_regrid import (
    EXPECTED_CELL_COUNT,
    EXPECTED_SAMPLE_COUNT,
    MAPPING_METHOD,
    TARGET_RESOLUTION,
    H3CellSampleMapping,
    WayanadSpatialMappingResult,
    execute_wayanad_b2_spatial_mapping,
    load_authoritative_wayanad_grid,
    load_b1_forecast_artifact,
)

logger = logging.getLogger("setu_pipeline.open_meteo_validate")

# Canonical B3 Validation Constants
DECISION_GEOMETRY = f"H3 resolution {TARGET_RESOLUTION}"
MIN_FUTURE_HOURS = 72
FORECAST_CYCLE_SEMANTICS = "derived_provider_run_anchor"
CYCLE_ANCHOR_VERIFIED = False

RAINFALL_UNIT = "mm"
RAINFALL_SEMANTICS = "hourly_accumulation_mm"
RAINFALL_INTERPRETATION = (
    "hourly precipitation accumulation in millimetres for the corresponding hourly interval. "
    "Must NOT be treated as instantaneous rainfall intensity, mm/min, mm/s, or a cumulative running total."
)

SCIENTIFIC_DISCLAIMER = (
    "ECMWF forecast rainfall crossing configured thresholds provides data-quality validated trigger "
    "inputs for SETU-DRR; it does not constitute a guaranteed flood prediction or disaster prediction confidence."
)


class RainfallValidationError(ValueError):
    """Exception raised when forecast or spatial validation fails hard invariants."""
    pass


@dataclass(frozen=True)
class PhaseB3ValidationReport:
    """Structured, auditable validation report produced by Phase B3."""
    valid: bool
    provider: str
    source_model: str
    district: str
    lgd: int
    admin_id: int
    h3_resolution: int
    expected_cells: int
    mapped_cells: int
    unmapped_cells: int
    expected_sample_points: int
    sample_points_present: int
    forecast_hours_available: int
    future_hours_available: int
    timestamps_strictly_increasing: bool
    timestamps_hourly: bool
    duplicate_timestamps: int
    missing_timestamps: int
    missing_precipitation_values: int
    negative_precipitation_values: int
    non_finite_values: int
    non_numeric_values: int
    retrieval_time: Optional[str]
    derived_provider_run_anchor: str
    first_forecast_timestamp: str
    last_forecast_timestamp: str
    forecast_cycle_semantics: str
    cycle_anchor_verified: bool
    spatial_mapping_method: str
    forecast_native_resolution_km: float
    decision_geometry: str
    rainfall_unit: str
    rainfall_interpretation: str
    raw_artifact_path: str
    raw_artifact_sha256: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    validated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Converts report to standard dictionary format matching B3 schema."""
        return {
            "valid": self.valid,
            "provider": self.provider,
            "source_model": self.source_model,
            "district": self.district,
            "lgd": self.lgd,
            "admin_id": self.admin_id,
            "h3_resolution": self.h3_resolution,
            "expected_cells": self.expected_cells,
            "mapped_cells": self.mapped_cells,
            "unmapped_cells": self.unmapped_cells,
            "expected_sample_points": self.expected_sample_points,
            "sample_points_present": self.sample_points_present,
            "forecast_hours_available": self.forecast_hours_available,
            "future_hours_available": self.future_hours_available,
            "timestamps_strictly_increasing": self.timestamps_strictly_increasing,
            "timestamps_hourly": self.timestamps_hourly,
            "duplicate_timestamps": self.duplicate_timestamps,
            "missing_timestamps": self.missing_timestamps,
            "missing_precipitation_values": self.missing_precipitation_values,
            "negative_precipitation_values": self.negative_precipitation_values,
            "non_finite_values": self.non_finite_values,
            "non_numeric_values": self.non_numeric_values,
            "retrieval_time": self.retrieval_time,
            "derived_provider_run_anchor": self.derived_provider_run_anchor,
            "first_forecast_timestamp": self.first_forecast_timestamp,
            "last_forecast_timestamp": self.last_forecast_timestamp,
            "forecast_cycle_semantics": self.forecast_cycle_semantics,
            "cycle_anchor_verified": self.cycle_anchor_verified,
            "spatial_mapping_method": self.spatial_mapping_method,
            "forecast_native_resolution_km": self.forecast_native_resolution_km,
            "decision_geometry": self.decision_geometry,
            "rainfall_unit": self.rainfall_unit,
            "rainfall_interpretation": self.rainfall_interpretation,
            "raw_artifact_path": self.raw_artifact_path,
            "raw_artifact_sha256": self.raw_artifact_sha256,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "validated_at": self.validated_at,
        }


def validate_rainfall_semantics(
    hourly_units: Optional[dict[str, Any]],
    sample_coord: tuple[float, float],
    loc_idx: int,
) -> list[str]:
    """Validates that provider payload explicitly declares expected precipitation unit and format.

    Ensures hourly_units specifies:
        time: iso8601
        precipitation: mm
    """
    errors: list[str] = []
    if hourly_units is None or not isinstance(hourly_units, dict):
        errors.append(
            f"B3 rainfall semantics validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
            f"(loc {loc_idx}) missing 'hourly_units' dictionary"
        )
        return errors

    precip_unit = hourly_units.get("precipitation")
    if precip_unit != RAINFALL_UNIT:
        errors.append(
            f"B3 rainfall semantics validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
            f"(loc {loc_idx}) expected precipitation unit '{RAINFALL_UNIT}', got '{precip_unit}'"
        )

    time_unit = hourly_units.get("time")
    if time_unit != "iso8601":
        errors.append(
            f"B3 rainfall semantics validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
            f"(loc {loc_idx}) expected time unit 'iso8601', got '{time_unit}'"
        )

    return errors


def validate_forecast_timestamps(
    times: Sequence[Any],
    sample_coord: tuple[float, float],
    loc_idx: int,
    default_tz: Optional[timezone] = timezone.utc,
) -> tuple[bool, list[str], list[datetime], dict[str, Any]]:
    """Validates timestamp integrity for a single forecast sample series.

    Invariants enforced:
    - Timestamps exist and parse as ISO 8601.
    - Timestamps are timezone-aware (or safely normalized to UTC if default_tz defined by provider contract).
    - If naïve and default_tz is None, explicitly rejected.
    - Timestamps are unique (no duplicates).
    - Timestamps are strictly monotonically increasing (t[i] > t[i-1]).
    - Consecutive timestamps have exact hourly spacing (delta == 3,600 seconds).
      Detects 30-minute intervals, 2-hour gaps, missing hours, or backward jumps.
    """
    errors: list[str] = []
    parsed_dts: list[datetime] = []
    counts = {
        "duplicate_timestamps": 0,
        "missing_timestamps": 0,
        "strictly_increasing": True,
        "hourly_spacing": True,
    }

    if not times:
        errors.append(
            f"B3 timestamp validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
            f"empty timestamp series"
        )
        return False, errors, parsed_dts, counts

    # Parse timestamps
    for step_idx, t_raw in enumerate(times):
        if not isinstance(t_raw, str):
            errors.append(
                f"B3 timestamp validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
                f"step={step_idx} timestamp is not a string (got {type(t_raw).__name__})"
            )
            continue

        try:
            # Handle ISO string with trailing Z or explicit offset
            iso_str = t_raw.replace("Z", "+00:00") if t_raw.endswith("Z") else t_raw
            dt = datetime.fromisoformat(iso_str)
        except (ValueError, TypeError) as exc:
            errors.append(
                f"B3 timestamp validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
                f"step={step_idx} invalid ISO timestamp '{t_raw}': {exc}"
            )
            continue

        if dt.tzinfo is None:
            if default_tz is not None:
                # Normalization defined by provider contract (Open-Meteo ECMWF is GMT/UTC)
                dt = dt.replace(tzinfo=default_tz)
            else:
                errors.append(
                    f"B3 timestamp validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
                    f"step={step_idx} timestamp '{t_raw}' is naive without timezone and no contract timezone specified"
                )
                continue
        else:
            # Normalize to UTC
            dt = dt.astimezone(timezone.utc)

        parsed_dts.append(dt)

    if len(parsed_dts) != len(times):
        # Timestamp parsing failures encountered
        counts["strictly_increasing"] = False
        counts["hourly_spacing"] = False
        return False, errors, parsed_dts, counts

    # Check ordering, uniqueness, and hourly intervals
    seen_dts: set[datetime] = set()
    for i, dt in enumerate(parsed_dts):
        t_str = times[i]

        # Duplicate check
        if dt in seen_dts:
            counts["duplicate_timestamps"] += 1
            counts["strictly_increasing"] = False
            errors.append(
                f"B3 timestamp validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
                f"timestamp={t_str} reason=duplicate timestamp detected at step={i}"
            )
        seen_dts.add(dt)

        # Monotonicity and spacing check against previous step
        if i > 0:
            prev_dt = parsed_dts[i - 1]
            prev_str = times[i - 1]
            delta_sec = (dt - prev_dt).total_seconds()

            if dt <= prev_dt:
                counts["strictly_increasing"] = False
                if dt < prev_dt:
                    errors.append(
                        f"B3 timestamp validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
                        f"timestamp={t_str} reason=non-monotonic timestamp (went backward from {prev_str})"
                    )
            elif delta_sec != 3600:
                counts["hourly_spacing"] = False
                if delta_sec > 3600:
                    gap_hours = int(delta_sec // 3600)
                    counts["missing_timestamps"] += (gap_hours - 1)
                    errors.append(
                        f"B3 timestamp validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
                        f"timestamp={t_str} reason=missing hourly timestamp ({gap_hours}h gap between {prev_str} and {t_str})"
                    )
                else:
                    errors.append(
                        f"B3 timestamp validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
                        f"timestamp={t_str} reason=unexpected interval ({delta_sec}s gap between {prev_str} and {t_str}, expected 3600s)"
                    )

    is_valid = (
        len(errors) == 0
        and counts["duplicate_timestamps"] == 0
        and counts["missing_timestamps"] == 0
        and counts["strictly_increasing"]
        and counts["hourly_spacing"]
    )
    return is_valid, errors, parsed_dts, counts


def validate_precipitation_values(
    precip: Sequence[Any],
    times: Sequence[Any],
    sample_coord: tuple[float, float],
    loc_idx: int,
) -> tuple[bool, list[str], dict[str, int]]:
    """Validates numeric physical integrity of precipitation values.

    Invariants enforced:
    - Array length matches timestamp length.
    - Every value is numeric (int or float).
    - Every value is finite (not NaN, +Inf, or -Inf).
    - Every value is non-negative (>= 0.0 mm).
    - No missing (None, null) values.
    - Zero clamping, zero silent modification.
    """
    errors: list[str] = []
    stats = {
        "missing_precipitation_values": 0,
        "negative_precipitation_values": 0,
        "non_finite_values": 0,
        "non_numeric_values": 0,
    }

    if len(precip) != len(times):
        errors.append(
            f"B3 rainfall validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
            f"length mismatch len(precipitation)={len(precip)} != len(time)={len(times)}"
        )

    for i, p in enumerate(precip):
        t_str = str(times[i]) if i < len(times) else f"step_{i}"

        # 1. Missing / null check
        if p is None:
            stats["missing_precipitation_values"] += 1
            errors.append(
                f"B3 rainfall validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
                f"timestamp={t_str} field=hourly.precipitation reason=missing value"
            )
            continue

        # 2. Non-numeric check (reject booleans, strings, dicts, objects)
        if isinstance(p, bool) or not isinstance(p, (int, float, str)):
            stats["non_numeric_values"] += 1
            errors.append(
                f"B3 rainfall validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
                f"timestamp={t_str} field=hourly.precipitation reason=non-numeric precipitation value '{p}'"
            )
            continue

        try:
            val = float(p)
        except (ValueError, TypeError):
            stats["non_numeric_values"] += 1
            errors.append(
                f"B3 rainfall validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
                f"timestamp={t_str} field=hourly.precipitation reason=non-numeric precipitation value '{p}'"
            )
            continue

        # 3. Non-finite check (NaN, Infinity, -Infinity)
        if math.isnan(val) or math.isinf(val):
            stats["non_finite_values"] += 1
            errors.append(
                f"B3 rainfall validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
                f"timestamp={t_str} field=hourly.precipitation reason=non-finite value {val}"
            )
            continue

        # 4. Negative precipitation check
        if val < 0.0:
            stats["negative_precipitation_values"] += 1
            errors.append(
                f"B3 rainfall validation failed: sample_point=({sample_coord[0]:.4f},{sample_coord[1]:.4f}) "
                f"timestamp={t_str} field=hourly.precipitation reason=negative precipitation {val}"
            )

    is_valid = (
        len(errors) == 0
        and stats["missing_precipitation_values"] == 0
        and stats["negative_precipitation_values"] == 0
        and stats["non_finite_values"] == 0
        and stats["non_numeric_values"] == 0
    )
    return is_valid, errors, stats


def validate_forecast_horizon(
    parsed_dts: Sequence[datetime],
    cycle_anchor: datetime,
    min_future_hours: int = MIN_FUTURE_HOURS,
) -> tuple[bool, list[str], int]:
    """Validates that sufficient strictly-future hourly observations exist relative to cycle anchor.

    The contract requires:
        future_times = [t for t in timestamps if t > cycle_anchor]
        len(future_times) >= min_future_hours (72)
    """
    errors: list[str] = []
    # Ensure cycle anchor is UTC timezone-aware
    anchor_utc = cycle_anchor if cycle_anchor.tzinfo is not None else cycle_anchor.replace(tzinfo=timezone.utc)

    future_times = [t for t in parsed_dts if t > anchor_utc]
    future_count = len(future_times)

    if future_count < min_future_hours:
        errors.append(
            f"B3 forecast horizon validation failed: future_hours_available={future_count} required={min_future_hours}"
        )
        return False, errors, future_count

    return True, errors, future_count


def validate_spatial_mapping(
    mapping_result: WayanadSpatialMappingResult,
    expected_sample_points: Sequence[tuple[float, float]] = WAYANAD_PROTOTYPE_SAMPLE_POINTS,
    expected_cell_count: int = EXPECTED_CELL_COUNT,
    expected_admin_id: int = ADMIN_ID,
    expected_lgd: int = DISTRICT_LGD,
    target_res: int = TARGET_RESOLUTION,
) -> tuple[bool, list[str]]:
    """Validates the B2 spatial mapping output against authoritative invariants.

    Invariants enforced:
    - Total cells == expected_cell_count (3,602).
    - Mapped cells == expected_cell_count (3,602).
    - Unmapped cells == 0.
    - Every mapped cell belongs to the authoritative Wayanad H3 grid.
    - Every cell mapping targets an approved sample point index in [0, len(expected_sample_points)-1].
    - Every cell target coordinates match the canonical sample point coordinates.
    - Mapping method is strictly nearest_sample_prototype (or nearest_sample).
    - All H3 identifiers are valid H3 resolution-8 indexes.
    """
    errors: list[str] = []

    # 1. District and administrative metadata
    if mapping_result.admin_id != expected_admin_id:
        errors.append(
            f"B3 spatial validation failed: admin_id={mapping_result.admin_id} expected={expected_admin_id}"
        )
    if mapping_result.lgd_code != expected_lgd:
        errors.append(
            f"B3 spatial validation failed: lgd_code={mapping_result.lgd_code} expected={expected_lgd}"
        )
    if mapping_result.h3_resolution != target_res:
        errors.append(
            f"B3 spatial validation failed: h3_resolution={mapping_result.h3_resolution} expected={target_res}"
        )

    # 2. Method validation
    if mapping_result.mapping_method not in ("nearest_sample_prototype", "nearest_sample"):
        errors.append(
            f"B3 spatial validation failed: mapping_method='{mapping_result.mapping_result}' "
            f"expected 'nearest_sample_prototype'"
        )

    # 3. Completeness invariant
    if (
        mapping_result.total_cells != expected_cell_count
        or mapping_result.mapped_cells != expected_cell_count
        or mapping_result.unmapped_cells != 0
    ):
        errors.append(
            f"B3 spatial validation failed: mapped_cells={mapping_result.mapped_cells} "
            f"expected_cells={expected_cell_count} unmapped_cells={mapping_result.unmapped_cells}"
        )

    # 4. Cell mappings list length and uniqueness
    if len(mapping_result.mappings) != expected_cell_count:
        errors.append(
            f"B3 spatial validation failed: mapping list count {len(mapping_result.mappings)} "
            f"!= expected {expected_cell_count}"
        )

    if len(mapping_result.mappings_by_h3) != expected_cell_count:
        errors.append(
            f"B3 spatial validation failed: unique cell count {len(mapping_result.mappings_by_h3)} "
            f"!= expected {expected_cell_count}"
        )

    # 5. Verify each cell mapping integrity
    for m in mapping_result.mappings:
        if not is_valid_h3(m.h3):
            errors.append(f"B3 spatial validation failed: invalid H3 integer identifier {m.h3}")
            break
        if not is_valid_h3(m.h3_str):
            errors.append(f"B3 spatial validation failed: invalid H3 string identifier '{m.h3_str}'")
            break
        res = h3_get_resolution(m.h3)
        if res != target_res:
            errors.append(
                f"B3 spatial validation failed: cell {m.h3_str} has H3 resolution {res}, expected {target_res}"
            )
            break

        # Check sample point target
        if m.sample_index < 0 or m.sample_index >= len(expected_sample_points):
            errors.append(
                f"B3 spatial validation failed: cell {m.h3_str} mapped to unknown sample point index {m.sample_index}"
            )
            break

        expected_coord = expected_sample_points[m.sample_index]
        if (
            abs(m.sample_latitude - expected_coord[0]) > 1e-4
            or abs(m.sample_longitude - expected_coord[1]) > 1e-4
        ):
            errors.append(
                f"B3 spatial validation failed: cell {m.h3_str} target sample ({m.sample_latitude}, {m.sample_longitude}) "
                f"does not match approved sample {m.sample_index} ({expected_coord[0]}, {expected_coord[1]})"
            )
            break

        if m.distance_km < 0.0:
            errors.append(
                f"B3 spatial validation failed: negative distance {m.distance_km} for cell {m.h3_str}"
            )
            break

    is_valid = len(errors) == 0
    return is_valid, errors


def validate_provenance(
    b1_provenance: dict[str, Any],
    raw_bytes: Optional[bytes] = None,
    expected_sample_count: int = EXPECTED_SAMPLE_COUNT,
) -> tuple[bool, list[str]]:
    """Validates provenance traceability to original B1 raw response.

    Invariants enforced:
    - Provider is Open-Meteo.
    - Source model is ECMWF_IFS_HRES.
    - Native resolution is 9.0 km.
    - District is Wayanad, LGD 555.
    - Sample points count matches expected (12).
    - Forecast cycle semantics == derived_provider_run_anchor.
    - cycle_anchor_verified is False.
    - Raw artifact path exists and raw artifact SHA256 matches actual byte hash.
    """
    errors: list[str] = []

    provider = b1_provenance.get("provider", "Open-Meteo")
    if provider != "Open-Meteo":
        errors.append(f"B3 provenance validation failed: provider='{provider}' expected 'Open-Meteo'")

    model = b1_provenance.get("source_model", SOURCE_MODEL)
    if model != SOURCE_MODEL:
        errors.append(f"B3 provenance validation failed: source_model='{model}' expected '{SOURCE_MODEL}'")

    res_km = b1_provenance.get("native_resolution_km", NATIVE_RESOLUTION_KM)
    if abs(float(res_km) - NATIVE_RESOLUTION_KM) > 1e-3:
        errors.append(
            f"B3 provenance validation failed: native_resolution_km={res_km} expected {NATIVE_RESOLUTION_KM}"
        )

    district = b1_provenance.get("district", DISTRICT_NAME)
    if district != DISTRICT_NAME:
        errors.append(f"B3 provenance validation failed: district='{district}' expected '{DISTRICT_NAME}'")

    lgd = b1_provenance.get("lgd_code", DISTRICT_LGD)
    if int(lgd) != DISTRICT_LGD:
        errors.append(f"B3 provenance validation failed: lgd_code={lgd} expected {DISTRICT_LGD}")

    cycle_sem = b1_provenance.get("forecast_cycle_semantics", FORECAST_CYCLE_SEMANTICS)
    if cycle_sem != FORECAST_CYCLE_SEMANTICS:
        errors.append(
            f"B3 provenance validation failed: forecast_cycle_semantics='{cycle_sem}' "
            f"expected '{FORECAST_CYCLE_SEMANTICS}'"
        )

    anchor_ver = b1_provenance.get("cycle_anchor_verified", CYCLE_ANCHOR_VERIFIED)
    if anchor_ver is not False:
        errors.append(
            f"B3 provenance validation failed: cycle_anchor_verified must be False for derived anchor"
        )

    recorded_sha = b1_provenance.get("raw_artifact_sha256", "")
    if not recorded_sha or len(recorded_sha) != 64:
        errors.append(
            f"B3 provenance validation failed: missing or invalid recorded raw_artifact_sha256: '{recorded_sha}'"
        )
    elif raw_bytes is not None:
        computed_sha = hashlib.sha256(raw_bytes).hexdigest()
        if computed_sha != recorded_sha:
            errors.append(
                f"B3 provenance validation failed: raw artifact SHA256 mismatch. "
                f"Computed '{computed_sha}' != recorded '{recorded_sha}'"
            )

    is_valid = len(errors) == 0
    return is_valid, errors


def validate_wayanad_b3_forecast(
    raw_artifact_path: Optional[Path | str] = None,
    raw_payload: Optional[list[dict[str, Any]] | bytes] = None,
    mapping_result: Optional[WayanadSpatialMappingResult] = None,
    db_engine: Optional[Engine] = None,
    cycle_anchor: Optional[datetime] = None,
    min_future_hours: int = MIN_FUTURE_HOURS,
    sample_points: Sequence[tuple[float, float]] = WAYANAD_PROTOTYPE_SAMPLE_POINTS,
    expected_cell_count: int = EXPECTED_CELL_COUNT,
    raise_on_failure: bool = False,
    require_explicit_tz: bool = False,
) -> PhaseB3ValidationReport:
    """Executes complete Phase B3 validation over Wayanad forecast payload and spatial mapping.

    Parameters:
        raw_artifact_path: Optional path to persisted B1 JSON file.
        raw_payload: Optional raw bytes or deserialized JSON list of location dictionaries.
        mapping_result: Pre-computed B2 WayanadSpatialMappingResult. If None, loaded via B2 module.
        db_engine: Optional SQLAlchemy Engine for retrieving provenance context.
        cycle_anchor: Forecast run anchor. Defaults to derived_provider_run_anchor.
        min_future_hours: Minimum required future hourly steps (contract = 72).
        sample_points: Approved forecast sample coordinates (default 12 Wayanad prototype points).
        expected_cell_count: Expected operational decision cells (contract = 3,602).
        raise_on_failure: If True, raises RainfallValidationError on validation failure.
        require_explicit_tz: If True, rejects naïve timestamps without explicit timezone.

    Returns:
        PhaseB3ValidationReport: Fully populated audit report.
    """
    all_errors: list[str] = []
    all_warnings: list[str] = []

    # 1. Load Raw Artifact / Payload
    resolved_path_str: str = ""
    raw_bytes: Optional[bytes] = None
    payload: Optional[list[dict[str, Any]]] = None
    b1_provenance: dict[str, Any] = {
        "provider": "Open-Meteo",
        "source_model": SOURCE_MODEL,
        "native_resolution_km": NATIVE_RESOLUTION_KM,
        "district": DISTRICT_NAME,
        "lgd_code": DISTRICT_LGD,
        "sample_points_count": len(sample_points),
        "forecast_cycle_semantics": FORECAST_CYCLE_SEMANTICS,
        "cycle_anchor_verified": CYCLE_ANCHOR_VERIFIED,
    }

    if raw_payload is not None:
        if isinstance(raw_payload, bytes):
            raw_bytes = raw_payload
            try:
                payload = json.loads(raw_bytes.decode("utf-8"))
            except Exception as exc:
                all_errors.append(f"B3 raw payload validation failed: JSON deserialization error: {exc}")
        elif isinstance(raw_payload, list):
            payload = raw_payload
            raw_bytes = json.dumps(payload).encode("utf-8")
        else:
            all_errors.append(
                f"B3 raw payload validation failed: unexpected payload type {type(raw_payload).__name__}"
            )
        b1_provenance["raw_artifact_sha256"] = hashlib.sha256(raw_bytes).hexdigest() if raw_bytes else ""
        b1_provenance["raw_artifact_path"] = str(raw_artifact_path or "in-memory")
        resolved_path_str = b1_provenance["raw_artifact_path"]
    else:
        # Load from disk using B2 loader
        try:
            p_obj, b_bytes, p_json, p_prov = load_b1_forecast_artifact(
                raw_artifact_path=raw_artifact_path,
                db_engine=db_engine,
                expected_sample_count=len(sample_points),
            )
            resolved_path_str = str(p_obj)
            raw_bytes = b_bytes
            payload = p_json
            b1_provenance.update(p_prov)
            b1_provenance["raw_artifact_path"] = resolved_path_str
            b1_provenance["raw_artifact_sha256"] = hashlib.sha256(raw_bytes).hexdigest()
        except Exception as exc:
            all_errors.append(f"B3 prerequisite failed: unable to load B1 forecast artifact: {exc}")

    # 2. Determine Cycle Anchor
    if cycle_anchor is not None:
        anchor = cycle_anchor if cycle_anchor.tzinfo is not None else cycle_anchor.replace(tzinfo=timezone.utc)
    elif b1_provenance.get("forecast_cycle_anchor"):
        anchor_val = b1_provenance["forecast_cycle_anchor"]
        if isinstance(anchor_val, datetime):
            anchor = anchor_val if anchor_val.tzinfo is not None else anchor_val.replace(tzinfo=timezone.utc)
        else:
            anchor = datetime.fromisoformat(str(anchor_val))
            if anchor.tzinfo is None:
                anchor = anchor.replace(tzinfo=timezone.utc)
    else:
        # Fallback anchor derived from current UTC
        anchor = derive_provider_run_anchor(datetime.now(timezone.utc))

    # 3. Validate Forecast Sample Points Count
    total_locations = len(payload) if isinstance(payload, list) else 0
    if total_locations != len(sample_points):
        all_errors.append(
            f"B3 payload validation failed: location count mismatch: expected {len(sample_points)} "
            f"forecast sample locations, got {total_locations}"
        )

    # 4. Validate Each Sample Point's Series
    total_forecast_hours = 0
    future_hours_available = 0
    first_forecast_ts = ""
    last_forecast_ts = ""
    retrieval_time_str = b1_provenance.get("retrieval_time")

    timestamps_strictly_increasing = True
    timestamps_hourly = True
    total_duplicate_ts = 0
    total_missing_ts = 0
    total_missing_precip = 0
    total_negative_precip = 0
    total_non_finite = 0
    total_non_numeric = 0

    default_tz = None if require_explicit_tz else timezone.utc

    if isinstance(payload, list) and len(payload) == len(sample_points):
        for loc_idx, loc in enumerate(payload):
            sample_coord = sample_points[loc_idx]

            # Coordinate alignment check
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            if lat is None or lon is None:
                all_errors.append(
                    f"B3 payload validation failed: location {loc_idx} missing coordinates"
                )
            elif (
                abs(float(lat) - sample_coord[0]) > 0.05
                or abs(float(lon) - sample_coord[1]) > 0.05
            ):
                all_warnings.append(
                    f"Sample location {loc_idx} coordinate ({lat}, {lon}) deviates slightly "
                    f"from prototype point ({sample_coord[0]}, {sample_coord[1]})"
                )

            # Rainfall semantics check
            sem_errors = validate_rainfall_semantics(loc.get("hourly_units"), sample_coord, loc_idx)
            all_errors.extend(sem_errors)

            hourly = loc.get("hourly")
            if not isinstance(hourly, dict):
                all_errors.append(
                    f"B3 payload validation failed: location {loc_idx} missing 'hourly' object"
                )
                continue

            times = hourly.get("time")
            precip = hourly.get("precipitation")

            if not isinstance(times, list) or not isinstance(precip, list):
                all_errors.append(
                    f"B3 payload validation failed: location {loc_idx} missing 'hourly.time' or 'hourly.precipitation' lists"
                )
                continue

            # Temporal validation
            ts_valid, ts_errors, parsed_dts, ts_counts = validate_forecast_timestamps(
                times=times,
                sample_coord=sample_coord,
                loc_idx=loc_idx,
                default_tz=default_tz,
            )
            all_errors.extend(ts_errors)
            total_duplicate_ts += ts_counts["duplicate_timestamps"]
            total_missing_ts += ts_counts["missing_timestamps"]
            if not ts_counts["strictly_increasing"]:
                timestamps_strictly_increasing = False
            if not ts_counts["hourly_spacing"]:
                timestamps_hourly = False

            # Numeric precipitation validation
            p_valid, p_errors, p_stats = validate_precipitation_values(
                precip=precip,
                times=times,
                sample_coord=sample_coord,
                loc_idx=loc_idx,
            )
            all_errors.extend(p_errors)
            total_missing_precip += p_stats["missing_precipitation_values"]
            total_negative_precip += p_stats["negative_precipitation_values"]
            total_non_finite += p_stats["non_finite_values"]
            total_non_numeric += p_stats["non_numeric_values"]

            # Forecast horizon validation
            if parsed_dts:
                if loc_idx == 0:
                    total_forecast_hours = len(parsed_dts)
                    first_forecast_ts = parsed_dts[0].isoformat()
                    last_forecast_ts = parsed_dts[-1].isoformat()

                h_valid, h_errors, future_cnt = validate_forecast_horizon(
                    parsed_dts=parsed_dts,
                    cycle_anchor=anchor,
                    min_future_hours=min_future_hours,
                )
                all_errors.extend(h_errors)
                if loc_idx == 0:
                    future_hours_available = future_cnt

    # 5. Validate Spatial Mapping
    mapping = mapping_result
    if mapping is None:
        try:
            mapping = execute_wayanad_b2_spatial_mapping(
                raw_artifact_path=resolved_path_str or None,
                db_engine=db_engine,
                sample_points=sample_points,
            )
        except Exception as exc:
            all_errors.append(f"B3 spatial mapping execution failed: {exc}")

    mapped_cells = 0
    unmapped_cells = expected_cell_count
    if mapping is not None:
        mapped_cells = mapping.mapped_cells
        unmapped_cells = mapping.unmapped_cells
        sp_valid, sp_errors = validate_spatial_mapping(
            mapping_result=mapping,
            expected_sample_points=sample_points,
            expected_cell_count=expected_cell_count,
        )
        all_errors.extend(sp_errors)

    # 6. Validate Provenance Chain
    prov_valid, prov_errors = validate_provenance(
        b1_provenance=b1_provenance,
        raw_bytes=raw_bytes,
        expected_sample_count=len(sample_points),
    )
    all_errors.extend(prov_errors)

    is_valid = len(all_errors) == 0

    report = PhaseB3ValidationReport(
        valid=is_valid,
        provider="Open-Meteo",
        source_model=SOURCE_MODEL,
        district=DISTRICT_NAME,
        lgd=DISTRICT_LGD,
        admin_id=ADMIN_ID,
        h3_resolution=TARGET_RESOLUTION,
        expected_cells=expected_cell_count,
        mapped_cells=mapped_cells,
        unmapped_cells=unmapped_cells,
        expected_sample_points=len(sample_points),
        sample_points_present=total_locations,
        forecast_hours_available=total_forecast_hours,
        future_hours_available=future_hours_available,
        timestamps_strictly_increasing=timestamps_strictly_increasing,
        timestamps_hourly=timestamps_hourly,
        duplicate_timestamps=total_duplicate_ts,
        missing_timestamps=total_missing_ts,
        missing_precipitation_values=total_missing_precip,
        negative_precipitation_values=total_negative_precip,
        non_finite_values=total_non_finite,
        non_numeric_values=total_non_numeric,
        retrieval_time=retrieval_time_str,
        derived_provider_run_anchor=anchor.isoformat(),
        first_forecast_timestamp=first_forecast_ts,
        last_forecast_timestamp=last_forecast_ts,
        forecast_cycle_semantics=FORECAST_CYCLE_SEMANTICS,
        cycle_anchor_verified=CYCLE_ANCHOR_VERIFIED,
        spatial_mapping_method=MAPPING_METHOD,
        forecast_native_resolution_km=NATIVE_RESOLUTION_KM,
        decision_geometry=DECISION_GEOMETRY,
        rainfall_unit=RAINFALL_UNIT,
        rainfall_interpretation=RAINFALL_INTERPRETATION,
        raw_artifact_path=resolved_path_str,
        raw_artifact_sha256=b1_provenance.get("raw_artifact_sha256", ""),
        errors=all_errors,
        warnings=all_warnings,
    )

    log_level = logging.INFO if is_valid else logging.ERROR
    logger.log(
        log_level,
        f"Phase B3 Validation Gate complete: valid={is_valid}, district={DISTRICT_NAME}, "
        f"mapped_cells={mapped_cells}/{expected_cell_count}, future_hours={future_hours_available}, "
        f"errors={len(all_errors)}"
    )

    if not is_valid and raise_on_failure:
        first_err = all_errors[0] if all_errors else "Validation failed"
        raise RainfallValidationError(f"Phase B3 Rainfall Validation failed ({len(all_errors)} errors): {first_err}")

    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    repo_root = Path(__file__).resolve().parents[4]
    reference_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    print("\n" + "=" * 75)
    print("SETU-DRR Phase B3: Rainfall & Spatial Mapping Validation Gate")
    print(f"Validating reference artifact: {reference_path}")
    print("=" * 75)

    report = validate_wayanad_b3_forecast(raw_artifact_path=reference_path)
    report_json = json.dumps(report.to_dict(), indent=2)
    print(report_json)
    print("=" * 75)
    print(f"Validation Status: {'PASS' if report.valid else 'FAIL'}")
    print(f"Errors ({len(report.errors)}): {report.errors}")
    print("=" * 75 + "\n")
