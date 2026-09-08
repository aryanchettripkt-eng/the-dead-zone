"""Service layer for Active and Forecast Alert Zones (Day 6).

Section refs: docs/PRD1.md §6.3, §8.2, §14.1 (FR-3.10, FR-3.12, FR-3.15)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy.orm import Session

from api.repositories.alerts_repo import AlertsRepository
from core.config import settings
from core.constants import (
    ACTIVE_ALERT_MHI_LIVE,
    FORECAST_HORIZON_HOURS,
    MAX_TRIGGER_AGE_HOURS,
    PRZ_MHI_STATIC,
    SCREENING_GRADE_NOTICE,
)
from core.domain.hazard import evaluate_trigger_freshness
from core.enums import DataQuality
from core.errors import InvalidParametersError
from core.h3_utils import h3_to_str
from core.schemas.alerts import (
    ActiveAlertItem,
    ActiveAlertsResponse,
    ForecastAlertItem,
    ForecastAlertsResponse,
)

logger = logging.getLogger("setu_api.alerts_service")


class AlertsService:
    """Business logic for serving active trigger alerts and forecast threshold crossings."""

    def __init__(self, db: Session) -> None:
        self.repo = AlertsRepository(db)

    def evaluate_alert_freshness(
        self,
        valid_at: datetime,
        as_of: Optional[datetime] = None,
        max_age_hours: Optional[int] = None,
        source: Optional[str] = None,
    ) -> dict[str, Any]:
        """Evaluates trigger age and freshness according to canonical H5 rules."""
        max_age = max_age_hours if max_age_hours is not None else MAX_TRIGGER_AGE_HOURS
        return evaluate_trigger_freshness(valid_at, as_of=as_of, max_age_hours=max_age, source=source)

    def get_active_alerts(
        self,
        admin_id: Optional[int] = None,
        min_mhi: float = ACTIVE_ALERT_MHI_LIVE,
        dominant_hazard: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        as_of: Optional[datetime] = None,
        max_age_hours: Optional[int] = None,
    ) -> ActiveAlertsResponse:
        """Retrieves currently active dynamic alert cells exceeding MHI >= 0.75."""
        clamped_limit = min(max(limit, 1), 500)
        clamped_offset = max(offset, 0)

        records, total_cells, total_pop = self.repo.query_active_alerts(
            admin_id=admin_id,
            min_mhi=min_mhi,
            dominant_hazard=dominant_hazard,
            limit=clamped_limit,
            offset=clamped_offset,
            as_of=as_of,
            max_age_hours=max_age_hours if max_age_hours is not None else settings.MAX_TRIGGER_AGE_HOURS,
        )

        items: list[ActiveAlertItem] = []
        for r in records:
            h_int = r["h3"]
            h_str = h3_to_str(h_int)
            mhi_live = float(r.get("mhi_live") if r.get("mhi_live") is not None else 0.0)
            mhi_static = float(r.get("mhi_static") if r.get("mhi_static") is not None else 0.0)
            item_source = r.get("trigger_source") or r.get("source")
            is_synthetic = bool(
                item_source == "SYNTHETIC_DEMO"
                or (item_source and item_source.startswith("SYNTHETIC"))
                or (item_source and "DEMO" in item_source)
            )
            item_quality = DataQuality.SYNTHETIC if is_synthetic else DataQuality.VALID
            age_hours_val = float(r["age_hours"]) if r.get("age_hours") is not None else None

            items.append(
                ActiveAlertItem(
                    h3=h_str,
                    h3_int=h_int,
                    res=r["res"],
                    admin_id=r.get("admin_id"),
                    admin_name=r.get("admin_name"),
                    mhi_live=round(mhi_live, 4),
                    mhi_static=round(mhi_static, 4),
                    dominant_hazard=r.get("dominant_hazard") or "landslide",
                    trigger_source=item_source,
                    valid_at=r.get("valid_at"),
                    age_hours=age_hours_val,
                    data_quality=item_quality,
                    exposed_population=round(float(r.get("population") if r.get("population") is not None else 0.0), 2),
                    exposed_built_area_m2=round(float(r.get("built_area_m2") if r.get("built_area_m2") is not None else 0.0), 2),
                    centroid=[r["lon"], r["lat"]],
                    screening_grade=SCREENING_GRADE_NOTICE,
                )
            )

        return ActiveAlertsResponse(
            total_active_cells=total_cells,
            total_exposed_population=total_pop,
            issued_at=None,
            items=items,
        )

    def get_forecast_alerts(
        self,
        horizon_hours: int = 72,
        admin_id: Optional[int] = None,
        min_mhi: float = ACTIVE_ALERT_MHI_LIVE,
        limit: int = 100,
        offset: int = 0,
    ) -> ForecastAlertsResponse:
        """Retrieves forecast alert cells predicted to cross threshold within horizon (max 72h).
        
        Enforces FR-3.12 / FR-3.15: Horizon must be between 1 and 72 hours.
        """
        if horizon_hours < 1 or horizon_hours > FORECAST_HORIZON_HOURS:
            raise InvalidParametersError(
                f"Forecast horizon {horizon_hours}h is outside supported bounds [1, {FORECAST_HORIZON_HOURS}]."
            )

        clamped_limit = min(max(limit, 1), 500)
        clamped_offset = max(offset, 0)

        records, total_cells, total_pop = self.repo.query_forecast_alerts(
            admin_id=admin_id,
            min_mhi=min_mhi,
            horizon_hours=horizon_hours,
            limit=clamped_limit,
            offset=clamped_offset,
        )

        # Resolve forecast cycle from records or repository without fabricating now_utc
        resolved_cycle: Optional[datetime] = None
        if records and records[0].get("forecast_cycle_at"):
            resolved_cycle = records[0]["forecast_cycle_at"]
        else:
            resolved_cycle = self.repo.get_latest_forecast_cycle()

        items: list[ForecastAlertItem] = []

        for r in records:
            h_int = r["h3"]
            h_str = h3_to_str(h_int)
            mhi_fcst = float(r.get("mhi_fcst") if r.get("mhi_fcst") is not None else 0.0)
            mhi_static = float(r.get("mhi_static") if r.get("mhi_static") is not None else 0.0)
            item_cycle = r.get("forecast_cycle_at") or resolved_cycle
            item_horizon = r.get("horizon_hours") if r.get("horizon_hours") is not None else horizon_hours

            item_source = r.get("source")
            is_synthetic = bool(
                item_source == "SYNTHETIC_DEMO"
                or (item_source and item_source.startswith("SYNTHETIC"))
                or (item_source and "DEMO" in item_source)
            )
            item_quality = DataQuality.SYNTHETIC if is_synthetic else DataQuality.VALID

            items.append(
                ForecastAlertItem(
                    h3=h_str,
                    h3_int=h_int,
                    res=r["res"],
                    admin_id=r.get("admin_id"),
                    admin_name=r.get("admin_name"),
                    mhi_fcst=round(mhi_fcst, 4),
                    mhi_static=round(mhi_static, 4),
                    dominant_hazard=r.get("dominant_hazard") or "landslide",
                    issuing_model=None,
                    forecast_cycle_at=item_cycle,
                    valid_at=r.get("valid_at"),
                    horizon_hours=item_horizon,
                    data_quality=item_quality,
                    exposed_population=round(float(r.get("population") if r.get("population") is not None else 0.0), 2),
                    centroid=[r["lon"], r["lat"]],
                    screening_grade=SCREENING_GRADE_NOTICE,
                )
            )

        return ForecastAlertsResponse(
            total_forecast_cells=total_cells,
            total_exposed_population=total_pop,
            issuing_model=None,
            forecast_cycle_at=resolved_cycle,
            horizon_hours=horizon_hours,
            items=items,
        )

