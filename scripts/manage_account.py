"""Administrator tool: list accounts, grant a role, or link a crew account to a crew profile.

Run from the repository root with the virtual environment active:

    python scripts/manage_account.py list
    python scripts/manage_account.py role <email> DISPATCHER      (or CREW)
    python scripts/manage_account.py link <email> <crew_id>

Signing up with Google always creates a CREW account. This is the only way a
dispatcher account is created from a Google sign-up, so it stays under administrator control.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.db import fetch_all, get_conn  # noqa: E402

USAGE = __doc__


def main(argv) -> int:
    if not argv:
        print(USAGE)
        return 1
    command = argv[0]

    with get_conn() as conn:
        if command == "list" and len(argv) == 1:
            for u in fetch_all(conn, """
                SELECT u.user_id, u.email, u.role,
                       (u.google_sub IS NOT NULL) AS google,
                       (u.password_hash IS NOT NULL) AS password,
                       c.crew_id
                FROM users u LEFT JOIN crew_profiles c ON c.user_id = u.user_id
                ORDER BY u.user_id"""):
                print(u)
            return 0

        if command == "role" and len(argv) == 3 and argv[2].upper() in ("DISPATCHER", "CREW"):
            email, role = argv[1].strip().lower(), argv[2].upper()
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET role = %s WHERE LOWER(email) = %s", (role, email))
                if cur.rowcount == 0:
                    print(f"No account with email {email}.")
                    return 1
            print(f"{email} is now {role}.")
            return 0

        if command == "link" and len(argv) == 3 and argv[2].isdigit():
            email, crew_id = argv[1].strip().lower(), int(argv[2])
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM users WHERE LOWER(email) = %s", (email,))
                row = cur.fetchone()
                if row is None:
                    print(f"No account with email {email}.")
                    return 1
                cur.execute("SELECT 1 FROM crew_profiles WHERE crew_id = %s", (crew_id,))
                if cur.fetchone() is None:
                    print(f"No crew profile with crew_id {crew_id}.")
                    return 1
                cur.execute("UPDATE crew_profiles SET user_id = NULL WHERE user_id = %s", (row[0],))
                cur.execute("UPDATE crew_profiles SET user_id = %s WHERE crew_id = %s", (row[0], crew_id))
            print(f"{email} is now linked to crew_id {crew_id}.")
            return 0

    print(USAGE)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
