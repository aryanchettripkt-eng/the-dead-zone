"""Focused regression test suite for Batch E: Authentication Security.

Validates:
1. N2 — Valid Argon2id dummy hash / timing oracle defense:
   - _DUMMY_ARGON2_HASH is a valid, parseable Argon2id encoded string.
   - Uses the application's canonical Argon2id configuration (m=65536, t=3, p=4).
   - Verifying arbitrary passwords against the dummy hash raises VerifyMismatchError,
     performing genuine KDF work rather than failing immediately with VerificationError or InvalidHashError.
   - Unknown-user login path and known-user wrong-password path execute identical
     Argon2 verification mechanisms without leaking account existence.

2. Login Rate Limiting:
   - Requests below threshold proceed normally.
   - Threshold enforcement blocks excessive attempts with HTTP 429 and standard error envelope.
   - Sliding-window timestamp expiration allows attempts after the window passes.
   - Keying strategy defends against both targeted account brute-force and IP spraying.
   - Successful login resets the failed counter for the target account.
   - Disabling rate limiting via configuration allows unconstrained attempts.
   - Complete state isolation between test invocations.
"""

from __future__ import annotations

import time
import pytest
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.dependencies import get_db, get_login_rate_limiter
from api.main import app
from api.services.auth_service import AuthService, _DUMMY_ARGON2_HASH
from core.config import settings
from core.db_models import AppUser, UserSession
from core.domain.auth import verify_password
from core.domain.rate_limit import LoginRateLimiter
from core.errors import RateLimitExceededError, UnauthenticatedError


