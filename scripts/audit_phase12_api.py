"""Phase 12 Audit: Comprehensive API Endpoint and District Scoping Verification."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from api.main import app
from core.config import settings

def audit_phase12():
    print("==================================================================")
    print("PHASE 12: API AUDIT & DISTRICT SCOPING VERIFICATION")
    print("==================================================================")

    client = TestClient(app)
    eng = create_engine(settings.get_sqlalchemy_url())

    with eng.connect() as conn:
        barpeta_hab = conn.execute(text("""
            SELECT h.id, h.name, h.source_habitation_id
            FROM habitation h
            JOIN admin_boundary ab ON h.admin_id = ab.id
            WHERE ab.name = 'Barpeta'
            LIMIT 1;
        """)).mappings().first()

        assert barpeta_hab is not None
        b_hid = barpeta_hab["id"]
        print(f"[*] Testing Barpeta habitation: ID={b_hid}, Name={barpeta_hab['name']}")

    # -------------------------------------------------------------
    # 1. GET /habitations/{id}/sites (Default excludes non-eligible)
    # -------------------------------------------------------------
    print("\n[STEP 1] Testing default GET /habitations/{id}/sites...")
    res_def = client.get(f"/habitations/{b_hid}/sites")
    assert res_def.status_code == 200, f"Error: {res_def.status_code}: {res_def.text}"
    def_items = res_def.json().get("items", [])
    print(f"[*] Default sites count for Barpeta habitation {b_hid}: {len(def_items)}")
    assert len(def_items) == 0, f"VIOLATION: Default site listing leaked non-eligible sites: {len(def_items)}"
    print("[PASSED] Default site listing strictly excludes screening-only candidate sites.")

    # -------------------------------------------------------------
    # 2. GET /habitations/{id}/sites?include_screening=true
    # -------------------------------------------------------------
    print("\n[STEP 2] Testing GET /habitations/{id}/sites?include_screening=true...")
    res_scr = client.get(f"/habitations/{b_hid}/sites?include_screening=true")
    assert res_scr.status_code == 200, f"Error: {res_scr.status_code}: {res_scr.text}"
    scr_items = res_scr.json().get("items", [])
    print(f"[*] Screening sites count for Barpeta habitation {b_hid}: {len(scr_items)}")
    assert len(scr_items) > 0, "Expected screening candidate sites to be visible when include_screening=true"

    for it in scr_items[:5]:
        assert it["allocatable"] is False
        assert it["assessment_status"] == "screening_only"
        assert it["eligibility_status"] == "unknown"
        cap = it["capacity"]
        assert cap["cc_final"] is None
        assert cap["binding_constraint"] is None
        assert cap["land_screening_capacity"] is not None
        assert cap["data_quality"] == "unavailable"
    print("[PASSED] include_screening=true exposes screening sites with honest gaps and allocatable=False.")

    # -------------------------------------------------------------
    # 3. GET /habitations/{id}/external-recommendations
    # -------------------------------------------------------------
    print("\n[STEP 3] Testing GET /habitations/{id}/external-recommendations...")
    res_hab_rec = client.get(f"/habitations/{b_hid}/external-recommendations")
    assert res_hab_rec.status_code == 200, f"Error: {res_hab_rec.status_code}: {res_hab_rec.text}"
    recs = res_hab_rec.json()
    print(f"[*] External recommendations for habitation {b_hid}: {len(recs)}")
    assert len(recs) == 1, f"Expected 1 external recommendation for Barpeta habitation, got {len(recs)}"
    rec = recs[0]
    assert rec["origin_type"] == "external"
    assert rec["decision_status"] == "recommendation"
    assert rec["external_habitation_key"] == barpeta_hab["source_habitation_id"]
    assert rec["external_site_key"] is not None
    assert "Screening Grade" in rec["screening_grade"]
    print("[PASSED] Habitation external recommendation endpoint is decoupled and explicitly tagged.")

    # -------------------------------------------------------------
    # 4. GET /plan/external-recommendations?district=Barpeta
    # -------------------------------------------------------------
    print("\n[STEP 4] Testing GET /plan/external-recommendations?district=Barpeta...")
    res_plan_recs = client.get("/plan/external-recommendations?district=Barpeta")
    assert res_plan_recs.status_code == 200, f"Error: {res_plan_recs.status_code}: {res_plan_recs.text}"
    plan_data = res_plan_recs.json()
    assert plan_data["district"] == "Barpeta"
    assert plan_data["total_count"] == 14
    assert plan_data["total_households_recommended"] == 5348
    assert len(plan_data["items"]) == 14
    print(f"[PASSED] Plan external recommendations returned {plan_data['total_count']} items, {plan_data['total_households_recommended']} households.")

    # -------------------------------------------------------------
    # 5. GET /plan/benchmark?district=Barpeta
    # -------------------------------------------------------------
    print("\n[STEP 5] Testing GET /plan/benchmark?district=Barpeta...")
    res_bench = client.get("/plan/benchmark?district=Barpeta")
    assert res_bench.status_code == 200, f"Error: {res_bench.status_code}: {res_bench.text}"
    bench = res_bench.json()
    assert bench["status"] == "external_only"
    assert bench["setu_allocation_available"] is False
    assert bench["external_recommendations_count"] == 14
    assert bench["setu_allocations_count"] == 0
    assert bench["total_setu_allocated_households"] == 0
    assert len(bench["comparisons"]) == 14
    for c in bench["comparisons"]:
        assert c["external_recommendation"] is not None
        assert c["setu_canonical_allocation"] is None
        assert c["site_match"] is False
    print("[PASSED] Benchmark endpoint observational contract verified: external_only status, 0 fabricated SETU allocations.")

    # -------------------------------------------------------------
    # 6. Cross-District Leakage Isolation Check
    # -------------------------------------------------------------
    print("\n[STEP 6] Testing cross-district scoping isolation...")
    res_wayanad_recs = client.get("/plan/external-recommendations?district=Wayanad")
    assert res_wayanad_recs.status_code == 200
    assert res_wayanad_recs.json()["total_count"] == 0
    assert len(res_wayanad_recs.json()["items"]) == 0

    res_wayanad_bench = client.get("/plan/benchmark?district=Wayanad")
    assert res_wayanad_bench.status_code == 200
    assert res_wayanad_bench.json()["external_recommendations_count"] == 0

    print("[PASSED] Zero cross-district leakage. Barpeta recommendations never bleed into Wayanad or other pilots.")

    print("\n==================================================================")
    print("PHASE 12 AUDIT: 100% SUCCESS — ALL API CONTRACTS VERIFIED")
    print("==================================================================")

if __name__ == "__main__":
    audit_phase12()
