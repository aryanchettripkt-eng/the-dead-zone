"""Wayanad H3 Spatial Nearest-Sample Mapping (Phase B2).

Maps Wayanad's 3,602 H3 Resolution 8 operational decision cells to the 12
approved, polygon-verified Open-Meteo ECMWF IFS HRES forecast sample points
using a geographically correct geodesic (Haversine) distance calculation.

Phase B2 Scope: Spatial Mapping and In-Memory Provenance Assignment ONLY.
- Consumes already-persisted Phase B1 raw forecast artifact.
- Zero live external HTTP calls.
- Zero rainfall trigger calculation.
- Zero T_flood calculation.
- Zero MHI calculation.
- Zero writes to `hazard_dynamic` or `mhi_snapshot`.

Scientific Invariant:
H3-8 is the decision/reporting geometry; ECMWF IFS HRES remains ~9 km native resolution.
This is a deterministic nearest-sample assignment (nearest_sample_prototype), NOT
fine-scale meteorological interpolation or downscaling.
"""

from __future__ import annotations

import hashlib
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
from core.h3_utils import (
    h3_get_resolution,
    h3_to_centroid,
    h3_to_str,
    is_valid_h3,
)
from pipeline.ingestion.open_meteo_client import (
    ADMIN_ID,
    DISTRICT_LGD,
    DISTRICT_NAME,
    OPEN_METEO_ECMWF_ENDPOINT,
    SOURCE_ID,
    SOURCE_MODEL,
    NATIVE_RESOLUTION_KM,
    WAYANAD_PROTOTYPE_SAMPLE_POINTS,
)

logger = logging.getLogger("setu_pipeline.open_meteo_regrid")

