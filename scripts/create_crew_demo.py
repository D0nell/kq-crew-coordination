"""Create (or reset) a CREW account and link it to an existing crew profile.

Run from the repository root with the virtual environment active:

    python scripts/create_crew_demo.py <crew_id> <email> "<Full Name>"

The password is typed at a hidden prompt and stored only as an Argon2 hash.
"""

import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.auth import hash_password  # noqa: E402
from api.db import get_conn  # noqa: E402


def main() -> int:
    if len(sys.argv) != 4 or not sys.argv[1].isdigit():
        print('Usage: python scripts/create_crew_demo.py <crew_id> <email> "<Full Name>"')
        return 1

    crew_id, email, full_name = int(sys.argv[1]), sys.argv[2].strip().lower(), sys.argv[3].strip()
    password = getpass.getpass("Password (at least 8 characters): ")
    if len(password) < 8:
        print("Password is too short.")
        return 1

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM crew_profiles WHERE crew_id = %s", (crew_id,))
        if cur.fetchone() is None:
            print(f"No crew profile with crew_id {crew_id}.")
            return 1
        cur.execute(
            """
            INSERT INTO users (full_name, role, email, password_hash)
            VALUES (%s, 'CREW', %s, %s)
            ON CONFLICT (email) DO UPDATE
                SET role = 'CREW', full_name = EXCLUDED.full_name,
                    password_hash = EXCLUDED.password_hash
            RETURNING user_id
            """,
            (full_name, email, hash_password(password)),
        )
        user_id = cur.fetchone()[0]
        cur.execute("UPDATE crew_profiles SET user_id = NULL WHERE user_id = %s AND crew_id <> %s", (user_id, crew_id))
        cur.execute("UPDATE crew_profiles SET user_id = %s WHERE crew_id = %s", (user_id, crew_id))

    print(f"Crew account {email} (user_id {user_id}) is linked to crew_id {crew_id}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())