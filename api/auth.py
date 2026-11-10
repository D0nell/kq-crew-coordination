from google.auth.exceptions import TransportError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from .config import get_google_client_ids
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



# --------------------------------------------------------------------------
# Google sign-in. The browser or Android app sends Google's signed ID token;
# the server checks it, so a user cannot claim to be someone else.
class GoogleNotConfigured(Exception):
    """No GOOGLE_CLIENT_ID is set on this server."""


class GoogleSignInError(Exception):
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


def verify_google_credential(credential: str) -> dict:
    """Return the verified claims of a Google ID token, or raise GoogleSignInError."""
    client_ids = get_google_client_ids()
    if not client_ids:
        raise GoogleNotConfigured()

    try:
        claims = google_id_token.verify_oauth2_token(
            credential, google_requests.Request(), audience=None
        )
    except TransportError as exc:
        raise GoogleSignInError("Could not reach Google to check the sign-in. Try again.", 503) from exc
    except ValueError as exc:
        raise GoogleSignInError("Google sign-in could not be verified.") from exc

    if claims.get("aud") not in client_ids:
        raise GoogleSignInError("Google sign-in could not be verified.")
    if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise GoogleSignInError("Google sign-in could not be verified.")
    if not claims.get("email_verified") or not claims.get("email") or not claims.get("sub"):
        raise GoogleSignInError("Your Google email address is not verified.")
    return claims


def sign_in_with_google(claims: dict):
    """Find the account for these claims, or create a CREW account (sign-up).

    Returns (user, created). New accounts are always CREW: dispatcher access is
    granted later by an administrator and is never given by signing up.
    """
    sub = str(claims["sub"])
    email = claims["email"].strip().lower()
    name = (claims.get("name") or email.split("@")[0]).strip()[:120]
    columns = "user_id, full_name, role, email"

    with get_conn() as conn:
        user = fetch_one(conn, f"SELECT {columns} FROM users WHERE google_sub = %s", (sub,))
        if user:
            return user, False

        user = fetch_one(
            conn,
            f"SELECT {columns}, google_sub FROM users WHERE LOWER(email) = %s",
            (email,),
        )
        if user:
            if user.pop("google_sub", None):
                raise GoogleSignInError("This email is already linked to a different Google account.", 403)
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET google_sub = %s WHERE user_id = %s", (sub, user["user_id"]))
            return user, False

        user = fetch_one(
            conn,
            f"INSERT INTO users (full_name, role, email, google_sub) "
            f"VALUES (%s, 'CREW', %s, %s) RETURNING {columns}",
            (name, email, sub),
        )
        return user, True