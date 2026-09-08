"""Unit and service tests for SETU-DRR Authentication Part 1.

Section refs: SETU-DRR Auth Part 1 — Tests Required (§28).
Uses an isolated in-memory SQLite database to test service, repository, and FastAPI endpoints.
"""

import uuid
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.dependencies import get_db
from api.main import app
from api.services.auth_service import AuthService
from core.config import settings
from core.db_models import AppUser, UserSession
from core.domain.auth import hash_password, hash_session_token
from core.enums import Role
from core.errors import UnauthenticatedError, InvalidParametersError


@pytest.fixture
def auth_db_session():
    """Provides an isolated in-memory SQLite database with AppUser and UserSession tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS admin_boundary (id INTEGER PRIMARY KEY, name TEXT, level TEXT, lgd_code INTEGER, parent_id INTEGER);"))
        conn.commit()
    AppUser.__table__.create(engine)
    UserSession.__table__.create(engine)

    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client_with_db(auth_db_session):
    """TestClient wired with in-memory database override for get_db."""
    def _override_get_db():
        yield auth_db_session

    app.dependency_overrides[get_db] = _override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.pop(get_db, None)


class TestAuthService:
    def test_login_success(self, auth_db_session):
        service = AuthService(auth_db_session)
        service.register_civilian(
            email="citizen@example.org",
            password="SecurePassword123!",
            full_name="Jane Citizen",
        )

        user, token = service.login("citizen@example.org", "SecurePassword123!")
        assert user.email == "citizen@example.org"
        assert user.role == Role.CIVILIAN.value
        assert user.is_active is True
        assert user.last_login_at is not None
        assert isinstance(token, str)
        assert len(token) >= 32

    def test_login_case_insensitive_email(self, auth_db_session):
        service = AuthService(auth_db_session)
        service.register_civilian("mixed.Case@example.org", "SecurePassword123!", "Case User")

        user, token = service.login("MIXED.case@EXAMPLE.org", "SecurePassword123!")
        assert user.email == "mixed.case@example.org"

    def test_login_wrong_password_fails(self, auth_db_session):
        service = AuthService(auth_db_session)
        service.register_civilian("citizen@example.org", "SecurePassword123!", "Jane Citizen")

        with pytest.raises(UnauthenticatedError, match="Invalid email or password"):
            service.login("citizen@example.org", "WrongPassword!")

    def test_login_unknown_email_fails(self, auth_db_session):
        service = AuthService(auth_db_session)
        with pytest.raises(UnauthenticatedError, match="Invalid email or password"):
            service.login("nonexistent@example.org", "AnyPassword123!")

    def test_login_inactive_account_fails(self, auth_db_session):
        service = AuthService(auth_db_session)
        user = service.register_civilian("inactive@example.org", "Password123!", "Inactive User")
        user.is_active = False
        auth_db_session.commit()

        with pytest.raises(UnauthenticatedError, match="Account is inactive"):
            service.login("inactive@example.org", "Password123!")

    def test_resolve_session_success(self, auth_db_session):
        service = AuthService(auth_db_session)
        service.register_civilian("citizen@example.org", "SecurePassword123!", "Jane Citizen")
        _, token = service.login("citizen@example.org", "SecurePassword123!")

        resolved_user = service.resolve_session(token)
        assert resolved_user.email == "citizen@example.org"

    def test_resolve_session_expired_fails(self, auth_db_session):
        service = AuthService(auth_db_session)
        service.register_civilian("citizen@example.org", "SecurePassword123!", "Jane Citizen")
        _, token = service.login("citizen@example.org", "SecurePassword123!")

        # Backdate expiration
        token_hash = hash_session_token(token)
        session_record = service.repo.get_session_by_token_hash(token_hash)
        session_record.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        auth_db_session.commit()

        with pytest.raises(UnauthenticatedError, match="Session has expired"):
            service.resolve_session(token)

    def test_resolve_session_revoked_fails(self, auth_db_session):
        service = AuthService(auth_db_session)
        service.register_civilian("citizen@example.org", "SecurePassword123!", "Jane Citizen")
        _, token = service.login("citizen@example.org", "SecurePassword123!")

        service.logout(token)

        with pytest.raises(UnauthenticatedError, match="Session has been revoked"):
            service.resolve_session(token)

    def test_resolve_session_inactive_user_fails(self, auth_db_session):
        service = AuthService(auth_db_session)
        user = service.register_civilian("citizen@example.org", "SecurePassword123!", "Jane Citizen")
        _, token = service.login("citizen@example.org", "SecurePassword123!")

        # Deactivate user after session creation
        user.is_active = False
        auth_db_session.commit()

        with pytest.raises(UnauthenticatedError, match="inactive or not found"):
            service.resolve_session(token)

    def test_register_duplicate_email_fails(self, auth_db_session):
        service = AuthService(auth_db_session)
        service.register_civilian("citizen@example.org", "SecurePassword123!", "Citizen 1")

        with pytest.raises(InvalidParametersError, match="already exists"):
            service.register_civilian("citizen@example.org", "AnotherPassword!", "Citizen 2")


class TestAuthApiEndpoints:
    def test_login_api_sets_cookie_and_returns_user_dto(self, client_with_db, auth_db_session):
        service = AuthService(auth_db_session)
        service.register_civilian("citizen@example.org", "SecurePassword123!", "Citizen Test")

        res = client_with_db.post("/auth/login", json={
            "email": "citizen@example.org",
            "password": "SecurePassword123!",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["email"] == "citizen@example.org"
        assert data["full_name"] == "Citizen Test"
        assert data["role"] == "CIVILIAN"
        assert data["is_active"] is True
        assert "password_hash" not in data

        # Verify session cookie was set
        assert settings.SESSION_COOKIE_NAME in res.cookies
        cookie_val = res.cookies[settings.SESSION_COOKIE_NAME]
        assert len(cookie_val) >= 32

    def test_login_api_invalid_credentials_returns_401(self, client_with_db):
        res = client_with_db.post("/auth/login", json={
            "email": "unknown@example.org",
            "password": "AnyPassword123!",
        })
        assert res.status_code == 401
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] == "UNAUTHENTICATED"
        assert "Invalid email or password" in data["error"]["message"]

    def test_me_api_authenticated_and_unauthenticated(self, client_with_db, auth_db_session):
        # 1. Unauthenticated request -> 401
        res_unauth = client_with_db.get("/auth/me")
        assert res_unauth.status_code == 401
        assert res_unauth.json()["error"]["code"] == "UNAUTHENTICATED"

        # 2. Login to get cookie
        service = AuthService(auth_db_session)
        service.register_civilian("citizen@example.org", "SecurePassword123!", "Citizen Me")
        login_res = client_with_db.post("/auth/login", json={
            "email": "citizen@example.org",
            "password": "SecurePassword123!",
        })
        assert login_res.status_code == 200

        # 3. Authenticated request -> 200
        res_auth = client_with_db.get("/auth/me")
        assert res_auth.status_code == 200
        assert res_auth.json()["email"] == "citizen@example.org"

    def test_logout_api_revokes_session_and_clears_cookie(self, client_with_db, auth_db_session):
        service = AuthService(auth_db_session)
        service.register_civilian("citizen@example.org", "SecurePassword123!", "Citizen Logout")
        client_with_db.post("/auth/login", json={
            "email": "citizen@example.org",
            "password": "SecurePassword123!",
        })

        # Check me works
        assert client_with_db.get("/auth/me").status_code == 200

        # Logout
        logout_res = client_with_db.post("/auth/logout")
        assert logout_res.status_code == 200
        assert "Logged out successfully" in logout_res.json()["message"]

        # Subsequent me -> 401
        assert client_with_db.get("/auth/me").status_code == 401

    def test_register_api_creates_civilian(self, client_with_db):
        res = client_with_db.post("/auth/register", json={
            "email": "newcitizen@example.org",
            "password": "StrongPassword123!",
            "full_name": "New Citizen",
        })
        assert res.status_code == 201
        data = res.json()
        assert data["email"] == "newcitizen@example.org"
        assert data["role"] == "CIVILIAN"
        assert data["is_active"] is True
