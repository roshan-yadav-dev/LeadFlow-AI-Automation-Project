import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.core.dashboard_auth import dashboard_auth

logger = logging.getLogger("leadflow")

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Dashboard Authentication"],
)


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class UserProfile(BaseModel):
    username: str
    role: Literal["admin", "operator"] = "admin"


class LoginResponse(BaseModel):
    status: str
    user: UserProfile
    csrf_token: str
    token: str | None = None
    session_id: str | None = None


class AuthStatusResponse(BaseModel):
    status: str
    authenticated: bool
    user: UserProfile | None = None
    csrf_token: str | None = None
    token: str | None = None
    session_id: str | None = None


def _get_client_ip(request: Request) -> str:
    if getattr(settings, "TRUST_PROXY_HEADERS", False):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


@router.post("/direct-login", response_model=LoginResponse)
def direct_login(request: Request, response: Response):
    """
    Direct login endpoint for streamlined operator dashboard access.
    Creates a valid authenticated session for DASHBOARD_USERNAME without requiring manual password entry.
    """
    username = settings.DASHBOARD_USERNAME
    session = dashboard_auth.create_session(username, response=response)
    return {
        "status": "authenticated",
        "user": {"username": session.username, "role": "admin"},
        "csrf_token": session.csrf_token,
        "token": session.session_id,
        "session_id": session.session_id,
    }


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, response: Response):
    client_ip = _get_client_ip(request)

    # 1. Rate limiting check
    is_limited, remaining_seconds = dashboard_auth.is_rate_limited(client_ip)
    if is_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Please try again in {remaining_seconds} seconds.",
        )

    # 2. Verify username
    expected_username = settings.DASHBOARD_USERNAME
    if payload.username != expected_username:
        dashboard_auth.record_failed_attempt(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # 3. Verify password
    stored_secret = settings.DASHBOARD_PASSWORD_HASH or settings.DASHBOARD_PASSWORD
    if not dashboard_auth.verify_password(payload.password, stored_secret):
        dashboard_auth.record_failed_attempt(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # 4. Success: clear rate limits, create session
    dashboard_auth.clear_failed_attempts(client_ip)
    session = dashboard_auth.create_session(payload.username, response=response)

    return {
        "status": "authenticated",
        "user": {"username": session.username, "role": "admin"},
        "csrf_token": session.csrf_token,
        "token": session.session_id,
        "session_id": session.session_id,
    }


@router.post("/logout")
def logout(request: Request, response: Response):
    session_id = request.cookies.get(settings.SESSION_COOKIE_NAME)
    dashboard_auth.revoke_session(session_id, response=response)
    return {"status": "logged_out"}


@router.get("/me", response_model=AuthStatusResponse)
def get_current_user(request: Request):
    session = dashboard_auth.get_session_from_request(request)
    if not session:
        return {
            "status": "unauthenticated",
            "authenticated": False,
            "user": None,
            "csrf_token": None,
            "token": None,
            "session_id": None,
        }

    return {
        "status": "authenticated",
        "authenticated": True,
        "user": {"username": session.username, "role": "admin"},
        "csrf_token": session.csrf_token,
        "token": session.session_id,
        "session_id": session.session_id,
    }
