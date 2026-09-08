"""Pure domain logic for password hashing, verification, and session token generation.

Section refs: SETU-DRR Auth Part 1 — Identity + Password Verification + Server-Side Sessions.
Uses Argon2id (RFC 9106) for memory-hard, GPU/ASIC-resistant password hashing.
"""

from __future__ import annotations

import hashlib
import secrets
import logging
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

logger = logging.getLogger("setu_auth_domain")

# Argon2id password hasher initialized with secure defaults:
# Type: Argon2id, Memory: 64 MiB (65536 KiB), Time: 3 iterations, Parallelism: 4 threads, Hash length: 32 bytes
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hashes a plaintext password using Argon2id with random salt.
    
    Returns:
        Encoded Argon2id hash string (e.g. '$argon2id$v=19$m=65536,t=3,p=4$...').
    """
    if not password:
        raise ValueError("Password cannot be empty.")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verifies a plaintext password against an Argon2id hash in constant time.
    
    Returns:
        True if the password matches, False otherwise.
    """
    if not password or not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    except Exception as e:
        logger.warning(f"Unexpected error during password verification: {e}")
        return False


def generate_session_token() -> str:
    """Generates a cryptographically secure, URL-safe raw session token (32 bytes / ~43 chars)."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Computes SHA-256 one-way digest of raw session token for secure database storage.
    
    The raw token is held only by the client cookie; the database stores only this hash.
    """
    if not token:
        raise ValueError("Session token cannot be empty.")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
