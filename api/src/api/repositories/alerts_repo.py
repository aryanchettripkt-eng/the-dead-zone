"""PostGIS Repository for Active and Forecast Alert Zones (Day 6).

Section refs: docs/PRD1.md §6.3, §9.5, §9.6, FR-3.10, FR-3.12
"""

from __future__ import annotations

from typing import Any, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.constants import ACTIVE_ALERT_MHI_LIVE, PRZ_MHI_STATIC


class AlertsRepository:
    """PostGIS data access for active trigger alerts and forecast threshold crossings."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_latest_snapshot_valid_at(self) -> Optional[datetime]:
        """Returns the latest authoritative snapshot timestamp persisted in mhi_snapshot, if any.
        
        Prefers the latest snapshot that has associated live (non-forecast) triggers,
        falling back to the maximum snapshot timestamp in mhi_snapshot.
        """
        query = text("""
            SELECT COALESCE(
                (SELECT MAX(m.valid_at)
                 FROM mhi_snapshot m
                 JOIN hazard_dynamic hd ON m.valid_at = hd.valid_at AND hd.forecast_cycle_at IS NULL),
                (SELECT MAX(valid_at) FROM mhi_snapshot)
            ) as max_valid;
        """)
        row = self.db.execute(query).mappings().first()
        return row["max_valid"] if row and row.get("max_valid") else None

    def query_active_alerts(
        self,
        admin_id: Optional[int] = None,
        min_mhi: float = ACTIVE_ALERT_MHI_LIVE,
        dominant_hazard: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        valid_at: Optional[datetime] = None,
    ) -> tuple[list[dict[str, Any]], int, int]:
        """Queries H3 cells where dynamic live trigger causes MHI_live >= 0.75 and MHI_static < 0.75
        evaluated against the authoritative latest snapshot (or valid_at if specified).
        
        Returns:
            (records, total_cells_count, total_exposed_population)
        """
        target_valid_at = valid_at
        if target_valid_at is None:
            target_valid_at = self.get_latest_snapshot_valid_at()

        if target_valid_at is None:
            return [], 0, 0

        where_clauses = [
            "m.valid_at = :snapshot_valid_at",
            "m.mhi_live >= :min_mhi",
            "m.mhi_static < :prz_threshold",
        ]
        params: dict[str, Any] = {
            "snapshot_valid_at": target_valid_at,
            "min_mhi": float(min_mhi),
            "prz_threshold": float(PRZ_MHI_STATIC),
            "limit": limit,
            "offset": offset,
        }

        if admin_id is not None:
            where_clauses.append("(g.admin_id = :admin_id OR a.lgd_code = :admin_id)")
            params["admin_id"] = int(admin_id)

        if dominant_hazard:
            where_clauses.append("m.dominant_hazard = :dominant_hazard")
            params["dominant_hazard"] = dominant_hazard.lower()

        where_sql = " AND ".join(where_clauses)

        sql = f"""
            WITH deduplicated_hazard_active AS (
                SELECT DISTINCT ON (h3, valid_at)
                    h3,
                    valid_at,
                    hazard_type,
                    source,
                    ingested_at
                FROM hazard_dynamic
                WHERE forecast_cycle_at IS NULL
                  AND valid_at = :snapshot_valid_at
                ORDER BY h3, valid_at, ingested_at DESC, id DESC
            )
            SELECT
                g.h3,
                g.res,
                g.population,
                g.built_area_m2,
                ST_X(g.centroid::geometry) as lon,
                ST_Y(g.centroid::geometry) as lat,
                a.id as admin_id,
                a.name as admin_name,
                m.valid_at,
                m.mhi_static,
                m.mhi_live,
                m.mhi_fcst,
                m.dominant_hazard,
                m.zone_class,
                hd.source as trigger_source,
                hd.ingested_at,
                count(*) OVER() as full_count,
                sum(g.population) OVER() as full_exposed_pop
            FROM mhi_snapshot m
            JOIN grid_cell g ON m.h3 = g.h3
            LEFT JOIN admin_boundary a ON g.admin_id = a.id
            LEFT JOIN deduplicated_hazard_active hd ON m.h3 = hd.h3 AND m.valid_at = hd.valid_at
            WHERE {where_sql}
            ORDER BY m.mhi_live DESC, g.population DESC, g.h3 ASC
            LIMIT :limit OFFSET :offset;
        """

        rows = self.db.execute(text(sql), params).mappings().fetchall()
        if not rows:
            return [], 0, 0

        total_cells = int(rows[0]["full_count"])
        pop_raw = rows[0]["full_exposed_pop"]
        total_pop = int(round(float(pop_raw if pop_raw is not None else 0.0)))
        return [dict(r) for r in rows], total_cells, total_pop

    def get_latest_forecast_cycle(self) -> Optional[datetime]:
        """Returns the latest forecast cycle timestamp persisted in hazard_dynamic, if any."""
        query = text("""
            SELECT MAX(forecast_cycle_at) as max_cycle
            FROM hazard_dynamic
            WHERE forecast_cycle_at IS NOT NULL;
        """)
        row = self.db.execute(query).mappings().first()
        return row["max_cycle"] if row and row.get("max_cycle") else None

    def query_forecast_alerts(
        self,
        admin_id: Optional[int] = None,
        min_mhi: float = ACTIVE_ALERT_MHI_LIVE,
        horizon_hours: int = 72,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int, int]:
        """Queries H3 cells predicted to cross MHI >= 0.75 within forecast horizon (max 72h).
        
        Returns:
            (records, total_forecast_cells, total_exposed_population)
        """
        params: dict[str, Any] = {
            "min_mhi": float(min_mhi),
            "horizon_hours": int(horizon_hours),
            "limit": limit,
            "offset": offset,
        }

        outer_where = ""
        if admin_id is not None:
            outer_where = "WHERE (g.admin_id = :admin_id OR a.lgd_code = :admin_id)"
            params["admin_id"] = int(admin_id)

        sql = f"""
            WITH deduplicated_hazard_forecasts AS (
                SELECT DISTINCT ON (h3, valid_at)
                    h3,
                    valid_at,
                    forecast_cycle_at,
                    source,
                    ROUND(EXTRACT(EPOCH FROM (valid_at - forecast_cycle_at)) / 3600.0)::int AS horizon_hours
                FROM hazard_dynamic
                WHERE forecast_cycle_at IS NOT NULL
                  AND valid_at > forecast_cycle_at
                  AND valid_at <= forecast_cycle_at + (:horizon_hours * INTERVAL '1 hour')
                ORDER BY h3, valid_at, forecast_cycle_at DESC, ingested_at DESC, id DESC
            ),
            latest_snapshots AS (
                SELECT DISTINCT ON (m.h3)
                    m.h3,
                    m.valid_at,
                    m.mhi_static,
                    m.mhi_live,
                    m.mhi_fcst,
                    m.dominant_hazard,
                    m.zone_class,
                    hd.forecast_cycle_at,
                    hd.horizon_hours,
                    hd.source
                FROM mhi_snapshot m
                JOIN deduplicated_hazard_forecasts hd 
                  ON m.h3 = hd.h3 AND m.valid_at = hd.valid_at
                WHERE m.mhi_fcst >= :min_mhi
                ORDER BY m.h3, hd.forecast_cycle_at DESC, m.valid_at ASC
            )
            SELECT
                g.h3,
                g.res,
                g.population,
                g.built_area_m2,
                ST_X(g.centroid::geometry) as lon,
                ST_Y(g.centroid::geometry) as lat,
                a.id as admin_id,
                a.name as admin_name,
                m.valid_at,
                m.mhi_static,
                m.mhi_live,
                m.mhi_fcst,
                m.dominant_hazard,
                m.zone_class,
                m.forecast_cycle_at,
                m.horizon_hours,
                count(*) OVER() as full_count,
                sum(g.population) OVER() as full_exposed_pop
            FROM latest_snapshots m
            JOIN grid_cell g ON m.h3 = g.h3
            LEFT JOIN admin_boundary a ON g.admin_id = a.id
            {outer_where}
            ORDER BY m.mhi_fcst DESC, g.population DESC, g.h3 ASC
            LIMIT :limit OFFSET :offset;
        """

        rows = self.db.execute(text(sql), params).mappings().fetchall()
        if not rows:
            return [], 0, 0

        total_cells = int(rows[0]["full_count"])
        pop_raw = rows[0]["full_exposed_pop"]
        total_pop = int(round(float(pop_raw if pop_raw is not None else 0.0)))
        return [dict(r) for r in rows], total_cells, total_pop
