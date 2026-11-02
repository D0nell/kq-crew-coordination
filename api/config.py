"""Runtime settings, read from environment variables (and a .env file in the repo root)."""

import os

from dotenv import load_dotenv

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(_ROOT, ".env"))

DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/kq_crew_coordination"


def get_database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_model_path() -> str:
    return os.environ.get("MODEL_PATH", os.path.join(_ROOT, "models", "xgb_final_v1.pkl"))


def get_alert_threshold() -> float:
    """A transit raises an alert when P(delayed) is at or above this value (FR-05)."""
    return float(os.environ.get("ALERT_THRESHOLD", "0.5"))

def get_session_secret() -> str:
    """Return the session signing secret."""
    secret = os.environ.get("SESSION_SECRET")

    if secret:
        if secret == "local-development-only-change-me":
            raise RuntimeError("SESSION_SECRET must not use the development fallback.")
        return secret

    if os.environ.get("APP_ENV", "development").lower() == "production":
        raise RuntimeError("SESSION_SECRET must be set in production.")

    # Local development only; set a private secret in .env before deployment.
    return "local-development-only-change-me"


def session_https_only() -> bool:
    """Require HTTPS for session cookies in production."""
    return os.environ.get("APP_ENV", "development").lower() == "production"
