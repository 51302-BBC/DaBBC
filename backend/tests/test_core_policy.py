import unittest

from app.core.policy import can_assign, can_cancel_task, can_reopen_task, can_view_task, can_update_task_status
from app.core.security import hash_password, verify_password


class CorePolicyTests(unittest.TestCase):
    def setUp(self):
        self.manager = {"id": 1, "roles": ["manager", "employee"]}
        self.admin = {"id": 2, "roles": ["admin"]}
        self.member = {"id": 3, "supervisor_id": 1, "active": True}
        self.outsider = {"id": 4, "supervisor_id": 9, "active": True}
        self.task = {"assignee_id": 3, "created_by": 2, "assignee_supervisor_id": 1}

    def test_manager_scope_and_client_assignment(self):
        self.assertTrue(can_assign(self.manager, self.member, {3}))
        self.assertFalse(can_assign(self.manager, self.member, {4}))
        self.assertFalse(can_assign(self.manager, self.outsider, {4}))
        self.assertTrue(can_view_task(self.manager, self.task))

    def test_admin_can_dispatch_to_client_assignees(self):
        self.assertTrue(can_assign(self.admin, self.outsider, {4}))
        self.assertFalse(can_assign(self.admin, self.outsider, {3}))
        self.assertTrue(can_view_task(self.admin, self.task))
        self.assertFalse(can_update_task_status(self.admin, self.task, "completed"))

    def test_member_can_complete_own_work(self):
        self.assertTrue(can_update_task_status({"id": 3, "roles": ["employee"]}, self.task, "completed"))
        self.assertFalse(can_update_task_status({"id": 3, "roles": ["employee"]}, self.task, "canceled"))

    def test_cancellation_requires_configured_policy_and_nonterminal_state(self):
        assignee = {"id": 3, "roles": ["employee"]}
        owner = {"id": 9, "roles": ["owner"]}
        task = {**self.task, "status": "in_progress"}
        self.assertFalse(can_cancel_task(owner, task, None))
        self.assertTrue(can_cancel_task(owner, task, "owner"))
        self.assertFalse(can_cancel_task(owner, task, "creator"))
        self.assertTrue(can_cancel_task(assignee, task, "assignee"))
        self.assertFalse(can_cancel_task(assignee, {**task, "status": "completed"}, "assignee"))

    def test_reopening_requires_configured_policy_and_terminal_state(self):
        creator = {"id": 2, "roles": ["employee"]}
        task = {**self.task, "status": "completed"}
        self.assertFalse(can_reopen_task(creator, task, None))
        self.assertTrue(can_reopen_task(creator, task, "creator"))
        self.assertFalse(can_reopen_task(creator, task, "assignee"))
        self.assertFalse(can_reopen_task(creator, {**task, "status": "pending"}, "creator"))

    def test_password_salt_and_verification(self):
        encoded = hash_password("Safe-long-password123")
        self.assertNotEqual(encoded, hash_password("Safe-long-password123"))
        self.assertTrue(verify_password("Safe-long-password123", encoded))
        self.assertFalse(verify_password("Incorrect-password123", encoded))
        self.assertFalse(verify_password("Bad", "scrypt:invalid:invalid"))
