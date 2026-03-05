from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import secrets
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlmodel import select

from app.db import get_session, init_db
from app.models import (
    ApplicationStage,
    ApprovalRequest,
    ApprovalStatus,
    JobApplication,
    Owner,
    Project,
    ProjectStatus,
    SessionToken,
    Task,
    TaskPriority,
    TaskStatus,
    User,
)

SESSION_COOKIE = "pmc_session"
SESSION_HOURS = 12

app = FastAPI(title="Peach Mission Control")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    priority: TaskPriority = TaskPriority.medium
    owner: Owner = Owner.joint
    project: str = "general"
    due_date: date | None = None
    status: TaskStatus = TaskStatus.backlog


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: TaskPriority | None = None
    owner: Owner | None = None
    project: str | None = None
    due_date: date | None = None
    status: TaskStatus | None = None


class ApprovalCreate(BaseModel):
    title: str
    action_type: str = "external_action"
    payload: dict[str, Any] | list[Any] | str = ""
    requested_by: str = "api"


def _now() -> datetime:
    return datetime.now(UTC)


def _to_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"{salt.hex()}:{digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    salt_hex, hash_hex = stored.split(":", maxsplit=1)
    candidate = _hash_password(password, bytes.fromhex(salt_hex)).split(":", maxsplit=1)[1]
    return secrets.compare_digest(candidate, hash_hex)


def _current_user(request: Request) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    with get_session() as session:
        session_row = session.exec(select(SessionToken).where(SessionToken.token == token)).first()
        if not session_row or _to_utc(session_row.expires_at) < _now():
            raise HTTPException(status_code=401, detail="Session expired")

        user = session.get(User, session_row.user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid user")
        return user


def _optional_user(request: Request) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    with get_session() as session:
        session_row = session.exec(select(SessionToken).where(SessionToken.token == token)).first()
        if not session_row or _to_utc(session_row.expires_at) < _now():
            return None
        return session.get(User, session_row.user_id)


def _task_to_dict(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "priority": task.priority.value,
        "owner": task.owner.value,
        "project": task.project,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _approval_to_dict(item: ApprovalRequest) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "action_type": item.action_type,
        "payload": item.payload,
        "status": item.status.value,
        "requested_by": item.requested_by,
        "reviewed_by": item.reviewed_by,
        "review_note": item.review_note,
        "created_at": item.created_at.isoformat(),
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
    }


def _require_html_auth(request: Request) -> User:
    user = _optional_user(request)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


@app.on_event("startup")
def on_startup() -> None:
    init_db()

    default_user = os.getenv("PMC_ADMIN_USER", "admin")
    default_password = os.getenv("PMC_ADMIN_PASSWORD", "change-me")

    with get_session() as session:
        existing = session.exec(select(User).where(User.username == default_user)).first()
        if not existing:
            session.add(User(username=default_user, password_hash=_hash_password(default_password)))
            session.commit()


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("login.html", {"request": request, "error": ""})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)) -> HTMLResponse:
    with get_session() as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if not user or not _verify_password(password, user.password_hash):
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Invalid username or password"},
                status_code=401,
            )

        token = secrets.token_urlsafe(32)
        session.add(
            SessionToken(
                token=token,
                user_id=user.id,
                expires_at=_now() + timedelta(hours=SESSION_HOURS),
            )
        )
        session.commit()

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax")
    return response


@app.post("/logout")
def logout(request: Request) -> RedirectResponse:
    token = request.cookies.get(SESSION_COOKIE)
    with get_session() as session:
        if token:
            row = session.exec(select(SessionToken).where(SessionToken.token == token)).first()
            if row:
                session.delete(row)
                session.commit()
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    user = _require_html_auth(request)

    with get_session() as session:
        tasks = session.exec(select(Task).order_by(Task.created_at.desc())).all()
        projects = session.exec(select(Project).order_by(Project.created_at.desc())).all()
        apps = session.exec(select(JobApplication).order_by(JobApplication.created_at.desc())).all()
        approvals = session.exec(
            select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc()).limit(5)
        ).all()

    task_status = Counter(t.status.value for t in tasks)
    app_stage = Counter(a.stage.value for a in apps)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "tasks": tasks,
            "projects": projects,
            "apps": apps,
            "approvals": approvals,
            "task_status": task_status,
            "app_stage": app_stage,
        },
    )


