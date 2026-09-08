"""Service layer for static hazard layers consumed by the vector map."""

from typing import Optional

from sqlalchemy.orm import Session

from core.constants import PRZ_ANY_SUSCEPTIBILITY
from core.enums import Hazard, CoverageFlag
from core.errors import (
    DataUnavailableError,
    InvalidBboxError,
    InvalidH3IndexError,
    InvalidParametersError,
    InvalidResolutionError,
)
from core.h3_utils import h3_to_int, h3_to_str, is_valid_h3
from core.schemas.hazard import (
    FloodDriverDTO,
    HazardCellDTO,
    HazardCellDetailDTO,
    HazardLayerCoverageDTO,
    HazardLayerLegendDTO,
    HazardLayerResponse,
    HazardLayerSummaryDTO,
)
from api.repositories.hazard_repo import HazardRepository

# Class breaks are sampled here rather than at even value intervals. See
# HazardLayerLegendDTO for why a linear ramp fails on this distribution.
DEFAULT_QUANTILES: list[float] = [0.25, 0.5, 0.75, 0.90, 0.95, 0.99]

ALLOWED_RESOLUTIONS: tuple[int, ...] = (6, 7, 8, 9)

MAX_BBOX_AREA_SQ_DEG: float = 5.0

MAX_CELL_LIMIT: int = 30000


