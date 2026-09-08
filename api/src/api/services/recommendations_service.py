"""Service layer for external relocation recommendations and benchmark comparisons.

Orchestrates retrieval of external pipeline proposals and side-by-side comparative
evaluations against authoritative SETU decision engine outputs.
"""

from __future__ import annotations

import json
from typing import Any
from sqlalchemy.orm import Session

from api.repositories.recommendations_repo import RecommendationsRepository
from core.schemas.allocation import (
    AllocationBenchmarkComparisonItem,
    AllocationBenchmarkResponse,
    ExternalRecommendationItem,
    ExternalRecommendationListResponse,
)


class RecommendationsService:
    """Business logic service for external recommendations and benchmark analysis."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = RecommendationsRepository(db)

    def _to_dto(self, r: dict[str, Any]) -> ExternalRecommendationItem:
        """Converts raw repository mapping to ExternalRecommendationItem."""
        rationale = r.get("rationale") or {}
        if isinstance(rationale, str):
            try:
                rationale = json.loads(rationale)
            except Exception:
                rationale = {}

        return ExternalRecommendationItem(
            id=int(r["id"]),
            import_run_id=r["import_run_id"],
            habitation_id=int(r["habitation_id"]),
            habitation_name=r.get("habitation_name"),
            site_id=int(r["site_id"]),
            external_habitation_key=str(r["external_habitation_key"]),
            external_site_key=str(r["external_site_key"]),
            origin_type=str(r.get("origin_type", "external")),
            decision_status=str(r.get("decision_status", "recommendation")),
            households=int(r["households"]),
            tier=str(r["tier"]),
            priority_score=float(r.get("priority_score", 0.0)),
            distance_km=round(float(r.get("distance_km", 0.0)), 2),
            site_suitability=r.get("site_suitability"),
            site_cc_final=r.get("site_cc_final"),
            site_binding=r.get("site_binding"),
            has_group_split=bool(r.get("has_group_split", False)),
            rationale=rationale,
            screening_grade=str(r.get("screening_grade", "Screening Grade")),
            screening_caveats=r.get("screening_caveats"),
            source_pipeline=str(r.get("source_pipeline", "external_gis_v1")),
            pipeline_version=str(r.get("pipeline_version", "v1.0")),
            created_at=r["created_at"],
        )

    def get_recommendations_for_habitation(self, habitation_id: int) -> list[ExternalRecommendationItem]:
        """Returns external recommendations for a specific habitation."""
        raw_rows = self.repo.get_recommendations_for_habitation(habitation_id)
        return [self._to_dto(r) for r in raw_rows]

    def get_recommendations_for_district(self, district: str) -> ExternalRecommendationListResponse:
        """Returns all external recommendations for an administrative district."""
        raw_rows = self.repo.get_recommendations_for_district(district)
        items = [self._to_dto(r) for r in raw_rows]
        total_hh = sum(item.households for item in items)
        return ExternalRecommendationListResponse(
            district=district,
            total_count=len(items),
            total_households_recommended=total_hh,
            items=items,
        )

    def get_benchmark_comparison(self, district: str) -> AllocationBenchmarkResponse:
        """Compares external offline recommendations with SETU authoritative relocation plan."""
        ext_rows = self.repo.get_recommendations_for_district(district)
        canon_rows = self.repo.get_canonical_allocations_for_district(district)

        total_ext_hh = sum(r["households"] for r in ext_rows)
        total_canon_hh = sum(r["households"] for r in canon_rows)
        setu_available = len(canon_rows) > 0

        # Index canonical allocations by habitation_id
        canon_by_hab: dict[int, list[dict[str, Any]]] = {}
        for cr in canon_rows:
            canon_by_hab.setdefault(cr["habitation_id"], []).append(cr)

        # Index external recommendations by habitation_id
        ext_by_hab: dict[int, list[dict[str, Any]]] = {}
        for er in ext_rows:
            ext_by_hab.setdefault(er["habitation_id"], []).append(er)

        all_hab_ids = set(ext_by_hab.keys()) | set(canon_by_hab.keys())
        comparisons: list[AllocationBenchmarkComparisonItem] = []

        for hid in sorted(all_hab_ids):
            e_list = ext_by_hab.get(hid, [])
            c_list = canon_by_hab.get(hid, [])

            e_rec = e_list[0] if e_list else None
            c_rec = c_list[0] if c_list else None

            hab_name = (
                (e_rec.get("habitation_name") if e_rec else None)
                or (c_rec.get("habitation_name") if c_rec else None)
                or f"Habitation #{hid}"
            )
            demand_hh = (
                (e_rec.get("demand_households") if e_rec else None)
                or (c_rec.get("demand_households") if c_rec else None)
                or (e_rec.get("households") if e_rec else 0)
            )

            site_match = False
            notes: list[str] = []
            dist_delta = None
            hh_delta = 0

            ext_summary = None
            if e_rec:
                ext_summary = {
                    "site_id": e_rec["site_id"],
                    "external_site_key": e_rec["external_site_key"],
                    "households": e_rec["households"],
                    "tier": e_rec["tier"],
                    "priority_score": e_rec["priority_score"],
                    "distance_km": round(float(e_rec["distance_km"]), 2),
                    "screening_grade": e_rec["screening_grade"],
                }

            setu_summary = None
            if c_rec:
                setu_summary = {
                    "site_id": c_rec["site_id"],
                    "households": c_rec["households"],
                    "tier": c_rec["tier"],
                    "priority_score": c_rec["priority_score"],
                    "distance_km": round(float(c_rec.get("distance_km", 0.0)), 2),
                    "status": c_rec["status"],
                }

            if e_rec and c_rec:
                site_match = e_rec["site_id"] == c_rec["site_id"]
                hh_delta = c_rec["households"] - e_rec["households"]
                dist_delta = round(float(c_rec.get("distance_km", 0.0)) - float(e_rec.get("distance_km", 0.0)), 2)
                if not site_match:
                    notes.append("SETU optimizer routed to a different candidate site based on global network flow and multi-criteria capacity.")
                if e_rec.get("priority_score", 0.0) == 0.0 and c_rec.get("priority_score", 0.0) > 0.0:
                    notes.append("External recommendation had dormant priority score; SETU evaluated active multi-hazard priority.")
            elif e_rec and not c_rec:
                notes.append("External pipeline recommended relocation; SETU canonical allocation has not been run or site was deemed ineligible.")
            elif c_rec and not e_rec:
                notes.append("Habitation allocated under SETU optimization with no external pipeline counterpart.")

            comparisons.append(
                AllocationBenchmarkComparisonItem(
                    habitation_id=hid,
                    habitation_name=hab_name,
                    demand_households=demand_hh,
                    external_recommendation=ext_summary,
                    setu_canonical_allocation=setu_summary,
                    site_match=site_match,
                    household_delta=hh_delta,
                    distance_delta_km=dist_delta,
                    methodology_divergence_notes=notes,
                )
            )

        return AllocationBenchmarkResponse(
            district=district,
            status="comparative" if setu_available else "external_only",
            setu_allocation_available=setu_available,
            total_external_recommended_households=total_ext_hh,
            total_setu_allocated_households=total_canon_hh,
            external_recommendations_count=len(ext_rows),
            setu_allocations_count=len(canon_rows),
            comparisons=comparisons,
        )
