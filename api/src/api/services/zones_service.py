"""Service layer for H3 Zone queries and Cell Details."""

from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from core.h3_utils import is_valid_h3, h3_to_int, h3_to_str
from core.enums import ZoneClass
from core.errors import (
    InvalidH3IndexError,
    InvalidBboxError,
    InvalidResolutionError,
    DataUnavailableError,
)
from core.schemas.zones import (
    ZoneCellSummary,
    ZoneCellDetail,
    HazardDetailDTO,
)
from core.schemas.explanation import FeatureContributionDTO
from api.repositories.zones_repo import ZonesRepository


class ZonesService:
    def __init__(self, db: Session) -> None:
        self.repo = ZonesRepository(db)

    def get_zones(
        self,
        bbox: Optional[str] = None,
        res: int = 8,
        valid_at: Optional[datetime] = None,
        admin: Optional[int] = None,
        limit: int = 1000,
    ) -> list[ZoneCellSummary]:
        """Queries H3 cells within spatial viewport and returns summary records."""
        # 1. Validate resolution
        if res not in (6, 7, 8, 9):
            raise InvalidResolutionError(res)

        # 2. Validate and parse BBox
        min_lon = min_lat = max_lon = max_lat = None
        if bbox:
            parts = bbox.split(",")
            if len(parts) != 4:
                raise InvalidBboxError(
                    "BBox format must be 'min_lon,min_lat,max_lon,max_lat'.",
                    {"bbox": bbox},
                )
            try:
                min_lon, min_lat, max_lon, max_lat = map(float, parts)
            except ValueError:
                raise InvalidBboxError(
                    "BBox coordinates must be valid floating-point numbers.",
                    {"bbox": bbox},
                )

            # Spatial boundary checks
            if not (-180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0):
                raise InvalidBboxError("Longitude values must be between -180 and 180.")
            if not (-90.0 <= min_lat <= 90.0 and -90.0 <= max_lat <= 90.0):
                raise InvalidBboxError("Latitude values must be between -90 and 90.")
            if min_lon >= max_lon or min_lat >= max_lat:
                raise InvalidBboxError("min_lon/min_lat must be strictly less than max_lon/max_lat.")

            # Area limit check (Prevent querying overly large bounding box)
            bbox_area = (max_lon - min_lon) * (max_lat - min_lat)
            if bbox_area > 5.0:
                raise InvalidBboxError(
                    f"BBox area ({bbox_area:.2f} sq deg) exceeds maximum allowed viewport (5.0 sq deg).",
                    {"bbox_area": bbox_area, "max_allowed": 5.0},
                )

        # Cap limit
        clamped_limit = min(max(1, limit), 5000)

        # 3. Check snapshot availability if valid_at is supplied (H1)
        target_valid_at = None
        if valid_at is not None:
            target_valid_at = self.repo.resolve_snapshot_valid_at(valid_at)
            if target_valid_at is None:
                raise DataUnavailableError(
                    f"No hazard zone snapshot available at or before '{valid_at.isoformat()}'.",
                    {"valid_at": valid_at.isoformat()},
                )

        # 4. Query repository
        records = self.repo.query_zones(
            res=res,
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            admin_id=admin,
            limit=clamped_limit,
            valid_at=target_valid_at,
        )

        summaries = []
        for r in records:
            h_int = r["h3"]
            h_str = h3_to_str(h_int)
            mhi_val = r.get("mhi_static") if r.get("mhi_static") is not None else 0.0
            zone_class_str = r.get("zone_class") or "none"
            try:
                zone_class_enum = ZoneClass(zone_class_str)
            except ValueError:
                zone_class_enum = ZoneClass.NONE

            # Preserve dynamic MHI values without recomputation or falsy fallbacks (H2)
            raw_live = r.get("mhi_live")
            raw_fcst = r.get("mhi_fcst")
            mhi_live_val = round(float(raw_live), 4) if raw_live is not None else None
            mhi_fcst_val = round(float(raw_fcst), 4) if raw_fcst is not None else None

            summaries.append(
                ZoneCellSummary(
                    h3=h_str,
                    h3_int=h_int,
                    res=r["res"],
                    mhi=round(float(mhi_val), 4),
                    mhi_static=round(float(mhi_val), 4),
                    mhi_live=mhi_live_val,
                    mhi_fcst=mhi_fcst_val,
                    dominant_hazard=r.get("dominant_hazard") or "landslide",
                    zone_class=zone_class_enum,
                    dataset_version=r.get("dataset_version") or "demo-day2-v1",
                    model_version="baseline-v1",
                    data_quality="synthetic",
                    population=round(float(r.get("population") if r.get("population") is not None else 0.0), 2),
                    built_area_m2=round(float(r.get("built_area_m2") if r.get("built_area_m2") is not None else 0.0), 2),
                    centroid=[r["lon"], r["lat"]],
                )
            )

        return summaries

    def get_zone_detail(self, h3_param: str) -> ZoneCellDetail:
        """Retrieves full cell dossier with SHAP / heuristic explanations."""
        if not is_valid_h3(h3_param):
            raise InvalidH3IndexError(h3_param)

        h3_int = h3_to_int(h3_param)
        data = self.repo.get_zone_by_h3(h3_int)
        if not data:
            raise DataUnavailableError(f"H3 cell '{h3_param}' is not populated in the current dataset.")

        cell = data["cell"]
        hazards = data["hazards"]

        # Parse zone class
        zone_class_str = cell.get("zone_class") or "none"
        try:
            zone_class_enum = ZoneClass(zone_class_str)
        except ValueError:
            zone_class_enum = ZoneClass.NONE

        # Format hazard items
        hazard_dtos = []
        for hz in hazards:
            sus = float(hz.get("susceptibility") if hz.get("susceptibility") is not None else 0.0)
            hazard_dtos.append(
                HazardDetailDTO(
                    hazard_type=hz["hazard_type"],
                    susceptibility=round(sus, 4),
                    confidence=round(float(hz.get("confidence") if hz.get("confidence") is not None else 1.0), 2),
                    trigger_value=None,
                    forecast_trigger=None,
                    score=round(sus, 4),
                )
            )

        # Parse explanation factors
        factors_raw = cell.get("factors") or []
        explanation_dtos = []
        for f in factors_raw:
            feat_v = f.get("value")
            feat_c = f.get("contribution")
            explanation_dtos.append(
                FeatureContributionDTO(
                    feature=f.get("feature", "unknown"),
                    value=round(float(feat_v if feat_v is not None else 0.0), 2),
                    contribution=round(float(feat_c if feat_c is not None else 0.0), 4),
                    method=f.get("method", "heuristic"),
                    rank=f.get("rank"),
                )
            )

        return ZoneCellDetail(
            h3=h3_to_str(h3_int),
            h3_int=h3_int,
            res=cell["res"],
            dataset_version=cell.get("dataset_version") or "demo-day2-v1",
            model_version=cell.get("model_version") or "baseline-v1",
            data_quality="synthetic",
            valid_at=cell.get("valid_at") or datetime.now(timezone.utc),
            admin_id=cell.get("admin_id"),
            admin_name=cell.get("admin_name"),
            habitation_id=cell.get("habitation_id"),
            habitation_name=cell.get("habitation_name"),
            population=round(float(cell.get("population") if cell.get("population") is not None else 0.0), 2),
            built_area_m2=round(float(cell.get("built_area_m2") if cell.get("built_area_m2") is not None else 0.0), 2),
            centroid=[cell["lon"], cell["lat"]],
            mhi_static=round(float(cell.get("mhi_static") if cell.get("mhi_static") is not None else 0.0), 4),
            mhi_live=round(float(cell["mhi_live"]), 4) if cell.get("mhi_live") is not None else None,
            mhi_fcst=round(float(cell["mhi_fcst"]), 4) if cell.get("mhi_fcst") is not None else None,
            dominant_hazard=cell.get("dominant_hazard") or "landslide",
            zone_class=zone_class_enum,
            confidence=0.85,
            hazards=hazard_dtos,
            explanation=explanation_dtos,
            screening_grade=cell.get("screening_grade") or "Screening Grade: Geotechnical investigation required before decision",
        )