class HazardService:
    def __init__(self, db: Session) -> None:
        self.repo = HazardRepository(db)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_bbox(bbox: Optional[str]) -> tuple[Optional[float], ...]:
        """Parses and range-checks a 'min_lon,min_lat,max_lon,max_lat' string."""
        if not bbox:
            return (None, None, None, None)

        parts = bbox.split(",")
        if len(parts) != 4:
            raise InvalidBboxError(
                "BBox format must be 'min_lon,min_lat,max_lon,max_lat'.", {"bbox": bbox}
            )
        try:
            min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
        except ValueError:
            raise InvalidBboxError(
                "BBox coordinates must be valid floating-point numbers.", {"bbox": bbox}
            )

        if not (-180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0):
            raise InvalidBboxError("Longitude values must be between -180 and 180.")
        if not (-90.0 <= min_lat <= 90.0 and -90.0 <= max_lat <= 90.0):
            raise InvalidBboxError("Latitude values must be between -90 and 90.")
        if min_lon >= max_lon or min_lat >= max_lat:
            raise InvalidBboxError("min_lon/min_lat must be strictly less than max_lon/max_lat.")

        area = (max_lon - min_lon) * (max_lat - min_lat)
        if area > MAX_BBOX_AREA_SQ_DEG:
            raise InvalidBboxError(
                f"BBox area ({area:.2f} sq deg) exceeds maximum allowed viewport "
                f"({MAX_BBOX_AREA_SQ_DEG} sq deg).",
                {"bbox_area": area, "max_allowed": MAX_BBOX_AREA_SQ_DEG},
            )
        return (min_lon, min_lat, max_lon, max_lat)

    @staticmethod
    def _validate_hazard_type(hazard_type: str) -> str:
        try:
            return Hazard(hazard_type).value
        except ValueError:
            raise InvalidParametersError(
                f"Unknown hazard_type '{hazard_type}'.",
                {"hazard_type": hazard_type, "allowed": [h.value for h in Hazard]},
            )

    @staticmethod
    def _dedupe_ascending(values: list[float]) -> list[float]:
        """Drops duplicate and non-monotonic breaks so the legend never renders empty classes."""
        result: list[float] = []
        for v in values:
            rounded = round(float(v), 4)
            if not result or rounded > result[-1]:
                result.append(rounded)
        return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_layers(self) -> list[HazardLayerSummaryDTO]:
        """Enumerates published static hazard layers so the client can build its layer switcher."""
        rows = self.repo.list_layers()
        return [
            HazardLayerSummaryDTO(
                hazard_type=r["hazard_type"],
                res=int(r["res"]),
                cell_count=int(r["cell_count"]),
                model_version=r["model_version"] or "v1.0.0",
                min_susceptibility=round(float(r["min_susceptibility"] or 0.0), 4),
                max_susceptibility=round(float(r["max_susceptibility"] or 0.0), 4),
                mean_susceptibility=round(float(r["mean_susceptibility"] or 0.0), 4),
                confidence_ceiling=round(float(r["confidence_ceiling"] or 1.0), 4),
            )
            for r in rows
        ]

    def get_layer(
        self,
        hazard_type: str = Hazard.RIVERINE_FLOOD.value,
        res: int = 8,
        bbox: Optional[str] = None,
        admin: Optional[int] = None,
        min_susceptibility: float = 0.0,
        limit: int = 20000,
    ) -> HazardLayerResponse:
        """Returns every hazard cell in the viewport plus the legend needed to colour them."""
        hazard = self._validate_hazard_type(hazard_type)

        if res not in ALLOWED_RESOLUTIONS:
            raise InvalidResolutionError(res, list(ALLOWED_RESOLUTIONS))

        if not (0.0 <= min_susceptibility <= 1.0):
            raise InvalidParametersError(
                "min_susceptibility must be within [0.0, 1.0].",
                {"min_susceptibility": min_susceptibility},
            )

        min_lon, min_lat, max_lon, max_lat = self._parse_bbox(bbox)
        clamped_limit = min(max(1, limit), MAX_CELL_LIMIT)

        stats = self.repo.query_layer_statistics(
            hazard_type=hazard,
            res=res,
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            admin=admin,
            quantiles=DEFAULT_QUANTILES,
        )
        if stats is None:
            raise DataUnavailableError(
                f"No '{hazard}' cells published at resolution {res} for the requested extent.",
                {"hazard_type": hazard, "res": res, "bbox": bbox, "admin": admin},
            )

        rows = self.repo.query_layer_cells(
            hazard_type=hazard,
            res=res,
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            admin=admin,
            min_susceptibility=min_susceptibility,
            limit=clamped_limit,
        )

        cells = [
            HazardCellDTO(
                h3=h3_to_str(int(r["h3"])),
                susceptibility=round(float(r["susceptibility"] or 0.0), 4),
                confidence=round(float(r["confidence"] or 0.0), 4),
                quality_flag=self._coerce_flag(r["quality_flag"]),
                hard_zero_fraction=(
                    round(float(r["hard_zero_fraction"]), 4)
                    if r["hard_zero_fraction"] is not None
                    else None
                ),
            )
            for r in rows
        ]

        # A ceiling of 0 would make the client divide by zero; fall back to 1.0 so an
        # unpopulated confidence column degrades to "raw values are already displayable".
        ceiling = float(stats["confidence_ceiling"] or 0.0) or 1.0

        legend = HazardLayerLegendDTO(
            method="quantile",
            quantiles=list(DEFAULT_QUANTILES),
            breaks=self._dedupe_ascending(list(stats["breaks"] or [])),
            domain=[
                round(float(stats["min_susceptibility"] or 0.0), 4),
                round(float(stats["max_susceptibility"] or 1.0), 4),
            ],
            confidence_ceiling=round(ceiling, 4),
            prz_susceptibility_threshold=PRZ_ANY_SUSCEPTIBILITY,
        )

        coverage = HazardLayerCoverageDTO(
            full=int(stats["full_count"] or 0),
            low_coverage=int(stats["low_coverage_count"] or 0),
            no_coverage=int(stats["no_coverage_count"] or 0),
        )

        return HazardLayerResponse(
            hazard_type=hazard,
            res=res,
            count=len(cells),
            truncated=len(cells) >= clamped_limit,
            model_version=stats["model_version"] or "v1.0.0",
            legend=legend,
            coverage=coverage,
            cells=cells,
        )

    def get_cell_detail(
        self,
        h3_param: str,
        hazard_type: str = Hazard.RIVERINE_FLOOD.value,
    ) -> HazardCellDetailDTO:
        """Retrieves the per-cell dossier: score, coverage provenance, and physical drivers."""
        hazard = self._validate_hazard_type(hazard_type)

        if not is_valid_h3(h3_param):
            raise InvalidH3IndexError(h3_param)

        h3_int = h3_to_int(h3_param)
        row = self.repo.get_cell_detail(h3_int, hazard)
        if not row:
            raise DataUnavailableError(
                f"H3 cell '{h3_param}' has no published '{hazard}' record.",
                {"h3": h3_param, "hazard_type": hazard},
            )

        ceiling = self.repo.get_confidence_ceiling(hazard) or 1.0
        confidence = float(row["confidence"] or 0.0)
        susceptibility = float(row["susceptibility"] or 0.0)

        drivers = FloodDriverDTO(
            mean_inundation_frequency=self._opt_round(row["mean_inundation_frequency"], 4),
            mean_hand_m=self._opt_round(row["mean_hand_m"], 2),
            min_hand_m=self._opt_round(row["min_hand_m"], 2),
            mean_slope_deg=self._opt_round(row["mean_slope_deg"], 2),
            mean_cropland_fraction=self._opt_round(row["mean_cropland_fraction"], 4),
            max_susceptibility=self._opt_round(row["max_susceptibility"], 4),
            valid_pixel_fraction=self._opt_round(row["valid_pixel_fraction"], 4),
            hard_zero_fraction=self._opt_round(row["hard_zero_fraction"], 4),
            observation_ceiling=int(row["observation_ceiling"] or 30),
        )

        return HazardCellDetailDTO(
            h3=h3_to_str(h3_int),
            h3_int=h3_int,
            res=int(row["res"]),
            hazard_type=row["hazard_type"],
            susceptibility=round(susceptibility, 4),
            confidence=round(confidence, 4),
            confidence_normalised=round(min(1.0, confidence / ceiling), 4),
            quality_flag=self._coerce_flag(row["quality_flag"]),
            model_version=row["model_version"] or "v1.0.0",
            centroid=[round(float(row["lon"]), 6), round(float(row["lat"]), 6)],
            admin_name=row["admin_name"],
            population=round(float(row["population"] or 0.0), 2),
            is_permanent_red_candidate=susceptibility >= PRZ_ANY_SUSCEPTIBILITY,
            drivers=drivers,
        )

    # ------------------------------------------------------------------
    # Coercion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_flag(value: Optional[str]) -> CoverageFlag:
        """Never silently upgrades an unknown flag to FULL — unknown provenance is not full coverage."""
        try:
            return CoverageFlag(value or CoverageFlag.FULL.value)
        except ValueError:
            return CoverageFlag.LOW_COVERAGE

    @staticmethod
    def _opt_round(value: Optional[float], digits: int) -> Optional[float]:
        return round(float(value), digits) if value is not None else None
