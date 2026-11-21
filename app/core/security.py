
import secrets
from fastapi import Header, HTTPException, Request, status

from app.core.config import settings
from app.core.dashboard_auth import dashboard_auth


async def verify_webhook_secret(
    request: Request,
    x_webhook_secret: str | None = Header(default=None),
):
    # 1. Direct Webhook Authentication via Header
    if x_webhook_secret is not None:
        expected_secret = settings.WEBHOOK_SECRET

        if not expected_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Webhook authentication is not configured",
            )

        if not secrets.compare_digest(x_webhook_secret, expected_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook credentials",
            )

        return True

    # 2. Secure Dashboard Session Authentication via HttpOnly Cookie
    session = dashboard_auth.get_session_from_request(request)
    if session is not None:
        # Enforce CSRF protection on state-changing operations
        if request.method in ("POST", "PATCH", "DELETE", "PUT"):
            csrf_token = request.headers.get("X-CSRF-Token")
            if not csrf_token or not secrets.compare_digest(csrf_token, session.csrf_token):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid or missing CSRF token",
                )
        return True

    # Neither valid webhook header nor active session cookie
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid webhook credentials",
    )
