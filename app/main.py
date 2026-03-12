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
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlmodel import func, or_, select

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
FILTER_KEYS = ("q", "project", "status", "owner", "priority")


def _auth_disabled() -> bool:
    return os.getenv("PMC_AUTH_DISABLED", "1").lower() in {"1", "true", "yes", "on"}


def _dev_user() -> User:
    return User(id=0, username="dev", password_hash="disabled", is_active=True)


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
    sort_order: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: TaskPriority | None = None
    owner: Owner | None = None
    project: str | None = None
    due_date: date | None = None
    status: TaskStatus | None = None
    sort_order: int | None = None


class ApprovalCreate(BaseModel):
    title: str
    action_type: str = "external_action"
    payload: dict[str, Any] | list[Any] | str = ""
    requested_by: str = "api"


class TaskReorderItem(BaseModel):
    id: int
    status: TaskStatus
    sort_order: int


class TaskReorderPayload(BaseModel):
    items: list[TaskReorderItem]


class TaskFilterParams(BaseModel):
    q: str = ""
    project: str = ""
    status: str = ""
    owner: str = ""
    priority: str = ""

    def cleaned(self) -> dict[str, str]:
        return {
            key: value.strip()
            for key, value in self.model_dump().items()
            if isinstance(value, str) and value.strip()
        }

    def query_string(self) -> str:
        cleaned = self.cleaned()
        return urlencode(cleaned)

    def with_updates(self, **updates: str) -> str:
        payload = self.cleaned() | {k: v for k, v in updates.items() if v}
        payload = {k: v for k, v in payload.items() if v}
        encoded = urlencode(payload)
        return f"?{encoded}" if encoded else ""


def _read_filters(
    q: str = Query(""),
    project: str = Query(""),
    status: str = Query(""),
    owner: str = Query(""),
    priority: str = Query(""),
) -> TaskFilterParams:
    return TaskFilterParams(
        q=q,
        project=project,
        status=status,
        owner=owner,
        priority=priority,
    )


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
    if _auth_disabled():
        return _dev_user()

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
    if _auth_disabled():
        return _dev_user()

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
        "sort_order": task.sort_order,
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


def _next_sort_order(session: Any) -> int:
    max_order = session.exec(select(func.max(Task.sort_order))).one()
    return int(max_order or 0) + 1


def _task_select(filters: TaskFilterParams):
    query = select(Task)
    cleaned = filters.cleaned()

    if search := cleaned.get("q"):
        needle = f"%{search.lower()}%"
        query = query.where(
            or_(
                func.lower(Task.title).like(needle),
                func.lower(Task.description).like(needle),
                func.lower(Task.project).like(needle),
            )
        )
    if project := cleaned.get("project"):
        query = query.where(func.lower(Task.project) == project.lower())
    if status := cleaned.get("status"):
        query = query.where(Task.status == TaskStatus(status))
    if owner := cleaned.get("owner"):
        query = query.where(Task.owner == Owner(owner))
    if priority := cleaned.get("priority"):
        query = query.where(Task.priority == TaskPriority(priority))
    return query


def _list_tasks(session: Any, filters: TaskFilterParams | None = None) -> list[Task]:
    filters = filters or TaskFilterParams()
    return session.exec(
        _task_select(filters).order_by(
            Task.status.asc(),
            Task.sort_order.asc(),
            Task.updated_at.desc(),
        )
    ).all()


def _filter_context(
    tasks: list[Task], filters: TaskFilterParams, project_options: list[str] | None = None
) -> dict[str, Any]:
    projects = sorted({task.project for task in tasks if task.project})
    if project_options:
        projects = sorted({*projects, *[project for project in project_options if project]})

    cleaned = filters.cleaned()
    labels = {
        "q": "Search",
        "project": "Project",
        "status": "Status",
        "owner": "Owner",
        "priority": "Priority",
    }
    active_filters = [
        {
            "key": key,
            "label": labels[key],
            "value": value,
            "clear_href": filters.with_updates(**{key: ""}),
        }
        for key, value in cleaned.items()
    ]

    return {
        "filters": filters,
        "filter_query": filters.query_string(),
        "projects": projects,
        "owners": [owner.value for owner in Owner],
        "priorities": [priority.value for priority in TaskPriority],
        "statuses": [status.value for status in TaskStatus],
        "active_filter_count": len(cleaned),
        "active_filters": active_filters,
        "has_active_filters": bool(cleaned),
    }


