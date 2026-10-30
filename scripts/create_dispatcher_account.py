from pathlib import Path
import sys
from getpass import getpass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from argon2 import PasswordHasher
from api.db import fetch_one, get_conn


def main():
    full_name = input("Full name [Donell Bikketi]: ").strip()
    if not full_name:
        full_name = "Donell Bikketi"

    email = input("Email [donellbikketi@gmail.com]: ").strip()
    if not email:
        email = "donellbikketi@gmail.com"

    if "@" not in email or len(email) > 160:
        print("Please enter a valid email address.")
        return

    with get_conn() as conn:
        existing = fetch_one(
            conn,
            "SELECT user_id, full_name, email, role FROM users "
            "WHERE LOWER(email) = LOWER(%s)",
            (email,),
        )

    if existing:
        print(
            f"An account already exists for {existing['email']} "
            f"with role {existing['role']}. No account created."
        )
        print("Use scripts/set_user_password.py if you need to set its password.")
        return

    print("\nCreating a DISPATCHER account.")
    password = getpass("Choose a password (minimum 12 characters): ")
    if len(password) < 12:
        print("Password must contain at least 12 characters.")
        return

    repeated = getpass("Enter the password again: ")
    if password != repeated:
        print("Passwords do not match.")
        return

    password_hash = PasswordHasher().hash(password)

    with get_conn() as conn:
        user = fetch_one(
            conn,
            """
            INSERT INTO users (full_name, role, email, password_hash)
            VALUES (%s, 'DISPATCHER', %s, %s)
            RETURNING user_id, full_name, role, email
            """,
            (full_name, email, password_hash),
        )

    print("\nDispatcher account created successfully.")
    print(f"User ID: {user['user_id']}")
    print(f"Name:    {user['full_name']}")
    print(f"Role:    {user['role']}")
    print(f"Email:   {user['email']}")
    print("Your password was stored as a secure hash, not plain text.")


if __name__ == "__main__":
    main()
