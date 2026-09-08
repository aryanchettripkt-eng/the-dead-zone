"""Focused regression tests for Pass 7: H8 + M4.

Verifies:
1. H8 — Dependency/package boundary correctness:
   - Direct runtime imports in `core` (sqlalchemy, geoalchemy2, h3, ortools) are explicitly declared in `core/pyproject.toml`.
   - Direct runtime imports in `pipeline` (joblib, numpy, pyproj) are explicitly declared in `pipeline/pyproject.toml`.
   - Core submodules resolve without reliance on accidental sibling dependencies.

2. M4 — Sentinel-1 packaging boundary & reachability correctness:
   - Canonical Sentinel-1 SAR flood module is packaged inside `pipeline.hazard.flood` under `src/pipeline`.
   - No root module shadowing: `pipeline.__file__` resolves to `pipeline/src/pipeline/__init__.py`.
   - Canonical Sentinel-1 exports are importable and reachable.
   - Algorithmic invariants (linear_to_db, detect_water, permanent water filtering, frequency calculation)
     run deterministically offline with synthetic arrays without external network/STAC calls.
   - Built wheel distribution includes `pipeline/hazard/flood/`.
"""

from __future__ import annotations

import ast
import os
import sys
import zipfile
import subprocess
import tomllib
from pathlib import Path
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestH8DependencyBoundaries:
    """H8: Validates that packages explicitly declare their direct runtime dependencies."""

    def test_core_declares_all_direct_runtime_dependencies(self):
        """Verify that core/pyproject.toml declares all 3rd-party dependencies directly imported in core."""
        core_pyproject_path = REPO_ROOT / "core" / "pyproject.toml"
        assert core_pyproject_path.exists(), "core/pyproject.toml must exist"

        with open(core_pyproject_path, "rb") as f:
            data = tomllib.load(f)

        declared_deps = {dep.split(">=")[0].split("<")[0].split("==")[0].strip().lower()
                         for dep in data["project"]["dependencies"]}

        # Mandatory direct runtime dependencies confirmed in core/src/core/
        required_deps = {
            "pydantic",
            "pydantic-settings",
            "python-dotenv",
            "sqlalchemy",
            "geoalchemy2",
            "h3",
            "ortools",
        }
        missing = required_deps - declared_deps
        assert not missing, f"core/pyproject.toml is missing declared direct dependencies: {missing}"

    def test_pipeline_declares_all_direct_runtime_dependencies(self):
        """Verify that pipeline/pyproject.toml declares all 3rd-party dependencies directly imported in pipeline."""
        pipeline_pyproject_path = REPO_ROOT / "pipeline" / "pyproject.toml"
        assert pipeline_pyproject_path.exists(), "pipeline/pyproject.toml must exist"

        with open(pipeline_pyproject_path, "rb") as f:
            data = tomllib.load(f)

        declared_deps = {dep.split(">=")[0].split("<")[0].split("==")[0].split("[")[0].strip().lower()
                         for dep in data["project"]["dependencies"]}

        # Mandatory direct runtime dependencies confirmed in pipeline/src/pipeline/
        required_deps = {
            "core",
            "h3",
            "geopandas",
            "rasterio",
            "pystac-client",
            "planetary-computer",
            "sqlalchemy",
            "psycopg",
            "matplotlib",
            "python-dotenv",
            "joblib",
            "numpy",
            "pyproj",
        }
        missing = required_deps - declared_deps
        assert not missing, f"pipeline/pyproject.toml is missing declared direct dependencies: {missing}"

    def test_core_runtime_modules_import_cleanly(self):
        """Verify core modules with heavy dependencies import without error."""
        import core.db_models as db_models
        import core.h3_utils as h3_utils
        import core.domain.allocation as allocation

        assert hasattr(db_models, "Base")
        assert hasattr(db_models, "Habitation")
        assert hasattr(h3_utils, "is_valid_h3")
        assert hasattr(allocation, "HabitationDemand")


