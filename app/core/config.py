
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    PROJECT_NAME = os.getenv("PROJECT_NAME", "LeadFlow AI")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

    # AI Provider Configuration
    AI_PROVIDER = os.getenv("AI_PROVIDER", "groq").lower()

    # Gemini AI Configuration (Fallback / Optional)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    GEMINI_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "30000"))

    # Groq AI Configuration
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    GROQ_TIMEOUT = int(os.getenv("GROQ_TIMEOUT", "30000"))
    GROQ_MAX_RETRIES = int(os.getenv("GROQ_MAX_RETRIES", "2"))
    GROQ_MAX_COMPLETION_TOKENS = int(os.getenv("GROQ_MAX_COMPLETION_TOKENS", "2048"))

    # Google Sheets Configuration
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
    GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        "credentials/service-account.json"
    )

    # Insecure default passwords strictly forbidden in production
    INSECURE_DEFAULT_PASSWORDS = frozenset({
        "admin123",
        "LeadFlow2026!Secure",
        "admin",
        "password",
        "changeme",
        "12345678",
    })

    # Security Configuration
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

    def validate(self_or_cls):
        target = self_or_cls
        required = [
            "GOOGLE_SHEET_ID",
            "WEBHOOK_SECRET",
        ]

        if target.AI_PROVIDER == "groq":
            required.append("GROQ_API_KEY")
        elif target.AI_PROVIDER == "gemini":
            required.append("GEMINI_API_KEY")
        else:
            raise RuntimeError(
                f"Unsupported AI provider: {target.AI_PROVIDER}"
            )

        missing = [
            key for key in required
            if not getattr(target, key, None)
        ]

        if missing:
            raise RuntimeError(
                f"Missing environment variables: {', '.join(missing)}"
            )

        # Enforce Production Credential Hardening
        env = (getattr(target, "ENVIRONMENT", None) or os.getenv("ENVIRONMENT") or "").lower()
        if env in ("production", "prod"):
            pwd_hash = getattr(target, "DASHBOARD_PASSWORD_HASH", None) or os.getenv("DASHBOARD_PASSWORD_HASH")
            if not pwd_hash:
                env_password = getattr(target, "DASHBOARD_PASSWORD", None) or os.getenv("DASHBOARD_PASSWORD")
                if not env_password or env_password in target.INSECURE_DEFAULT_PASSWORDS:
                    raise RuntimeError(
                        "In production, DASHBOARD_PASSWORD must be explicitly configured with a secure non-default password, or DASHBOARD_PASSWORD_HASH must be provided."
                    )
            default_session_secret = "leadflow-dashboard-secure-session-key-32-chars-min"
            session_secret = getattr(target, "SESSION_SECRET_KEY", None) or os.getenv("SESSION_SECRET_KEY")
            if session_secret == default_session_secret and not os.getenv("SESSION_SECRET_KEY"):
                raise RuntimeError(
                    "In production, SESSION_SECRET_KEY must be explicitly configured with a high-entropy secret key."
                )

    # Gmail OAuth Configuration
    GMAIL_CLIENT_SECRET_FILE = os.getenv(
        "GMAIL_CLIENT_SECRET_FILE",
        "credentials/gmail_oauth_client.json"
    )

    GMAIL_TOKEN_FILE = os.getenv(
        "GMAIL_TOKEN_FILE",
        "credentials/gmail_token.json"
    )

    GMAIL_REDIRECT_URI = os.getenv(
        "GMAIL_REDIRECT_URI",
        "http://localhost:8001/api/v1/gmail/oauth/callback"
    )

    GMAIL_SENDER_EMAIL = os.getenv("GMAIL_SENDER_EMAIL")
    GMAIL_SYNC_ENABLED = os.getenv(
        "GMAIL_SYNC_ENABLED", "false"
    ).lower() == "true"
    GMAIL_SYNC_INTERVAL_SECONDS = int(
        os.getenv("GMAIL_SYNC_INTERVAL_SECONDS", "300")
    )
    GMAIL_SYNC_BATCH_SIZE = int(
        os.getenv("GMAIL_SYNC_BATCH_SIZE", "50")
    )
    GMAIL_SYNC_MAX_PAGES = int(
        os.getenv("GMAIL_SYNC_MAX_PAGES", "5")
    )
    GMAIL_DB_FILE = os.getenv(
        "GMAIL_DB_FILE",
        "credentials/gmail_inbox.sqlite3"
    )
    GMAIL_INTELLIGENCE_DB_FILE = os.getenv(
        "GMAIL_INTELLIGENCE_DB_FILE",
        "credentials/gmail_intelligence.sqlite3"
    )
    GMAIL_INTELLIGENCE_BATCH_SIZE = int(
        os.getenv("GMAIL_INTELLIGENCE_BATCH_SIZE", "20")
    )
    GMAIL_INTELLIGENCE_MAX_BATCH_SIZE = int(
        os.getenv("GMAIL_INTELLIGENCE_MAX_BATCH_SIZE", "100")
    )
    GMAIL_INTELLIGENCE_MAX_BODY_CHARS = int(
        os.getenv("GMAIL_INTELLIGENCE_MAX_BODY_CHARS", "12000")
    )

    # Automation Configuration
    AUTOMATION_DB_FILE = os.getenv(
        "AUTOMATION_DB_FILE",
        "credentials/automation.sqlite3"
    )
    AUTOMATION_WORKER_ENABLED = os.getenv(
        "AUTOMATION_WORKER_ENABLED", "true"
    ).lower() == "true"
    AUTOMATION_WORKER_POLL_INTERVAL_SECONDS = int(
        os.getenv("AUTOMATION_WORKER_POLL_INTERVAL_SECONDS", "10")
    )
    AUTOMATION_DEFAULT_TIMEZONE = os.getenv(
        "AUTOMATION_DEFAULT_TIMEZONE", "Asia/Kolkata"
    )

    # Admin Notification Configuration
    ADMIN_NOTIFICATION_EMAIL = os.getenv("ADMIN_NOTIFICATION_EMAIL", "").strip() or None

    # Dashboard & Frontend Configuration
    DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", "admin")
    DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "LeadFlow2026!Secure")
    DASHBOARD_PASSWORD_HASH = os.getenv("DASHBOARD_PASSWORD_HASH", None)
    SESSION_SECRET_KEY = os.getenv(
        "SESSION_SECRET_KEY",
        os.getenv("WEBHOOK_SECRET", "leadflow-dashboard-secure-session-key-32-chars-min")
    )
    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "leadflow_session")
    SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_SECONDS", "86400"))
    TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"
    CORS_ORIGINS = [
        orig.strip()
        for orig in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000",
        ).split(",")
        if orig.strip()
    ]
    CORS_ORIGIN_REGEX = os.getenv(
        "CORS_ORIGIN_REGEX",
        r"https?://.*(onrender\.com|vercel\.app|netlify\.app|localhost|127\.0\.0\.1)(:\d+)?",
    )
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

settings = Settings()