@app.get("/kanban", response_class=HTMLResponse)
def kanban_page(request: Request) -> HTMLResponse:
    user = _require_html_auth(request)
    with get_session() as session:
        tasks = session.exec(select(Task).order_by(Task.updated_at.desc())).all()

    grouped = {status.value: [] for status in TaskStatus}
    for task in tasks:
        grouped[task.status.value].append(task)

    return templates.TemplateResponse(
        "kanban.html",
        {"request": request, "user": user, "grouped": grouped, "statuses": list(TaskStatus)},
    )


@app.get("/approvals", response_class=HTMLResponse)
def approvals_page(request: Request) -> HTMLResponse:
    user = _require_html_auth(request)
    with get_session() as session:
        items = session.exec(
            select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
        ).all()
    return templates.TemplateResponse(
        "approvals.html", {"request": request, "user": user, "items": items}
    )


@app.post("/approvals/{approval_id}/review")
def review_approval(
    request: Request,
    approval_id: int,
    decision: ApprovalStatus = Form(...),
    note: str = Form(""),
) -> RedirectResponse:
    user = _require_html_auth(request)
    if decision not in {ApprovalStatus.approved, ApprovalStatus.rejected}:
        raise HTTPException(status_code=400, detail="Invalid review decision")

    with get_session() as session:
        item = session.get(ApprovalRequest, approval_id)
        if not item:
            raise HTTPException(status_code=404, detail="Approval not found")
        item.status = decision
        item.review_note = note
        item.reviewed_by = user.username
        item.reviewed_at = _now()
        session.add(item)
        session.commit()

    return RedirectResponse(url="/approvals", status_code=303)


@app.get("/reports/weekly", response_class=HTMLResponse)
def weekly_report_page(request: Request) -> HTMLResponse:
    user = _require_html_auth(request)
    report = _weekly_report_data()
    return templates.TemplateResponse(
        "weekly_report.html", {"request": request, "user": user, "report": report}
    )


@app.post("/tasks")
def create_task(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    priority: TaskPriority = Form(TaskPriority.medium),
    owner: Owner = Form(Owner.joint),
    project: str = Form("general"),
    due_date: str = Form(""),
) -> RedirectResponse:
    _require_html_auth(request)
    parsed_due = date.fromisoformat(due_date) if due_date else None
    task = Task(
        title=title,
        description=description,
        priority=priority,
        owner=owner,
        project=project,
        due_date=parsed_due,
        updated_at=_now(),
    )
    with get_session() as session:
        session.add(task)
        session.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/tasks/{task_id}/status")
def update_task_status(
    request: Request, task_id: int, status: TaskStatus = Form(...)
) -> RedirectResponse:
    _require_html_auth(request)
    with get_session() as session:
        task = session.get(Task, task_id)
        if task:
            task.status = status
            task.updated_at = _now()
            session.add(task)
            session.commit()
    return RedirectResponse(url="/kanban", status_code=303)


@app.post("/projects")
def create_project(
    request: Request,
    name: str = Form(...),
    goal: str = Form(""),
    status: ProjectStatus = Form(ProjectStatus.active),
) -> RedirectResponse:
    _require_html_auth(request)
    p = Project(name=name, goal=goal, status=status)
    with get_session() as session:
        session.add(p)
        session.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/applications")
def create_application(
    request: Request,
    company: str = Form(...),
    role: str = Form(...),
    stage: ApplicationStage = Form(ApplicationStage.discovered),
    url: str = Form(""),
    notes: str = Form(""),
) -> RedirectResponse:
    _require_html_auth(request)
    a = JobApplication(company=company, role=role, stage=stage, url=url, notes=notes)
    with get_session() as session:
        session.add(a)
        session.commit()
    return RedirectResponse(url="/", status_code=303)


@app.get("/api/tasks")
def api_list_tasks(user: User = Depends(_current_user)) -> JSONResponse:
    with get_session() as session:
        tasks = session.exec(select(Task).order_by(Task.created_at.desc())).all()
    return JSONResponse({"items": [_task_to_dict(t) for t in tasks], "actor": user.username})


@app.post("/api/tasks")
def api_create_task(payload: TaskCreate, user: User = Depends(_current_user)) -> JSONResponse:
    task = Task(**payload.model_dump(), updated_at=_now())
    with get_session() as session:
        session.add(task)
        session.commit()
        session.refresh(task)
    return JSONResponse(_task_to_dict(task) | {"created_by": user.username}, status_code=201)


