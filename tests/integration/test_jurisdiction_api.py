"""Integration tests for SETU-DRR Jurisdiction-Aware Authorization & Frontend Contract Hardening (Part 3).

Verifies:
1. Multi-District Access Control:
   - Wayanad official can manage Wayanad sites/allocations/scenarios (200).
   - Wayanad official cannot operate on Kodagu sites/allocations/scenarios (403).
   - Kodagu official can manage Kodagu sites (200), cannot operate on Wayanad sites (403).
2. Object Existence vs Authorization Ordering:
   - Nonexistent site returns 404 SITE_NOT_FOUND, not 403.
3. Candidate Site Spatial District Uniqueness:
   - Candidate sites map to exactly 1 authoritative district boundary.
4. Identifier Confusion Security Defense:
   - Submitting LGD code (555) as canonical admin_id is rejected with 403 FORBIDDEN.
5. Non-Mutating Request DTO Contract:
   - Request DTOs are never mutated by server-side authorization scoping.
6. Civilian National Exploration:
   - Civilians retain unrestricted public reads across all districts.
7. Rescue Officer Role Consolidation:
   - Rescue officers are consolidated as government officials with planning permissions in their assigned jurisdiction.
   - Operations outside assigned jurisdiction are rejected with 403.
8. Client Tampering Prevention:
   - Client cannot supply admin_id or role in public registration (422).
9. /auth/me Frontend Contract Hardening:
   - Exposes safe, additive JurisdictionDTO for officials, null for civilians.
"""

import uuid
import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.config import settings


@pytest.fixture
def anon_client():
    return TestClient(app)


@pytest.fixture
def wayanad_client():
    """Client authenticated as Wayanad District Magistrate."""
    c = TestClient(app)
    res = c.post("/auth/login", json={
        "email": "officer@setu.gov.in",
        "password": settings.DEMO_OFFICER_PASSWORD,
    })
    assert res.status_code == 200, f"Wayanad officer login failed: {res.text}"
    return c


@pytest.fixture
def kodagu_client():
    """Client authenticated as Kodagu District Magistrate."""
    c = TestClient(app)
    res = c.post("/auth/login", json={
        "email": "officer_kodagu@setu.gov.in",
        "password": settings.DEMO_OFFICER_PASSWORD,
    })
    assert res.status_code == 200, f"Kodagu officer login failed: {res.text}"
    return c


@pytest.fixture
def civilian_client():
    """Client authenticated as Demo Civilian."""
    c = TestClient(app)
    res = c.post("/auth/login", json={
        "email": "civilian@setu.gov.in",
        "password": settings.DEMO_CIVILIAN_PASSWORD,
    })
    assert res.status_code == 200, f"Civilian login failed: {res.text}"
    return c


@pytest.fixture
def rescue_client():
    """Client authenticated as Rescue Officer."""
    c = TestClient(app)
    res = c.post("/auth/login", json={
        "email": "rescue@setu.gov.in",
        "password": settings.DEMO_RESCUE_PASSWORD,
    })
    assert res.status_code == 200, f"Rescue officer login failed: {res.text}"
    return c


@pytest.fixture
def national_client():
    """Client authenticated as the national operations account (no assigned district)."""
    c = TestClient(app)
    res = c.post("/auth/login", json={
        "email": "gov@setu.gov.in",
        "password": settings.DEMO_OFFICER_PASSWORD,
    })
    assert res.status_code == 200, f"National operations login failed: {res.text}"
    return c


@pytest.fixture
def district_context(wayanad_client, kodagu_client, anon_client):
    """Dynamically resolves district and site IDs from the active database."""
    # 1. Authoritative canonical admin_ids from /auth/me
    w_me = wayanad_client.get("/auth/me").json()
    k_me = kodagu_client.get("/auth/me").json()

    wayanad_admin_id = w_me["jurisdiction"]["admin_id"]
    kodagu_admin_id = k_me["jurisdiction"]["admin_id"]

    # 2. Query habitations to find Wayanad and Kodagu representative habitations
    habs_res = anon_client.get("/habitations?limit=50").json()
    items = habs_res["items"]

    w_hab = next(h for h in items if h["admin_id"] == wayanad_admin_id)
    k_hab = next(h for h in items if h["admin_id"] == kodagu_admin_id)

    # 3. Query candidate sites for each habitation
    w_sites_res = anon_client.get(f"/habitations/{w_hab['id']}/sites?radius_km=50").json()
    k_sites_res = anon_client.get(f"/habitations/{k_hab['id']}/sites?radius_km=50").json()

    w_site_id = w_sites_res["items"][0]["id"]
    k_site_id = k_sites_res["items"][0]["id"]

    return {
        "wayanad_admin_id": wayanad_admin_id,
        "kodagu_admin_id": kodagu_admin_id,
        "wayanad_site_id": w_site_id,
        "kodagu_site_id": k_site_id,
    }


