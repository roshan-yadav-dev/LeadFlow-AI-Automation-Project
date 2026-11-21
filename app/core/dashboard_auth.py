import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

from fastapi import HTTPException, Request, Response, status

from app.core.config import settings

logger = logging.getLogger("leadflow")


@dataclass
class DashboardSession:
    session_id: str
    username: str
    csrf_token: str
    created_at: float
    expires_at: float


class DashboardAuthManager:
    """
    Secure server-side dashboard session and authentication manager.
    - Password verification (PBKDF2 SHA-256)
    - HttpOnly, SameSite session cookies
    - CSRF protection for mutations
    - Brute-force rate limiting per client IP
    """

    def __init__(self):
        self._lock = Lock()
        self._sessions: dict[str, DashboardSession] = {}
        self._login_attempts: dict[str, list[float]] = {}
        self._max_attempts = 5
        self._lockout_window_seconds = 900  # 15 minutes

    @staticmethod
    def hash_password(password: str, salt: bytes | None = None) -> str:
        """Hash a password with PBKDF2-HMAC-SHA256 and return hex string."""
        if salt is None:
            salt = secrets.token_bytes(16)
        iterations = 100_000
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return f"{salt.hex()}${key.hex()}"

    @classmethod
    def verify_password(cls, plain_password: str, stored_hash_or_plain: str) -> bool:
        """Verify plain password against stored hash or configured plain password."""
        if not stored_hash_or_plain or not plain_password:
            return False

        # In production, reject any insecure development default passwords
        if settings.ENVIRONMENT.lower() in ("production", "prod"):
            if plain_password in settings.INSECURE_DEFAULT_PASSWORDS:
                logger.warning("Rejected attempt to use insecure default password in production environment.")
                return False

        if "$" in stored_hash_or_plain:
            try:
                salt_hex, key_hex = stored_hash_or_plain.split("$", 1)
                salt = bytes.fromhex(salt_hex)
                expected_key = bytes.fromhex(key_hex)
                computed = hashlib.pbkdf2_hmac(
                    "sha256", plain_password.encode("utf-8"), salt, 100_000
                )
                return hmac.compare_digest(computed, expected_key)
            except Exception:
                return False
        else:
            return secrets.compare_digest(plain_password, stored_hash_or_plain)

    def is_rate_limited(self, client_ip: str) -> tuple[bool, int]:
        """Check if client IP has exceeded maximum failed login attempts."""
        now = time.time()
        with self._lock:
            attempts = self._login_attempts.get(client_ip, [])
            valid_attempts = [t for t in attempts if now - t < self._lockout_window_seconds]
            self._login_attempts[client_ip] = valid_attempts

            if len(valid_attempts) >= self._max_attempts:
                remaining = int(self._lockout_window_seconds - (now - valid_attempts[0]))
                return True, max(1, remaining)
            return False, 0

    def record_failed_attempt(self, client_ip: str):
        now = time.time()
        with self._lock:
            attempts = self._login_attempts.setdefault(client_ip, [])
            attempts.append(now)

    def clear_failed_attempts(self, client_ip: str):
        with self._lock:
            self._login_attempts.pop(client_ip, None)

    def create_session(self, username: str, response: Response | None = None) -> DashboardSession:
        now = time.time()
        session_id = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        expires_at = now + settings.SESSION_MAX_AGE_SECONDS

        session = DashboardSession(
            session_id=session_id,
            username=username,
            csrf_token=csrf_token,
            created_at=now,
            expires_at=expires_at,
        )

        with self._lock:
            # Purge expired sessions
            expired = [sid for sid, s in self._sessions.items() if s.expires_at <= now]
            for sid in expired:
                del self._sessions[sid]
            self._sessions[session_id] = session

        if response is not None:
            is_prod = settings.ENVIRONMENT.lower() in ("production", "prod")
            response.set_cookie(
                key=settings.SESSION_COOKIE_NAME,
                value=session_id,
                max_age=settings.SESSION_MAX_AGE_SECONDS,
                httponly=True,
                samesite="lax",
                secure=is_prod,
                path="/",
            )
            # Also set CSRF cookie readable by JS for double-submit
            response.set_cookie(
                key="leadflow_csrf",
                value=csrf_token,
                max_age=settings.SESSION_MAX_AGE_SECONDS,
                httponly=False,
                samesite="lax",
                secure=is_prod,
                path="/",
            )

        return session

    def get_session(self, session_id: str | None) -> DashboardSession | None:
        if not session_id:
            return None
        now = time.time()
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            if session.expires_at <= now:
                del self._sessions[session_id]
                return None
            return session

    def get_session_from_request(self, request: Request) -> DashboardSession | None:
        session_id = request.cookies.get(settings.SESSION_COOKIE_NAME)
        return self.get_session(session_id)

    def revoke_session(self, session_id: str | None, response: Response | None = None) -> bool:
        if not session_id:
            return False
        with self._lock:
            removed = self._sessions.pop(session_id, None) is not None

        if response is not None:
            is_prod = settings.ENVIRONMENT.lower() in ("production", "prod")
            response.delete_cookie(
                key=settings.SESSION_COOKIE_NAME,
                path="/",
                httponly=True,
                samesite="lax",
                secure=is_prod,
            )
            response.delete_cookie(
                key="leadflow_csrf",
                path="/",
                httponly=False,
                samesite="lax",
                secure=is_prod,
            )
        return removed


dashboard_auth = DashboardAuthManager()
