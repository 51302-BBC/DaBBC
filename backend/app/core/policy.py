ROLES = frozenset({"owner", "manager", "admin", "employee"})
PROTECTED_TASK_STATUSES = frozenset({"completed", "canceled"})
TASK_TRANSITION_POLICIES = frozenset({"owner", "creator", "assignee"})


def has_role(actor, *roles):
    return bool(set(actor["roles"]).intersection(roles))


def can_assign(actor, assignee, client_assignees):
    if not assignee["active"] or assignee["id"] not in client_assignees:
        return False
    return (
        has_role(actor, "owner", "admin")
        or has_role(actor, "manager") and assignee["supervisor_id"] == actor["id"]
    )


def can_view_task(actor, task):
    return (
        has_role(actor, "owner")
        or actor["id"] in {task["assignee_id"], task["created_by"]}
        or has_role(actor, "manager") and task["assignee_supervisor_id"] == actor["id"]
    )


def can_manage_task(actor, task):
    return has_role(actor, "owner") or (
        has_role(actor, "manager", "admin") and task["created_by"] == actor["id"]
    )


def can_update_task_status(actor, task, status):
    return (
        status in {"pending", "in_progress", "completed"}
        and task.get("status") not in PROTECTED_TASK_STATUSES
        and (actor["id"] == task["assignee_id"] or has_role(actor, "owner"))
    )


def matches_transition_policy(actor, task, policy):
    if policy == "owner":
        return has_role(actor, "owner")
    if policy == "creator":
        return actor["id"] == task["created_by"]
    return policy == "assignee" and actor["id"] == task["assignee_id"]


def can_cancel_task(actor, task, policy):
    return task["status"] not in PROTECTED_TASK_STATUSES and matches_transition_policy(actor, task, policy)


def can_reopen_task(actor, task, policy):
    return task["status"] in PROTECTED_TASK_STATUSES and matches_transition_policy(actor, task, policy)
