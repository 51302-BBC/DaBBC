"""Create four explicitly local demo accounts and return their login credentials."""

import json
import secrets
from os import getenv
from urllib.parse import urlsplit

from app.core import repository
from app.core.security import hash_password
from app.database import connect

ACCOUNTS = (
    ("owner", "測試老闆"),
    ("manager", "測試主管"),
    ("employee", "測試員工"),
    ("admin", "測試行政"),
)


def main():
    url = urlsplit(getenv("APP_BASE_URL", "http://localhost:8080"))
    if url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("Demo accounts require a loopback application URL.")
    records = []
    supervisor_id = None
    with connect() as connection:
        repository.manager_hierarchy_lock(connection)
        for role, name in ACCOUNTS:
            email = f"demo-{role}@example.test"
            if repository.get_employee_by_email(connection, email):
                raise SystemExit("Demo account already exists. Existing passwords were preserved.")
            password = secrets.token_urlsafe(24)
            employee_id = repository.insert(connection, "employees", {
                "name": name,
                "email": email,
                "password_hash": hash_password(password),
                "roles": [role],
                "supervisor_id": supervisor_id if role == "employee" else None,
            })
            if role == "manager":
                supervisor_id = employee_id
            records.append({"role": role, "email": email, "password": password})
    print(json.dumps(records))


if __name__ == "__main__":
    main()
