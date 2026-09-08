"""Integration tests for Day 1 Database Schema, SQLAlchemy 2.0 ORM Models, and constraints."""

import uuid
from datetime import datetime, timezone, date
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from core.config import settings
from core.db_models import (
    Base,
    AdminBoundary,
    Habitation,
    GridCell,
    HazardStatic,
    MHISnapshot,
    Explanation,
    Vulnerability,
    DisasterEvent,
    CandidateSite,
    AllocationRun,
    RelocationPlan,
    PipelineRun,
    ServingVersion,
)


@pytest.fixture(scope="module")
def db_session():
    """Provides a database session for Day 1 integration tests."""
    engine = create_engine(settings.get_sqlalchemy_url(direct=True), pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


def test_pipeline_run_and_serving_version_orm(db_session):
    """Verify PipelineRun and ServingVersion ORM lifecycle."""
    run = PipelineRun(
        run_type="FULL",
        status="READY",
        code_version="v0.1.0",
        config_version="v1.0",
        model_version="v1.0.0",
    )
    db_session.add(run)
    db_session.flush()

    assert run.id is not None

    serving = ServingVersion(
        dataset_name=f"test_dataset_{uuid.uuid4().hex[:6]}",
        pipeline_run_id=run.id,
    )
    db_session.add(serving)
    db_session.flush()

    res = db_session.execute(
        select(ServingVersion).where(ServingVersion.dataset_name == serving.dataset_name)
    ).scalar_one()
    assert res.pipeline_run_id == run.id


def test_admin_and_habitation_spatial_orm(db_session):
    """Verify AdminBoundary and Habitation insertion with PostGIS geometries."""
    # Insert district admin boundary
    admin = AdminBoundary(
        level="district",
        lgd_code=999001 + int(uuid.uuid4().int % 10000),
        name="Test District",
        geom="SRID=4326;MULTIPOLYGON(((76.0 11.5, 76.2 11.5, 76.2 11.8, 76.0 11.8, 76.0 11.5)))",
    )
    db_session.add(admin)
    db_session.flush()

    # Insert habitation
    hab = Habitation(
        lgd_code=888001 + int(uuid.uuid4().int % 10000),
        name="Test Habitation",
        type="village",
        admin_id=admin.id,
        geom_point="SRID=4326;POINT(76.1320 11.6854)",
        population=1200,
        households=280,
    )
    db_session.add(hab)
    db_session.flush()

    assert hab.id is not None
    assert hab.admin_id == admin.id


def test_candidate_site_and_allocation_orm(db_session):
    """Verify CandidateSite, AllocationRun, and RelocationPlan ORM relationship."""
    # Insert candidate site
    site = CandidateSite(
        geom="SRID=4326;MULTIPOLYGON(((76.1 11.6, 76.15 11.6, 76.15 11.65, 76.1 11.65, 76.1 11.6)))",
        centroid="SRID=4326;POINT(76.125 11.625)",
        area_ha=5.2,
        tenure="government_revenue",
        slope_mean=6.5,
        mhi_max=0.12,
        cc_land=400,
        cc_water=250,
        cc_school=300,
        cc_health=500,
        cc_final=250,
        binding_constraint="water",
        suitability=85,
    )
    db_session.add(site)
    db_session.flush()

    # Insert Habitation
    hab = Habitation(
        name="Source Habitation For Relocation",
        type="village",
        geom_point="SRID=4326;POINT(76.10 11.60)",
        population=500,
        households=110,
    )
    db_session.add(hab)
    db_session.flush()

    # Create allocation run
    alloc_run = AllocationRun(
        status="COMPLETED",
        solver_latency_ms=12.4,
        total_households_relocated=110,
    )
    db_session.add(alloc_run)
    db_session.flush()

    # Create relocation plan item
    plan = RelocationPlan(
        allocation_run_id=alloc_run.id,
        habitation_id=hab.id,
        site_id=site.id,
        households=110,
        tier="immediate",
        priority_score=0.88,
        has_group_split=False,
    )
    db_session.add(plan)
    db_session.flush()

    assert plan.id is not None
    assert plan.site_id == site.id