MAPPING_METHOD = "nearest_sample_prototype"
EXPECTED_CELL_COUNT = 3602
EXPECTED_SAMPLE_COUNT = 12
TARGET_RESOLUTION = 8


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate geodesic distance between two coordinates using the Haversine formula.

    Uses WGS-84 mean Earth radius R = 6371.0088 km to ensure accurate distance
    calculation accounting for spherical curvature and longitude scaling.
    """
    R = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


@dataclass(frozen=True)
class H3CellSampleMapping:
    """Mapping of a single H3 Resolution 8 cell to its nearest ECMWF forecast sample point."""
    h3: int
    h3_str: str
    lat: float
    lon: float
    sample_index: int
    sample_latitude: float
    sample_longitude: float
    distance_km: float
    mapping_method: str = MAPPING_METHOD


@dataclass(frozen=True)
class WayanadSpatialMappingResult:
    """Auditable in-memory spatial mapping artifact produced by Phase B2."""
    district: str
    lgd_code: int
    admin_id: int
    h3_resolution: int
    total_cells: int
    mapped_cells: int
    unmapped_cells: int
    sample_points_count: int
    mappings: list[H3CellSampleMapping]
    mappings_by_h3: dict[int, H3CellSampleMapping]
    mappings_by_h3_str: dict[str, H3CellSampleMapping]
    cell_counts_by_sample: dict[int, int]
    min_distance_km: float
    median_distance_km: float
    mean_distance_km: float
    p90_distance_km: float
    max_distance_km: float
    mapping_method: str = MAPPING_METHOD
    provenance: dict[str, Any] = field(default_factory=dict)


def load_authoritative_wayanad_grid(
    db_engine: Optional[Engine] = None,
    admin_id: int = ADMIN_ID,
    target_res: int = TARGET_RESOLUTION,
    expected_lgd: int = DISTRICT_LGD,
    expected_district_name: str = DISTRICT_NAME,
    expected_cell_count: int = EXPECTED_CELL_COUNT,
    grid_cells_override: Optional[Sequence[tuple[int, float, float]]] = None,
) -> list[tuple[int, float, float]]:
    """Loads authoritative Wayanad H3-8 decision cells from database.

    Enforces district metadata invariants and verifies cell count == 3,602.
    Does NOT regenerate the grid.

    Returns:
        List of (h3_int, lat, lon) tuples ordered deterministically by h3 ascending.
    """
    if grid_cells_override is not None:
        cells = list(grid_cells_override)
        if len(cells) != expected_cell_count:
            raise ValueError(
                f"B2 grid invariant failed: expected Wayanad H3-{target_res} grid with "
                f"{expected_cell_count} cells, found {len(cells)} in override."
            )
        return cells

    engine = db_engine
    if engine is None:
        db_url = settings.get_sqlalchemy_url(direct=True)
        engine = create_engine(db_url)

    logger.info(f"Loading authoritative Wayanad H3-{target_res} grid (admin_id={admin_id})...")

    with engine.connect() as conn:
        # 1. Verify administrative boundary invariants
        try:
            admin_row = conn.execute(
                text("SELECT id, name, lgd_code FROM admin_boundary WHERE id = :admin_id"),
                {"admin_id": admin_id},
            ).mappings().first()

            if admin_row is not None:
                if admin_row["lgd_code"] != expected_lgd:
                    raise ValueError(
                        f"B2 admin boundary invariant failed: admin_id={admin_id} has LGD "
                        f"{admin_row['lgd_code']}, expected {expected_lgd}."
                    )
                if expected_district_name.lower() not in admin_row["name"].lower():
                    raise ValueError(
                        f"B2 admin boundary invariant failed: admin_id={admin_id} is named "
                        f"'{admin_row['name']}', expected '{expected_district_name}'."
                    )
        except Exception as exc:
            # If admin_boundary query raises an assertion or DB error, propagate or log
            if isinstance(exc, ValueError):
                raise
            logger.warning(f"Could not verify admin_boundary table ({exc}), proceeding to grid_cell query.")

        # 2. Query grid_cell table
        try:
            rows = conn.execute(
                text("""
                    SELECT h3,
                           ST_Y(centroid::geometry) as lat,
                           ST_X(centroid::geometry) as lon
                    FROM grid_cell
                    WHERE admin_id = :admin_id AND res = :target_res
                    ORDER BY h3 ASC;
                """),
                {"admin_id": admin_id, "target_res": target_res},
            ).fetchall()
        except Exception:
            # SQLite / fallback without PostGIS ST_Y / ST_X
            raw_h3_rows = conn.execute(
                text("""
                    SELECT h3
                    FROM grid_cell
                    WHERE admin_id = :admin_id AND res = :target_res
                    ORDER BY h3 ASC;
                """),
                {"admin_id": admin_id, "target_res": target_res},
            ).fetchall()
            rows = []
            for r in raw_h3_rows:
                h_val = int(r[0])
                c_lon, c_lat = h3_to_centroid(h_val)
                rows.append((h_val, c_lat, c_lon))

    cells: list[tuple[int, float, float]] = []
    for r in rows:
        h3_val = int(r[0])
        lat_val = float(r[1])
        lon_val = float(r[2])
        cells.append((h3_val, lat_val, lon_val))

    if len(cells) != expected_cell_count:
        raise ValueError(
            f"B2 grid invariant failed: expected Wayanad H3-{target_res} grid with "
            f"{expected_cell_count} cells, found {len(cells)}."
        )

    return cells


def load_b1_forecast_artifact(
    raw_artifact_path: Optional[Path | str] = None,
    db_engine: Optional[Engine] = None,
    expected_sample_count: int = EXPECTED_SAMPLE_COUNT,
) -> tuple[Path, bytes, list[dict[str, Any]], dict[str, Any]]:
    """Loads and validates the completed Phase B1 Open-Meteo raw JSON artifact.

    Enforces:
    - Raw artifact exists on disk.
    - Zero live HTTP network requests.
    - JSON structure is valid and contains expected sample locations.
    - Reuses B1 provenance metadata from DB or artifact context.
    """
    resolved_path: Optional[Path] = None

    if raw_artifact_path is not None:
        p = Path(raw_artifact_path)
        if p.exists():
            resolved_path = p
        else:
            raise FileNotFoundError(
                f"B2 prerequisite missing: B1 Open-Meteo raw artifact not found at '{raw_artifact_path}'. "
                f"B2 requires the completed B1 raw artifact and does not perform live network requests."
            )

    # If not explicitly passed, locate from database source_snapshot or repo defaults
    if resolved_path is None and db_engine is not None:
        try:
            with db_engine.connect() as conn:
                snap_row = conn.execute(
                    text("""
                        SELECT id, uri, sha256, metadata
                        FROM source_snapshot
                        WHERE source_id = 'open_meteo_ecmwf'
                        ORDER BY retrieved_at DESC LIMIT 1;
                    """)
                ).mappings().first()
                if snap_row and snap_row["uri"]:
                    uri_str = snap_row["uri"]
                    if uri_str.startswith("file:///"):
                        candidate = Path(uri_str.replace("file:///", ""))
                        if candidate.exists():
                            resolved_path = candidate
        except Exception as exc:
            logger.debug(f"Could not query source_snapshot for artifact path: {exc}")

    # Default fallback paths in local repository
    if resolved_path is None:
        repo_root = Path(__file__).resolve().parents[4]
        candidate_paths = [
            settings.DATA_ROOT / "raw" / "open_meteo" / "ecmwf_wayanad_20260908T120000Z.json",
            repo_root / "data" / "raw" / "open_meteo" / "ecmwf_wayanad_20260908T120000Z.json",
        ]
        for c in candidate_paths:
            if c.exists():
                resolved_path = c
                break

    if resolved_path is None or not resolved_path.exists():
        raise FileNotFoundError(
            "B2 prerequisite missing: B1 Open-Meteo raw artifact not found. "
            "B2 requires the completed B1 raw artifact and does not perform live network requests."
        )

    raw_bytes = resolved_path.read_bytes()
    raw_sha = hashlib.sha256(raw_bytes).hexdigest()

    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"B2 payload validation failed: Malformed JSON in B1 artifact '{resolved_path}': {exc}")

    if not isinstance(payload, list):
        raise ValueError(f"B2 payload validation failed: Expected list of sample locations, got {type(payload).__name__}")

    if len(payload) != expected_sample_count:
        raise ValueError(
            f"B2 sample-point invariant failed: expected {expected_sample_count} forecast sample locations, "
            f"found {len(payload)} in artifact."
        )

    # Check that each location entry has coordinates and hourly data
    for idx, loc in enumerate(payload):
        if not isinstance(loc, dict) or "latitude" not in loc or "longitude" not in loc:
            raise ValueError(f"B2 payload validation failed: Location {idx} missing coordinates.")
        if "hourly" not in loc or not isinstance(loc["hourly"], dict):
            raise ValueError(f"B2 payload validation failed: Location {idx} missing 'hourly' data.")

    # Retrieve associated B1 snapshot/run metadata if DB available
    b1_provenance: dict[str, Any] = {
        "raw_artifact_path": str(resolved_path),
        "raw_artifact_sha256": raw_sha,
        "raw_artifact_bytes": len(raw_bytes),
    }

    if db_engine is not None:
        try:
            with db_engine.connect() as conn:
                snap = conn.execute(
                    text("""
                        SELECT s.id as snapshot_id, s.metadata, r.id as run_id
                        FROM source_snapshot s
                        LEFT JOIN pipeline_run r ON r.source_snapshot_id = s.id
                        WHERE s.sha256 = :sha
                        ORDER BY s.retrieved_at DESC LIMIT 1;
                    """),
                    {"sha": raw_sha},
                ).mappings().first()
                if snap:
                    b1_provenance["source_snapshot_id"] = snap["snapshot_id"]
                    b1_provenance["pipeline_run_id"] = snap["run_id"]
                    if snap["metadata"]:
                        meta = snap["metadata"] if isinstance(snap["metadata"], dict) else json.loads(snap["metadata"])
                        b1_provenance["forecast_cycle_anchor"] = meta.get("forecast_cycle_anchor")
        except Exception as exc:
            logger.debug(f"Could not load B1 DB provenance: {exc}")

    return resolved_path, raw_bytes, payload, b1_provenance


def execute_wayanad_b2_spatial_mapping(
    raw_artifact_path: Optional[Path | str] = None,
    db_engine: Optional[Engine] = None,
    sample_points: Sequence[tuple[float, float]] = WAYANAD_PROTOTYPE_SAMPLE_POINTS,
    admin_id: int = ADMIN_ID,
    target_res: int = TARGET_RESOLUTION,
    grid_cells_override: Optional[Sequence[tuple[int, float, float]]] = None,
) -> WayanadSpatialMappingResult:
    """Executes Phase B2 spatial nearest-sample assignment for Wayanad.

    Algorithm:
        1. Load and validate the completed B1 forecast artifact (fail explicitly if missing).
        2. Validate the 12 approved sample points.
        3. Load the authoritative Wayanad H3-8 decision grid (verify exactly 3,602 cells).
        4. For every cell, compute geodesic (Haversine) distance to each sample point.
        5. Assign cell to nearest sample point with deterministic tie-breaking.
        6. Verify completeness: exactly 3,602 / 3,602 cells mapped, 0 unmapped.
        7. Assemble auditable in-memory result with full provenance.

    Strict Boundaries:
        - ZERO writes to database tables.
        - ZERO rainfall trigger calculations.
        - ZERO modifications to core hazard engine or ML.
    """
    # 1. Validate sample points input
    if len(sample_points) != EXPECTED_SAMPLE_COUNT:
        raise ValueError(
            f"B2 sample-point invariant failed: expected {EXPECTED_SAMPLE_COUNT} approved ECMWF sample points, "
            f"found {len(sample_points)}."
        )

    # 2. Load and validate B1 forecast artifact
    artifact_path, raw_bytes, payload, b1_meta = load_b1_forecast_artifact(
        raw_artifact_path=raw_artifact_path,
        db_engine=db_engine,
        expected_sample_count=len(sample_points),
    )

    # 3. Load authoritative Wayanad H3-8 decision cells
    cells = load_authoritative_wayanad_grid(
        db_engine=db_engine,
        admin_id=admin_id,
        target_res=target_res,
        grid_cells_override=grid_cells_override,
    )

    total_cells = len(cells)
    logger.info(
        f"Starting Phase B2 nearest-sample mapping: {total_cells} H3-{target_res} cells -> "
        f"{len(sample_points)} forecast sample points..."
    )

    mappings: list[H3CellSampleMapping] = []
    mappings_by_h3: dict[int, H3CellSampleMapping] = {}
    mappings_by_h3_str: dict[str, H3CellSampleMapping] = {}
    cell_counts: dict[int, int] = {i: 0 for i in range(len(sample_points))}
    distances: list[float] = []

    # 4. Deterministic nearest-sample assignment
    for h3_int, lat, lon in cells:
        # Validate H3 identity and resolution
        if not is_valid_h3(h3_int):
            raise ValueError(f"B2 invalid H3 identifier encountered: {h3_int}")
        res = h3_get_resolution(h3_int)
        if res != target_res:
            raise ValueError(f"B2 cell resolution mismatch for {h3_int}: got {res}, expected {target_res}")

        h3_str = h3_to_str(h3_int)

        best_idx = -1
        best_dist = float("inf")

        for s_idx, (s_lat, s_lon) in enumerate(sample_points):
            d = haversine_km(lat, lon, s_lat, s_lon)
            # Deterministic tie-breaking: distance ascending, sample_index ascending
            if d < best_dist - 1e-9:
                best_dist = d
                best_idx = s_idx
            elif abs(d - best_dist) <= 1e-9:
                if s_idx < best_idx:
                    best_dist = d
                    best_idx = s_idx

        mapping = H3CellSampleMapping(
            h3=h3_int,
            h3_str=h3_str,
            lat=round(lat, 6),
            lon=round(lon, 6),
            sample_index=best_idx,
            sample_latitude=sample_points[best_idx][0],
            sample_longitude=sample_points[best_idx][1],
            distance_km=round(best_dist, 4),
            mapping_method=MAPPING_METHOD,
        )

        mappings.append(mapping)
        mappings_by_h3[h3_int] = mapping
        mappings_by_h3_str[h3_str] = mapping
        cell_counts[best_idx] += 1
        distances.append(best_dist)

    # 5. Enforce Completeness and Integrity
    mapped_cells = len(mappings)
    unmapped_cells = total_cells - mapped_cells

    if mapped_cells != EXPECTED_CELL_COUNT or unmapped_cells != 0:
        raise ValueError(
            f"B2 mapping completeness failed: {mapped_cells}/{total_cells} cells assigned, "
            f"{unmapped_cells} unmapped."
        )

    if len(mappings_by_h3) != EXPECTED_CELL_COUNT:
        raise ValueError(
            f"B2 uniqueness failed: expected {EXPECTED_CELL_COUNT} unique H3 cells, got {len(mappings_by_h3)}."
        )

    for m in mappings:
        if m.sample_index not in range(len(sample_points)):
            raise ValueError(f"B2 invalid sample index assigned to cell {m.h3}: {m.sample_index}")
        if m.distance_km < 0.0:
            raise ValueError(f"B2 negative distance computed for cell {m.h3}: {m.distance_km}")

    # 6. Compute distance metrics
    distances_sorted = sorted(distances)
    min_d = distances_sorted[0]
    max_d = distances_sorted[-1]
    mean_d = sum(distances_sorted) / len(distances_sorted)
    median_d = distances_sorted[len(distances_sorted) // 2]
    p90_d = distances_sorted[int(len(distances_sorted) * 0.9)]

    # 7. Retain Full Provenance
    provenance = {
        "provider": "Open-Meteo",
        "provider_endpoint": OPEN_METEO_ECMWF_ENDPOINT,
        "source_model": SOURCE_MODEL,
        "native_resolution_km": NATIVE_RESOLUTION_KM,
        "district": DISTRICT_NAME,
        "state": "Kerala",
        "lgd_code": DISTRICT_LGD,
        "admin_id": ADMIN_ID,
        "h3_resolution": target_res,
        "sample_points_count": len(sample_points),
        "mapping_method": MAPPING_METHOD,
        "raw_artifact_path": b1_meta.get("raw_artifact_path", str(artifact_path)),
        "raw_artifact_sha256": b1_meta.get("raw_artifact_sha256", ""),
        "raw_artifact_bytes": b1_meta.get("raw_artifact_bytes", len(raw_bytes)),
        "source_snapshot_id": str(b1_meta.get("source_snapshot_id", "")),
        "pipeline_run_id": str(b1_meta.get("pipeline_run_id", "")),
        "forecast_cycle_anchor": b1_meta.get("forecast_cycle_anchor"),
        "cycle_anchor_verified": False,
        "mapped_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        f"Phase B2 Spatial Mapping complete: {mapped_cells}/{total_cells} cells mapped. "
        f"Distance km: min={min_d:.3f}, median={median_d:.3f}, mean={mean_d:.3f}, max={max_d:.3f}"
    )

    return WayanadSpatialMappingResult(
        district=DISTRICT_NAME,
        lgd_code=DISTRICT_LGD,
        admin_id=admin_id,
        h3_resolution=target_res,
        total_cells=total_cells,
        mapped_cells=mapped_cells,
        unmapped_cells=unmapped_cells,
        sample_points_count=len(sample_points),
        mappings=mappings,
        mappings_by_h3=mappings_by_h3,
        mappings_by_h3_str=mappings_by_h3_str,
        cell_counts_by_sample=cell_counts,
        min_distance_km=round(min_d, 3),
        median_distance_km=round(median_d, 3),
        mean_distance_km=round(mean_d, 3),
        p90_distance_km=round(p90_d, 3),
        max_distance_km=round(max_d, 3),
        mapping_method=MAPPING_METHOD,
        provenance=provenance,
    )


# Backward compatibility alias
def build_wayanad_h3_spatial_downscaling(
    db_engine: Optional[Engine] = None,
    sample_points: Sequence[tuple[float, float]] = WAYANAD_PROTOTYPE_SAMPLE_POINTS,
    admin_id: int = ADMIN_ID,
    target_res: int = TARGET_RESOLUTION,
) -> WayanadSpatialMappingResult:
    """Backward compatibility wrapper delegating to execute_wayanad_b2_spatial_mapping."""
    return execute_wayanad_b2_spatial_mapping(
        db_engine=db_engine,
        sample_points=sample_points,
        admin_id=admin_id,
        target_res=target_res,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    result = execute_wayanad_b2_spatial_mapping()

    print("\n" + "=" * 70)
    print("Open-Meteo B2 spatial mapping complete")
    print(f"District:                      {result.district}")
    print(f"LGD:                           {result.lgd_code}")
    print(f"H3 resolution:                 {result.h3_resolution}")
    print(f"Decision cells:                {result.total_cells}")
    print(f"Forecast samples:              {result.sample_points_count}")
    print(f"Mapped cells:                  {result.mapped_cells}")
    print(f"Unmapped cells:                {result.unmapped_cells}")
    print(f"Mapping method:                {result.mapping_method}")
    print(f"Distance Min:                  {result.min_distance_km:.3f} km")
    print(f"Distance Median:               {result.median_distance_km:.3f} km")
    print(f"Distance Mean:                 {result.mean_distance_km:.3f} km")
    print(f"Distance 90th %tile:           {result.p90_distance_km:.3f} km")
    print(f"Distance Max:                  {result.max_distance_km:.3f} km")
    print("\nAssignment Distribution Across 12 Forecast Samples:")
    for s_idx, count in sorted(result.cell_counts_by_sample.items()):
        pct = (count / result.total_cells) * 100
        coord = WAYANAD_PROTOTYPE_SAMPLE_POINTS[s_idx]
        print(f"  Sample {s_idx:2d} ({coord[0]:.4f}, {coord[1]:.4f}): {count:4d} cells ({pct:5.1f}%)")
    print("=" * 70 + "\n")
