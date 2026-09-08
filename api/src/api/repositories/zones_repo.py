"""Database repository for H3 grid cells, hazards, MHI snapshots, and explanations."""

from typing import Optional, Any, Sequence
from datetime import datetime
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.orm import Session, joinedload

from core.db_models import (
    GridCell,
    HazardStatic,
    MHISnapshot,
    Explanation,
    AdminBoundary,
    Habitation,
)
from core.h3_utils import h3_to_int, h3_to_str, h3_to_centroid


class ZonesRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def resolve_snapshot_valid_at(self, valid_at: Optional[datetime] = None) -> Optional[datetime]:
        """Resolves the coherent snapshot timestamp as of valid_at (or latest if None)."""
        if valid_at is not None:
            query = text("SELECT MAX(valid_at) as target_time FROM mhi_snapshot WHERE valid_at <= :valid_at;")
            row = self.db.execute(query, {"valid_at": valid_at}).mappings().first()
        else:
            query = text("SELECT MAX(valid_at) as target_time FROM mhi_snapshot;")
            row = self.db.execute(query).mappings().first()
        return row["target_time"] if row and row.get("target_time") else None

    def query_zones(
        self,
        res: int,
        min_lon: Optional[float] = None,
        min_lat: Optional[float] = None,
        max_lon: Optional[float] = None,
        max_lat: Optional[float] = None,
        admin_id: Optional[int] = None,
        limit: int = 1000,
        valid_at: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Queries grid cells and joins their latest MHI snapshot within the spatial bounding box."""
        # Using raw SQL with spatial index for sub-10ms performance
        conditions = ["g.res = :res"]
        params: dict[str, Any] = {"res": res, "limit": limit}

        if min_lon is not None and min_lat is not None and max_lon is not None and max_lat is not None:
            conditions.append(
                "g.geom && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)"
            )
            params.update({
                "min_lon": min_lon,
                "min_lat": min_lat,
                "max_lon": max_lon,
                "max_lat": max_lat,
            })

        if admin_id is not None:
            conditions.append("(g.admin_id = :admin_id OR a.lgd_code = :admin_id)")
            params["admin_id"] = admin_id

        admin_join = "LEFT JOIN admin_boundary a ON g.admin_id = a.id" if admin_id is not None else ""
        where_clause = " AND ".join(conditions)

        if valid_at is not None:
            lateral_sql = """
                SELECT mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class
                FROM mhi_snapshot
                WHERE h3 = g.h3 AND valid_at = :snapshot_time
                LIMIT 1
            """
            params["snapshot_time"] = valid_at
        else:
            lateral_sql = """
                SELECT mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class
                FROM mhi_snapshot
                WHERE h3 = g.h3
                ORDER BY valid_at DESC
                LIMIT 1
            """

        query = text(f"""
            SELECT 
                g.h3,
                g.res,
                g.population,
                g.built_area_m2,
                g.dataset_version,
                ST_X(g.centroid::geometry) as lon,
                ST_Y(g.centroid::geometry) as lat,
                m.mhi_static,
                m.mhi_live,
                m.mhi_fcst,
                m.dominant_hazard,
                m.zone_class
            FROM grid_cell g
            {admin_join}
            LEFT JOIN LATERAL (
                {lateral_sql}
            ) m ON true
            WHERE {where_clause}
            LIMIT :limit;
        """)

        results = self.db.execute(query, params).mappings().all()
        return [dict(r) for r in results]

    def get_zone_by_h3(self, h3_int: int) -> Optional[dict[str, Any]]:
        """Retrieves full zone details including static hazard breakdown and SHAP explanation."""
        query = text("""
            SELECT 
                g.h3,
                g.res,
                g.population,
                g.built_area_m2,
                g.dataset_version,
                ST_X(g.centroid::geometry) as lon,
                ST_Y(g.centroid::geometry) as lat,
                a.id as admin_id,
                a.name as admin_name,
                h.id as habitation_id,
                h.name as habitation_name,
                m.valid_at,
                m.mhi_static,
                m.mhi_live,
                m.mhi_fcst,
                m.dominant_hazard,
                m.zone_class,
                e.model_version,
                e.factors,
                e.screening_grade
            FROM grid_cell g
            LEFT JOIN admin_boundary a ON g.admin_id = a.id
            LEFT JOIN habitation h ON g.habitation_id = h.id
            LEFT JOIN LATERAL (
                SELECT valid_at, mhi_static, mhi_live, mhi_fcst, dominant_hazard, zone_class
                FROM mhi_snapshot
                WHERE h3 = g.h3
                ORDER BY valid_at DESC
                LIMIT 1
            ) m ON true
            LEFT JOIN explanation e ON g.h3 = e.h3
            WHERE g.h3 = :h3;
        """)

        cell = self.db.execute(query, {"h3": h3_int}).mappings().first()
        if not cell:
            return None

        # Query static hazard breakdown
        hazard_query = text("""
            SELECT hazard_type, susceptibility, confidence, model_version
            FROM hazard_static
            WHERE h3 = :h3;
        """)
        hazards = self.db.execute(hazard_query, {"h3": h3_int}).mappings().all()

        return {
            "cell": dict(cell),
            "hazards": [dict(hz) for hz in hazards],
        }
