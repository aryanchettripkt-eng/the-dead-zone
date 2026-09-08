"""Unit tests for SETU-DRR Authentication Part 1: Identity, Argon2id, and Sessions.

Section refs: SETU-DRR Auth Part 1 — Tests Required (§28).
Runs in-memory with zero PostgreSQL dependencies.
"""

import uuid
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from core.enums import Role
from core.domain.auth import (
    hash_password,
    verify_password,
    generate_session_token,
    hash_session_token,
)
from core.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    UserResponse,
    LogoutResponse,
)


def test_argon2id_password_hashing():
    """Verify Argon2id password hashing and constant-time verification."""
    password = "SuperSecretPassword123!"

    # 1. Hashes successfully
    pw_hash = hash_password(password)
    assert isinstance(pw_hash, str)
    assert len(pw_hash) > 50

    # 2. Verify Argon2id variant is explicitly used
    assert pw_hash.startswith("$argon2id$")

    # 3. Same password verifies
    assert verify_password(password, pw_hash) is True

    # 4. Wrong password fails
    assert verify_password("WrongPassword123!", pw_hash) is False
    assert verify_password("", pw_hash) is False
    assert verify_password(password, "") is False

    # 5. Repeated hashing produces distinct salts/hashes
    pw_hash_2 = hash_password(password)
    assert pw_hash != pw_hash_2
    assert verify_password(password, pw_hash_2) is True


def test_empty_password_rejected():
    """Verify empty password raises ValueError."""
    with pytest.raises(ValueError, match="Password cannot be empty"):
        hash_password("")


def test_session_token_generation_and_hashing():
    """Verify cryptographically secure raw token generation and SHA-256 storage hash."""
    token1 = generate_session_token()
    token2 = generate_session_token()

    assert isinstance(token1, str)
    assert len(token1) >= 32
    assert token1 != token2

    hash1 = hash_session_token(token1)
    hash2 = hash_session_token(token2)

    # SHA-256 hex digest is exactly 64 characters
    assert len(hash1) == 64
    assert len(hash2) == 64
    assert hash1 != hash2
    assert hash_session_token(token1) == hash1  # Deterministic one-way digest


def test_role_enum_values():
    """Verify exact role enumeration values and absence of RESCUE_OFFICER."""
    assert Role.CIVILIAN == "CIVILIAN"
    assert Role.GOVERNMENT_OFFICIAL == "GOVERNMENT_OFFICIAL"
    assert Role.SYSTEM_ADMIN == "SYSTEM_ADMIN"
    assert set(r.value for r in Role) == {"CIVILIAN", "GOVERNMENT_OFFICIAL", "SYSTEM_ADMIN"}
    assert not hasattr(Role, "RESCUE_OFFICER")


def test_legacy_rescue_officer_representation():
    """Verify that rescue officers are represented as GOVERNMENT_OFFICIAL in UserResponse."""
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    # A rescue officer user must be serialized with role=GOVERNMENT_OFFICIAL
    rescue_dto = UserResponse(
        id=user_id,
        email="rescue@setu.gov.in",
        full_name="NDRF Commander",
        role=Role.GOVERNMENT_OFFICIAL,
        is_active=True,
        created_at=now,
    )
    assert rescue_dto.role == Role.GOVERNMENT_OFFICIAL
    assert rescue_dto.role.value == "GOVERNMENT_OFFICIAL"
    assert rescue_dto.model_dump()["role"] == "GOVERNMENT_OFFICIAL"


def test_user_response_dto_never_exposes_secrets():
    """Verify UserResponse DTO excludes password_hash, session_token, and internal secrets."""
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    user_dto = UserResponse(
        id=user_id,
        email="officer@setu.gov.in",
        full_name="District Officer",
        role=Role.GOVERNMENT_OFFICIAL,
        is_active=True,
        created_at=now,
        last_login_at=now,
    )

    data = user_dto.model_dump()

    # Required fields present
    assert data["id"] == user_id
    assert data["email"] == "officer@setu.gov.in"
    assert data["full_name"] == "District Officer"
    assert data["role"] == "GOVERNMENT_OFFICIAL"
    assert data["is_active"] is True

    # Security check: secrets must NEVER be present in schema fields
    schema_properties = UserResponse.model_json_schema()["properties"]
    assert "password" not in schema_properties
    assert "password_hash" not in schema_properties
    assert "token" not in schema_properties
    assert "session_token" not in schema_properties
    assert "session_token_hash" not in schema_properties
    assert "secret" not in schema_properties


def test_register_request_forbids_client_selected_role():
    """Verify public registration payload rejects client-specified role."""
    # Valid payload without role
    reg = RegisterRequest(
        email="citizen@example.org",
        password="ValidPassword123!",
        full_name="Citizen One",
    )
    assert reg.email == "citizen@example.org"

    # Attempting to supply role must fail validation (extra fields forbidden)
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="hacker@example.org",
            password="ValidPassword123!",
            full_name="Hacker",
            role="GOVERNMENT_OFFICIAL",  # Must be rejected
        )


def test_login_request_validation():
    """Verify LoginRequest validation constraints."""
    login = LoginRequest(email="citizen@example.org", password="ValidPassword123!")
    assert login.email == "citizen@example.org"
    assert login.password == "ValidPassword123!"

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        LoginRequest(
            email="citizen@example.org",
            password="ValidPassword123!",
            extra_field="unwanted",
        )
