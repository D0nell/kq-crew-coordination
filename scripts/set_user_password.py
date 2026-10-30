from pathlib import Path
import sys
from getpass import getpass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from argon2 import PasswordHasher

from api.db import fetch_one, get_conn


def main():
    email = input("Existing account email: ").strip()

    if not email:
        print("Email is required.")
        return

    with get_conn() as conn:
        user = fetch_one(
            conn,
            """
            SELECT user_id, full_name, email, role
            FROM users
            WHERE LOWER(email) = LOWER(%s)
            """,
            (email,),
        )

    if not user:
        print("No existing account matches that email. No changes made.")
        return

    print(f"\nAccount: {user['full_name']}")
    print(f"Role:    {user['role']}")
    print(f"Email:   {user['email']}")

    confirmation = input(
        "\nSet or reset the password for this account? Type YES to continue: "
    )
    if confirmation != "YES":
        print("Cancelled. No changes made.")
        return

    password = getpass("New password (minimum 12 characters): ")
    if len(password) < 12:
        print("Password must be at least 12 characters. No changes made.")
        return

    repeated = getpass("Enter the password again: ")
    if password != repeated:
        print("Passwords do not match. No changes made.")
        return

    password_hash = PasswordHasher().hash(password)

    with get_conn() as conn:
        updated = fetch_one(
            conn,
            """
            UPDATE users
            SET password_hash = %s
            WHERE user_id = %s
            RETURNING user_id, email, role
            """,
            (password_hash, user["user_id"]),
        )

    if updated:
        print(
            f"\nPassword set successfully for {updated['email']} "
            f"({updated['role']})."
        )
    else:
        print("Account was not updated. Please retry.")


if __name__ == "__main__":
    main()
