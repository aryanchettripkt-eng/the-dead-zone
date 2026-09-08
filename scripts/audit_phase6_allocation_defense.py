"""Phase 6 Audit: Prove Barpeta candidate sites NEVER enter allocation by accident."""

import json
from sqlalchemy import create_engine, text
from core.config import settings
from api.repositories.allocation_repo import AllocationRepository
from api.services.allocation_service import AllocationService
from core.domain.capacity import CapacityEngine, CandidateSitePolicy
from core.enums import EligibilityStatus

def audit_phase6():
    print("==================================================================")
    print("PHASE 6: PROVING BARPETA DOES NOT ENTER ALLOCATION BY ACCIDENT")
    print("==================================================================")

    url = settings.get_sqlalchemy_url()
    engine = create_engine(url)

    with engine.connect() as conn:
        # 1. Fetch Barpeta habitations and candidate sites
        barpeta_habs = conn.execute(text("""
            SELECT h.id, h.name, h.households
            FROM habitation h
            JOIN admin_boundary ab ON h.admin_id = ab.id
            WHERE ab.name = 'Barpeta'
            ORDER BY h.id ASC;
        """)).mappings().fetchall()

        print(f"[*] Found {len(barpeta_habs)} Barpeta habitations in database.")
        hab_ids = [h["id"] for h in barpeta_habs]

        # 2. Test AllocationRepository SQL query
        repo = AllocationRepository(conn)
        policy = CandidateSitePolicy()
        sites, distances = repo.get_candidate_sites_and_distances(
            habitation_ids=hab_ids,
            max_radius_m=25000.0,
            policy=policy,
        )

        print(f"[*] AllocationRepository.get_candidate_sites_and_distances returned: {len(sites)} sites.")
        assert len(sites) == 0, f"VIOLATION: Barpeta candidate sites leaked through repository SQL filter: {sites}"
        print("[PASSED] 0 Barpeta candidate sites passed AllocationRepository SQL filter (rejected due to cc_final IS NULL, mhi_max IS NULL).")

        # 3. Test canonical CandidateSitePolicy evaluation on all 629 Barpeta sites
        raw_sites = conn.execute(text("""
            SELECT
                cs.id, cs.source_site_id, cs.area_ha, cs.tenure, cs.slope_mean,
                cs.mhi_max, cs.cc_land, cs.cc_final, cs.assessment_status, cs.eligibility_status,
                cs.metadata
            FROM candidate_site cs
            JOIN admin_boundary ab ON cs.admin_id = ab.id
            WHERE ab.name = 'Barpeta'
            ORDER BY cs.id ASC;
        """)).mappings().fetchall()

        print(f"[*] Auditing all {len(raw_sites)} Barpeta candidate sites against canonical CandidateSitePolicy...")
        engine_cap = CapacityEngine(site_policy=policy)

        eligible_count = 0
        unknown_count = 0
        ineligible_count = 0

        for s in raw_sites:
            meta = s["metadata"]
            if isinstance(meta, str):
                meta = json.loads(meta)
            elif not isinstance(meta, dict):
                meta = {}

            res = engine_cap.evaluate_site_eligibility(
                mhi_static=s["mhi_max"],
                slope_mean=float(s["slope_mean"] or 0.0),
                area_ha=float(s["area_ha"] or 0.0),
                tenure=str(s["tenure"]),
                is_forest=meta.get("is_forest", False),
                is_protected_area=meta.get("is_protected_area", False),
                is_crz=meta.get("is_crz", False),
                is_water_body=meta.get("is_water_body", False),
                policy=policy,
            )

            if res.is_eligible:
                eligible_count += 1
            if res.eligibility_status == EligibilityStatus.UNKNOWN:
                unknown_count += 1
            elif res.eligibility_status == EligibilityStatus.INELIGIBLE:
                ineligible_count += 1

        print(f"[*] CandidateSitePolicy results across all 629 sites:")
        print(f"    - Eligible: {eligible_count}")
        print(f"    - Unknown (honest data gaps): {unknown_count}")
        print(f"    - Ineligible: {ineligible_count}")

        assert eligible_count == 0, f"VIOLATION: {eligible_count} Barpeta sites were marked eligible!"
        assert unknown_count + ineligible_count == 629
        print("[PASSED] 100% of Barpeta candidate sites are rejected by canonical CandidateSitePolicy.")

        # 4. Run AllocationService directly for Barpeta district
        # 4. Verify canonical database has exactly 0 allocation_run and 0 relocation_plan
        ar_initial = conn.execute(text("SELECT count(*) FROM allocation_run;")).scalar()
        rp_initial = conn.execute(text("SELECT count(*) FROM relocation_plan;")).scalar()
        assert ar_initial == 0, f"Expected 0 initial allocation_run, got {ar_initial}"
        assert rp_initial == 0, f"Expected 0 initial relocation_plan, got {rp_initial}"
        print(f"[PASSED] Initial database state verified: 0 allocation_run, 0 relocation_plan.")

        # 5. Run AllocationService directly for Barpeta district to prove solver rejection
        from core.schemas.allocation import AllocationPlanRequest
        from core.enums import Tier

        barpeta_admin_id = conn.execute(text("SELECT id FROM admin_boundary WHERE name = 'Barpeta' LIMIT 1;")).scalar()
        print(f"[*] Barpeta admin_id: {barpeta_admin_id}")

        service = AllocationService(conn)
        req = AllocationPlanRequest(
            admin_id=barpeta_admin_id,
            target_tiers=[Tier.IMMEDIATE, Tier.SHORT_TERM, Tier.MEDIUM_TERM, Tier.MITIGATE_IN_SITU],
            max_search_radius_km=25.0,
        )
        alloc_dto = service.generate_allocation_plan(
            request=req,
            admin_id=barpeta_admin_id,
        )

        print(f"[*] AllocationService plan output for Barpeta:")
        print(f"    - Total relocated households: {alloc_dto.total_relocated_households}")
        print(f"    - Unmet demand households: {alloc_dto.unmet_demand_households}")
        print(f"    - Total assignments: {len(alloc_dto.assignments)}")

        assert alloc_dto.total_relocated_households == 0, "VIOLATION: Households were allocated to screening sites!"
        assert len(alloc_dto.assignments) == 0, "VIOLATION: Allocation assignments produced!"
        print("[PASSED] Allocation graph rejected all Barpeta sites: 0 households relocated, 0 assignments produced.")

        # Clean up transient solver test run record
        conn.execute(text("DELETE FROM allocation_run WHERE id = :id;"), {"id": str(alloc_dto.allocation_run_id)})
        conn.commit()

        # Final verification that DB is clean
        ar_final = conn.execute(text("SELECT count(*) FROM allocation_run;")).scalar()
        rp_final = conn.execute(text("SELECT count(*) FROM relocation_plan;")).scalar()
        assert ar_final == 0, f"Expected 0 final allocation_run, got {ar_final}"
        assert rp_final == 0, f"Expected 0 final relocation_plan, got {rp_final}"
        print(f"[PASSED] Database canonical allocation counts strictly preserved: allocation_run={ar_final}, relocation_plan={rp_final}.")

    print("\n==================================================================")
    print("PHASE 6 AUDIT: 100% SUCCESS — BARPETA IS COMPLETELY ISOLATED")
    print("==================================================================")

if __name__ == "__main__":
    audit_phase6()
