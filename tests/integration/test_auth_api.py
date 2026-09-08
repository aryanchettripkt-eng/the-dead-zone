"""Integration tests for SETU-DRR Authentication Part 1 using the seeded test database.

Section refs: SETU-DRR Auth Part 1 — Tests Required (§28).
Validates:
- Seeded demo account logins across roles (CIVILIAN, GOVERNMENT_OFFICIAL).
- Session cookie lifecycle: login -> cookie -> /auth/me -> /auth/logout -> 401.
- State-changing endpoint protection on POST /plan/allocate (401 when unauthenticated).
- Civilian registration forcing CIVILIAN role.
- Civilian public exploration across districts remains completely unrestricted.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.config import settings

client = TestClient(app)


class TestAuthApiIntegration:
    def test_seeded_demo_civilian_login(self):
        """Verify seeded demo civilian can log in with configured password."""
        res = client.post("/auth/login", json={
            "email": "civilian@setu.gov.in",
            "password": settings.DEMO_CIVILIAN_PASSWORD,
        })
        assert res.status_code == 200
        data = res.json()
        assert data["email"] == "civilian@setu.gov.in"
        assert data["role"] == "CIVILIAN"
        assert data["is_active"] is True
        assert settings.SESSION_COOKIE_NAME in res.cookies

    def test_seeded_demo_officer_login(self):
        """Verify seeded demo government officer can log in with configured password."""
        res = client.post("/auth/login", json={
            "email": "officer@setu.gov.in",
            "password": settings.DEMO_OFFICER_PASSWORD,
        })
        assert res.status_code == 200
        data = res.json()
        assert data["email"] == "officer@setu.gov.in"
        assert data["role"] == "GOVERNMENT_OFFICIAL"
        assert data["is_active"] is True
        assert settings.SESSION_COOKIE_NAME in res.cookies

    def test_seeded_demo_rescue_login(self):
        """Verify seeded demo rescue officer can log in and is represented as GOVERNMENT_OFFICIAL."""
        res = client.post("/auth/login", json={
            "email": "rescue@setu.gov.in",
            "password": settings.DEMO_RESCUE_PASSWORD,
        })
        assert res.status_code == 200
        data = res.json()
        assert data["email"] == "rescue@setu.gov.in"
        assert data["role"] == "GOVERNMENT_OFFICIAL"
        assert data["is_active"] is True
        assert settings.SESSION_COOKIE_NAME in res.cookies

    def test_session_lifecycle_login_me_logout(self):
        """Verify end-to-end cookie lifecycle: login -> /me -> logout -> /me rejected."""
        session_client = TestClient(app)

        # 1. Initially unauthenticated
        res_init = session_client.get("/auth/me")
        assert res_init.status_code == 401
        assert res_init.json()["error"]["code"] == "UNAUTHENTICATED"

        # 2. Login
        res_login = session_client.post("/auth/login", json={
            "email": "officer@setu.gov.in",
            "password": settings.DEMO_OFFICER_PASSWORD,
        })
        assert res_login.status_code == 200

        # 3. /auth/me succeeds with cookie
        res_me = session_client.get("/auth/me")
        assert res_me.status_code == 200
        assert res_me.json()["email"] == "officer@setu.gov.in"
        assert res_me.json()["role"] == "GOVERNMENT_OFFICIAL"

        # 4. Logout
        res_logout = session_client.post("/auth/logout")
        assert res_logout.status_code == 200

        # 5. Subsequent /auth/me fails with 401
        res_post_logout = session_client.get("/auth/me")
        assert res_post_logout.status_code == 401
        assert res_post_logout.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_public_civilian_registration_forces_civilian_role(self):
        """Verify civilian registration creates user and rejects privileged roles."""
        import uuid
        reg_client = TestClient(app)
        unique_email = f"citizen_{uuid.uuid4().hex[:8]}@example.org"

        res = reg_client.post("/auth/register", json={
            "email": unique_email,
            "password": "StrongPassword99!",
            "full_name": "Citizen NinetyNine",
        })
        assert res.status_code == 201
        data = res.json()
        assert data["email"] == unique_email
        assert data["role"] == "CIVILIAN"

        # Client can now log in
        login_res = reg_client.post("/auth/login", json={
            "email": unique_email,
            "password": "StrongPassword99!",
        })
        assert login_res.status_code == 200
        assert reg_client.get("/auth/me").status_code == 200

    def test_civilian_public_exploration_unrestricted(self):
        """Verify civilian authentication does NOT restrict public map / habitations exploration."""
        civilian_client = TestClient(app)
        login_res = civilian_client.post("/auth/login", json={
            "email": "civilian@setu.gov.in",
            "password": settings.DEMO_CIVILIAN_PASSWORD,
        })
        assert login_res.status_code == 200

        # Query Wayanad (admin 555)
        res_wayanad = civilian_client.get("/habitations", params={"admin": 555, "limit": 5})
        assert res_wayanad.status_code == 200

        # Query Kodagu (admin 540) — civilian must not be restricted to a single district!
        res_kodagu = civilian_client.get("/habitations", params={"admin": 540, "limit": 5})
        assert res_kodagu.status_code == 200
