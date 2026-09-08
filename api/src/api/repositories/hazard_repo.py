"""Database repository for static hazard layers served to the vector map.

Reads `hazard_static` (+ `hazard_static_flood`) directly rather than going through
`mhi_snapshot`, which the flood pipeline never populates.
"""

from typing import Optional, Any
from sqlalchemy import text
from sqlalchemy.orm import Session


class HazardRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def query_layer_cells(
        self,
        hazard_type: str,
        res: int,
        min_lon: Optional[float] = None,
        min_lat: Optional[float] = None,
        max_lon: Optional[float] = None,
        max_lat: Optional[float] = None,
        admin: Optional[int] = None,
        min_susceptibility: float = 0.0,
        limit: int = 20000,
    ) -> list[dict[str, Any]]:
        """Returns hazard cells for a viewport, ordered by descending susceptibility.

        Ordering matters: when `limit` clips the result set, the client keeps the most
        hazardous cells rather than an arbitrary spatial slice.
        """
        conditions = ["h.hazard_type = :hazard_type", "g.res = :res"]
        params: dict[str, Any] = {
            "hazard_type": hazard_type,
            "res": res,
            "limit": limit,
        }

        if None not in (min_lon, min_lat, max_lon, max_lat):
            conditions.append(
                "g.geom && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)"
            )
            params.update({
                "min_lon": min_lon,
                "min_lat": min_lat,
                "max_lon": max_lon,
                "max_lat": max_lat,
            })

        admin_join = ""
        if admin is not None:
            admin_join = "LEFT JOIN admin_boundary a ON g.admin_id = a.id"
            conditions.append("(g.admin_id = :admin OR a.lgd_code = :admin)")
            params["admin"] = admin

        if min_susceptibility > 0.0:
            # Hard-zero and no-coverage cells are semantically meaningful at 0.0, so the
            # filter only applies once the caller explicitly asks for a floor above zero.
            conditions.append("h.susceptibility >= :min_susceptibility")
            params["min_susceptibility"] = min_susceptibility

        where_clause = " AND ".join(conditions)

        query = text(f"""
            SELECT
                g.h3,
                h.susceptibility,
                h.confidence,
                h.quality_flag,
                h.model_version,
                f.hard_zero_fraction
            FROM hazard_static h
            JOIN grid_cell g ON g.h3 = h.h3
            {admin_join}
            LEFT JOIN hazard_static_flood f ON f.h3 = h.h3
            WHERE {where_clause}
            ORDER BY h.susceptibility DESC
            LIMIT :limit;
        """)

        return [dict(r) for r in self.db.execute(query, params).mappings().all()]

    def query_layer_statistics(
        self,
        hazard_type: str,
        res: int,
        min_lon: Optional[float] = None,
        min_lat: Optional[float] = None,
        max_lon: Optional[float] = None,
        max_lat: Optional[float] = None,
        admin: Optional[int] = None,
        quantiles: Optional[list[float]] = None,
    ) -> Optional[dict[str, Any]]:
        """Computes quantile class breaks and the confidence ceiling over the same population.

        `percentile_cont` runs in PostgreSQL so the breaks describe every matching cell,
        not just the page the client received.
        """
        if quantiles is None:
            quantiles = [0.25, 0.5, 0.75, 0.9, 0.95, 0.99]

        conditions = ["h.hazard_type = :hazard_type", "g.res = :res"]
        params: dict[str, Any] = {
            "hazard_type": hazard_type,
            "res": res,
            "quantiles": quantiles,
        }

        if None not in (min_lon, min_lat, max_lon, max_lat):
            conditions.append(
                "g.geom && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)"
            )
            params.update({
                "min_lon": min_lon,
                "min_lat": min_lat,
                "max_lon": max_lon,
                "max_lat": max_lat,
            })

        admin_join = ""
        if admin is not None:
            admin_join = "LEFT JOIN admin_boundary a ON g.admin_id = a.id"
            conditions.append("(g.admin_id = :admin OR a.lgd_code = :admin)")
            params["admin"] = admin

        where_clause = " AND ".join(conditions)

        query = text(f"""
            SELECT
                COUNT(*) AS cell_count,
                MIN(h.susceptibility) AS min_susceptibility,
                MAX(h.susceptibility) AS max_susceptibility,
                AVG(h.susceptibility) AS mean_susceptibility,
                MAX(h.confidence) AS confidence_ceiling,
                MAX(h.model_version) AS model_version,
                COUNT(*) FILTER (WHERE h.quality_flag = 'full') AS full_count,
                COUNT(*) FILTER (WHERE h.quality_flag = 'low_coverage') AS low_coverage_count,
                COUNT(*) FILTER (WHERE h.quality_flag = 'no_coverage') AS no_coverage_count,
                percentile_cont(CAST(:quantiles AS double precision[]))
                    WITHIN GROUP (ORDER BY h.susceptibility) AS breaks
            FROM hazard_static h
            JOIN grid_cell g ON g.h3 = h.h3
            {admin_join}
            WHERE {where_clause};
        """)

        row = self.db.execute(query, params).mappings().first()
        if not row or not row["cell_count"]:
            return None
        return dict(row)

    def list_layers(self) -> list[dict[str, Any]]:
        """Enumerates every published static hazard layer with its headline statistics."""
        query = text("""
            SELECT
                h.hazard_type,
                g.res,
                COUNT(*) AS cell_count,
                MAX(h.model_version) AS model_version,
                MIN(h.susceptibility) AS min_susceptibility,
                MAX(h.susceptibility) AS max_susceptibility,
                AVG(h.susceptibility) AS mean_susceptibility,
                MAX(h.confidence) AS confidence_ceiling
            FROM hazard_static h
            JOIN grid_cell g ON g.h3 = h.h3
            GROUP BY h.hazard_type, g.res
            ORDER BY h.hazard_type, g.res;
        """)
        return [dict(r) for r in self.db.execute(query).mappings().all()]

    def get_cell_detail(self, h3_int: int, hazard_type: str) -> Optional[dict[str, Any]]:
        """Retrieves one cell with its flood driver metrics for the dossier panel."""
        query = text("""
            SELECT
                g.h3,
                g.res,
                g.population,
                ST_X(g.centroid::geometry) AS lon,
                ST_Y(g.centroid::geometry) AS lat,
                a.name AS admin_name,
                h.hazard_type,
                h.susceptibility,
                h.confidence,
                h.quality_flag,
                h.model_version,
                f.max_susceptibility,
                f.valid_pixel_fraction,
                f.hard_zero_fraction,
                f.mean_inundation_frequency,
                f.mean_hand_m,
                f.min_hand_m,
                f.mean_slope_deg,
                f.mean_cropland_fraction,
                f.observation_ceiling
            FROM hazard_static h
            JOIN grid_cell g ON g.h3 = h.h3
            LEFT JOIN admin_boundary a ON g.admin_id = a.id
            LEFT JOIN hazard_static_flood f ON f.h3 = h.h3
            WHERE h.h3 = :h3 AND h.hazard_type = :hazard_type;
        """)
        row = self.db.execute(query, {"h3": h3_int, "hazard_type": hazard_type}).mappings().first()
        return dict(row) if row else None

    def get_confidence_ceiling(self, hazard_type: str) -> float:
        """Returns the maximum confidence present in a layer, for client-side normalisation."""
        query = text("""
            SELECT MAX(confidence) AS ceiling
            FROM hazard_static
            WHERE hazard_type = :hazard_type;
        """)
        row = self.db.execute(query, {"hazard_type": hazard_type}).mappings().first()
        ceiling = row["ceiling"] if row else None
        return float(ceiling) if ceiling else 1.0
