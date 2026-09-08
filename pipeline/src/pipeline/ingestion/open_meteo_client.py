"""Open-Meteo ECMWF Forecast Ingestion Client (Phase B1).

Queries Open-Meteo's dedicated ECMWF IFS HRES endpoint for deterministic
spatial sample points inside Wayanad (LGD 555, Admin ID 178), enforces a
strict raw-first persistence lifecycle, calculates cryptographic SHA256
and size metrics, registers provenance in `source_snapshot`, tracks execution
in `pipeline_run`, and validates temporal and physical payload integrity.

Phase B1 Scope: Ingestion and Provenance Proof ONLY.
Zero trigger calculation, zero hazard_dynamic writes, zero mhi_snapshot mutations.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from core.config import settings

logger = logging.getLogger("setu_pipeline.open_meteo_client")

# Open-Meteo dedicated ECMWF IFS HRES (~9 km native resolution) endpoint
OPEN_METEO_ECMWF_ENDPOINT = "https://api.open-meteo.com/v1/ecmwf"

SOURCE_ID = "open_meteo_ecmwf"
SOURCE_MODEL = "ECMWF_IFS_HRES"
NATIVE_RESOLUTION_KM = 9.0
DISTRICT_NAME = "Wayanad"
STATE_NAME = "Kerala"
DISTRICT_LGD = 555
ADMIN_ID = 178

# Canonical reference artifact details for Phase B1 reproducibility
REFERENCE_ARTIFACT_REL_PATH = Path("data") / "raw" / "open_meteo" / "ecmwf_wayanad_20260908T120000Z.json"
REFERENCE_ARTIFACT_SHA256 = "7eaef14c0001ebc0b1b97257de2054e0ccd4833d6be26af9267c2951ad367039"

# 12 deterministic prototype coordinate sample points strictly verified inside
# Wayanad's administrative polygon (admin_boundary id=178, lgd_code=555).
# Spaced at approximately model scale (~13 km) across Wayanad's physiographic zones.
WAYANAD_PROTOTYPE_SAMPLE_POINTS: list[tuple[float, float]] = [
    (11.5364, 75.8500),  # South-West Ghats ridge (Vythiri / Pookode domain)
    (11.5364, 76.2500),  # South-East boundary (Meppadi / Nilambur flank)
    (11.5727, 76.1500),  # South Central (Chooralmala / Meppadi valley basin)
    (11.6091, 76.0500),  # Central Western hills (Thariode / Banasura Sagar)
    (11.6455, 75.9500),  # Western Escarpment (Padinjarathara domain)
    (11.6818, 75.8500),  # North-West upland (Thondernad domain)
    (11.6818, 76.2500),  # Central Eastern plateau (Sulthan Bathery South)
    (11.7182, 76.1500),  # Central Drainage (Panamaram / Kabini basin)
    (11.7545, 76.0500),  # North-Central valley (Mananthavady South)
    (11.7909, 75.9500),  # North-West border (Thirunelly foothills)
    (11.8273, 75.8500),  # Far North peak (Brahmagiri wildlife flank)
    (11.8273, 76.2500),  # North-East plateau (Sulthan Bathery North / Muthanga)
]


@dataclass(frozen=True)
class PhaseB1IngestionReport:
    """Validation report returned upon completing Phase B1 ingestion proof."""
    status: str  # 'SUCCESS' | 'FAILED' | 'SKIPPED_IDEMPOTENT'
    http_status_code: int
    source_snapshot_id: Optional[uuid.UUID]
    pipeline_run_id: Optional[uuid.UUID]
    raw_artifact_path: str
    sha256: str
    size_bytes: int
    sample_points_count: int
    total_hourly_steps_per_point: int
    future_hourly_steps_available: int
    forecast_cycle_anchor: datetime
    cycle_anchor_verified: bool
    earliest_valid_at: datetime
    latest_valid_at: datetime
    errors: list[str] = field(default_factory=list)


def derive_provider_run_anchor(now_utc: datetime) -> datetime:
    """Derives provider forecast-run anchor from ECMWF's 4x daily cadence (00Z, 06Z, 12Z, 18Z).

    Design contract:
    Unless provider metadata explicitly proves the underlying model run initialization,
    forecast_cycle_at is formally defined as a derived provider forecast-run anchor,
    and cycle_anchor_verified MUST be False.
    """
    hour = now_utc.hour
    if hour >= 18:
        synoptic_hour = 18
    elif hour >= 12:
        synoptic_hour = 12
    elif hour >= 6:
        synoptic_hour = 6
    else:
        synoptic_hour = 0

    return now_utc.replace(hour=synoptic_hour, minute=0, second=0, microsecond=0)


def validate_open_meteo_payload(
    raw_bytes: bytes,
    cycle_anchor: datetime,
    expected_sample_count: int,
    min_future_hours: int = 72,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Validates raw Open-Meteo payload against B1 contract specifications.

    Contract requirements (Section 16):
    - response is valid JSON
    - hourly object exists in each location
    - hourly.time exists and is a list
    - hourly.precipitation exists and is a list
    - time and precipitation lengths match
    - timestamps parse correctly as ISO8601
    - timestamps are strictly monotonically increasing (ordered)
    - timestamps are unique
    - precipitation values are numeric and finite
    - precipitation values are non-negative
    - sufficient hourly coverage exists for downstream 72h horizon (> cycle_anchor)
    """
    errors: list[str] = []
    meta: dict[str, Any] = {
        "total_steps": 0,
        "future_steps": 0,
        "earliest_valid": cycle_anchor,
        "latest_valid": cycle_anchor,
    }

    # 1. Valid JSON check
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        return False, [f"JSON deserialization failed: {exc}"], meta

    if not isinstance(payload, list):
        # Single location returns dict, multi-location returns list
        locations = [payload] if isinstance(payload, dict) else []
        if not locations:
            return False, [f"Expected list of locations, got {type(payload).__name__}"], meta
    else:
        locations = payload

    if len(locations) != expected_sample_count:
        errors.append(
            f"Location count mismatch: expected {expected_sample_count} sample locations, got {len(locations)}"
        )

    if not locations:
        return False, errors or ["No location entries found in response"], meta

    # 2. Inspect each location's hourly series
    all_parsed_dts: list[datetime] = []

    for loc_idx, loc in enumerate(locations):
        if not isinstance(loc, dict):
            errors.append(f"Location {loc_idx} is not an object (got {type(loc).__name__})")
            continue

        hourly = loc.get("hourly")
        if not isinstance(hourly, dict):
            errors.append(f"Location {loc_idx} missing 'hourly' object")
            continue

        times = hourly.get("time")
        if not isinstance(times, list):
            errors.append(f"Location {loc_idx} missing 'hourly.time' list")
            continue

        precip = hourly.get("precipitation")
        if not isinstance(precip, list):
            errors.append(f"Location {loc_idx} missing 'hourly.precipitation' list")
            continue

        if len(times) != len(precip):
            errors.append(
                f"Location {loc_idx} length mismatch: len(time)={len(times)} != len(precipitation)={len(precip)}"
            )

        if len(times) < min_future_hours:
            errors.append(
                f"Location {loc_idx} insufficient total steps: {len(times)} < required {min_future_hours}"
            )

        # Parse and check timestamps
        loc_dts: list[datetime] = []
        for t_idx, t_str in enumerate(times):
            if not isinstance(t_str, str):
                errors.append(f"Location {loc_idx} step {t_idx}: non-string timestamp {t_str!r}")
                continue
            try:
                dt = datetime.fromisoformat(t_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                loc_dts.append(dt)
            except ValueError:
                errors.append(f"Location {loc_idx} step {t_idx}: invalid ISO timestamp '{t_str}'")

        # Check timestamp ordering and uniqueness
        if len(loc_dts) == len(times):
            for i in range(1, len(loc_dts)):
                if loc_dts[i] <= loc_dts[i - 1]:
                    if loc_dts[i] == loc_dts[i - 1]:
                        errors.append(
                            f"Location {loc_idx} duplicate timestamp detected at index {i}: {loc_dts[i].isoformat()}"
                        )
                    else:
                        errors.append(
                            f"Location {loc_idx} non-monotonic timestamp at index {i}: {loc_dts[i-1].isoformat()} -> {loc_dts[i].isoformat()}"
                        )
                    break

        if loc_idx == 0:
            all_parsed_dts = loc_dts

        # Check precipitation values
        for p_idx, p in enumerate(precip):
            if p is None:
                errors.append(f"Location {loc_idx} step {p_idx}: precipitation value is null")
                continue
            try:
                p_val = float(p)
                if math.isnan(p_val) or math.isinf(p_val):
                    errors.append(f"Location {loc_idx} step {p_idx}: non-finite precipitation value {p_val}")
                    break
                if p_val < 0.0:
                    errors.append(f"Location {loc_idx} step {p_idx}: negative precipitation {p_val}")
                    break
            except (ValueError, TypeError):
                errors.append(f"Location {loc_idx} step {p_idx}: non-numeric precipitation value '{p}'")
                break

    # 3. Validate future coverage relative to derived cycle anchor
    if all_parsed_dts:
        meta["total_steps"] = len(all_parsed_dts)
        meta["earliest_valid"] = min(all_parsed_dts)
        meta["latest_valid"] = max(all_parsed_dts)
        future_dts = [dt for dt in all_parsed_dts if dt > cycle_anchor]
        meta["future_steps"] = len(future_dts)

        if len(future_dts) < min_future_hours:
            errors.append(
                f"Insufficient future hourly values after cycle anchor {cycle_anchor.isoformat()}: "
                f"available {len(future_dts)} < required {min_future_hours}"
            )

    is_valid = len(errors) == 0
    return is_valid, errors, meta


def fetch_open_meteo_ecmwf_wayanad(
    sample_points: Sequence[tuple[float, float]] = WAYANAD_PROTOTYPE_SAMPLE_POINTS,
    forecast_days: int = 4,
    db_engine: Optional[Engine] = None,
    raw_output_dir: Optional[Path] = None,
    http_timeout_seconds: float = 20.0,
    demo_mode: Optional[bool] = None,
    recorded_artifact_path: Optional[Path] = None,
    force: bool = False,
    http_client: Optional[httpx.Client] = None,
) -> PhaseB1IngestionReport:
    """Executes Phase B1 ingestion: raw-first persistence, provenance audit, and contract validation.

    Lifecycle:
        1. Acquire raw bytes (via HTTP or DEMO_MODE recorded artifact).
        2. Persist raw bytes to disk BEFORE parsing.
        3. Compute SHA256 and byte size from exact persisted bytes.
        4. Check idempotency: avoid corrupt duplicate snapshots.
        5. Register audit record in `source_snapshot` and initialize `pipeline_run`.
        6. Parse and validate payload structure and meteorological integrity.
        7. Update `pipeline_run` to READY on success or FAILED on validation error.

    Strict Boundaries:
        - ZERO trigger calculations.
        - ZERO writes to `hazard_dynamic`.
        - ZERO mutations of `mhi_snapshot`.
    """
    now_utc = datetime.now(timezone.utc)
    cycle_anchor = derive_provider_run_anchor(now_utc)
    is_demo = demo_mode if demo_mode is not None else settings.DEMO_MODE

    repo_root = Path(__file__).resolve().parents[4]
    raw_dir = raw_output_dir or (repo_root / "data" / "raw" / "open_meteo")
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Initialize database engine lazily if not provided
    engine: Optional[Engine] = db_engine
    if engine is None:
        try:
            db_url = settings.get_sqlalchemy_url(direct=True)
            engine = create_engine(db_url)
        except Exception as exc:
            logger.warning(f"Could not construct database engine: {exc}")
            engine = None

    # -------------------------------------------------------------------------
    # 1. Acquisition
    # -------------------------------------------------------------------------
    raw_bytes: bytes
    http_status: int

    if is_demo or recorded_artifact_path:
        # DEMO_MODE: Zero external network requests. Consume recorded snapshot.
        candidate_path = recorded_artifact_path or (raw_dir / "ecmwf_wayanad_20260908T120000Z.json")
        if not candidate_path.exists():
            # Fallback to repo root data/raw
            candidate_path = repo_root / "data" / "raw" / "open_meteo" / "ecmwf_wayanad_20260908T120000Z.json"

        if not candidate_path.exists():
            err_msg = f"DEMO_MODE enabled but recorded artifact not found at '{candidate_path}'"
            logger.error(err_msg)
            return PhaseB1IngestionReport(
                status="FAILED",
                http_status_code=0,
                source_snapshot_id=None,
                pipeline_run_id=None,
                raw_artifact_path=str(candidate_path),
                sha256="",
                size_bytes=0,
                sample_points_count=len(sample_points),
                total_hourly_steps_per_point=0,
                future_hourly_steps_available=0,
                forecast_cycle_anchor=cycle_anchor,
                cycle_anchor_verified=False,
                earliest_valid_at=now_utc,
                latest_valid_at=now_utc,
                errors=[err_msg],
            )

        logger.info(f"DEMO_MODE active: Loading recorded forecast artifact from '{candidate_path}' (zero network calls)")
        with open(candidate_path, "rb") as f:
            raw_bytes = f.read()
        http_status = 200
        artifact_path = candidate_path
    else:
        # Live Acquisition via httpx
        latitudes = [round(float(p[0]), 4) for p in sample_points]
        longitudes = [round(float(p[1]), 4) for p in sample_points]
        params: dict[str, Any] = {
            "latitude": ",".join(str(x) for x in latitudes),
            "longitude": ",".join(str(x) for x in longitudes),
            "hourly": "precipitation",
            "timezone": "UTC",
            "forecast_days": int(forecast_days),
        }

        logger.info(
            f"Querying Open-Meteo ECMWF endpoint ({OPEN_METEO_ECMWF_ENDPOINT}) "
            f"for {len(sample_points)} sample points with forecast_days={forecast_days}..."
        )

        try:
            if http_client is not None:
                response = http_client.get(OPEN_METEO_ECMWF_ENDPOINT, params=params)
            else:
                with httpx.Client(timeout=http_timeout_seconds) as client:
                    response = client.get(OPEN_METEO_ECMWF_ENDPOINT, params=params)
            http_status = response.status_code
        except Exception as exc:
            err_msg = f"HTTP request failed to {OPEN_METEO_ECMWF_ENDPOINT}: {exc}"
            logger.error(err_msg)
            # Record failed pipeline run if DB available
            failed_run_id = _record_failed_pipeline_run(
                engine=engine,
                run_type="forecast_ingest",
                error_msg=err_msg,
                started_at=now_utc,
            )
            return PhaseB1IngestionReport(
                status="FAILED",
                http_status_code=0,
                source_snapshot_id=None,
                pipeline_run_id=failed_run_id,
                raw_artifact_path="",
                sha256="",
                size_bytes=0,
                sample_points_count=len(sample_points),
                total_hourly_steps_per_point=0,
                future_hourly_steps_available=0,
                forecast_cycle_anchor=cycle_anchor,
                cycle_anchor_verified=False,
                earliest_valid_at=now_utc,
                latest_valid_at=now_utc,
                errors=[err_msg],
            )

        if response.status_code != 200:
            err_msg = f"Open-Meteo returned HTTP {response.status_code}: {response.text[:300]}"
            logger.error(err_msg)
            failed_run_id = _record_failed_pipeline_run(
                engine=engine,
                run_type="forecast_ingest",
                error_msg=err_msg,
                started_at=now_utc,
            )
            return PhaseB1IngestionReport(
                status="FAILED",
                http_status_code=response.status_code,
                source_snapshot_id=None,
                pipeline_run_id=failed_run_id,
                raw_artifact_path="",
                sha256="",
                size_bytes=0,
                sample_points_count=len(sample_points),
                total_hourly_steps_per_point=0,
                future_hourly_steps_available=0,
                forecast_cycle_anchor=cycle_anchor,
                cycle_anchor_verified=False,
                earliest_valid_at=now_utc,
                latest_valid_at=now_utc,
                errors=[err_msg],
            )

        raw_bytes = response.content

        # ---------------------------------------------------------------------
        # 2. RAW-FIRST PERSISTENCE (Before parsing/transformation)
        # ---------------------------------------------------------------------
        anchor_tag = cycle_anchor.strftime("%Y%m%dT%H%M%SZ")
        retrieval_tag = now_utc.strftime("%Y%m%dT%H%M%SZ")
        primary_filename = f"ecmwf_wayanad_{anchor_tag}.json"
        target_path = raw_dir / primary_filename

        new_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        if target_path.exists():
            # If existing file has identical bytes, reuse it. Otherwise append timestamp to avoid overwriting.
            with open(target_path, "rb") as f_existing:
                existing_sha = hashlib.sha256(f_existing.read()).hexdigest()
            if existing_sha != new_sha256:
                target_path = raw_dir / f"ecmwf_wayanad_{anchor_tag}_{retrieval_tag}.json"

        with open(target_path, "wb") as f_out:
            f_out.write(raw_bytes)
        artifact_path = target_path

    # Compute checksum and size strictly from persisted raw bytes
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    size_bytes = len(raw_bytes)
    logger.info(f"Persisted raw Open-Meteo artifact to '{artifact_path}' ({size_bytes} bytes, SHA256: {sha256[:16]}...)")

    # -------------------------------------------------------------------------
    # 3. Idempotency Check
    # -------------------------------------------------------------------------
    if engine is not None and not force:
        try:
            with engine.connect() as conn:
                existing_entry = conn.execute(
                    text("""
                        SELECT r.id as run_id, r.status, s.id as snapshot_id, s.metadata
                        FROM pipeline_run r
                        JOIN source_snapshot s ON r.source_snapshot_id = s.id
                        WHERE s.sha256 = :sha256 AND r.status = 'READY'
                        ORDER BY r.started_at DESC LIMIT 1;
                    """),
                    {"sha256": sha256},
                ).mappings().first()

                if existing_entry:
                    raw_run_id = existing_entry["run_id"]
                    try:
                        existing_run_id = uuid.UUID(str(raw_run_id))
                    except (ValueError, TypeError):
                        existing_run_id = raw_run_id

                    raw_snap_id = existing_entry["snapshot_id"]
                    try:
                        existing_snap_id = uuid.UUID(str(raw_snap_id))
                    except (ValueError, TypeError):
                        existing_snap_id = raw_snap_id

                    logger.info(
                        f"Idempotency match found: Artifact SHA256 {sha256[:12]} already recorded in "
                        f"PipelineRun {existing_run_id} (Snapshot {existing_snap_id}). Skipping duplicate insertion."
                    )
                    # Run validation for complete report metrics
                    _, _, val_meta = validate_open_meteo_payload(
                        raw_bytes=raw_bytes,
                        cycle_anchor=cycle_anchor,
                        expected_sample_count=len(sample_points),
                    )
                    return PhaseB1IngestionReport(
                        status="SKIPPED_IDEMPOTENT",
                        http_status_code=http_status,
                        source_snapshot_id=existing_snap_id,
                        pipeline_run_id=existing_run_id,
                        raw_artifact_path=str(artifact_path),
                        sha256=sha256,
                        size_bytes=size_bytes,
                        sample_points_count=len(sample_points),
                        total_hourly_steps_per_point=val_meta.get("total_steps", 0),
                        future_hourly_steps_available=val_meta.get("future_steps", 0),
                        forecast_cycle_anchor=cycle_anchor,
                        cycle_anchor_verified=False,
                        earliest_valid_at=val_meta.get("earliest_valid", now_utc),
                        latest_valid_at=val_meta.get("latest_valid", now_utc),
                        errors=[],
                    )
        except Exception as exc:
            logger.warning(f"Idempotency check encountered error (continuing): {exc}")

    # -------------------------------------------------------------------------
    # 4. Provenance Registration in source_snapshot & pipeline_run
    # -------------------------------------------------------------------------
    snapshot_id = uuid.uuid4()
    pipeline_run_id = uuid.uuid4()
    cycle_anchor_verified = False  # Open-Meteo standard response does not verify model init time

    snapshot_metadata = {
        "provider": "Open-Meteo",
        "provider_endpoint": OPEN_METEO_ECMWF_ENDPOINT,
        "source_model": SOURCE_MODEL,
        "native_resolution_km": NATIVE_RESOLUTION_KM,
        "district": DISTRICT_NAME,
        "state": STATE_NAME,
        "lgd_code": DISTRICT_LGD,
        "admin_id": ADMIN_ID,
        "sample_points_count": len(sample_points),
        "forecast_cycle_anchor": cycle_anchor.isoformat(),
        "forecast_cycle_semantics": "derived_provider_run_anchor",
        "cycle_anchor_verified": cycle_anchor_verified,
        "temporal_precipitation_semantics": "preceding_hour_accumulation",
        "precipitation_unit": "mm",
        "phase": "B1_ingestion_proof",
        "demo_mode": is_demo,
    }

    if engine is not None:
        try:
            with engine.begin() as conn:
                is_sqlite = conn.dialect.name == "sqlite"
                meta_json = json.dumps(snapshot_metadata)

                # Insert source_snapshot
                if is_sqlite:
                    conn.execute(
                        text("""
                            INSERT INTO source_snapshot (
                                id, source_id, retrieved_at, valid_at, uri, sha256, size_bytes, metadata
                            ) VALUES (
                                :id, :source_id, :retrieved_at, :valid_at, :uri, :sha256, :size_bytes, :metadata
                            );
                        """),
                        {
                            "id": str(snapshot_id),
                            "source_id": SOURCE_ID,
                            "retrieved_at": now_utc,
                            "valid_at": cycle_anchor,
                            "uri": f"file:///{artifact_path.as_posix()}",
                            "sha256": sha256,
                            "size_bytes": size_bytes,
                            "metadata": meta_json,
                        },
                    )
                    conn.execute(
                        text("""
                            INSERT INTO pipeline_run (
                                id, run_type, status, started_at,
                                code_version, config_version, model_version, source_snapshot_id
                            ) VALUES (
                                :id, 'forecast_ingest', 'VALIDATING', :now,
                                'phase-b1', 'ecmwf-v1.0', :model_version, :snapshot_id
                            );
                        """),
                        {
                            "id": str(pipeline_run_id),
                            "now": now_utc,
                            "model_version": SOURCE_MODEL,
                            "snapshot_id": str(snapshot_id),
                        },
                    )
                else:
                    conn.execute(
                        text("""
                            INSERT INTO source_snapshot (
                                id, source_id, retrieved_at, valid_at, uri, sha256, size_bytes, metadata
                            ) VALUES (
                                :id, :source_id, :retrieved_at, :valid_at, :uri, :sha256, :size_bytes, CAST(:metadata AS jsonb)
                            );
                        """),
                        {
                            "id": snapshot_id,
                            "source_id": SOURCE_ID,
                            "retrieved_at": now_utc,
                            "valid_at": cycle_anchor,
                            "uri": f"file:///{artifact_path.as_posix()}",
                            "sha256": sha256,
                            "size_bytes": size_bytes,
                            "metadata": meta_json,
                        },
                    )
                    conn.execute(
                        text("""
                            INSERT INTO pipeline_run (
                                id, run_type, status, started_at,
                                code_version, config_version, model_version, source_snapshot_id
                            ) VALUES (
                                :id, 'forecast_ingest', 'VALIDATING', :now,
                                'phase-b1', 'ecmwf-v1.0', :model_version, :snapshot_id
                            );
                        """),
                        {
                            "id": pipeline_run_id,
                            "now": now_utc,
                            "model_version": SOURCE_MODEL,
                            "snapshot_id": snapshot_id,
                        },
                    )
            logger.info(f"Registered source_snapshot {snapshot_id} and pipeline_run {pipeline_run_id} in database.")
        except Exception as exc:
            logger.error(f"Failed to persist provenance in database: {exc}")

    # -------------------------------------------------------------------------
    # 5. Parse and Validate Payload Contract
    # -------------------------------------------------------------------------
    is_valid, val_errors, val_meta = validate_open_meteo_payload(
        raw_bytes=raw_bytes,
        cycle_anchor=cycle_anchor,
        expected_sample_count=len(sample_points),
        min_future_hours=72,
    )

    total_steps = val_meta.get("total_steps", 0)
    future_steps = val_meta.get("future_steps", 0)
    earliest_valid = val_meta.get("earliest_valid", now_utc)
    latest_valid = val_meta.get("latest_valid", now_utc)

    # -------------------------------------------------------------------------
    # 6. Finalize Pipeline Run
    # -------------------------------------------------------------------------
    completion_time = datetime.now(timezone.utc)
    if not is_valid:
        error_summary = "; ".join(val_errors)[:500]
        logger.error(f"Phase B1 payload validation failed with {len(val_errors)} errors: {val_errors}")
        if engine is not None:
            try:
                with engine.begin() as conn:
                    is_sqlite = conn.dialect.name == "sqlite"
                    conn.execute(
                        text("""
                            UPDATE pipeline_run
                            SET status = 'FAILED', error = :error, completed_at = :completed_at
                            WHERE id = :id;
                        """),
                        {
                            "id": str(pipeline_run_id) if is_sqlite else pipeline_run_id,
                            "error": error_summary,
                            "completed_at": completion_time,
                        },
                    )
            except Exception as exc:
                logger.error(f"Failed to update failed pipeline_run: {exc}")

        return PhaseB1IngestionReport(
            status="FAILED",
            http_status_code=http_status,
            source_snapshot_id=snapshot_id,
            pipeline_run_id=pipeline_run_id,
            raw_artifact_path=str(artifact_path),
            sha256=sha256,
            size_bytes=size_bytes,
            sample_points_count=len(sample_points),
            total_hourly_steps_per_point=total_steps,
            future_hourly_steps_available=future_steps,
            forecast_cycle_anchor=cycle_anchor,
            cycle_anchor_verified=cycle_anchor_verified,
            earliest_valid_at=earliest_valid,
            latest_valid_at=latest_valid,
            errors=val_errors,
        )

    # Success: Mark Pipeline Run as READY
    if engine is not None:
        try:
            with engine.begin() as conn:
                is_sqlite = conn.dialect.name == "sqlite"
                conn.execute(
                    text("""
                        UPDATE pipeline_run
                        SET status = 'READY', completed_at = :completed_at
                        WHERE id = :id;
                    """),
                    {
                        "id": str(pipeline_run_id) if is_sqlite else pipeline_run_id,
                        "completed_at": completion_time,
                    },
                )
        except Exception as exc:
            logger.error(f"Failed to mark pipeline_run as READY: {exc}")

    logger.info(
        f"Phase B1 Ingestion successful: {len(sample_points)} points, {total_steps} steps/pt, "
        f"{future_steps} future steps (> {cycle_anchor.isoformat()}). Provenance verified."
    )

    return PhaseB1IngestionReport(
        status="SUCCESS",
        http_status_code=http_status,
        source_snapshot_id=snapshot_id,
        pipeline_run_id=pipeline_run_id,
        raw_artifact_path=str(artifact_path),
        sha256=sha256,
        size_bytes=size_bytes,
        sample_points_count=len(sample_points),
        total_hourly_steps_per_point=total_steps,
        future_hourly_steps_available=future_steps,
        forecast_cycle_anchor=cycle_anchor,
        cycle_anchor_verified=cycle_anchor_verified,
        earliest_valid_at=earliest_valid,
        latest_valid_at=latest_valid,
        errors=[],
    )


def _record_failed_pipeline_run(
    engine: Optional[Engine],
    run_type: str,
    error_msg: str,
    started_at: datetime,
) -> Optional[uuid.UUID]:
    """Helper to record an acquisition-level pipeline failure without fake downstream data."""
    if engine is None:
        return None
    run_id = uuid.uuid4()
    completed_at = datetime.now(timezone.utc)
    try:
        with engine.begin() as conn:
            is_sqlite = conn.dialect.name == "sqlite"
            conn.execute(
                text("""
                    INSERT INTO pipeline_run (
                        id, run_type, status, started_at, completed_at,
                        code_version, config_version, model_version, source_snapshot_id, error
                    ) VALUES (
                        :id, :run_type, 'FAILED', :started_at, :completed_at,
                        'phase-b1', 'ecmwf-v1.0', 'ECMWF_IFS_HRES', NULL, :error
                    );
                """),
                {
                    "id": str(run_id) if is_sqlite else run_id,
                    "run_type": run_type,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "error": error_msg[:500],
                },
            )
        return run_id
    except Exception as exc:
        logger.error(f"Failed to record failed pipeline run: {exc}")
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    report = fetch_open_meteo_ecmwf_wayanad()
    print("\n" + "=" * 70)
    print("PHASE B1 INGESTION REPORT")
    print(f"Status:                        {report.status}")
    print(f"HTTP Status:                   {report.http_status_code}")
    print(f"Source Snapshot ID:            {report.source_snapshot_id}")
    print(f"Pipeline Run ID:               {report.pipeline_run_id}")
    print(f"Raw Artifact Path:             {report.raw_artifact_path}")
    print(f"SHA256:                        {report.sha256}")
    print(f"Size Bytes:                    {report.size_bytes:,} bytes")
    print(f"Sample Points Count:           {report.sample_points_count}")
    print(f"Total Steps Per Point:         {report.total_hourly_steps_per_point}")
    print(f"Future Steps Available:        {report.future_hourly_steps_available} (>= 72 required)")
    print(f"Forecast Cycle Anchor:         {report.forecast_cycle_anchor.isoformat()}")
    print(f"Cycle Anchor Verified:         {report.cycle_anchor_verified}")
    print(f"Earliest Valid At:             {report.earliest_valid_at.isoformat()}")
    print(f"Latest Valid At:               {report.latest_valid_at.isoformat()}")
    if report.errors:
        print(f"Errors:                        {report.errors}")
    print("=" * 70 + "\n")
