"""Integration checks using a dedicated, disposable PostgreSQL database."""
import os
import unittest
from datetime import date
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.main import app

PASSWORD = "Integration-check-only"
OFFICE_EMAIL = "owner@example.test"


@unittest.skipUnless(os.getenv("ACCOUNTING_INTEGRATION_TEST"), "requires a disposable test database")
class ApplicationTest(unittest.TestCase):
    def assert_status(self, response, status):
        self.assertEqual(response.status_code, status, response.text[:500])
        return response

    def login(self, client, email):
        return self.assert_status(client.post("/api/auth/login", json={
            "email": email, "password": PASSWORD,
        }), 200).json()

    def add_employee(self, owner, name, email, mail, supervisor_id=None):
        employee = self.assert_status(owner.post("/api/employees", json={
            "name": name, "email": email, "supervisor_id": supervisor_id,
        }), 201).json()
        if not mail.called:
            self.assert_status(owner.post(f"/api/employees/{employee['id']}/invite"), 204)
        token = mail.call_args.args[-1]
        mail.reset_mock()
        with TestClient(app) as employee_client:
            self.assert_status(employee_client.post("/api/auth/activate", json={
                "token": token, "password": PASSWORD,
            }), 204)
            self.assert_status(employee_client.post("/api/auth/activate", json={
                "token": token, "password": PASSWORD,
            }), 422)
        return employee

    @patch("app.core.service.SMTPMailer.send_link")
    def test_assignment_review_and_export(self, mail):
        with TestClient(app) as owner, TestClient(app) as staff, TestClient(app) as outsider:
            self.assert_status(outsider.get("/api/tasks"), 401)
            self.assert_status(outsider.post("/api/auth/logout", headers={"Origin": "https://outside.example"}), 403)
            self.assert_status(owner.get("/api/health"), 200)
            manager = self.login(owner, OFFICE_EMAIL)
            self.assert_status(owner.patch(f"/api/employees/{manager['id']}", json={
                "roles": ["owner", "manager", "admin", "employee"],
            }), 200)
            employee = self.add_employee(owner, "驗證員工", "staff@example.test", mail, manager["id"])
            other = self.add_employee(owner, "另一位員工", "other@example.test", mail, manager["id"])
            self.login(staff, employee["email"])
            self.login(outsider, other["email"])
            self.assert_status(staff.post("/api/employees", json={
                "name": "不允許新增", "email": "no@example.test",
            }), 403)
            company = self.assert_status(owner.post("/api/clients", json={
                "name": "廊橋製造", "assignee_ids": [employee["id"]],
            }), 201).json()
            expense = {
                "kind": "expense",
                "details": {"client_id": company["id"], "date": "2026-12-08", "amount": 120, "purpose": "交通"},
            }
            self.assert_status(outsider.post("/api/requests", json=expense), 422)
            self.assert_status(staff.post("/api/requests", json=expense), 201)
            task = self.assert_status(owner.post("/api/tasks", json={
                "title": "核對進項憑證", "description": "比對發票與總帳",
                "client_id": company["id"], "assignee_id": employee["id"],
            }), 201).json()
            self.assertEqual(self.assert_status(staff.get("/api/tasks"), 200).json()[0]["id"], task["id"])
            self.assertEqual(self.assert_status(outsider.get("/api/tasks"), 200).json(), [])
            self.assert_status(staff.patch(f"/api/tasks/{task['id']}", json={"status": "in_progress"}), 200)
            self.assertTrue(self.assert_status(staff.get("/api/notifications"), 200).json())

            events = self.assert_status(staff.get("/api/calendar?month=2026-12"), 200).json()
            self.assertTrue(any(event["title"] == "行憲紀念日" for event in events))
            request = self.assert_status(staff.post("/api/requests", json={
                "kind": "outing", "details": {
                    "start_at": "2026-12-08T10:00:00+08:00", "end_at": "2026-12-08T11:00:00+08:00",
                    "reason": "查閱憑證",
                },
            }), 201).json()
            request_path = f"/api/requests/{request['id']}"
            self.assert_status(staff.post(request_path + "/approve", json={}), 403)
            self.assert_status(owner.post(request_path + "/approve", json={}), 200)
            public_events = self.assert_status(outsider.get("/api/calendar?month=2026-12"), 200).json()
            self.assertTrue(any(event["category"] == "personnel" for event in public_events))
            self.assertNotIn("查閱憑證", str(public_events))

            leave_type = self.assert_status(owner.post("/api/leave-types", json={
                "name": "特休", "requires_balance": True,
            }), 201).json()
            self.assert_status(owner.put("/api/leave-balances", json={
                "employee_id": employee["id"], "leave_type_id": leave_type["id"], "total_minutes": 60,
            }), 200)
            leave_payload = {"kind": "leave", "details": {
                "start_at": "2026-12-08T13:00:00+08:00", "end_at": "2026-12-08T14:00:00+08:00",
                "leave_type_id": leave_type["id"],
            }}
            leave = self.assert_status(staff.post("/api/requests", json=leave_payload), 201).json()
            self.assert_status(staff.post("/api/requests", json=leave_payload), 409)
            leave_path = f"/api/requests/{leave['id']}"
            self.assert_status(owner.post(leave_path + "/approve"), 200)
            cancellation = self.assert_status(staff.post(leave_path + "/cancel"), 200).json()
            self.assert_status(owner.post(f"/api/requests/{cancellation['id']}/approve"), 200)
            self.assert_status(staff.post("/api/requests", json=leave_payload), 201)

            self.assert_status(staff.post("/api/attendance/clock", json={"action": "in"}), 200)
            day = date(2026, 12, 8).isoformat()
            export = self.assert_status(owner.get("/api/reports/export", params={
                "start": day, "end": day,
            }), 200)
            self.assertTrue(load_workbook(BytesIO(export.content), read_only=True).sheetnames)
            period = {"start": day, "end": day, "employee_id": employee["id"]}
            version_one = self.assert_status(owner.post("/api/reports/finalize", json=period), 201).json()
            version_two = self.assert_status(owner.post("/api/reports/finalize", json=period), 201).json()
            self.assertEqual(version_two["version"], version_one["version"] + 1)
            v2_path = f"/api/reports/{version_two['id']}/download"
            v2_file = self.assert_status(owner.get(v2_path), 200).content
            unchanged = self.assert_status(owner.post("/api/reports/export", json=period), 200)
            self.assertEqual(unchanged.content, v2_file)
            revisions = self.assert_status(owner.get("/api/reports", params=period), 200).json()["versions"]
            self.assertEqual(len(revisions), 2)
            correction = self.assert_status(staff.post("/api/requests", json={
                "kind": "outing", "details": {
                    "start_at": "2026-12-08T15:00:00+08:00",
                    "end_at": "2026-12-08T16:00:00+08:00",
                },
            }), 201).json()
            self.assert_status(owner.post(f"/api/requests/{correction['id']}/approve"), 200)
            self.assert_status(owner.get("/api/reports/export", params=period), 200)
            self.assertEqual(len(self.assert_status(owner.get("/api/reports", params=period), 200).json()["versions"]), 2)
            revised = self.assert_status(owner.post("/api/reports/export", json=period), 200)
            revisions = self.assert_status(owner.get("/api/reports", params=period), 200).json()["versions"]
            self.assertEqual([item["version"] for item in revisions], [3, 2, 1])
            self.assertNotEqual(revised.content, v2_file)
            self.assertEqual(self.assert_status(owner.get(v2_path), 200).content, v2_file)
            self.assertEqual(
                self.assert_status(owner.post("/api/reports/export", json=period), 200).content,
                revised.content,
            )
            history_path = f"/api/reports/{version_one['id']}/download"
            self.assert_status(staff.get(history_path), 403)
            self.assert_status(owner.get(history_path), 200)
            self.assert_status(owner.patch(f"/api/employees/{employee['id']}", json={"active": False}), 200)
            self.assert_status(staff.get("/api/auth/me"), 401)
