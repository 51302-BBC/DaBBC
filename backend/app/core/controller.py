import os

from fastapi import APIRouter, Depends, Request, Response

from app.database import get_db
from . import repository as repo, service
from .model import ClientCreate, ClientPatch, EmployeeCreate, EmployeePatch, Identifier, Login, Recover, SetPassword, TaskCreate, TaskPatch

router = APIRouter()
current_user = service.current_user


@router.post("/auth/login")
def login(payload: Login, request: Request, response: Response, conn=Depends(get_db)):
    token, user = service.login(conn, payload.email, payload.password)
    service.logout(conn, request.cookies.get(service.SESSION_COOKIE))
    response.set_cookie(
        service.SESSION_COOKIE, token, max_age=service.SESSION_MAX_AGE,
        httponly=True, secure=os.getenv("COOKIE_SECURE", "").lower() in {"true", "1"},
        samesite="lax", path="/",
    )
    return user


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, conn=Depends(get_db)):
    service.logout(conn, request.cookies.get(service.SESSION_COOKIE))
    response.delete_cookie(service.SESSION_COOKIE, path="/")


@router.get("/auth/me")
def me(actor=Depends(current_user)):
    return actor


@router.post("/auth/forgot", status_code=204)
def forgot(payload: Recover, conn=Depends(get_db)):
    service.recover(conn, payload.email)


@router.post("/auth/activate", status_code=204)
def activate(payload: SetPassword, conn=Depends(get_db)):
    service.set_password(conn, payload.token, payload.password, "activate")


@router.post("/auth/reset", status_code=204)
def reset(payload: SetPassword, conn=Depends(get_db)):
    service.set_password(conn, payload.token, payload.password, "reset")


@router.get("/employees")
def employees(actor=Depends(current_user), conn=Depends(get_db)):
    return service.employees(conn, actor)


@router.post("/employees", status_code=201)
def create_employee(payload: EmployeeCreate, actor=Depends(current_user), conn=Depends(get_db)):
    return service.create_employee(conn, actor, payload)


@router.get("/employees/{employee_id}")
def employee(employee_id: Identifier, actor=Depends(current_user), conn=Depends(get_db)):
    return service.find(next((row for row in service.employees(conn, actor) if row["id"] == employee_id), None))


@router.patch("/employees/{employee_id}")
def patch_employee(employee_id: Identifier, payload: EmployeePatch, actor=Depends(current_user), conn=Depends(get_db)):
    return service.patch_employee(conn, actor, employee_id, payload)


@router.post("/employees/{employee_id}/invite", status_code=204)
def invite(employee_id: Identifier, actor=Depends(current_user), conn=Depends(get_db)):
    service.invite_employee(conn, actor, employee_id)


@router.get("/employees/{employee_id}/handoff")
def employee_handoff(employee_id: Identifier, actor=Depends(current_user), conn=Depends(get_db)):
    return service.handoff(conn, actor, employee_id)


@router.get("/clients")
def clients(actor=Depends(current_user), conn=Depends(get_db)):
    return service.clients(conn, actor)


@router.post("/clients", status_code=201)
def create_client(payload: ClientCreate, actor=Depends(current_user), conn=Depends(get_db)):
    return service.create_client(conn, actor, payload)


@router.get("/clients/{client_id}")
def client(client_id: Identifier, actor=Depends(current_user), conn=Depends(get_db)):
    return service.find(next((row for row in service.clients(conn, actor) if row["id"] == client_id), None))


@router.patch("/clients/{client_id}")
def patch_client(client_id: Identifier, payload: ClientPatch, actor=Depends(current_user), conn=Depends(get_db)):
    return service.patch_client(conn, actor, client_id, payload)


@router.get("/tasks")
def tasks(actor=Depends(current_user), conn=Depends(get_db)):
    return service.tasks(conn, actor)


@router.post("/tasks", status_code=201)
def create_task(payload: TaskCreate, actor=Depends(current_user), conn=Depends(get_db)):
    return service.create_task(conn, actor, payload)


@router.get("/tasks/{task_id}")
def task(task_id: Identifier, actor=Depends(current_user), conn=Depends(get_db)):
    return service.task_for_actor(conn, actor, task_id)


@router.patch("/tasks/{task_id}")
def patch_task(task_id: Identifier, payload: TaskPatch, actor=Depends(current_user), conn=Depends(get_db)):
    return service.patch_task(conn, actor, task_id, payload)


@router.get("/tasks/{task_id}/history")
def task_history(task_id: Identifier, actor=Depends(current_user), conn=Depends(get_db)):
    service.task_for_actor(conn, actor, task_id)
    return repo.task_history(conn, task_id)


@router.get("/notifications")
def notifications(actor=Depends(current_user), conn=Depends(get_db)):
    return repo.get_notifications(conn, actor["id"])


@router.patch("/notifications/{notification_id}/read")
def read_notification(notification_id: Identifier, actor=Depends(current_user), conn=Depends(get_db)):
    return service.find(repo.read_notification(conn, actor["id"], notification_id), "找不到通知")
