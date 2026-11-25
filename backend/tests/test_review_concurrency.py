"""Exercise shared review notifications against PostgreSQL row locks."""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database import connect
from app.main import app
from app.workflows import service


@unittest.skipUnless(os.getenv("ACCOUNTING_INTEGRATION_TEST"), "requires a disposable test database")
class ReviewConcurrencyTest(unittest.TestCase):
    def test_two_admin_applicants_can_submit_in_parallel(self):
        password = "Integration-check-only"
        email_addresses = ("admin-first@example.test", "admin-second@example.test")
        with TestClient(app) as first, TestClient(app) as second:
            with connect() as connection:
                for email in email_addresses:
                    connection.execute(
                        "INSERT INTO employees(name,email,password_hash,roles) VALUES(%s,%s,%s,%s)",
                        ("行政驗證帳號", email, hash_password(password), ["admin", "employee"]),
                    )

            for client, email in zip((first, second), email_addresses):
                login = client.post("/api/auth/login", json={"email": email, "password": password})
                self.assertEqual(login.status_code, 200, login.text)

            ready = Barrier(2)
            notify = service.notify_reviewers

            def concurrently_notify(repository, request):
                ready.wait(timeout=5)
                return notify(repository, request)

            def submit(client):
                return client.post("/api/requests", json={
                    "kind": "profile_change", "details": {"phone": "02-0000-0000"},
                })

            with patch.object(service, "notify_reviewers", side_effect=concurrently_notify):
                with ThreadPoolExecutor(max_workers=2) as workers:
                    responses = list(workers.map(submit, (first, second)))

            for response in responses:
                self.assertEqual(response.status_code, 201, response.text)
            for client in (first, second):
                inbox = client.get("/api/notifications")
                self.assertTrue(any("待審個人資料修改" in item["message"] for item in inbox.json()))
