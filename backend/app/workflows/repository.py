from psycopg.types.json import Jsonb

SCHEMA = """
CREATE TABLE IF NOT EXISTS wf_schedule (
    id boolean PRIMARY KEY DEFAULT true CHECK(id),
    weekdays integer[] NOT NULL,
    start_time time NOT NULL,
    end_time time NOT NULL,
    break_minutes integer NOT NULL CHECK (break_minutes >= 0)
);
CREATE TABLE IF NOT EXISTS wf_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date date NOT NULL,
    title text NOT NULL,
    category text NOT NULL CHECK (category IN ('holiday','meeting')),
    workday_override boolean
);
CREATE INDEX IF NOT EXISTS wf_events_date_idx ON wf_events (date);
CREATE TABLE IF NOT EXISTS wf_clock (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id bigint NOT NULL REFERENCES employees(id),
    date date NOT NULL,
    direction text NOT NULL CHECK (direction IN ('in','out')),
    recorded_at timestamptz NOT NULL,
    correction_id bigint,
    CHECK (direction IN ('in','out'))
);
CREATE UNIQUE INDEX IF NOT EXISTS wf_clock_original_idx ON wf_clock(employee_id,date,direction)
    WHERE correction_id IS NULL;
CREATE INDEX IF NOT EXISTS wf_clock_employee_date_idx ON wf_clock(employee_id,date,id);
CREATE TABLE IF NOT EXISTS wf_leave_types (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE,
    requires_balance boolean NOT NULL
);
CREATE TABLE IF NOT EXISTS wf_leave_balances (
    employee_id bigint NOT NULL REFERENCES employees(id),
    leave_type_id bigint NOT NULL REFERENCES wf_leave_types(id),
    total_minutes integer NOT NULL CHECK(total_minutes >= 0),
    PRIMARY KEY(employee_id,leave_type_id)
);
CREATE TABLE IF NOT EXISTS wf_overtime_targets (
    employee_id bigint PRIMARY KEY REFERENCES employees(id),
    minutes integer NOT NULL CHECK(minutes >= 0)
);
CREATE TABLE IF NOT EXISTS wf_delegates (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    supervisor_id bigint REFERENCES employees(id),
    reviewer_id bigint NOT NULL REFERENCES employees(id),
    start date NOT NULL,
    "end" date NOT NULL,
    CHECK (start <= "end")
);
CREATE TABLE IF NOT EXISTS wf_requests (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id bigint NOT NULL REFERENCES employees(id),
    kind text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    reviewer_id bigint REFERENCES employees(id),
    manually_assigned boolean NOT NULL DEFAULT false,
    details jsonb NOT NULL,
    original_id bigint REFERENCES wf_requests(id),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS wf_requests_employee_idx ON wf_requests(employee_id,status);
CREATE INDEX IF NOT EXISTS wf_requests_reviewer_idx ON wf_requests(reviewer_id,status);
CREATE UNIQUE INDEX IF NOT EXISTS wf_request_cancel_pending_idx ON wf_requests(original_id)
    WHERE original_id IS NOT NULL AND status = 'pending';
CREATE TABLE IF NOT EXISTS wf_request_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id bigint NOT NULL REFERENCES wf_requests(id),
    actor_id bigint REFERENCES employees(id),
    action text NOT NULL,
    reason text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS wf_receipts (
    request_id bigint PRIMARY KEY REFERENCES wf_requests(id),
    name text NOT NULL,
    content bytea NOT NULL
);
CREATE TABLE IF NOT EXISTS wf_reports (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_start date NOT NULL,
    period_end date NOT NULL,
    employee_id bigint REFERENCES employees(id),
    version integer NOT NULL,
    finalized_by bigint NOT NULL REFERENCES employees(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    document bytea NOT NULL
);
ALTER TABLE wf_reports ADD COLUMN IF NOT EXISTS content_hash text;
"""


def bootstrap(conn):
    conn.execute(SCHEMA)


