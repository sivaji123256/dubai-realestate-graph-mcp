"""
One-off CLI to bootstrap the first admin account (or any account).

Usage:
    python webapp/create_admin.py <email> <name> <password> [role]

role defaults to "admin". Run this once against your Neo4j instance to
create the first login -- after that, admins can add reps from the Team
panel in the app itself.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)  # webapp/ itself, for user_store
sys.path.insert(0, os.path.join(_HERE, ".."))  # project root, for neo4j_client (loads .env itself)

from user_store import create_user, get_user  # noqa: E402


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)

    email, name, password = sys.argv[1], sys.argv[2], sys.argv[3]
    role = sys.argv[4] if len(sys.argv) > 4 else "admin"

    if get_user(email):
        print(f"A user with email {email} already exists -- nothing to do.")
        sys.exit(1)

    user = create_user(email, name, password, role)
    print(f"Created {user['role']} account: {user['email']} ({user['name']})")


if __name__ == "__main__":
    main()
