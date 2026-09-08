"""Pydantic v2 data transfer objects for authentication, registration, and user identity.

Section refs: SETU-DRR Auth Part 1 — Identity + Password Verification + Server-Side Sessions.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from core.enums import Role

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginRequest(BaseModel):
    """Request payload for user authentication."""
    model_config = ConfigDict(extra="forbid")

    email: str = Field(
        ...,
        pattern=EMAIL_PATTERN,
        description="User account email address.",
        examples=["officer@setu.gov.in"],
    )
    password: str = Field(..., min_length=1, description="Account password.", examples=["********"])


class RegisterRequest(BaseModel):
    """Request payload for public civilian registration.
    
    Role is strictly not accepted from client and is automatically set to CIVILIAN.
    """
    model_config = ConfigDict(extra="forbid")

    email: str = Field(
        ...,
        pattern=EMAIL_PATTERN,
        description="Valid email address.",
        examples=["citizen@example.org"],
    )
    password: str = Field(..., min_length=8, description="Secure password (minimum 8 characters).")
    full_name: str = Field(..., min_length=1, max_length=200, description="Full name of the user.", examples=["Asha Nair"])


class JurisdictionDTO(BaseModel):
    """Authoritative administrative jurisdiction assignment."""
    model_config = ConfigDict(from_attributes=True)

    admin_id: int = Field(..., description="Canonical administrative boundary ID (admin_boundary.id).")
    name: str = Field(..., description="Administrative boundary name (e.g. Wayanad, Kodagu).")
    level: str = Field(..., description="Administrative boundary level (e.g. district, state).")
    lgd_code: Optional[int] = Field(None, description="Local Government Directory (LGD) code.")


class UserResponse(BaseModel):
    """Safe authenticated identity DTO.
    
    Guaranteed never to expose password hashes, session tokens, or internal secrets.
    """
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique user identifier.")
    email: str = Field(..., description="User email address.")
    full_name: str = Field(..., description="Full name of user.")
    role: Role = Field(..., description="User role (CIVILIAN, GOVERNMENT_OFFICIAL, SYSTEM_ADMIN).")
    is_active: bool = Field(..., description="Whether user account is active.")
    created_at: datetime = Field(..., description="Account creation timestamp.")
    last_login_at: Optional[datetime] = Field(None, description="Timestamp of most recent successful login.")
    jurisdiction: Optional[JurisdictionDTO] = Field(
        default=None,
        description="Administrative jurisdiction assigned to privileged user, or None for unconstrained/civilian users.",
    )


class LogoutResponse(BaseModel):
    """Response returned upon successful session revocation."""
    message: str = Field(default="Logged out successfully.", description="Status message.")
