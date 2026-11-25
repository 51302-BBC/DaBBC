from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=254,
                                         pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=3000)]
Role = Literal["owner", "manager", "admin", "employee"]
Status = Literal["pending", "in_progress", "completed", "canceled"]
Identifier = Annotated[int, Field(gt=0, le=2**63 - 1)]


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Payload):
    email: Email
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class Recover(Payload):
    email: Email


class SetPassword(Payload):
    token: Annotated[str, StringConstraints(min_length=32, max_length=128)]
    password: Password


class EmployeeCreate(Payload):
    name: Name
    email: Email
    supervisor_id: Identifier | None = None
    started_on: date | None = None
    roles: list[Role] | None = Field(default=None, min_length=1, max_length=4)


class EmployeePatch(Payload):
    name: Name | None = None
    email: Email | None = None
    roles: list[Role] | None = Field(default=None, max_length=4)
    supervisor_id: Identifier | None = None
    active: bool | None = None
    started_on: date | None = None
    phone: Text | None = None
    address: Text | None = None
    emergency_contact: Text | None = None


class ClientCreate(Payload):
    name: Name
    active: bool = True
    assignee_ids: list[Identifier] = Field(default_factory=list, max_length=500)


class ClientPatch(Payload):
    name: Name | None = None
    active: bool | None = None
    assignee_ids: list[Identifier] | None = Field(default=None, max_length=500)


class TaskCreate(Payload):
    title: Name
    description: Text = ""
    client_id: Identifier
    assignee_id: Identifier
    due_on: date | None = None
    status: Literal["pending"] = "pending"


class TaskPatch(Payload):
    title: Name | None = None
    description: Text | None = None
    assignee_id: Identifier | None = None
    status: Status | None = None
    due_on: date | None = None
