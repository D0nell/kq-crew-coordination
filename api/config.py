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
