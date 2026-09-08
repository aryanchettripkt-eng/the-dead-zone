"""In-memory sliding-window rate limiting for authentication attempts (Batch E).

Provides thread-safe tracking of failed login attempts keyed by normalized email
and client IP to defend against brute-force and credential stuffing attacks without
introducing external infrastructure dependencies.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from threading import Lock
from typing import Optional

logger = logging.getLogger("setu_rate_limiter")


class LoginRateLimiter:
    """Thread-safe sliding-window rate limiter for login attempts.

    Maintains in-memory lists of attempt timestamps for:
    1. 'email:<normalized_email>' - protects individual accounts from targeted brute force.
    2. 'ip:<client_ip>' - protects the service from distributed spraying across accounts.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        max_ip_attempts: int = 20,
        window_seconds: int = 60,
        enabled: bool = True,
    ) -> None:
        self.max_attempts = max_attempts
        self.max_ip_attempts = max_ip_attempts
        self.window_seconds = window_seconds
        self.enabled = enabled
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def check_rate_limit(self, email: str, client_ip: str) -> Optional[int]:
        """Checks whether the email or client IP has exceeded the allowed attempts.

        Returns:
            Retry-after seconds if blocked, or None if the request is permitted.
        """
        if not self.enabled:
            return None

        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            # 1. Check account / email rate limit
            norm_email = email.strip().lower() if email else ""
            if norm_email:
                email_key = f"email:{norm_email}"
                valid_email_attempts = [t for t in self._attempts[email_key] if t > cutoff]
                self._attempts[email_key] = valid_email_attempts
                if len(valid_email_attempts) >= self.max_attempts:
                    oldest = valid_email_attempts[0]
                    retry_after = max(1, int(self.window_seconds - (now - oldest)))
                    logger.warning(
                        f"Login rate limit exceeded for email '{norm_email}': "
                        f"{len(valid_email_attempts)}/{self.max_attempts} attempts. "
                        f"Retry-after: {retry_after}s"
                    )
                    return retry_after

            # 2. Check client IP rate limit
            clean_ip = client_ip.strip() if client_ip else "127.0.0.1"
            if clean_ip:
                ip_key = f"ip:{clean_ip}"
                valid_ip_attempts = [t for t in self._attempts[ip_key] if t > cutoff]
                self._attempts[ip_key] = valid_ip_attempts
                if len(valid_ip_attempts) >= self.max_ip_attempts:
                    oldest = valid_ip_attempts[0]
                    retry_after = max(1, int(self.window_seconds - (now - oldest)))
                    logger.warning(
                        f"Login rate limit exceeded for IP '{clean_ip}': "
                        f"{len(valid_ip_attempts)}/{self.max_ip_attempts} attempts. "
                        f"Retry-after: {retry_after}s"
                    )
                    return retry_after

        return None

    def record_failed_attempt(self, email: str, client_ip: str) -> None:
        """Records a failed authentication attempt for both email and client IP."""
        if not self.enabled:
            return

        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            norm_email = email.strip().lower() if email else ""
            if norm_email:
                email_key = f"email:{norm_email}"
                self._attempts[email_key] = [t for t in self._attempts[email_key] if t > cutoff]
                self._attempts[email_key].append(now)

            clean_ip = client_ip.strip() if client_ip else "127.0.0.1"
            if clean_ip:
                ip_key = f"ip:{clean_ip}"
                self._attempts[ip_key] = [t for t in self._attempts[ip_key] if t > cutoff]
                self._attempts[ip_key].append(now)

    def record_successful_login(self, email: str) -> None:
        """Clears failed attempts for an email upon successful authentication."""
        if not self.enabled:
            return

        with self._lock:
            norm_email = email.strip().lower() if email else ""
            if norm_email:
                email_key = f"email:{norm_email}"
                self._attempts.pop(email_key, None)

    def reset(self) -> None:
        """Clears all tracking state across all keys (essential for test isolation)."""
        with self._lock:
            self._attempts.clear()
