"""Regression tests for Batch C: N1 (Python 3.11-3.13 import) and N3 (test-order pollution).

Section refs: Batch C remediation plan
- N1: api.dependencies must import Optional from typing so annotations evaluate cleanly.
- N3: tests/unit/test_flood_h3_zonal.py must not leak sys.path modifications or FastAPI
      dependency overrides to subsequent tests.
"""

import inspect
import sys
from typing import get_type_hints

import pytest
from fastapi.testclient import TestClient


class TestN1PythonTypingCompatibility:
    """N1: Validates that api.dependencies and related routes evaluate annotations without NameError."""

    def test_optional_imported_and_annotations_evaluable(self):
        """Verify that resolve_effective_admin_id and get_site_district_admin_id annotations evaluate cleanly."""
        import api.dependencies as deps

        # Direct annotation access (fails with NameError under PEP 649 / Python 3.11-3.13 if Optional missing)
        ann_resolve = deps.resolve_effective_admin_id.__annotations__
        assert "requested_admin_id" in ann_resolve

        ann_district = deps.get_site_district_admin_id.__annotations__
        assert "return" in ann_district

        # inspect.get_annotations / get_type_hints verification
        hints_resolve = get_type_hints(deps.resolve_effective_admin_id)
        assert hints_resolve.get("requested_admin_id") is not None

        hints_district = get_type_hints(deps.get_site_district_admin_id)
        assert hints_district.get("return") is not None

    def test_all_api_dependencies_annotations_resolve(self):
        """Verify all functions in api.dependencies can have their annotations inspected without error."""
        import api.dependencies as deps

        for attr_name in dir(deps):
            obj = getattr(deps, attr_name)
            if inspect.isfunction(obj) or inspect.isclass(obj):
                try:
                    _ = inspect.get_annotations(obj)
                except Exception as exc:
                    pytest.fail(f"Annotation resolution failed for api.dependencies.{attr_name}: {exc}")


class TestN3TestIsolationRegression:
    """N3: Validates that test_flood_h3_zonal does not mutate sys.path or leak dependency overrides."""

    def test_importing_test_flood_h3_zonal_does_not_mutate_sys_path(self):
        """Importing test_flood_h3_zonal must not prepend REPO_ROOT/pipeline to sys.path."""
        before_path = list(sys.path)

        # Import or re-import the module
        if "tests.unit.test_flood_h3_zonal" in sys.modules:
            del sys.modules["tests.unit.test_flood_h3_zonal"]

        import tests.unit.test_flood_h3_zonal as zonal_test

        after_path = list(sys.path)

        # sys.path must not have REPO_ROOT/pipeline prepended
        assert not any(p.endswith("\\pipeline") or p.endswith("/pipeline") for p in after_path if p not in before_path)

    def test_executing_flood_tests_does_not_mutate_sys_path_or_overrides(self):
        """Executing zonal flood unit tests leaves sys.path and app.dependency_overrides untouched."""
        from api.main import app
        import tests.unit.test_flood_h3_zonal as zonal_test

        prior_overrides = dict(app.dependency_overrides)
        prior_path = list(sys.path)

        # Execute pure zonal tests
        zonal_test.test_polyfill_reporting_aoi_count()
        zonal_test.test_h3_cells_to_geodataframe()
        zonal_test.test_apply_quality_flags()

        # Verify no mutations occurred
        assert sys.path == prior_path
        assert app.dependency_overrides == prior_overrides

    def test_subsequent_app_client_clean_state(self):
        """Another test creating a client or using app after zonal test experiences a clean environment."""
        from api.main import app

        # Verify no rogue dependency overrides on app
        assert "mock_dep" not in app.dependency_overrides

        client = TestClient(app)
        # Health check endpoint executes without interference
        response = client.get("/health/ready")
        # Ready endpoint responds (either 200 or 503 depending on DB, but not 500 from leaked overrides)
        assert response.status_code in (200, 503)