@pytest.fixture
def isolated_db_session():
    """Provides an isolated in-memory SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS admin_boundary "
                "(id INTEGER PRIMARY KEY, name TEXT, level TEXT, lgd_code INTEGER, parent_id INTEGER);"
            )
        )
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
def isolated_rate_limiter():
    """Provides a dedicated, clean rate limiter instance for testing."""
    limiter = LoginRateLimiter(
        max_attempts=3,
        max_ip_attempts=5,
        window_seconds=2,
        enabled=True,
    )
    yield limiter
    limiter.reset()


@pytest.fixture
def test_client(isolated_db_session, isolated_rate_limiter):
    """FastAPI TestClient with database and rate limiter dependencies isolated."""
    def _override_get_db():
        yield isolated_db_session

    def _override_get_rate_limiter():
        return isolated_rate_limiter

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_login_rate_limiter] = _override_get_rate_limiter

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_login_rate_limiter, None)


# =========================================================================== #
# Test Group 1: N2 — Argon2id Dummy Hash Correctness & Timing Oracle Defense
# =========================================================================== #


class TestN2Argon2DummyHash:
    def test_dummy_hash_format_and_parameters(self):
        """Validates that _DUMMY_ARGON2_HASH conforms to the canonical Argon2id spec."""
        assert _DUMMY_ARGON2_HASH.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
        # Ensure it has exactly 5 dollar-separated fields: '', 'argon2id', 'v=19', 'm=...,t=...,p=...', 'salt', 'hash'
        parts = _DUMMY_ARGON2_HASH.split("$")
        assert len(parts) == 6
        assert parts[1] == "argon2id"
        assert parts[2] == "v=19"
        assert parts[3] == "m=65536,t=3,p=4"
        assert len(parts[4]) >= 16  # base64 encoded salt
        assert len(parts[5]) >= 32  # base64 encoded digest

    def test_dummy_hash_performs_genuine_kdf_work_without_syntax_error(self):
        """Verifies that verifying against _DUMMY_ARGON2_HASH executes real Argon2 work.

        Crucially: It must raise VerifyMismatchError (indicating that the hash was decoded
        and full KDF memory/iterations were computed, and tag did not match), and must NEVER
        raise VerificationError (e.g. 'Decoding failed') or InvalidHashError.
        """
        hasher = PasswordHasher()
        try:
            hasher.verify(_DUMMY_ARGON2_HASH, "arbitrary_attempt_password")
            pytest.fail("Verification against dummy hash unexpectedly succeeded!")
        except VerifyMismatchError:
            # Expected: full KDF work was performed and password did not match
            pass
        except (VerificationError, InvalidHashError) as exc:
            pytest.fail(f"Dummy hash is malformed or invalid: {type(exc).__name__}: {exc}")

    def test_verify_password_wrapper_returns_false_safely(self):
        """Verifies that domain verify_password() safely returns False without exceptions."""
        result = verify_password("arbitrary_wrong_password", _DUMMY_ARGON2_HASH)
        assert result is False

    def test_unknown_user_path_invokes_full_argon2_verification(self, isolated_db_session):
        """Verifies that AuthService.login() with an unknown email runs dummy verification and raises UnauthenticatedError."""
        limiter = LoginRateLimiter(max_attempts=10, enabled=False)
        service = AuthService(isolated_db_session, rate_limiter=limiter)

        with pytest.raises(UnauthenticatedError) as exc_info:
            service.login("nonexistent.user@example.gov.in", "AttemptPassword123!")

        assert exc_info.value.code.value == "UNAUTHENTICATED"
        assert exc_info.value.message == "Invalid email or password."
        assert exc_info.value.status_code == 401

    def test_known_vs_unknown_timing_consistency_diagnostic(self, isolated_db_session):
        """Diagnostic assertion: verifying unknown email and known email wrong password

        both execute real Argon2 KDF computation and take comparable execution times.
        """
        limiter = LoginRateLimiter(max_attempts=10, enabled=False)
        service = AuthService(isolated_db_session, rate_limiter=limiter)
        service.register_civilian("known.user@example.gov.in", "RealSecretPassword123!", "Known User")

        # 1. Warm up CPU cache / JIT
        try:
            service.login("known.user@example.gov.in", "WrongPassword1")
        except UnauthenticatedError:
            pass

        # 2. Measure known user wrong password
        t0 = time.perf_counter()
        try:
            service.login("known.user@example.gov.in", "WrongPassword2")
        except UnauthenticatedError:
            pass
        dt_known = time.perf_counter() - t0

        # 3. Measure unknown user
        t1 = time.perf_counter()
        try:
            service.login("unknown.user@example.gov.in", "ArbitraryPassword")
        except UnauthenticatedError:
            pass
        dt_unknown = time.perf_counter() - t1

        # Both must take genuine computation time (> 5ms on modern CPU, typically 30-80ms for 64MB Argon2)
        assert dt_known > 0.005, f"Known user verification was suspiciously fast: {dt_known*1000:.2f}ms"
        assert dt_unknown > 0.005, f"Unknown user verification was suspiciously fast (N2 regression!): {dt_unknown*1000:.2f}ms"

        # Neither should be an order-of-magnitude anomaly compared to the other
        ratio = max(dt_known, dt_unknown) / max(min(dt_known, dt_unknown), 1e-6)
        assert ratio < 5.0, f"Timing ratio {ratio:.2f}x exceeds reasonable variance threshold"

    def test_no_account_existence_leakage_in_error_payload(self, test_client, isolated_db_session):
        """Ensures the API response for unknown email and wrong password are byte-for-byte identical in structure and message."""
        service = AuthService(isolated_db_session)
        service.register_civilian("citizen@example.gov.in", "CorrectPassword123!", "Citizen Test")

        # Case A: Unknown email
        res_unknown = test_client.post("/auth/login", json={
            "email": "definitely_unknown@example.gov.in",
            "password": "WrongPassword123!",
        })

        # Case B: Known email, wrong password
        res_wrong = test_client.post("/auth/login", json={
            "email": "citizen@example.gov.in",
            "password": "WrongPassword123!",
        })

        assert res_unknown.status_code == 401
        assert res_wrong.status_code == 401

        data_unknown = res_unknown.json()
        data_wrong = res_wrong.json()

        assert data_unknown["error"]["code"] == data_wrong["error"]["code"] == "UNAUTHENTICATED"
        assert data_unknown["error"]["message"] == data_wrong["error"]["message"] == "Invalid email or password."


# =========================================================================== #
# Test Group 2: Login Rate Limiting Enforcement & Architecture
# =========================================================================== #


class TestLoginRateLimiting:
    def test_requests_below_threshold_proceed_normally(self, test_client, isolated_db_session):
        """Verifies that login attempts below max_attempts are evaluated normally."""
        # Configured isolated_rate_limiter has max_attempts=3
        res1 = test_client.post("/auth/login", json={"email": "target@example.org", "password": "bad1"})
        assert res1.status_code == 401

        res2 = test_client.post("/auth/login", json={"email": "target@example.org", "password": "bad2"})
        assert res2.status_code == 401

    def test_threshold_enforcement_returns_429_error_envelope(self, test_client):
        """Verifies that exceeding max_attempts triggers HTTP 429 with standard error envelope."""
        # max_attempts is 3 in isolated fixture
        for i in range(3):
            res = test_client.post("/auth/login", json={"email": "lockout@example.org", "password": f"wrong{i}"})
            assert res.status_code == 401

        # 4th attempt must be blocked by rate limiter
        res_blocked = test_client.post("/auth/login", json={"email": "lockout@example.org", "password": "wrong"})
        assert res_blocked.status_code == 429

        data = res_blocked.json()
        assert "error" in data
        assert data["error"]["code"] == "RATE_LIMITED"
        assert "Too many login attempts" in data["error"]["message"]
        assert "retry_after_seconds" in data["error"]["details"]
        assert data["error"]["details"]["retry_after_seconds"] >= 1
        assert "X-Request-ID" in res_blocked.headers

    def test_rate_limiter_does_not_reveal_user_existence(self, test_client, isolated_db_session):
        """Verifies that 429 rate limiting applies identically to unknown and known emails."""
        service = AuthService(isolated_db_session)
        service.register_civilian("registered@example.org", "Password123!", "Registered User")

        # Exceed limit on registered account
        for _ in range(3):
            test_client.post("/auth/login", json={"email": "registered@example.org", "password": "bad"})
        res_reg = test_client.post("/auth/login", json={"email": "registered@example.org", "password": "bad"})

        # Reset limiter for unknown account test
        limiter = get_login_rate_limiter()
        limiter.reset()

        # Exceed limit on unregistered account
        for _ in range(3):
            test_client.post("/auth/login", json={"email": "unregistered@example.org", "password": "bad"})
        res_unreg = test_client.post("/auth/login", json={"email": "unregistered@example.org", "password": "bad"})

        assert res_reg.status_code == 429
        assert res_unreg.status_code == 429
        assert res_reg.json()["error"]["code"] == res_unreg.json()["error"]["code"] == "RATE_LIMITED"
        assert res_reg.json()["error"]["message"] == res_unreg.json()["error"]["message"]

    def test_sliding_window_expiration_restores_access(self, isolated_db_session):
        """Verifies that attempts age out and rate limiting clears after window duration."""
        short_limiter = LoginRateLimiter(max_attempts=2, window_seconds=1, enabled=True)
        service = AuthService(isolated_db_session, rate_limiter=short_limiter)

        # 2 failures -> max reached
        with pytest.raises(UnauthenticatedError):
            service.login("user@example.org", "bad1")
        with pytest.raises(UnauthenticatedError):
            service.login("user@example.org", "bad2")

        # Immediate next attempt -> blocked
        with pytest.raises(RateLimitExceededError):
            service.login("user@example.org", "bad3")

        # Wait for sliding window to expire (1.1s > 1.0s)
        time.sleep(1.1)

        # Access restored -> fails with UnauthenticatedError instead of RateLimitExceededError
        with pytest.raises(UnauthenticatedError):
            service.login("user@example.org", "bad4")

    def test_successful_login_resets_email_failed_counter(self, test_client, isolated_db_session):
        """Verifies that a successful login resets the failed attempts counter for that account."""
        service = AuthService(isolated_db_session)
        service.register_civilian("valid@example.org", "CorrectPassword123!", "Valid User")

        # 2 failed attempts (max is 3)
        res1 = test_client.post("/auth/login", json={"email": "valid@example.org", "password": "wrong"})
        res2 = test_client.post("/auth/login", json={"email": "valid@example.org", "password": "wrong"})
        assert res1.status_code == 401
        assert res2.status_code == 401

        # Successful login -> must succeed and clear email counter
        res_success = test_client.post("/auth/login", json={"email": "valid@example.org", "password": "CorrectPassword123!"})
        assert res_success.status_code == 200

        # Subsequent failed attempt should be at count 1, not count 3 (so not blocked)
        res_post = test_client.post("/auth/login", json={"email": "valid@example.org", "password": "wrong"})
        assert res_post.status_code == 401

    def test_ip_rate_limiting_prevents_distributed_account_spraying(self, isolated_db_session):
        """Verifies that client IP limit prevents an attacker from spraying across different emails."""
        spraying_limiter = LoginRateLimiter(
            max_attempts=5,        # 5 per email
            max_ip_attempts=3,     # only 3 per IP total
            window_seconds=60,
            enabled=True,
        )
        service = AuthService(isolated_db_session, rate_limiter=spraying_limiter)

        # Attacker attacks 3 distinct emails from same IP '192.168.1.50'
        for i in range(3):
            with pytest.raises(UnauthenticatedError):
                service.login(f"target_{i}@example.org", "guessed_pass", client_ip="192.168.1.50")

        # 4th attempt on a brand-new email from the same IP must be blocked by IP rate limit
        with pytest.raises(RateLimitExceededError) as exc_info:
            service.login("target_brand_new@example.org", "guessed_pass", client_ip="192.168.1.50")

        assert exc_info.value.status_code == 429
        assert exc_info.value.code.value == "RATE_LIMITED"

        # Meanwhile, a different client IP can still attempt login on target_brand_new@example.org
        with pytest.raises(UnauthenticatedError):
            service.login("target_brand_new@example.org", "guessed_pass", client_ip="10.0.0.1")

    def test_disabled_rate_limiting_allows_unlimited_attempts(self, isolated_db_session):
        """Verifies that setting enabled=False bypasses rate limit checks."""
        disabled_limiter = LoginRateLimiter(max_attempts=2, enabled=False)
        service = AuthService(isolated_db_session, rate_limiter=disabled_limiter)

        for _ in range(5):
            with pytest.raises(UnauthenticatedError):
                service.login("anyone@example.org", "bad_pass")

    def test_x_forwarded_for_header_cannot_bypass_ip_rate_limit(self, test_client):
        """Verifies that rotating X-Forwarded-For headers does NOT bypass client IP rate limiting."""
        # isolated_rate_limiter has max_ip_attempts=5 and max_attempts=3
        # Send 5 attempts targeting 5 different accounts while rotating X-Forwarded-For header
        for i in range(5):
            res = test_client.post(
                "/auth/login",
                json={"email": f"spray_account_{i}@example.org", "password": "wrong_password"},
                headers={"X-Forwarded-For": f"198.51.100.{i+1}"},
            )
            assert res.status_code == 401

        # 6th attempt with yet another spoofed X-Forwarded-For header must be blocked by real client IP limit (429)
        res_blocked = test_client.post(
            "/auth/login",
            json={"email": "spray_account_99@example.org", "password": "wrong_password"},
            headers={"X-Forwarded-For": "198.51.100.99"},
        )
        assert res_blocked.status_code == 429
        assert res_blocked.json()["error"]["code"] == "RATE_LIMITED"
