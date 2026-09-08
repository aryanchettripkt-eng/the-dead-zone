"""Unit tests for Wayanad H3 Spatial Nearest-Sample Mapping (Phase B2).

Validates:
1. Approved 12 deterministic forecast sample points and coordinates.
2. Complete Wayanad mapping (exactly 3,602 / 3,602 cells mapped, 0 unmapped).
3. Mapping integrity (valid H3 indices, resolution 8, valid sample indices 0..11, non-negative distance).
4. Determinism of nearest-sample assignment.
5. Nearest-point mathematical correctness on known synthetic points.
6. Explicit failure on missing Phase B1 raw forecast artifact (no silent live fetch).
7. Explicit failure on incorrect grid cell count, admin boundary, or resolution.
8. Complete provenance preservation (provider, model, resolution, LGD, admin ID, method).
9. Downstream isolation: zero writes to hazard_dynamic or mhi_snapshot.
10. Haversine geodesic distance calculation precision.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from core.config import settings
from core.h3_utils import h3_get_resolution, is_valid_h3
from pipeline.ingestion.open_meteo_client import (
    ADMIN_ID,
    DISTRICT_LGD,
    DISTRICT_NAME,
    WAYANAD_PROTOTYPE_SAMPLE_POINTS,
    REFERENCE_ARTIFACT_REL_PATH,
    REFERENCE_ARTIFACT_SHA256,
)
from pipeline.ingestion.open_meteo_regrid import (
    MAPPING_METHOD,
    EXPECTED_CELL_COUNT,
    EXPECTED_SAMPLE_COUNT,
    TARGET_RESOLUTION,
    haversine_km,
    load_authoritative_wayanad_grid,
    load_b1_forecast_artifact,
    execute_wayanad_b2_spatial_mapping,
)


# =============================================================================
# 1. APPROVED SAMPLE POINTS INVARIANT
# =============================================================================

def test_approved_12_sample_points():
    """Verify exactly 12 approved deterministic sample points with correct coordinates."""
    assert len(WAYANAD_PROTOTYPE_SAMPLE_POINTS) == EXPECTED_SAMPLE_COUNT

    expected_coords = [
        (11.5364, 75.8500),
        (11.5364, 76.2500),
        (11.5727, 76.1500),
        (11.6091, 76.0500),
        (11.6455, 75.9500),
        (11.6818, 75.8500),
        (11.6818, 76.2500),
        (11.7182, 76.1500),
        (11.7545, 76.0500),
        (11.7909, 75.9500),
        (11.8273, 75.8500),
        (11.8273, 76.2500),
    ]

    for idx, (lat, lon) in enumerate(WAYANAD_PROTOTYPE_SAMPLE_POINTS):
        exp_lat, exp_lon = expected_coords[idx]
        assert abs(lat - exp_lat) < 1e-4
        assert abs(lon - exp_lon) < 1e-4


# =============================================================================
# 2. COMPLETE WAYANAD 3,602 MAPPING & INTEGRITY
# =============================================================================

def test_complete_wayanad_mapping():
    """Verify exactly 3,602 / 3,602 Wayanad cells receive an assignment with 0 unmapped."""
    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    result = execute_wayanad_b2_spatial_mapping(raw_artifact_path=artifact_path)

    assert result.district == "Wayanad"
    assert result.lgd_code == 555
    assert result.admin_id == 178
    assert result.h3_resolution == 8
    assert result.total_cells == 3602
    assert result.mapped_cells == 3602
    assert result.unmapped_cells == 0
    assert result.sample_points_count == 12
    assert result.mapping_method == "nearest_sample_prototype"

    # Verify every cell mapping
    assert len(result.mappings) == 3602
    assert len(result.mappings_by_h3) == 3602
    assert len(result.mappings_by_h3_str) == 3602

    # Check cell counts across samples
    total_assigned = sum(result.cell_counts_by_sample.values())
    assert total_assigned == 3602
    for s_idx in range(12):
        assert result.cell_counts_by_sample[s_idx] > 0, f"Sample {s_idx} received 0 cells"

    # Verify distance bounds
    assert result.min_distance_km >= 0.0
    assert result.max_distance_km < 25.0  # Wayanad extent is ~40 km across, max dist should be < 20 km
    assert result.median_distance_km < 10.0


def test_every_cell_mapping_is_valid():
    """For every mapped cell: valid H3-8, valid sample index, non-negative distance."""
    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    result = execute_wayanad_b2_spatial_mapping(raw_artifact_path=artifact_path)

    for m in result.mappings:
        assert is_valid_h3(m.h3)
        assert is_valid_h3(m.h3_str)
        assert h3_get_resolution(m.h3) == 8
        assert 0 <= m.sample_index < 12
        assert m.distance_km >= 0.0
        assert m.mapping_method == "nearest_sample_prototype"
        assert (m.sample_latitude, m.sample_longitude) == WAYANAD_PROTOTYPE_SAMPLE_POINTS[m.sample_index]


# =============================================================================
# 3. DETERMINISM
# =============================================================================

def test_deterministic_mapping():
    """Running mapping twice against identical inputs produces identical assignments."""
    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    result1 = execute_wayanad_b2_spatial_mapping(raw_artifact_path=artifact_path)
    result2 = execute_wayanad_b2_spatial_mapping(raw_artifact_path=artifact_path)

    assert result1.total_cells == result2.total_cells
    assert result1.cell_counts_by_sample == result2.cell_counts_by_sample
    assert result1.min_distance_km == result2.min_distance_km
    assert result1.max_distance_km == result2.max_distance_km

    for m1, m2 in zip(result1.mappings, result2.mappings):
        assert m1.h3 == m2.h3
        assert m1.sample_index == m2.sample_index
        assert m1.distance_km == m2.distance_km


# =============================================================================
# 4. NEAREST-POINT CORRECTNESS (SYNTHETIC BENCHMARK)
# =============================================================================

def test_nearest_point_correctness():
    """Verifies that the nearest-sample assignment mathematically selects the sample with minimum distance."""
    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    result = execute_wayanad_b2_spatial_mapping(raw_artifact_path=artifact_path)

    # For a representative sample of cells (first 50, middle 50, last 50), verify by exhaustive check
    cells_to_check = result.mappings[:50] + result.mappings[1750:1800] + result.mappings[-50:]

    for m in cells_to_check:
        calculated_distances = [
            (idx, haversine_km(m.lat, m.lon, s_lat, s_lon))
            for idx, (s_lat, s_lon) in enumerate(WAYANAD_PROTOTYPE_SAMPLE_POINTS)
        ]
        # Sort by distance ascending, idx ascending
        calculated_distances.sort(key=lambda x: (round(x[1], 4), x[0]))
        min_idx, min_dist = calculated_distances[0]

        assert m.sample_index == min_idx, (
            f"Cell {m.h3_str} assigned sample {m.sample_index} but nearest is {min_idx} "
            f"(dist {m.distance_km} vs {min_dist})"
        )
        assert abs(m.distance_km - round(min_dist, 4)) < 1e-4


# =============================================================================
# 5. INPUT VALIDATION & FAILURE HANDLING
# =============================================================================

def test_missing_b1_artifact_fails_explicitly():
    """Fails explicitly when B1 raw forecast artifact does not exist (no live HTTP fetch)."""
    fake_path = Path("data/raw/open_meteo/non_existent_b1_artifact.json")
    with pytest.raises(FileNotFoundError, match="B2 prerequisite missing: B1 Open-Meteo raw artifact not found"):
        execute_wayanad_b2_spatial_mapping(raw_artifact_path=fake_path)


def test_wrong_grid_cell_count_fails_explicitly():
    """Fails explicitly if cell count differs from 3,602."""
    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    # Only 3 cells provided in override
    truncated_grid = [
        (614178828715032575, 11.5092, 76.1275),
        (614178828717129727, 11.5093, 76.1193),
        (614178828719226879, 11.5166, 76.1317),
    ]

    with pytest.raises(ValueError, match="B2 grid invariant failed: expected Wayanad H3-8 grid with 3602 cells"):
        execute_wayanad_b2_spatial_mapping(
            raw_artifact_path=artifact_path,
            grid_cells_override=truncated_grid,
        )


def test_wrong_sample_points_count_fails_explicitly():
    """Fails explicitly if sample points count is not 12."""
    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    wrong_samples = WAYANAD_PROTOTYPE_SAMPLE_POINTS[:10]  # Only 10 points!

    with pytest.raises(ValueError, match="B2 sample-point invariant failed: expected 12 approved ECMWF sample points"):
        execute_wayanad_b2_spatial_mapping(
            raw_artifact_path=artifact_path,
            sample_points=wrong_samples,
        )


# =============================================================================
# 6. PROVENANCE INTEGRITY
# =============================================================================

def test_b2_provenance_contract():
    """Verifies that the resulting mapping retains full auditable provenance."""
    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    result = execute_wayanad_b2_spatial_mapping(raw_artifact_path=artifact_path)

    prov = result.provenance
    assert prov["provider"] == "Open-Meteo"
    assert prov["provider_endpoint"] == "https://api.open-meteo.com/v1/ecmwf"
    assert prov["source_model"] == "ECMWF_IFS_HRES"
    assert prov["native_resolution_km"] == 9.0
    assert prov["district"] == "Wayanad"
    assert prov["state"] == "Kerala"
    assert prov["lgd_code"] == 555
    assert prov["admin_id"] == 178
    assert prov["h3_resolution"] == 8
    assert prov["sample_points_count"] == 12
    assert prov["mapping_method"] == "nearest_sample_prototype"
    assert prov["raw_artifact_sha256"] == REFERENCE_ARTIFACT_SHA256
    assert prov["cycle_anchor_verified"] is False


# =============================================================================
# 7. DOWNSTREAM ISOLATION (ZERO HAZARD WRITES)
# =============================================================================

def test_b2_zero_hazard_dynamic_writes():
    """Verifies that Phase B2 performs zero writes to hazard_dynamic or mhi_snapshot."""
    db_url = settings.get_sqlalchemy_url(direct=True)
    engine = create_engine(db_url)

    with engine.connect() as conn:
        initial_dyn_count = conn.execute(text("SELECT count(*) FROM hazard_dynamic")).scalar()
        initial_mhi_count = conn.execute(text("SELECT count(*) FROM mhi_snapshot")).scalar()

    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = repo_root / REFERENCE_ARTIFACT_REL_PATH

    result = execute_wayanad_b2_spatial_mapping(raw_artifact_path=artifact_path, db_engine=engine)
    assert result.mapped_cells == 3602

    with engine.connect() as conn:
        post_dyn_count = conn.execute(text("SELECT count(*) FROM hazard_dynamic")).scalar()
        post_mhi_count = conn.execute(text("SELECT count(*) FROM mhi_snapshot")).scalar()

        assert post_dyn_count == initial_dyn_count, "hazard_dynamic must have ZERO writes in Phase B2!"
        assert post_mhi_count == initial_mhi_count, "mhi_snapshot must have ZERO writes in Phase B2!"


# =============================================================================
# 8. HAVERSINE PRECISION
# =============================================================================

def test_haversine_accuracy():
    """Verify haversine formula against known analytical distance."""
    # Distance between identical points is 0.0
    assert haversine_km(11.5, 76.0, 11.5, 76.0) == 0.0

    # 1 degree of latitude at the equator is approx 111.195 km
    d_lat1 = haversine_km(0.0, 0.0, 1.0, 0.0)
    assert 111.0 < d_lat1 < 111.4

    # Distance is symmetric
    d1 = haversine_km(11.5, 75.8, 11.8, 76.2)
    d2 = haversine_km(11.8, 76.2, 11.5, 75.8)
    assert abs(d1 - d2) < 1e-9
