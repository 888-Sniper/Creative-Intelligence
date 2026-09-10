"""Seed an isolated E2E database (test infrastructure only, never production).

Creates an active admin, an active employee, and a pending employee, each
with a live session token, and writes the raw tokens to a JSON file for
Playwright to plant as session cookies. Usage:
    python3 e2e/seed.py <db_path> <seeds_json_path>
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "Backend"))

from ci_backend import employees as emp
from ci_backend.db import (ensure_migrated, make_engine,  # noqa: E402
                           make_session_factory)


def main() -> None:
    db_path, seeds_path = sys.argv[1], sys.argv[2]
    container = sys.argv[3] if len(sys.argv) > 3 else ""
    engine = make_engine(db_path)
    ensure_migrated(engine)
    factory = make_session_factory(engine)
    with factory() as sess:
        admin = emp.admin_create(sess, "root", "boss@foap.test",
                                 first_name="Boss", last_name="Admin",
                                 role="admin")
        employee = emp.admin_create(sess, admin.id, "ada@foap.test",
                                    first_name="Ada", last_name="L",
                                    role="employee")
        pending, _ = emp.ensure_identity(sess, {
            "email": "pip@foap.test", "verified": True,
            "workos_user_id": "w-pip", "first_name": "Pip",
            "last_name": "Pending", "avatar_url": ""})
        assert pending.status == "pending", pending.status
        seeds = {
            "admin": emp.create_session(sess, admin.id, "", container),
            "employee": emp.create_session(sess, employee.id, "", container),
            "pending": emp.create_session(sess, pending.id, "w-pip",
                                           container),
        }
    with open(seeds_path, "w") as fh:
        json.dump(seeds, fh)
    print("seeded %s" % db_path)


if __name__ == "__main__":
    main()
