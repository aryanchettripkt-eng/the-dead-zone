"""Phase 7 Audit: Honest Capacity Semantics and API JSON NULL preservation."""

import json
from fastapi.testclient import TestClient
from api.main import app
from core.domain.capacity import CapacityEngine, CapacityDataQuality
from core.enums import BindingConstraint

def audit_phase7():
    print("==================================================================")
    print("PHASE 7: HONEST CAPACITY SEMANTICS & API JSON NULL PRESERVATION")
    print("==================================================================")

    engine = CapacityEngine()

    # 1. Pure domain function test
    print("\n[STEP 1] Testing CapacityEngine.calculate_final_capacity with missing lifelines...")
    cc_final, binding, tied = engine.calculate_final_capacity(
        cc_land=250,
        cc_water=None,
        cc_school=None,
        cc_health=None,
    )
    print(f"[*] calculate_final_capacity(cc_land=250, lifelines=None) -> cc_final={cc_final}, binding={binding}")
    assert cc_final is None, f"VIOLATION: cc_final was calculated as {cc_final} instead of None!"
    assert binding is None, f"VIOLATION: binding_constraint was calculated as {binding} instead of None!"
    assert tied == []
    print("[PASSED] calculate_final_capacity preserves honest NULL when lifelines are missing.")

    # 2. Comprehensive evaluate_site_capacity test
    print("\n[STEP 2] Testing CapacityEngine.evaluate_site_capacity with missing lifelines...")
    eval_res = engine.evaluate_site_capacity(
        area_developable_m2=50000.0,
        water_yield_liters_per_day=None,
        spare_school_seats=None,
        spare_health_capacity_pop=None,
    )
    print(f"[*] evaluate_site_capacity -> cc_land={eval_res.cc_land}, cc_final={eval_res.cc_final}, quality={eval_res.data_quality}")
    assert eval_res.cc_land > 0, "Land capacity should be computed from developable area"
    assert eval_res.cc_water is None
    assert eval_res.cc_school is None
    assert eval_res.cc_health is None
    assert eval_res.cc_final is None, f"VIOLATION: cc_final is {eval_res.cc_final}"
    assert eval_res.binding_constraint is None, f"VIOLATION: binding_constraint is {eval_res.binding_constraint}"
    assert eval_res.data_quality == CapacityDataQuality.UNAVAILABLE
    print("[PASSED] evaluate_site_capacity preserves honest NULLs and UNAVAILABLE quality flag.")

    # 3. Test API JSON serialization via TestClient
    print("\n[STEP 3] Testing API serialization on Barpeta candidate site...")
    client = TestClient(app)

    # First fetch habitations to get a Barpeta habitation and its sites
    res_habs = client.get("/habitations", params={"admin": 186, "limit": 1})
    if res_habs.status_code != 200 or not res_habs.json().get("items"):
        # Find Barpeta habitation ID from DB
        from sqlalchemy import create_engine, text
        from core.config import settings
        eng = create_engine(settings.get_sqlalchemy_url())
        with eng.connect() as conn:
            hab_id = conn.execute(text("SELECT h.id FROM habitation h JOIN admin_boundary ab ON h.admin_id = ab.id WHERE ab.name = 'Barpeta' LIMIT 1;")).scalar()
            site_id = conn.execute(text("SELECT cs.id FROM candidate_site cs JOIN admin_boundary ab ON cs.admin_id = ab.id WHERE ab.name = 'Barpeta' LIMIT 1;")).scalar()
    else:
        hab_id = res_habs.json()["items"][0]["id"]
        res_sites = client.get(f"/habitations/{hab_id}/sites?include_screening=true")
        site_id = res_sites.json()["items"][0]["id"]

    print(f"[*] Testing Barpeta site ID: {site_id}")

    # Test GET /sites/{id}
    res_site = client.get(f"/sites/{site_id}")
    assert res_site.status_code == 200, f"GET /sites/{site_id} returned {res_site.status_code}: {res_site.text}"
    site_data = res_site.json()

    print(f"[*] GET /sites/{site_id} payload checks:")
    print(f"    - assessment_status: {site_data.get('assessment_status')}")
    print(f"    - eligibility_status: {site_data.get('eligibility_status')}")
    print(f"    - allocatable: {site_data.get('allocatable')}")
    
    cap_nested = site_data.get("capacity", {})
    print(f"    - capacity.cc_final: {cap_nested.get('cc_final')}")
    print(f"    - capacity.binding_constraint: {cap_nested.get('binding_constraint')}")
    print(f"    - capacity.cc_land: {cap_nested.get('cc_land')}")
    print(f"    - capacity.land_screening_capacity: {cap_nested.get('land_screening_capacity')}")
    print(f"    - capacity.data_quality: {cap_nested.get('data_quality')}")

    assert cap_nested.get("cc_final") is None, f"VIOLATION: cc_final was {cap_nested.get('cc_final')}"
    assert cap_nested.get("binding_constraint") is None, f"VIOLATION: binding_constraint was {cap_nested.get('binding_constraint')}"
    assert cap_nested.get("cc_land") is not None
    assert cap_nested.get("land_screening_capacity") is not None
    assert site_data.get("assessment_status") == "screening_only"
    assert site_data.get("eligibility_status") == "unknown"
    assert site_data.get("allocatable") is False

    # Test GET /habitations/{hab_id}/sites?include_screening=true
    res_list = client.get(f"/habitations/{hab_id}/sites?include_screening=true")
    assert res_list.status_code == 200
    list_items = res_list.json()["items"]
    assert len(list_items) > 0
    first_item = list_items[0]

    print(f"[*] GET /habitations/{hab_id}/sites?include_screening=true item checks:")
    print(f"    - assessment_status: {first_item.get('assessment_status')}")
    print(f"    - eligibility_status: {first_item.get('eligibility_status')}")
    print(f"    - allocatable: {first_item.get('allocatable')}")
    item_cap = first_item.get("capacity", {})
    print(f"    - capacity.cc_final: {item_cap.get('cc_final')}")
    print(f"    - capacity.binding_constraint: {item_cap.get('binding_constraint')}")
    print(f"    - capacity.cc_land: {item_cap.get('cc_land')}")
    print(f"    - capacity.land_screening_capacity: {item_cap.get('land_screening_capacity')}")

    assert item_cap.get("cc_final") is None, f"VIOLATION: item cc_final was {item_cap.get('cc_final')}"
    assert item_cap.get("binding_constraint") is None, f"VIOLATION: item binding_constraint was {item_cap.get('binding_constraint')}"
    assert item_cap.get("cc_land") is not None
    assert item_cap.get("land_screening_capacity") is not None
    assert first_item.get("assessment_status") == "screening_only"
    assert first_item.get("eligibility_status") == "unknown"
    assert first_item.get("allocatable") is False

    print("[PASSED] API serialization strictly preserves honest NULL for cc_final and binding_constraint across detail and list endpoints.")
    print("\n==================================================================")
    print("PHASE 7 AUDIT: 100% SUCCESS — HONEST CAPACITY SEMANTICS PROVEN")
    print("==================================================================")

if __name__ == "__main__":
    audit_phase7()
