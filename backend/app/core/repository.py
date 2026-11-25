from pathlib import Path

from psycopg import sql
from psycopg.types.json import Jsonb

EMPLOYEE_PUBLIC = "id, name, email, roles, supervisor_id, active, started_on, inactive_on, phone, address, emergency_contact"
TASK_DETAILS = """
    SELECT t.*, c.name AS client_name, e.name AS assignee_name,
           e.supervisor_id AS assignee_supervisor_id
    FROM tasks t JOIN clients c ON c.id=t.client_id JOIN employees e ON e.id=t.assignee_id
"""
CLIENT_DETAILS = """
    SELECT c.*, ARRAY(
        SELECT a.employee_id FROM client_assignees a
        WHERE a.client_id=c.id ORDER BY a.employee_id
    ) AS assignee_ids, ARRAY(
        SELECT e.name FROM client_assignees a JOIN employees e ON e.id=a.employee_id
        WHERE a.client_id=c.id ORDER BY a.employee_id
    ) AS assignee_names FROM clients c
"""


def setup(conn):
    conn.execute(Path(__file__).with_name("schema.sql").read_text())


def get_employee(conn, employee_id, *, lock=False):
    query = f"SELECT {EMPLOYEE_PUBLIC} FROM employees WHERE id=%s"
    return conn.execute(query + (" FOR NO KEY UPDATE" if lock else ""), (employee_id,)).fetchone()


def get_employee_by_email(conn, email, *, lock=False):
    query = f"SELECT {EMPLOYEE_PUBLIC}, password_hash FROM employees WHERE email=%s"
    return conn.execute(query + (" FOR NO KEY UPDATE" if lock else ""), (email,)).fetchone()


def get_employees(conn):
    return conn.execute(f"SELECT {EMPLOYEE_PUBLIC} FROM employees ORDER BY name, id").fetchall()


def insert(conn, table, values):
    query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, values)),
        sql.SQL(", ").join(sql.Placeholder() for _ in values),
    )
    result = conn.execute(query + sql.SQL(" RETURNING id"), tuple(values.values())).fetchone()
    return result["id"]


def patch(conn, table, record_id, values):
    if not values:
        return
    assignments = sql.SQL(", ").join(
        sql.SQL("{}={}").format(sql.Identifier(column), sql.Placeholder()) for column in values
    )
    query = sql.SQL("UPDATE {} SET {} WHERE id=%s").format(sql.Identifier(table), assignments)
    conn.execute(query, (*values.values(), record_id))


def manager_hierarchy_lock(conn):
    conn.execute("SELECT pg_advisory_xact_lock(83020201)")


def get_session_employee(conn, digest):
    return conn.execute(
        """SELECT e.id,e.name,e.email,e.roles,e.supervisor_id,e.active
           FROM sessions s JOIN employees e ON e.id=s.employee_id
           WHERE s.digest=%s AND s.expires_at>now() AND e.active""",
        (digest,),
    ).fetchone()


def create_session(conn, employee_id, digest):
    conn.execute("DELETE FROM sessions WHERE employee_id=%s AND expires_at<=now()", (employee_id,))
    conn.execute(
        """INSERT INTO sessions(digest,employee_id,expires_at)
           VALUES(%s,%s,now()+interval '12 hours')""",
        (digest, employee_id),
    )


def delete_session(conn, digest):
    conn.execute("DELETE FROM sessions WHERE digest=%s", (digest,))


def revoke_credentials(conn, employee_id):
    conn.execute("DELETE FROM sessions WHERE employee_id=%s", (employee_id,))
    conn.execute("DELETE FROM account_tokens WHERE employee_id=%s", (employee_id,))


def issue_token(conn, employee_id, purpose, digest, valid_hours):
    conn.execute(
        "DELETE FROM account_tokens WHERE employee_id=%s AND purpose=%s", (employee_id, purpose)
    )
    conn.execute(
        """INSERT INTO account_tokens(digest,employee_id,purpose,expires_at)
           VALUES(%s,%s,%s,now()+%s*interval '1 hour')""",
        (digest, employee_id, purpose, valid_hours),
    )


def get_token_employee(conn, digest, purpose):
    return conn.execute(
        """SELECT employee_id FROM account_tokens
           WHERE digest=%s AND purpose=%s AND expires_at>now()""",
        (digest, purpose),
    ).fetchone()


def consume_token(conn, digest, purpose):
    return conn.execute(
        """DELETE FROM account_tokens WHERE digest=%s AND purpose=%s AND expires_at>now()
           RETURNING employee_id""",
        (digest, purpose),
    ).fetchone()


def lock_client(conn, client_id):
    return conn.execute("SELECT id FROM clients WHERE id=%s FOR UPDATE", (client_id,)).fetchone()


def get_client(conn, client_id):
    return conn.execute(CLIENT_DETAILS + " WHERE c.id=%s", (client_id,)).fetchone()


def get_clients(conn):
    return conn.execute(CLIENT_DETAILS + " ORDER BY c.name,c.id").fetchall()


def set_client_assignees(conn, client_id, assignee_ids):
    conn.execute("DELETE FROM client_assignees WHERE client_id=%s", (client_id,))
    with conn.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO client_assignees(client_id,employee_id) VALUES(%s,%s)",
            [(client_id, employee_id) for employee_id in assignee_ids],
        )


def get_task(conn, task_id, *, lock=False):
    query = TASK_DETAILS + " WHERE t.id=%s" + (" FOR UPDATE OF t" if lock else "")
    return conn.execute(query, (task_id,)).fetchone()


def get_tasks(conn):
    return conn.execute(TASK_DETAILS + " ORDER BY t.due_on NULLS LAST,t.id DESC").fetchall()


def task_history(conn, task_id):
    return conn.execute(
        """SELECT h.*,e.name AS actor_name FROM task_history h
           JOIN employees e ON e.id=h.actor_id
           WHERE h.task_id=%s ORDER BY h.id DESC""",
        (task_id,),
    ).fetchall()


def log_task(conn, task_id, actor_id, action, changes):
    insert(conn, "task_history", {
        "task_id": task_id, "actor_id": actor_id, "action": action, "changes": Jsonb(changes)
    })


def notify(conn, employee_id, message):
    insert(conn, "notifications", {"employee_id": employee_id, "message": message})


def get_notifications(conn, employee_id):
    return conn.execute(
        """SELECT id,message,created_at,read_at FROM notifications
           WHERE employee_id=%s ORDER BY id DESC""",
        (employee_id,),
    ).fetchall()


def read_notification(conn, employee_id, notification_id):
    return conn.execute(
        """UPDATE notifications SET read_at=COALESCE(read_at,now())
           WHERE id=%s AND employee_id=%s RETURNING id,message,created_at,read_at""",
        (notification_id, employee_id),
    ).fetchone()


def employee_handoff(conn, employee_id):
    return {
        "tasks": conn.execute(
            """SELECT id,title,status FROM tasks
               WHERE assignee_id=%s AND status IN ('pending','in_progress') ORDER BY id""",
            (employee_id,),
        ).fetchall(),
        "direct_reports": conn.execute(
            "SELECT id,name,active FROM employees WHERE supervisor_id=%s ORDER BY name", (employee_id,)
        ).fetchall(),
    }
