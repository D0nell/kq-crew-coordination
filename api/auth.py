from fastapi import HTTPException, Request
from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

from .db import fetch_one, get_conn

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password securely using Argon2."""
    if not password:
        raise ValueError("Password cannot be empty.")
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verify a password without exposing hash errors to callers."""
    if not password or not password_hash:
        return False

    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def authenticate_user(email: str, password: str):
    """Authenticate an existing account; public registration is not supported."""
    with get_conn() as conn:
        user = fetch_one(
            conn,
            """
            SELECT user_id, full_name, role, email, password_hash
            FROM users
            WHERE LOWER(email) = LOWER(%s)
            """,
            (email.strip(),),
        )

    if not user or not verify_password(password, user.get("password_hash")):
        return None

    # Never return a password hash to the application or browser.
    user.pop("password_hash", None)
    return user


def get_current_user(request: Request):
    """Load the current account from the database using its session ID."""
    user_id = request.session.get("user_id")

    if user_id is None:
        raise HTTPException(status_code=401, detail="Please log in.")

    with get_conn() as conn:
        user = fetch_one(
            conn,
            """
            SELECT user_id, full_name, role, email, phone
            FROM users
            WHERE user_id = %s
            """,
            (user_id,),
        )

    if not user:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Session is no longer valid.")

    return user


def require_dispatcher(request: Request):
    """Allow operational dashboard actions only for dispatcher accounts."""
    user = get_current_user(request)

    if user["role"] != "DISPATCHER":
        raise HTTPException(
            status_code=403,
            detail="Dispatcher access is required.",
        )

    return user



def require_crew(request: Request):
    """Allow the crew-facing mobile endpoints only for crew accounts."""
    user = get_current_user(request)

    if user["role"] != "CREW":
        raise HTTPException(
            status_code=403,
            detail="Crew access is required.",
        )

    return user