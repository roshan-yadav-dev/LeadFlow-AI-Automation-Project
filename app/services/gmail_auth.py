
import hashlib
import json
import logging
import os
import secrets
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from itsdangerous import (
    URLSafeTimedSerializer,
    BadSignature,
    SignatureExpired,
)

from app.core.config import settings

logger = logging.getLogger("leadflow")

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

STATE_SERIALIZER = URLSafeTimedSerializer(
    settings.WEBHOOK_SECRET,
    salt="leadflow-gmail-oauth"
)

STATE_DIR = Path("credentials/oauth_states")


def _state_file(state: str) -> Path:
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    return STATE_DIR / f"{state_hash}.json"


def create_oauth_url():
    flow = Flow.from_client_secrets_file(
        settings.GMAIL_CLIENT_SECRET_FILE,
        scopes=GMAIL_SCOPES,
        redirect_uri=settings.GMAIL_REDIRECT_URI,
        autogenerate_code_verifier=False,
    )

    # Generate and preserve the PKCE verifier.
    code_verifier = secrets.token_urlsafe(64)
    flow.code_verifier = code_verifier

    signed_state = STATE_SERIALIZER.dumps(
        secrets.token_urlsafe(32)
    )

    # Store the verifier server-side, not in the browser URL.
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_path = _state_file(signed_state)

    state_path.write_text(
        json.dumps({"code_verifier": code_verifier})
    )
    os.chmod(state_path, 0o600)

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=signed_state,
    )

    return authorization_url, signed_state


def complete_oauth(authorization_response: str, state: str):
    try:
        STATE_SERIALIZER.loads(state, max_age=600)
    except (BadSignature, SignatureExpired):
        raise ValueError("Invalid or expired OAuth state")

    state_path = _state_file(state)

    if not state_path.exists():
        raise ValueError("OAuth state expired or already used")

    try:
        state_data = json.loads(state_path.read_text())
        code_verifier = state_data["code_verifier"]
    finally:
        # A callback state can only be used once.
        state_path.unlink(missing_ok=True)

    flow = Flow.from_client_secrets_file(
        settings.GMAIL_CLIENT_SECRET_FILE,
        scopes=GMAIL_SCOPES,
        state=state,
        redirect_uri=settings.GMAIL_REDIRECT_URI,
        autogenerate_code_verifier=False,
    )

    # Restore the verifier from server-side storage.
    flow.code_verifier = code_verifier

    flow.fetch_token(
        authorization_response=authorization_response
    )

    credentials = flow.credentials

    token_path = Path(settings.GMAIL_TOKEN_FILE)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json())
    os.chmod(token_path, 0o600)

    logger.info("Gmail OAuth authorization completed")
    return credentials


def get_gmail_credentials():
    token_path = Path(settings.GMAIL_TOKEN_FILE)

    if not token_path.exists():
        raise RuntimeError(
            "Gmail is not connected. Authorize Gmail first."
        )

    credentials = Credentials.from_authorized_user_file(
        str(token_path),
        scopes=GMAIL_SCOPES,
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        token_path.write_text(credentials.to_json())
        os.chmod(token_path, 0o600)

    if not credentials.valid:
        raise RuntimeError(
            "Gmail credentials are invalid. Reauthorize Gmail."
        )

    return credentials


def is_gmail_connected():
    try:
        get_gmail_credentials()
        return True
    except Exception as exc:
        logger.warning(
            "Gmail connection check failed (%s)",
            type(exc).__name__,
        )
        return False
