"""Database repository for user identities and authenticated server-side sessions.

Section refs: SETU-DRR Auth Part 1 — Identity + Password Verification + Server-Side Sessions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload, defer

from core.db_models import AppUser, UserSession, AdminBoundary


class AuthRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_user_by_email(self, email: str) -> Optional[AppUser]:
        """Retrieves user by normalized email (case-insensitive search)."""
        stmt = (
            select(AppUser)
            .options(
                joinedload(AppUser.admin_boundary)
                .defer(AdminBoundary.geom)
                .defer(AdminBoundary.bbox)
            )
            .where(AppUser.email == email.strip().lower())
        )
        return self.db.execute(stmt).scalars().first()

    def get_user_by_id(self, user_id: uuid.UUID) -> Optional[AppUser]:
        """Retrieves user by UUID primary key."""
        stmt = (
            select(AppUser)
            .options(
                joinedload(AppUser.admin_boundary)
                .defer(AdminBoundary.geom)
                .defer(AdminBoundary.bbox)
            )
            .where(AppUser.id == user_id)
        )
        return self.db.execute(stmt).scalars().first()

    def create_user(
        self,
        email: str,
        password_hash: str,
        full_name: str,
        role: str,
        is_active: bool = True,
    ) -> AppUser:
        """Creates a new user record in PostgreSQL."""
        now = datetime.now(timezone.utc)
        user = AppUser(
            id=uuid.uuid4(),
            email=email.strip().lower(),
            password_hash=password_hash,
            full_name=full_name.strip(),
            role=role,
            is_active=is_active,
            created_at=now,
            updated_at=now,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_last_login(self, user_id: uuid.UUID, login_time: Optional[datetime] = None) -> None:
        """Updates the last_login_at timestamp for the user."""
        ts = login_time or datetime.now(timezone.utc)
        stmt = update(AppUser).where(AppUser.id == user_id).values(last_login_at=ts)
        self.db.execute(stmt)
        self.db.commit()

    def create_session(
        self,
        user_id: uuid.UUID,
        session_token_hash: str,
        expires_at: datetime,
    ) -> UserSession:
        """Persists a new server-side session."""
        now = datetime.now(timezone.utc)
        session = UserSession(
            id=uuid.uuid4(),
            user_id=user_id,
            session_token_hash=session_token_hash,
            created_at=now,
            expires_at=expires_at,
            last_seen_at=now,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_session_by_token_hash(self, token_hash: str) -> Optional[UserSession]:
        """Looks up session by SHA-256 hash digest, eagerly loading the associated user and jurisdiction."""
        stmt = (
            select(UserSession)
            .options(
                joinedload(UserSession.user)
                .joinedload(AppUser.admin_boundary)
                .defer(AdminBoundary.geom)
                .defer(AdminBoundary.bbox)
            )
            .where(UserSession.session_token_hash == token_hash)
        )
        return self.db.execute(stmt).scalars().first()

    def revoke_session(self, session_id: uuid.UUID) -> None:
        """Marks a session as revoked."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(UserSession)
            .where(UserSession.id == session_id)
            .values(revoked_at=now)
        )
        self.db.execute(stmt)
        self.db.commit()
