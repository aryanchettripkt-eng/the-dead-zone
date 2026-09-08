"""Unit tests for DataImportRun provenance, lifecycle states, and integrity constraints."""

from __future__ import annotations

import json
import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from core.config import settings
from core.enums import ImportRunStatus


def test_data_import_run_lifecycle():
    """Tests the STAGED -> VALIDATED -> PROMOTED -> SUPERSEDED lifecycle."""
    eng = create_engine(settings.get_sqlalchemy_url())
    run_id = uuid.uuid4()
    dummy_manifest_hash = f"test_{run_id.hex[:16]}"

    with eng.begin() as conn:
        # 1. Create STAGED
        conn.execute(text("""
            INSERT INTO data_import_run (
                id, dataset_name, district_name, source_pipeline, pipeline_version,
                manifest_hash, artifact_hashes, status, row_counts
            ) VALUES (
                :id, 'test_dataset', 'TestDistrict', 'test_pipe', 'v1',
                :hash, '{}'::jsonb, :status, '{}'::jsonb
            );
        """), {"id": str(run_id), "hash": dummy_manifest_hash, "status": ImportRunStatus.STAGED.value})

        status = conn.execute(text("SELECT status FROM data_import_run WHERE id = :id"), {"id": str(run_id)}).scalar()
        assert status == ImportRunStatus.STAGED.value

        # 2. Advance to VALIDATED
        conn.execute(text("""
            UPDATE data_import_run
            SET status = :status, validated_at = now()
            WHERE id = :id;
        """), {"id": str(run_id), "status": ImportRunStatus.VALIDATED.value})

        status = conn.execute(text("SELECT status FROM data_import_run WHERE id = :id"), {"id": str(run_id)}).scalar()
        assert status == ImportRunStatus.VALIDATED.value

        # 3. Promote
        conn.execute(text("""
            UPDATE data_import_run
            SET status = :status, promoted_at = now()
            WHERE id = :id;
        """), {"id": str(run_id), "status": ImportRunStatus.PROMOTED.value})

        status = conn.execute(text("SELECT status FROM data_import_run WHERE id = :id"), {"id": str(run_id)}).scalar()
        assert status == ImportRunStatus.PROMOTED.value

        # 4. Supersede
        conn.execute(text("""
            UPDATE data_import_run
            SET status = :status
            WHERE id = :id;
        """), {"id": str(run_id), "status": ImportRunStatus.SUPERSEDED.value})

        status = conn.execute(text("SELECT status FROM data_import_run WHERE id = :id"), {"id": str(run_id)}).scalar()
        assert status == ImportRunStatus.SUPERSEDED.value

        # Cleanup
        conn.execute(text("DELETE FROM data_import_run WHERE id = :id"), {"id": str(run_id)})


def test_data_import_run_on_delete_restrict():
    """Tests ON DELETE RESTRICT on candidate_site preventing deletion of referenced import_run."""
    eng = create_engine(settings.get_sqlalchemy_url())
    run_id = uuid.uuid4()
    dummy_hash = f"test_{run_id.hex[:16]}"

    # 1. Setup in committed transaction
    with eng.begin() as conn:
        conn.execute(text("""
            INSERT INTO data_import_run (
                id, dataset_name, district_name, source_pipeline, pipeline_version,
                manifest_hash, artifact_hashes, status, row_counts
            ) VALUES (
                :id, 'test_dataset', 'TestDistrict', 'test_pipe', 'v1',
                :hash, '{}'::jsonb, 'PROMOTED', '{}'::jsonb
            );
        """), {"id": str(run_id), "hash": dummy_hash})

        site_id = conn.execute(text("""
            INSERT INTO candidate_site (
                source_site_id, import_run_id,
                geom, centroid, area_ha, slope_mean, tenure,
                suitability, cc_land, assessment_status, eligibility_status
            ) VALUES (
                'test_site_restrict', :run_id,
                ST_Multi(ST_GeomFromText('POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))', 4326)),
                ST_GeomFromText('POINT(0.5 0.5)', 4326),
                2.5, 1.0, 'tenure_unverified',
                50, 100, 'screening_only', 'unknown'
            ) RETURNING id;
        """), {"run_id": str(run_id)}).scalar()

    # 2. Attempt deletion in separate transaction (must raise IntegrityError)
    with pytest.raises(IntegrityError):
        with eng.begin() as conn:
            conn.execute(text("DELETE FROM data_import_run WHERE id = :id"), {"id": str(run_id)})

    # 3. Cleanup: delete child first, then parent
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM candidate_site WHERE id = :id"), {"id": site_id})
        conn.execute(text("DELETE FROM data_import_run WHERE id = :id"), {"id": str(run_id)})