def _dashboard_payload(tasks: list[Task], approvals: list[ApprovalRequest]) -> dict[str, Any]:
    today = date.today()
    task_status = Counter(task.status.value for task in tasks)
    priority_counts = Counter(task.priority.value for task in tasks)
    owner_counts = Counter(task.owner.value for task in tasks)

    overdue = [
        task
        for task in tasks
        if task.due_date and task.due_date < today and task.status != TaskStatus.done
    ]
    due_soon = [
        task
        for task in tasks
        if (
            task.due_date
            and today <= task.due_date <= today + timedelta(days=7)
            and task.status != TaskStatus.done
        )
    ]
    blocked = [task for task in tasks if task.status == TaskStatus.blocked]
    in_progress = [task for task in tasks if task.status == TaskStatus.in_progress]
    recent = sorted(tasks, key=lambda task: task.updated_at, reverse=True)[:6]
    high_priority = [
        task
        for task in tasks
        if task.priority == TaskPriority.high and task.status != TaskStatus.done
    ]
    pending_approvals = [item for item in approvals if item.status == ApprovalStatus.pending]

    return {
        "task_status": task_status,
        "priority_counts": priority_counts,
        "owner_counts": owner_counts,
        "top_summary": {
            "total": len(tasks),
            "in_progress": len(in_progress),
            "blocked": len(blocked),
            "due_this_week": len(due_soon),
        },
        "action_center": {
            "high_priority": high_priority[:5],
            "overdue": overdue[:5],
            "pending_approvals": pending_approvals[:5],
        },
        "risk_blockers": {
            "blocked": blocked[:6],
            "overdue": overdue[:6],
        },
        "timeline": recent,
        "insights": {
            "focus_owner": owner_counts.most_common(1)[0][0] if owner_counts else "n/a",
            "top_priority": priority_counts.most_common(1)[0][0] if priority_counts else "n/a",
            "completion_ratio": round(
                (task_status.get(TaskStatus.done.value, 0) / len(tasks)) * 100
            )
            if tasks
            else 0,
        },
    }


def _weekly_report_data(filters: TaskFilterParams | None = None) -> dict[str, Any]:
    filters = filters or TaskFilterParams()
    start = _now() - timedelta(days=7)
    with get_session() as session:
        all_tasks = _list_tasks(session, filters)
        weekly = [task for task in all_tasks if _to_utc(task.updated_at) >= start]
        approvals = session.exec(select(ApprovalRequest)).all()
        weekly_approvals = [
            approval for approval in approvals if _to_utc(approval.created_at) >= start
        ]

    by_status = Counter(task.status.value for task in weekly)
    by_owner = Counter(task.owner.value for task in weekly)
    by_project = Counter(task.project for task in weekly)
    pending_approvals = [item for item in weekly_approvals if item.status == ApprovalStatus.pending]
    throughput = [task for task in weekly if task.status == TaskStatus.done]
    blocked = [task for task in weekly if task.status == TaskStatus.blocked]
    recent_changes = sorted(weekly, key=lambda task: task.updated_at, reverse=True)[:8]

    return {
        "window_days": 7,
        "tasks_touched": len(weekly),
        "tasks_done": by_status.get(TaskStatus.done.value, 0),
        "tasks_blocked": by_status.get(TaskStatus.blocked.value, 0),
        "status_breakdown": dict(by_status),
        "owner_breakdown": dict(by_owner),
        "project_breakdown": dict(by_project),
        "approvals_created": len(weekly_approvals),
        "approvals_pending": len(pending_approvals),
        "throughput": [_task_to_dict(task) for task in throughput[:5]],
        "blockers": [_task_to_dict(task) for task in blocked[:5]],
        "recent_changes": [_task_to_dict(task) for task in recent_changes],
    }


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
    if _auth_disabled():
        return RedirectResponse(url="/", status_code=303)
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
def dashboard(request: Request, filters: TaskFilterParams = Depends(_read_filters)) -> HTMLResponse:
    user = _require_html_auth(request)

    with get_session() as session:
        tasks = _list_tasks(session, filters)
        projects = session.exec(select(Project).order_by(Project.created_at.desc())).all()
        approvals = session.exec(
            select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc()).limit(10)
        ).all()

    dashboard_data = _dashboard_payload(tasks, approvals)
    project_options = [project.name for project in projects]
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "tasks": tasks,
            "projects_meta": projects,
            **dashboard_data,
            **_filter_context(tasks, filters, project_options),
        },
    )