class TestM4Sentinel1PackagingAndReachability:
    """M4: Validates Sentinel-1 SAR flood packaging, reachability, and root shadowing elimination."""

    def test_pipeline_origin_is_src_pipeline(self):
        """Verify pipeline imports from src/pipeline/__init__.py and not from a stale root directory."""
        import pipeline
        pipeline_origin = Path(pipeline.__file__).resolve()
        expected_origin = (REPO_ROOT / "pipeline" / "src" / "pipeline" / "__init__.py").resolve()
        assert pipeline_origin == expected_origin, (
            f"pipeline.__file__ resolved to '{pipeline_origin}', expected '{expected_origin}'. "
            "Module shadowing defect is present!"
        )

    def test_pipeline_subpackages_reachable_from_root(self):
        """Verify pipeline.jobs, pipeline.adapters, and pipeline.hazard.flood are all reachable."""
        import pipeline.jobs as jobs
        import pipeline.adapters as adapters
        import pipeline.hazard.flood as flood

        assert hasattr(jobs, "compute_and_persist_dynamic_snapshots")
        assert hasattr(jobs, "ingest_sentinel1_artifact")
        assert hasattr(adapters, "sentinel1_adapter")
        assert hasattr(flood, "detect_water")

    def test_canonical_sentinel1_public_exports(self):
        """Verify canonical Sentinel-1 functions are exported by pipeline.hazard.flood."""
        from pipeline.hazard.flood import (
            get_barpeta_bbox_wgs84,
            get_barpeta_bounds_projected,
            get_stac_client,
            query_sentinel1_rtc,
            extract_scene_metadata,
            linear_to_db,
            stream_and_clip_raster,
            detect_water,
            save_raster_geotiff,
            DEFAULT_VV_WATER_THRESHOLD_DB,
            generate_permanent_water_mask,
            filter_permanent_water,
            stream_jrc_occurrence,
            create_master_grid,
            process_scene_inundation,
            accumulate_inundation_stack,
            calculate_inundation_frequency,
        )

        bbox = get_barpeta_bbox_wgs84()
        assert len(bbox) == 4
        assert bbox[0] < bbox[2]
        assert bbox[1] < bbox[3]

    def test_sentinel1_linear_to_db_offline_invariant(self):
        """Deterministic offline test of linear backscatter to decibels conversion."""
        from pipeline.hazard.flood.water_mask import linear_to_db

        # Synthetic linear power array
        linear_power = np.array([
            [0.01, 0.1],
            [0.0, -1.0],  # invalid values
            [1.0, 10.0],
        ], dtype=np.float32)

        array_db, valid_mask = linear_to_db(linear_power, nodata_val=0.0)

        assert valid_mask.shape == (3, 2)
        # Check valid mask
        assert valid_mask[0, 0] is True or valid_mask[0, 0] == 1
        assert valid_mask[0, 1] is True or valid_mask[0, 1] == 1
        assert valid_mask[1, 0] == 0 or valid_mask[1, 0] is False  # 0 is nodata
        assert valid_mask[1, 1] == 0 or valid_mask[1, 1] is False  # negative is invalid

        # Check dB values: 10 * log10(0.01) = -20 dB, 10 * log10(1.0) = 0 dB
        assert np.isclose(array_db[0, 0], -20.0, atol=1e-3)
        assert np.isclose(array_db[2, 0], 0.0, atol=1e-3)
        assert np.isclose(array_db[2, 1], 10.0, atol=1e-3)

    def test_sentinel1_detect_water_offline_invariant(self):
        """Deterministic offline test of SAR water mask thresholding."""
        from pipeline.hazard.flood.water_mask import detect_water

        # Synthetic dB array: threshold = -16.0 dB
        vv_db = np.array([
            [-22.0, -18.0],  # water (< -16.0)
            [-12.0, -5.0],   # land (>= -16.0)
        ], dtype=np.float32)
        valid_mask = np.array([
            [True, True],
            [True, False],   # last pixel invalid
        ])

        mask = detect_water(vv_db, valid_mask, threshold_db=-16.0)

        # 0 = Land, 1 = Water, 255 = Nodata
        assert mask[0, 0] == 1  # water
        assert mask[0, 1] == 1  # water
        assert mask[1, 0] == 0  # land
        assert mask[1, 1] == 255  # nodata

    def test_sentinel1_permanent_water_filtering_offline_invariant(self):
        """Deterministic offline test of removing permanent water bodies from inundation mask."""
        from pipeline.hazard.flood.permanent_water import filter_permanent_water

        water_mask = np.array([
            [1, 1],   # both detected as water
            [0, 255], # land and nodata
        ], dtype=np.uint8)

        permanent_mask = np.array([
            [True, False],  # (0, 0) is permanent river/lake, (0, 1) is temporary flood
            [False, False],
        ], dtype=bool)

        filtered = filter_permanent_water(water_mask, permanent_mask)

        # Permanent water pixel reset to 0 (non-flood)
        assert filtered[0, 0] == 0
        # Temporary inundation pixel remains 1
        assert filtered[0, 1] == 1
        # Land remains 0
        assert filtered[1, 0] == 0
        # Nodata remains 255
        assert filtered[1, 1] == 255

    def test_sentinel1_inundation_frequency_offline_invariant(self):
        """Deterministic offline test of empirical inundation frequency F(x, y) = W / V."""
        from pipeline.hazard.flood.frequency_stack import calculate_inundation_frequency

        water_counts = np.array([
            [5, 2],
            [0, 0],
        ], dtype=np.uint16)
        valid_counts = np.array([
            [10, 4],
            [10, 0],  # (1, 1) has 0 observations
        ], dtype=np.uint16)

        frequency, confidence_mask = calculate_inundation_frequency(
            water_counts, valid_counts, min_observations=1
        )

        assert confidence_mask[0, 0] is True or confidence_mask[0, 0] == 1
        assert confidence_mask[1, 1] == 0 or confidence_mask[1, 1] is False

        assert np.isclose(frequency[0, 0], 0.5)
        assert np.isclose(frequency[0, 1], 0.5)
        assert np.isclose(frequency[1, 0], 0.0)
        assert np.isnan(frequency[1, 1])

    def test_wheel_package_contains_sentinel1_flood_module(self, tmp_path):
        """Level 3 Packaging Verification: builds the wheel and verifies flood files are included."""
        # Run uv build --package pipeline into tmp_path
        cmd = [
            "uv", "build",
            "--package", "pipeline",
            "--out-dir", str(tmp_path),
        ]
        result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        assert result.returncode == 0, f"uv build failed: {result.stderr}"

        # Find built wheel
        wheels = list(tmp_path.glob("*.whl"))
        assert len(wheels) == 1, f"Expected 1 wheel, found: {wheels}"
        wheel_path = wheels[0]

        with zipfile.ZipFile(wheel_path, "r") as z:
            names = set(z.namelist())

        # Verify key flood files exist in the wheel distribution
        expected_in_wheel = {
            "pipeline/hazard/flood/__init__.py",
            "pipeline/hazard/flood/aoi.py",
            "pipeline/hazard/flood/water_mask.py",
            "pipeline/hazard/flood/permanent_water.py",
            "pipeline/hazard/flood/frequency_stack.py",
            "pipeline/hazard/flood/stac.py",
            "pipeline/jobs/ingest_flood_data.py",
            "pipeline/adapters/sentinel1_adapter.py",
        }
        for item in expected_in_wheel:
            assert item in names, f"Expected '{item}' inside wheel '{wheel_path.name}', but was omitted!"

    def test_wheel_installation_and_isolated_imports(self, tmp_path):
        """Level 3 Packaging Verification: extracts built wheels (core & pipeline) into isolated location and tests imports without repo source on sys.path."""
        dist_dir = tmp_path / "dist"
        isolated_site = tmp_path / "isolated_site"
        dist_dir.mkdir()
        isolated_site.mkdir()

        # 1. Build core and pipeline wheels
        cmd_core = ["uv", "build", "--package", "core", "--out-dir", str(dist_dir)]
        build_core = subprocess.run(cmd_core, cwd=REPO_ROOT, capture_output=True, text=True)
        assert build_core.returncode == 0, f"uv build core failed: {build_core.stderr}"

        cmd_pipe = ["uv", "build", "--package", "pipeline", "--out-dir", str(dist_dir)]
        build_pipe = subprocess.run(cmd_pipe, cwd=REPO_ROOT, capture_output=True, text=True)
        assert build_pipe.returncode == 0, f"uv build pipeline failed: {build_pipe.stderr}"

        # 2. Extract both wheels into isolated location
        for whl in dist_dir.glob("*.whl"):
            with zipfile.ZipFile(whl, "r") as z:
                z.extractall(isolated_site)

        # 3. In a sub-process, run python with isolated_site as first import location
        # and strip workspace source paths to prove imports resolve strictly from the packaged wheels
        script = (
            "import sys, os\n"
            f"isolated = r'{isolated_site}'\n"
            f"repo = r'{REPO_ROOT}'\n"
            "# Exclude repo source trees from sys.path\n"
            "sys.path = [p for p in sys.path if not p.startswith(os.path.join(repo, 'pipeline')) and not p.startswith(os.path.join(repo, 'core')) and not p.startswith(os.path.join(repo, 'api')) and p != repo]\n"
            "sys.path.insert(0, isolated)\n"
            "import core\n"
            "import pipeline\n"
            "assert isolated in core.__file__, f'Expected core from {isolated}, got {core.__file__}'\n"
            "assert isolated in pipeline.__file__, f'Expected pipeline from {isolated}, got {pipeline.__file__}'\n"
            "import pipeline.jobs as jobs\n"
            "import pipeline.adapters as adapters\n"
            "import pipeline.hazard.flood as flood\n"
            "from pipeline.hazard.flood import detect_water, linear_to_db, query_sentinel1_rtc, calculate_inundation_frequency\n"
            "from pipeline.jobs import ingest_sentinel1_artifact\n"
            "from pipeline.adapters.sentinel1_adapter import sentinel1_adapter\n"
            "print('ISOLATED_WHEEL_VERIFICATION_SUCCESS')\n"
        )

        sub_res = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        assert sub_res.returncode == 0, f"Subprocess import verification failed:\n{sub_res.stderr}"
        assert "ISOLATED_WHEEL_VERIFICATION_SUCCESS" in sub_res.stdout
