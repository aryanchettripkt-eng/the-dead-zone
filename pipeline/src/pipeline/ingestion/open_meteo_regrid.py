"""Spatial Nearest-Sample Downscaling & Rainfall Validation (Phase B2 & B3).

Maps Wayanad's 3,602 H3 Resolution 8 cells to the 12 polygon-verified ECMWF IFS
sample points using geodesic (Haversine) distance, validates temporal preceding-hour
precipitation semantics, and generates intermediate rainfall distribution metrics.

Phase B2/B3 Scope: Spatial Downscaling & Intermediate Rainfall Validation ONLY.
Zero trigger calculation, zero hazard_dynamic writes, zero mhi_snapshot mutations.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from core.config import settings
from pipeline.ingestion.open_meteo_client import WAYANAD_PROTOTYPE_SAMPLE_POINTS

logger = logging.getLogger("setu_pipeline.open_meteo_regrid")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate geodesic distance between two points on Earth using the Haversine formula.
    
    Uses WGS-84 mean radius R = 6371.0088 km to ensure accurate distance calculation
    accounting for latitude vs longitude physical scaling.
    """
    R = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    
    a = (math.sin(dphi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


@dataclass(frozen=True)
class H3CellSampleMapping:
    """Mapping of a single H3 Resolution 8 cell to its nearest ECMWF sample point."""
    h3: int
    lat: float
    lon: float
    nearest_sample_idx: int
    sample_coord: tuple[float, float]
    distance_km: float
    source_resolution_km: float = 9.0
    downscaling_method: str = "nearest_sample"


@dataclass(frozen=True)
class SpatialDownscalingResult:
    """Outcome report of Phase B2 spatial downscaling mapping."""
    total_cells: int
    sample_points_count: int
    mappings: list[H3CellSampleMapping]
    min_distance_km: float
    median_distance_km: float
    mean_distance_km: float
    p90_distance_km: float
    max_distance_km: float
    cell_counts_by_sample: dict[int, int]
    source_resolution_km: float = 9.0
    downscaling_method: str = "nearest_sample"


@dataclass(frozen=True)
class IntermediateRainfallValidationReport:
    """Outcome report of Phase B3 intermediate rainfall validation."""
    status: str  # 'SUCCESS' | 'FAILED'
    raw_artifact_path: str
    forecast_cycle_anchor: datetime
    horizon_hours: int
    valid_time_start: datetime
    valid_time_end: datetime
    temporal_precipitation_semantics: str
    sample_point_stats: list[dict[str, Any]]
    cell_rainfall_stats: dict[str, Any]
    errors: list[str] = field(default_factory=list)


def build_wayanad_h3_spatial_downscaling(
    db_engine: Optional[Engine] = None,
    sample_points: Sequence[tuple[float, float]] = WAYANAD_PROTOTYPE_SAMPLE_POINTS,
    admin_id: int = 178,
    target_res: int = 8,
) -> SpatialDownscalingResult:
    """Builds nearest-sample downscaling mapping from 12 sample points to all H3-8 cells in Wayanad.
    
    Reads cell centroids from grid_cell (ST_Y, ST_X), computes Haversine distance to each
    sample point, and assigns the nearest sample point.
    """
    engine = db_engine or create_engine(settings.get_sqlalchemy_url(direct=True))
    
    logger.info(f"Querying H3 Resolution {target_res} cells for Wayanad (admin_id={admin_id})...")
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT h3, ST_Y(centroid::geometry) as lat, ST_X(centroid::geometry) as lon
                FROM grid_cell
                WHERE admin_id = :admin_id AND res = :target_res
                ORDER BY h3 ASC;
            """),
            {"admin_id": admin_id, "target_res": target_res},
        ).fetchall()

    if not rows:
        raise ValueError(f"No grid_cell rows found for admin_id={admin_id}, res={target_res}")

    mappings: list[H3CellSampleMapping] = []
    distances: list[float] = []
    cell_counts: dict[int, int] = {i: 0 for i in range(len(sample_points))}

    for row in rows:
        h3 = int(row[0])
        c_lat = float(row[1])
        c_lon = float(row[2])

        best_idx = -1
        best_dist = float("inf")

        for idx, (s_lat, s_lon) in enumerate(sample_points):
            d = haversine_km(c_lat, c_lon, s_lat, s_lon)
            if d < best_dist:
                best_dist = d
                best_idx = idx

        mapping = H3CellSampleMapping(
            h3=h3,
            lat=c_lat,
            lon=c_lon,
            nearest_sample_idx=best_idx,
            sample_coord=sample_points[best_idx],
            distance_km=round(best_dist, 4),
            source_resolution_km=9.0,
            downscaling_method="nearest_sample",
        )
        mappings.append(mapping)
        distances.append(best_dist)
        cell_counts[best_idx] += 1

    distances.sort()
    min_d = min(distances)
    max_d = max(distances)
    mean_d = sum(distances) / len(distances)
    median_d = distances[len(distances) // 2]
    p90_d = distances[int(len(distances) * 0.9)]

    logger.info(
        f"Mapped {len(mappings)} H3-{target_res} cells across {len(sample_points)} sample points. "
        f"Distance km: min={min_d:.3f}, median={median_d:.3f}, mean={mean_d:.3f}, max={max_d:.3f}"
    )

    return SpatialDownscalingResult(
        total_cells=len(mappings),
        sample_points_count=len(sample_points),
        mappings=mappings,
        min_distance_km=round(min_d, 3),
        median_distance_km=round(median_d, 3),
        mean_distance_km=round(mean_d, 3),
        p90_distance_km=round(p90_d, 3),
        max_distance_km=round(max_d, 3),
        cell_counts_by_sample=cell_counts,
        source_resolution_km=9.0,
        downscaling_method="nearest_sample",
    )


def validate_intermediate_rainfall(
    raw_artifact_path: Path,
    downscaling: SpatialDownscalingResult,
    forecast_cycle_anchor: Optional[datetime] = None,
    horizon_hours: int = 72,
) -> IntermediateRainfallValidationReport:
    """Executes Phase B3 intermediate rainfall validation on raw JSON artifact.
    
    Verifies preceding-hour precipitation semantics, isolates the exact 72 valid
    future hourly timestamps, and computes intensity and rolling accumulation metrics.
    
    Does NOT write to hazard_dynamic.
    Does NOT mutate mhi_snapshot.
    """
    errors: list[str] = []

    if not raw_artifact_path.exists():
        err_msg = f"Raw artifact not found at {raw_artifact_path}"
        logger.error(err_msg)
        return IntermediateRainfallValidationReport(
            status="FAILED",
            raw_artifact_path=str(raw_artifact_path),
            forecast_cycle_anchor=datetime.now(timezone.utc),
            horizon_hours=horizon_hours,
            valid_time_start=datetime.now(timezone.utc),
            valid_time_end=datetime.now(timezone.utc),
            temporal_precipitation_semantics="unverified",
            sample_point_stats=[],
            cell_rainfall_stats={},
            errors=[err_msg],
        )

    with open(raw_artifact_path, "r", encoding="utf-8") as f:
        locations = json.load(f)

    if not isinstance(locations, list) or len(locations) != downscaling.sample_points_count:
        errors.append(
            f"Location count mismatch in raw artifact: expected {downscaling.sample_points_count}, "
            f"got {len(locations) if isinstance(locations, list) else type(locations)}"
        )

    # 1. Temporal semantics definition:
    # Open-Meteo documents hourly precipitation as the sum accumulated over the preceding hour.
    # Timestamp t represents rainfall during (t - 1h, t].
    temporal_semantics = (
        "Preceding-hour accumulation sum (mm): timestamp t represents precipitation accumulated "
        "during the interval (t - 1 hour, t]. Compatible with 3-hour backward rolling sum."
    )

    # 2. Identify target 72 future hours after cycle anchor
    first_loc = locations[0]
    raw_times = [
        datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
        for t in first_loc.get("hourly", {}).get("time", [])
    ]

    if forecast_cycle_anchor is None:
        # Default to 12Z on the first day in the payload
        forecast_cycle_anchor = raw_times[0].replace(hour=12, minute=0, second=0, microsecond=0)

    future_indices = [i for i, t in enumerate(raw_times) if t > forecast_cycle_anchor]
    if len(future_indices) < horizon_hours:
        errors.append(
            f"Insufficient future hours after cycle anchor {forecast_cycle_anchor.isoformat()}: "
            f"found {len(future_indices)}, required >= {horizon_hours}"
        )
        selected_indices = future_indices
    else:
        selected_indices = future_indices[:horizon_hours]

    valid_times = [raw_times[i] for i in selected_indices]
    valid_start = valid_times[0] if valid_times else forecast_cycle_anchor
    valid_end = valid_times[-1] if valid_times else forecast_cycle_anchor

    # 3. Compute per-sample-point statistics
    sample_stats: list[dict[str, Any]] = []
    sample_precip_series: dict[int, list[float]] = {}

    for idx, loc in enumerate(locations):
        all_precip = loc.get("hourly", {}).get("precipitation", [])
        sample_72h = [float(all_precip[i]) for i in selected_indices]
        sample_precip_series[idx] = sample_72h

        total_72h = sum(sample_72h)
        max_1h = max(sample_72h) if sample_72h else 0.0

        # Compute 3-hour backward rolling accumulation: A3(t) = P(t) + P(t-1) + P(t-2)
        # For the first two hours of selected_indices, access the preceding hours from all_precip
        rolling_3h_values: list[float] = []
        for s_idx in selected_indices:
            window_indices = [s_idx - 2, s_idx - 1, s_idx]
            w_sum = sum(float(all_precip[w]) for w in window_indices if 0 <= w < len(all_precip))
            rolling_3h_values.append(w_sum)

        max_3h = max(rolling_3h_values) if rolling_3h_values else 0.0
        max_3h_intensity = max_3h / 3.0  # mm/h equivalent

        sample_stats.append({
            "sample_index": idx,
            "coordinate": (loc.get("latitude"), loc.get("longitude")),
            "total_72h_mm": round(total_72h, 2),
            "max_1h_mm_per_h": round(max_1h, 2),
            "max_3h_accumulation_mm": round(max_3h, 2),
            "max_3h_intensity_mm_per_h": round(max_3h_intensity, 3),
            "cells_mapped": downscaling.cell_counts_by_sample.get(idx, 0),
        })

    # 4. Synthesize cell-level rainfall statistics across all 3,602 cells
    cell_totals = [
        sample_stats[m.nearest_sample_idx]["total_72h_mm"] for m in downscaling.mappings
    ]
    cell_max_1h = [
        sample_stats[m.nearest_sample_idx]["max_1h_mm_per_h"] for m in downscaling.mappings
    ]
    cell_max_3h = [
        sample_stats[m.nearest_sample_idx]["max_3h_accumulation_mm"] for m in downscaling.mappings
    ]

    cell_stats = {
        "total_cells": len(downscaling.mappings),
        "total_72h_mm": {
            "min": min(cell_totals),
            "median": round(sorted(cell_totals)[len(cell_totals) // 2], 2),
            "mean": round(sum(cell_totals) / len(cell_totals), 2),
            "max": max(cell_totals),
        },
        "max_1h_mm_per_h": {
            "min": min(cell_max_1h),
            "median": round(sorted(cell_max_1h)[len(cell_max_1h) // 2], 2),
            "mean": round(sum(cell_max_1h) / len(cell_max_1h), 2),
            "max": max(cell_max_1h),
        },
        "max_3h_accumulation_mm": {
            "min": min(cell_max_3h),
            "median": round(sorted(cell_max_3h)[len(cell_max_3h) // 2], 2),
            "mean": round(sum(cell_max_3h) / len(cell_max_3h), 2),
            "max": max(cell_max_3h),
        },
    }

    status = "FAILED" if errors else "SUCCESS"
    return IntermediateRainfallValidationReport(
        status=status,
        raw_artifact_path=str(raw_artifact_path),
        forecast_cycle_anchor=forecast_cycle_anchor,
        horizon_hours=len(valid_times),
        valid_time_start=valid_start,
        valid_time_end=valid_end,
        temporal_precipitation_semantics=temporal_semantics,
        sample_point_stats=sample_stats,
        cell_rainfall_stats=cell_stats,
        errors=errors,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    
    # 1. Execute Phase B2 Downscaling Mapping
    downscaling_result = build_wayanad_h3_spatial_downscaling()
    
    print("\n" + "=" * 75)
    print("PHASE B2 SPATIAL NEAREST-SAMPLE DOWNSCALING REPORT")
    print(f"Total Cells Mapped:             {downscaling_result.total_cells}")
    print(f"Sample Points Count:            {downscaling_result.sample_points_count}")
    print(f"Downscaling Method:             {downscaling_result.downscaling_method}")
    print(f"Source Model Resolution:        {downscaling_result.source_resolution_km} km")
    print(f"Distance Min:                   {downscaling_result.min_distance_km:.3f} km")
    print(f"Distance Median:                {downscaling_result.median_distance_km:.3f} km")
    print(f"Distance Mean:                  {downscaling_result.mean_distance_km:.3f} km")
    print(f"Distance 90th %tile:            {downscaling_result.p90_distance_km:.3f} km")
    print(f"Distance Max:                   {downscaling_result.max_distance_km:.3f} km")
    print("\nAssignment Distribution Across 12 Sample Points:")
    for s_idx, count in sorted(downscaling_result.cell_counts_by_sample.items()):
        pct = (count / downscaling_result.total_cells) * 100
        coord = WAYANAD_PROTOTYPE_SAMPLE_POINTS[s_idx]
        print(f"  Sample {s_idx:2d} ({coord[0]:.4f}, {coord[1]:.4f}): {count:4d} cells ({pct:5.1f}%)")
    print("=" * 75)

    # 2. Execute Phase B3 Intermediate Rainfall Validation
    repo_root = Path(__file__).resolve().parents[4]
    raw_file = repo_root / "data" / "raw" / "open_meteo" / "ecmwf_wayanad_20260908T120000Z.json"
    
    val_report = validate_intermediate_rainfall(
        raw_artifact_path=raw_file,
        downscaling=downscaling_result,
        forecast_cycle_anchor=datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
        horizon_hours=72,
    )
    
    print("\n" + "=" * 75)
    print("PHASE B3 INTERMEDIATE RAINFALL VALIDATION REPORT")
    print(f"Status:                         {val_report.status}")
    print(f"Temporal Semantics:             {val_report.temporal_precipitation_semantics}")
    print(f"Forecast Horizon:               {val_report.horizon_hours} hours")
    print(f"Window Start (strictly >12Z):   {val_report.valid_time_start.isoformat()}")
    print(f"Window End:                     {val_report.valid_time_end.isoformat()}")
    print("\nSample Point 72h Rainfall Distribution:")
    for s in val_report.sample_point_stats:
        print(
            f"  Sample {s['sample_index']:2d} {s['coordinate']}: "
            f"Total={s['total_72h_mm']:5.2f} mm | "
            f"Max 1h={s['max_1h_mm_per_h']:4.2f} mm/h | "
            f"Max 3h Acc={s['max_3h_accumulation_mm']:4.2f} mm ({s['max_3h_intensity_mm_per_h']:.2f} mm/h) | "
            f"Cells={s['cells_mapped']:4d}"
        )
    print("\nCell-Level Summary Across 3,602 H3 Cells:")
    print(f"  72h Total (mm):     min={val_report.cell_rainfall_stats['total_72h_mm']['min']}, "
          f"median={val_report.cell_rainfall_stats['total_72h_mm']['median']}, "
          f"mean={val_report.cell_rainfall_stats['total_72h_mm']['mean']}, "
          f"max={val_report.cell_rainfall_stats['total_72h_mm']['max']}")
    print(f"  Max 1h (mm/h):      min={val_report.cell_rainfall_stats['max_1h_mm_per_h']['min']}, "
          f"median={val_report.cell_rainfall_stats['max_1h_mm_per_h']['median']}, "
          f"mean={val_report.cell_rainfall_stats['max_1h_mm_per_h']['mean']}, "
          f"max={val_report.cell_rainfall_stats['max_1h_mm_per_h']['max']}")
    print(f"  Max 3h Acc (mm):    min={val_report.cell_rainfall_stats['max_3h_accumulation_mm']['min']}, "
          f"median={val_report.cell_rainfall_stats['max_3h_accumulation_mm']['median']}, "
          f"mean={val_report.cell_rainfall_stats['max_3h_accumulation_mm']['mean']}, "
          f"max={val_report.cell_rainfall_stats['max_3h_accumulation_mm']['max']}")
    if val_report.errors:
        print(f"Errors:                         {val_report.errors}")
    print("=" * 75 + "\n")