class Repository:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, statement, params=()):
        return self.conn.execute(statement, params)

    def one(self, statement, params=()):
        return self.execute(statement, params).fetchone()

    def all(self, statement, params=()):
        return self.execute(statement, params).fetchall()

    def lock_employee(self, employee_id):
        return self.one("SELECT * FROM employees WHERE id = %s FOR NO KEY UPDATE", (employee_id,))

    def employee(self, employee_id):
        return self.one("SELECT * FROM employees WHERE id = %s", (employee_id,))

    def schedule(self):
        return self.one("SELECT weekdays,start_time,end_time,break_minutes FROM wf_schedule")

    def put_schedule(self, value):
        return self.one(
            """INSERT INTO wf_schedule (weekdays,start_time,end_time,break_minutes)
               VALUES (%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET
               weekdays=excluded.weekdays,start_time=excluded.start_time,
               end_time=excluded.end_time,break_minutes=excluded.break_minutes
               RETURNING weekdays,start_time,end_time,break_minutes""",
            (value.weekdays, value.start_time, value.end_time, value.break_minutes),
        )

    def clock_events(self, employee_id, start, end):
        return self.all(
            """SELECT date,direction,recorded_at,correction_id FROM wf_clock
               WHERE employee_id=%s AND date BETWEEN %s AND %s ORDER BY date,id""",
            (employee_id, start, end),
        )

    def insert_clock(self, employee_id, day, direction, recorded_at, correction_id=None):
        self.execute(
            "INSERT INTO wf_clock(employee_id,date,direction,recorded_at,correction_id) VALUES (%s,%s,%s,%s,%s)",
            (employee_id, day, direction, recorded_at, correction_id),
        )

    def events(self, start, end):
        return self.all(
            "SELECT * FROM wf_events WHERE date BETWEEN %s AND %s ORDER BY date,id", (start, end)
        )

    def insert_event(self, value):
        return self.one(
            "INSERT INTO wf_events(date,title,category,workday_override) VALUES (%s,%s,%s,%s) RETURNING *",
            (value.date, value.title, value.category, value.workday_override),
        )

    def requests(self):
        return self.all(
            """SELECT r.*,e.name employee_name,e.supervisor_id FROM wf_requests r
               JOIN employees e ON e.id=r.employee_id ORDER BY r.id DESC"""
        )

    def request(self, request_id, lock=False):
        return self.one(
            "SELECT * FROM wf_requests WHERE id=%s" + (" FOR UPDATE" if lock else ""), (request_id,)
        )

    def history(self, request_ids):
        return self.all(
            """SELECT h.*,e.name actor_name FROM wf_request_history h
               LEFT JOIN employees e ON e.id=h.actor_id
               WHERE h.request_id=ANY(%s) ORDER BY h.id""",
            (request_ids,),
        )

    def add_history(self, request_id, actor_id, action, reason=""):
        self.execute(
            "INSERT INTO wf_request_history(request_id,actor_id,action,reason) VALUES (%s,%s,%s,%s)",
            (request_id, actor_id, action, reason),
        )

    def insert_request(self, employee_id, kind, reviewer_id, details, original_id=None):
        return self.one(
            """INSERT INTO wf_requests(employee_id,kind,reviewer_id,details,original_id)
               VALUES (%s,%s,%s,%s,%s) RETURNING *""",
            (employee_id, kind, reviewer_id, Jsonb(details), original_id),
        )

    def set_status(self, request_id, status):
        return self.one("UPDATE wf_requests SET status=%s WHERE id=%s RETURNING *", (status, request_id))

    def set_reviewer(self, request_id, reviewer_id, manually=False):
        return self.one(
            "UPDATE wf_requests SET reviewer_id=%s,manually_assigned=%s WHERE id=%s RETURNING *",
            (reviewer_id, manually, request_id),
        )

    def resubmit(self, request_id, reviewer_id, details):
        return self.one(
            """UPDATE wf_requests SET reviewer_id=%s,details=%s,status='pending',manually_assigned=false
               WHERE id=%s RETURNING *""",
            (reviewer_id, Jsonb(details), request_id),
        )

    def leave_types(self):
        return self.all("SELECT * FROM wf_leave_types ORDER BY name,id")

    def leave_type(self, kind_id):
        return self.one("SELECT * FROM wf_leave_types WHERE id=%s", (kind_id,))

    def leave_used(self, employee_id, kind_id, exclude=None):
        return self.one(
            """SELECT
                 coalesce(sum((details->>'minutes')::int) FILTER(WHERE status='pending'),0) reserved,
                 coalesce(sum((details->>'minutes')::int) FILTER(WHERE status='approved'),0) used
               FROM wf_requests
               WHERE employee_id=%s AND kind='leave' AND original_id IS NULL
                 AND details->>'leave_type_id'=%s AND id<>%s""",
            (employee_id, str(kind_id), exclude or 0),
        )

    def balance(self, employee_id, kind_id):
        return self.one(
            "SELECT total_minutes FROM wf_leave_balances WHERE employee_id=%s AND leave_type_id=%s",
            (employee_id, kind_id),
        )

    def employees(self):
        return self.all("SELECT id,name,active,started_on,inactive_on FROM employees ORDER BY name,id")

    def delegates(self, day):
        return self.all(
            """SELECT d.*,e.active,e.roles FROM wf_delegates d JOIN employees e ON e.id=d.reviewer_id
               WHERE %s BETWEEN d.start AND d."end" ORDER BY d.start DESC,d.id DESC""",
            (day,),
        )

    def receipt(self, request_id):
        return self.one("SELECT name,content FROM wf_receipts WHERE request_id=%s", (request_id,))

    def put_receipt(self, request_id, name, content):
        self.execute(
            """INSERT INTO wf_receipts(request_id,name,content) VALUES (%s,%s,%s)
               ON CONFLICT(request_id) DO UPDATE SET name=excluded.name,content=excluded.content""",
            (request_id, name, content),
        )

    def report_versions(self, start, end, employee_id):
        return self.all(
            """SELECT id,period_start,period_end,employee_id,version,finalized_by,created_at
               FROM wf_reports WHERE period_start=%s AND period_end=%s
               AND employee_id IS NOT DISTINCT FROM %s ORDER BY version DESC""",
            (start, end, employee_id),
        )

    def lock_report_period(self, start, end, employee_id):
        key = f"office-report:{start}:{end}:{employee_id}"
        self.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (key,))

    def report_snapshot(self, report_id):
        return self.one("SELECT document,content_hash FROM wf_reports WHERE id=%s", (report_id,))

    def set_report_content_hash(self, report_id, content_hash):
        self.execute("UPDATE wf_reports SET content_hash=%s WHERE id=%s", (content_hash, report_id))

    def save_report(self, start, end, employee_id, actor, version, content_hash, content):
        return self.one(
            """INSERT INTO wf_reports(period_start,period_end,employee_id,version,finalized_by,content_hash,document)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id,version,created_at""",
            (start, end, employee_id, version, actor, content_hash, content),
        )