@app.get("/kanban", response_class=HTMLResponse)
def kanban_page(
    request: Request, filters: TaskFilterParams = Depends(_read_filters)
) -> HTMLResponse:
    user = _require_html_auth(request)
    with get_session() as session:
        tasks = _list_tasks(session, filters)
        projects = session.exec(select(Project).order_by(Project.created_at.desc())).all()

    grouped = {status.value: [] for status in TaskStatus}
    for task in tasks:
        grouped[task.status.value].append(_task_to_dict(task))

    return templates.TemplateResponse(
        "kanban.html",
        {
            "request": request,
            "user": user,
            "grouped": grouped,
            "tasks_json": json.dumps(grouped),
            **_filter_context(tasks, filters, [project.name for project in projects]),
        },
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
def weekly_report_page(
    request: Request, filters: TaskFilterParams = Depends(_read_filters)
) -> HTMLResponse:
    user = _require_html_auth(request)
    report = _weekly_report_data(filters)
    with get_session() as session:
        tasks = _list_tasks(session, filters)
        projects = session.exec(select(Project).order_by(Project.created_at.desc())).all()
    return templates.TemplateResponse(
        "weekly_report.html",
        {
            "request": request,
            "user": user,
            "report": report,
            **_filter_context(tasks, filters, [project.name for project in projects]),
        },
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
    with get_session() as session:
        task = Task(
            title=title,
            description=description,
            priority=priority,
            owner=owner,
            project=project,
            due_date=parsed_due,
            updated_at=_now(),
            sort_order=_next_sort_order(session),
        )
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
    project = Project(name=name, goal=goal, status=status)
    with get_session() as session:
        session.add(project)
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
    application = JobApplication(company=company, role=role, stage=stage, url=url, notes=notes)
    with get_session() as session:
        session.add(application)
        session.commit()
    return RedirectResponse(url="/", status_code=303)


@app.get("/api/tasks")
def api_list_tasks(
    filters: TaskFilterParams = Depends(_read_filters), user: User = Depends(_current_user)
) -> JSONResponse:
    with get_session() as session:
        tasks = _list_tasks(session, filters)
    return JSONResponse(
        {
            "items": [_task_to_dict(task) for task in tasks],
            "actor": user.username,
            "filters": filters.cleaned(),
        }
    )


@app.get("/api/tasks/{task_id}")
def api_get_task(task_id: int, user: User = Depends(_current_user)) -> JSONResponse:
    with get_session() as session:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
    return JSONResponse(_task_to_dict(task) | {"actor": user.username})


@app.post("/api/tasks")
def api_create_task(payload: TaskCreate, user: User = Depends(_current_user)) -> JSONResponse:
    with get_session() as session:
        body = payload.model_dump(exclude_none=True)
        task = Task(
            **body,
            updated_at=_now(),
            sort_order=body.get("sort_order", _next_sort_order(session)),
        )
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


@app.post("/api/tasks/reorder")
def api_reorder_tasks(
    payload: TaskReorderPayload, user: User = Depends(_current_user)
) -> JSONResponse:
    with get_session() as session:
        touched: list[Task] = []
        for item in payload.items:
            task = session.get(Task, item.id)
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {item.id} not found")
            task.status = item.status
            task.sort_order = item.sort_order
            task.updated_at = _now()
            session.add(task)
            touched.append(task)
        session.commit()
        for task in touched:
            session.refresh(task)
    ordered = sorted(touched, key=lambda row: row.sort_order)
    return JSONResponse(
        {
            "items": [_task_to_dict(task) for task in ordered],
            "updated_by": user.username,
        }
    )


@app.get("/api/approvals")
def api_list_approvals(user: User = Depends(_current_user)) -> JSONResponse:
    with get_session() as session:
        rows = session.exec(
            select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
        ).all()
    return JSONResponse(
        {"items": [_approval_to_dict(item) for item in rows], "actor": user.username}
    )


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
def export_tasks_json(
    filters: TaskFilterParams = Depends(_read_filters), _: User = Depends(_current_user)
) -> JSONResponse:
    with get_session() as session:
        tasks = _list_tasks(session, filters)
    return JSONResponse(
        {"items": [_task_to_dict(task) for task in tasks], "filters": filters.cleaned()}
    )


@app.get("/api/export/tasks.csv")
def export_tasks_csv(
    filters: TaskFilterParams = Depends(_read_filters), _: User = Depends(_current_user)
) -> StreamingResponse:
    with get_session() as session:
        tasks = _list_tasks(session, filters)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "title",
            "status",
            "priority",
            "owner",
            "project",
            "due_date",
            "sort_order",
            "updated_at",
        ]
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
                task.sort_order,
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
def api_weekly_report(
    filters: TaskFilterParams = Depends(_read_filters), _: User = Depends(_current_user)
) -> JSONResponse:
    return JSONResponse(_weekly_report_data(filters) | {"filters": filters.cleaned()})
