"""Repository for external relocation recommendations and benchmark comparisons.

Manages queries against external_relocation_recommendation linked to promoted data import runs.
"""

from __future__ import annotations

from typing import Any, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session


class RecommendationsRepository:
    """Data access layer for external pipeline recommendations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_recommendations_for_habitation(self, habitation_id: int) -> list[dict[str, Any]]:
        """Retrieves external recommendations for a specific habitation from the active promoted run."""
        sql = """
            SELECT
                err.id,
                err.import_run_id,
                err.habitation_id,
                h.name as habitation_name,
                err.site_id,
                err.external_habitation_key,
                err.external_site_key,
                err.origin_type,
                err.decision_status,
                err.households,
                err.tier,
                err.priority_score,
                err.distance_km,
                err.site_suitability,
                err.site_cc_final,
                err.site_binding,
                err.has_group_split,
                err.rationale,
                err.screening_grade,
                err.screening_caveats,
                err.source_pipeline,
                err.pipeline_version,
                err.created_at
            FROM external_relocation_recommendation err
            JOIN data_import_run dir ON err.import_run_id = dir.id
            JOIN habitation h ON err.habitation_id = h.id
            WHERE err.habitation_id = :habitation_id
              AND dir.status = 'PROMOTED'
            ORDER BY err.id ASC;
        """
        rows = self.db.execute(text(sql), {"habitation_id": habitation_id}).mappings().fetchall()
        return [dict(r) for r in rows]

    def get_recommendations_for_district(self, district: str) -> list[dict[str, Any]]:
        """Retrieves external recommendations for a district from its promoted run."""
        sql = """
            SELECT
                err.id,
                err.import_run_id,
                err.habitation_id,
                h.name as habitation_name,
                h.households as demand_households,
                err.site_id,
                err.external_habitation_key,
                err.external_site_key,
                err.origin_type,
                err.decision_status,
                err.households,
                err.tier,
                err.priority_score,
                err.distance_km,
                err.site_suitability,
                err.site_cc_final,
                err.site_binding,
                err.has_group_split,
                err.rationale,
                err.screening_grade,
                err.screening_caveats,
                err.source_pipeline,
                err.pipeline_version,
                err.created_at
            FROM external_relocation_recommendation err
            JOIN data_import_run dir ON err.import_run_id = dir.id
            JOIN habitation h ON err.habitation_id = h.id
            WHERE dir.district_name ILIKE :district
              AND dir.status = 'PROMOTED'
            ORDER BY err.priority_score DESC, err.households DESC, err.id ASC;
        """
        rows = self.db.execute(text(sql), {"district": district}).mappings().fetchall()
        return [dict(r) for r in rows]

    def get_canonical_allocations_for_district(self, district: str) -> list[dict[str, Any]]:
        """Retrieves SETU canonical relocation plan allocations for a district."""
        sql = """
            SELECT
                rp.id,
                rp.allocation_run_id,
                rp.habitation_id,
                h.name as habitation_name,
                h.households as demand_households,
                rp.site_id,
                rp.households,
                rp.tier,
                rp.priority_score,
                rp.rationale,
                rp.has_group_split,
                rp.status,
                rp.created_at,
                ST_Distance(h.geom_point::geography, cs.centroid::geography) / 1000.0 as distance_km
            FROM relocation_plan rp
            JOIN habitation h ON rp.habitation_id = h.id
            JOIN admin_boundary ab ON h.admin_id = ab.id
            JOIN candidate_site cs ON rp.site_id = cs.id
            JOIN allocation_run ar ON rp.allocation_run_id = ar.id
            WHERE ab.name ILIKE :district
            ORDER BY rp.priority_score DESC, rp.households DESC, rp.id ASC;
        """
        rows = self.db.execute(text(sql), {"district": district}).mappings().fetchall()
        return [dict(r) for r in rows]