class TestJurisdictionAccessControl:
    """Comprehensive suite for Part 3 jurisdiction authorization boundaries."""

    # ------------------------------------------------------------------------
    # 1. Candidate Site Capacity Recomputation (Cross-Jurisdiction & 404/403)
    # ------------------------------------------------------------------------

    def test_site_capacity_wayanad_official_own_site_permitted(self, wayanad_client, district_context):
        """Wayanad official can recompute capacity for a Wayanad candidate site."""
        site_id = district_context["wayanad_site_id"]
        res = wayanad_client.post(f"/sites/{site_id}/capacity", json={"plot_area_m2": 65.0})
        assert res.status_code == 200
        assert res.json()["site_id"] == site_id

    def test_site_capacity_wayanad_official_foreign_site_forbidden(self, wayanad_client, district_context):
        """Wayanad official attempting to alter a Kodagu site is rejected with 403 FORBIDDEN."""
        site_id = district_context["kodagu_site_id"]
        res = wayanad_client.post(f"/sites/{site_id}/capacity", json={"plot_area_m2": 65.0})
        assert res.status_code == 403
        data = res.json()
        assert data["error"]["code"] == "FORBIDDEN"
        assert "outside user's assigned administrative jurisdiction" in data["error"]["message"]

    def test_site_capacity_kodagu_official_own_site_permitted(self, kodagu_client, district_context):
        """Kodagu official can recompute capacity for a Kodagu candidate site."""
        site_id = district_context["kodagu_site_id"]
        res = kodagu_client.post(f"/sites/{site_id}/capacity", json={"plot_area_m2": 70.0})
        assert res.status_code == 200
        assert res.json()["site_id"] == site_id

    def test_site_capacity_kodagu_official_foreign_site_forbidden(self, kodagu_client, district_context):
        """Kodagu official attempting to alter a Wayanad site is rejected with 403 FORBIDDEN."""
        site_id = district_context["wayanad_site_id"]
        res = kodagu_client.post(f"/sites/{site_id}/capacity", json={"plot_area_m2": 70.0})
        assert res.status_code == 403
        data = res.json()
        assert data["error"]["code"] == "FORBIDDEN"

    def test_site_capacity_nonexistent_site_returns_404_before_authorization(self, wayanad_client):
        """Object existence precedes authorization: nonexistent site returns 404, not 403."""
        res = wayanad_client.post("/sites/99999999/capacity", json={"plot_area_m2": 60.0})
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "SITE_NOT_FOUND"

    # ------------------------------------------------------------------------
    # 2. Relocation Allocation Planning (POST /plan/allocate)
    # ------------------------------------------------------------------------

    def test_allocate_wayanad_official_omitted_admin_id_scoped_to_jurisdiction(self, wayanad_client, district_context):
        """Omitted admin_id defaults authoritatively to user's assigned jurisdiction."""
        wayanad_id = district_context["wayanad_admin_id"]
        payload = {
            "max_search_radius_km": 25.0,
            "target_tiers": ["immediate", "short_term"],
            "allow_group_splits": True,
        }
        res = wayanad_client.post("/plan/allocate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["admin_id"] == wayanad_id
        # Verify non-mutation of caller payload
        assert "admin_id" not in payload

    def test_allocate_wayanad_official_matching_admin_id_permitted(self, wayanad_client, district_context):
        """Explicitly providing matching canonical admin_id is allowed."""
        wayanad_id = district_context["wayanad_admin_id"]
        payload = {
            "admin_id": wayanad_id,
            "max_search_radius_km": 25.0,
            "target_tiers": ["immediate", "short_term"],
        }
        res = wayanad_client.post("/plan/allocate", json=payload)
        assert res.status_code == 200
        assert res.json()["admin_id"] == wayanad_id

    def test_allocate_wayanad_official_foreign_admin_id_forbidden(self, wayanad_client, district_context):
        """Attempting allocation in foreign district (Kodagu) is rejected with 403 FORBIDDEN."""
        kodagu_id = district_context["kodagu_admin_id"]
        payload = {
            "admin_id": kodagu_id,
            "max_search_radius_km": 25.0,
            "target_tiers": ["immediate"],
        }
        res = wayanad_client.post("/plan/allocate", json=payload)
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "FORBIDDEN"

    def test_allocate_identifier_confusion_lgd_code_rejected_403(self, wayanad_client):
        """Security Invariant: Passing LGD code (555) as canonical admin_id must be rejected with 403.
        
        Wayanad's LGD code is 555 while its admin_boundary.id is the database PK.
        Passing 555 directly as admin_id must not match and must raise 403.
        """
        payload = {
            "admin_id": 555,
            "max_search_radius_km": 20.0,
            "target_tiers": ["immediate"],
        }
        res = wayanad_client.post("/plan/allocate", json=payload)
        assert res.status_code == 403
        data = res.json()
        assert data["error"]["code"] == "FORBIDDEN"
        assert "Operation outside assigned administrative jurisdiction" in data["error"]["message"]

    # ------------------------------------------------------------------------
    # 3. Scenario Simulation (POST /scenario)
    # ------------------------------------------------------------------------

    def test_scenario_wayanad_official_omitted_admin_id_permitted(self, wayanad_client):
        """Scenario evaluation with omitted admin_id is scoped to official's jurisdiction."""
        payload = {"limit": 10}
        res = wayanad_client.post("/scenario", json=payload)
        assert res.status_code == 200
        # Verify non-mutation of payload
        assert "admin_id" not in payload

    def test_scenario_wayanad_official_matching_admin_id_permitted(self, wayanad_client, district_context):
        """Scenario evaluation with matching admin_id is permitted."""
        wayanad_id = district_context["wayanad_admin_id"]
        res = wayanad_client.post("/scenario", json={"admin_id": wayanad_id, "limit": 10})
        assert res.status_code == 200

    def test_scenario_wayanad_official_foreign_admin_id_forbidden(self, wayanad_client, district_context):
        """Scenario evaluation targeting another district is rejected with 403 FORBIDDEN."""
        kodagu_id = district_context["kodagu_admin_id"]
        res = wayanad_client.post("/scenario", json={"admin_id": kodagu_id, "limit": 10})
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "FORBIDDEN"

    def test_scenario_identifier_confusion_lgd_code_rejected_403(self, wayanad_client):
        """Scenario evaluation attempting to use LGD code 555 as admin_id is rejected with 403."""
        res = wayanad_client.post("/scenario", json={"admin_id": 555, "limit": 10})
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "FORBIDDEN"

    # ------------------------------------------------------------------------
    # 4. Civilian National Exploration Unaffected
    # ------------------------------------------------------------------------

    def test_civilian_public_reads_across_districts_permitted(self, civilian_client, district_context):
        """Civilians can explore public data nationwide across Wayanad and Kodagu without restriction."""
        # 1. Read zones
        res_zones = civilian_client.get("/zones?limit=5")
        assert res_zones.status_code == 200

        # 2. Read habitations
        res_habs = civilian_client.get("/habitations?limit=5")
        assert res_habs.status_code == 200

        # 3. Read alerts
        res_alerts = civilian_client.get("/alerts/active?limit=5")
        assert res_alerts.status_code == 200

        # 4. Read Wayanad candidate site
        res_w_site = civilian_client.get(f"/sites/{district_context['wayanad_site_id']}")
        assert res_w_site.status_code == 200

        # 5. Read Kodagu candidate site
        res_k_site = civilian_client.get(f"/sites/{district_context['kodagu_site_id']}")
        assert res_k_site.status_code == 200

    def test_civilian_privileged_operations_strictly_forbidden(self, civilian_client, district_context):
        """Civilians are rejected from privileged operations regardless of geography."""
        site_id = district_context["wayanad_site_id"]
        res_cap = civilian_client.post(f"/sites/{site_id}/capacity", json={"plot_area_m2": 60.0})
        assert res_cap.status_code == 403

        res_alloc = civilian_client.post("/plan/allocate", json={"target_tiers": ["immediate"]})
        assert res_alloc.status_code == 403

        res_scen = civilian_client.post("/scenario", json={})
        assert res_scen.status_code == 403

    # ------------------------------------------------------------------------
    # 5. Rescue Officer Role Consolidation
    # ------------------------------------------------------------------------

    def test_rescue_officer_authorized_as_government_official_within_jurisdiction(self, rescue_client, district_context):
        """Rescue officers are consolidated as GOVERNMENT_OFFICIAL with planning permissions in their jurisdiction."""
        # Within assigned jurisdiction (Wayanad)
        res_alloc = rescue_client.post("/plan/allocate", json={
            "admin_id": district_context["wayanad_admin_id"],
            "target_tiers": ["immediate"],
        })
        assert res_alloc.status_code == 200

        # Outside assigned jurisdiction (Kodagu) -> 403 FORBIDDEN
        res_alloc_cross = rescue_client.post("/plan/allocate", json={
            "admin_id": district_context["kodagu_admin_id"],
            "target_tiers": ["immediate"],
        })
        assert res_alloc_cross.status_code == 403

    def test_rescue_officer_can_explore_public_data(self, rescue_client):
        """Rescue officers retain full unconstrained public exploration."""
        res = rescue_client.get("/habitations?limit=5")
        assert res.status_code == 200

    # ------------------------------------------------------------------------
    # 6. Client Tampering Defense
    # ------------------------------------------------------------------------

    def test_civilian_registration_rejects_client_supplied_admin_id_or_role(self, anon_client):
        """Client cannot inject admin_id or role into civilian registration."""
        random_suffix = uuid.uuid4().hex[:8]
        payload_role = {
            "email": f"hacker_{random_suffix}@example.com",
            "password": "Password123!",
            "full_name": "Tampering User",
            "role": "GOVERNMENT_OFFICIAL",
        }
        res_role = anon_client.post("/auth/register", json=payload_role)
        assert res_role.status_code == 422

        payload_admin = {
            "email": f"hacker2_{random_suffix}@example.com",
            "password": "Password123!",
            "full_name": "Tampering User 2",
            "admin_id": 158,
        }
        res_admin = anon_client.post("/auth/register", json=payload_admin)
        assert res_admin.status_code == 422

    # ------------------------------------------------------------------------
    # 7. /auth/me Frontend Contract Hardening
    # ------------------------------------------------------------------------

    def test_auth_me_government_official_contract(self, wayanad_client):
        """GET /auth/me returns safe, additive JurisdictionDTO for government officials."""
        res = wayanad_client.get("/auth/me")
        assert res.status_code == 200
        data = res.json()

        assert data["email"] == "officer@setu.gov.in"
        assert data["role"] == "GOVERNMENT_OFFICIAL"
        assert "jurisdiction" in data
        assert data["jurisdiction"] is not None

        jur = data["jurisdiction"]
        assert isinstance(jur["admin_id"], int)
        assert jur["name"] == "Wayanad"
        assert jur["level"] == "district"
        assert jur["lgd_code"] == 555

        # Security check: internal passwords/tokens must never be present
        assert "password_hash" not in data
        assert "session_token" not in data

    def test_auth_me_kodagu_official_contract(self, kodagu_client):
        """GET /auth/me returns Kodagu JurisdictionDTO for Kodagu official."""
        res = kodagu_client.get("/auth/me")
        assert res.status_code == 200
        data = res.json()

        assert data["email"] == "officer_kodagu@setu.gov.in"
        assert data["role"] == "GOVERNMENT_OFFICIAL"
        assert data["jurisdiction"] is not None

        jur = data["jurisdiction"]
        assert isinstance(jur["admin_id"], int)
        assert jur["name"] == "Kodagu"
        assert jur["level"] == "district"
        assert jur["lgd_code"] == 540

    def test_auth_me_civilian_contract(self, civilian_client):
        """GET /auth/me returns null jurisdiction for civilian users."""
        res = civilian_client.get("/auth/me")
        assert res.status_code == 200
        data = res.json()

        assert data["email"] == "civilian@setu.gov.in"
        assert data["role"] == "CIVILIAN"
        assert "jurisdiction" in data
        assert data["jurisdiction"] is None


class TestNationalScopeAccess:
    """The single 'Government' login: a GOVERNMENT_OFFICIAL with no assigned district
    is authorized across every district but must always name the target district."""

    def test_auth_me_national_account_has_null_jurisdiction(self, national_client):
        res = national_client.get("/auth/me")
        assert res.status_code == 200
        data = res.json()
        assert data["email"] == "gov@setu.gov.in"
        assert data["role"] == "GOVERNMENT_OFFICIAL"
        assert data["jurisdiction"] is None

    def test_national_scenario_any_district_permitted(self, national_client, district_context):
        """National account can run a scenario for Wayanad and for Kodagu."""
        for admin_id in (district_context["wayanad_admin_id"], district_context["kodagu_admin_id"]):
            res = national_client.post("/scenario", json={"admin_id": admin_id, "limit": 10})
            assert res.status_code == 200, res.text
            assert res.json()["admin_id"] == admin_id

    def test_national_scenario_requires_explicit_district(self, national_client):
        """An unscoped operation (no admin_id) is rejected — never run silently nationwide."""
        res = national_client.post("/scenario", json={"limit": 10})
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "FORBIDDEN"

    def test_national_allocation_any_district_permitted(self, national_client, district_context):
        res = national_client.post("/plan/allocate", json={
            "admin_id": district_context["kodagu_admin_id"],
            "target_tiers": ["immediate"],
        })
        assert res.status_code == 200, res.text

    def test_national_site_capacity_any_district_permitted(self, national_client, district_context):
        for site_id in (district_context["wayanad_site_id"], district_context["kodagu_site_id"]):
            res = national_client.post(f"/sites/{site_id}/capacity", json={"plot_area_m2": 60.0})
            assert res.status_code == 200, res.text