@app.patch("/api/tasks/{task_id}")
def api_update_task(
    task_id: int, payload: TaskUpdate, user: User = Depends(_current_user)
) -> JSONResponse:
    with get_session() as session:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        for key, value in payload.model_dump(exclude_none=True).items():
            setattr(task, key, value)
        task.updated_at = _now()
        session.add(task)
        session.commit()
        session.refresh(task)
    return JSONResponse(_task_to_dict(task) | {"updated_by": user.username})


@app.get("/api/approvals")
def api_list_approvals(user: User = Depends(_current_user)) -> JSONResponse:
    with get_session() as session:
        rows = session.exec(
            select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
        ).all()
    return JSONResponse({"items": [_approval_to_dict(x) for x in rows], "actor": user.username})


@app.post("/api/approvals")
def api_create_approval(
    payload: ApprovalCreate, user: User = Depends(_current_user)
) -> JSONResponse:
    body = payload.model_dump()
    item = ApprovalRequest(
        title=body["title"],
        action_type=body["action_type"],
        payload=json.dumps(body["payload"], ensure_ascii=False)
        if not isinstance(body["payload"], str)
        else body["payload"],
        requested_by=body["requested_by"] or user.username,
    )
    with get_session() as session:
        session.add(item)
        session.commit()
        session.refresh(item)
    return JSONResponse(_approval_to_dict(item), status_code=201)


@app.patch("/api/approvals/{approval_id}")
def api_review_approval(
    approval_id: int,
    decision: ApprovalStatus,
    note: str = "",
    user: User = Depends(_current_user),
) -> JSONResponse:
    if decision not in {ApprovalStatus.approved, ApprovalStatus.rejected}:
        raise HTTPException(status_code=400, detail="Invalid decision")
    with get_session() as session:
        item = session.get(ApprovalRequest, approval_id)
        if not item:
            raise HTTPException(status_code=404, detail="Approval not found")
        item.status = decision
        item.review_note = note
        item.reviewed_by = user.username
        item.reviewed_at = _now()
        session.add(item)
        session.commit()
        session.refresh(item)
    return JSONResponse(_approval_to_dict(item))


@app.get("/api/export/tasks.json")
def export_tasks_json(_: User = Depends(_current_user)) -> JSONResponse:
    with get_session() as session:
        tasks = session.exec(select(Task).order_by(Task.created_at.desc())).all()
    return JSONResponse({"items": [_task_to_dict(t) for t in tasks]})


@app.get("/api/export/tasks.csv")
def export_tasks_csv(_: User = Depends(_current_user)) -> StreamingResponse:
    with get_session() as session:
        tasks = session.exec(select(Task).order_by(Task.created_at.desc())).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["id", "title", "status", "priority", "owner", "project", "due_date", "updated_at"]
    )
    for task in tasks:
        writer.writerow(
            [
                task.id,
                task.title,
                task.status.value,
                task.priority.value,
                task.owner.value,
                task.project,
                task.due_date.isoformat() if task.due_date else "",
                task.updated_at.isoformat(),
            ]
        )
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tasks_export.csv"},
    )


@app.get("/api/reports/weekly")
def api_weekly_report(_: User = Depends(_current_user)) -> JSONResponse:
    return JSONResponse(_weekly_report_data())


def _weekly_report_data() -> dict[str, Any]:
    start = _now() - timedelta(days=7)
    with get_session() as session:
        all_tasks = session.exec(select(Task)).all()
        weekly = [t for t in all_tasks if _to_utc(t.updated_at) >= start]
        approvals = session.exec(select(ApprovalRequest)).all()
        weekly_approvals = [a for a in approvals if _to_utc(a.created_at) >= start]

    by_status = Counter(t.status.value for t in weekly)
    by_owner = Counter(t.owner.value for t in weekly)
    pending_approvals = [a for a in weekly_approvals if a.status == ApprovalStatus.pending]

    return {
        "window_days": 7,
        "tasks_touched": len(weekly),
        "tasks_done": by_status.get(TaskStatus.done.value, 0),
        "tasks_blocked": by_status.get(TaskStatus.blocked.value, 0),
        "status_breakdown": dict(by_status),
        "owner_breakdown": dict(by_owner),
        "approvals_created": len(weekly_approvals),
        "approvals_pending": len(pending_approvals),
    }
