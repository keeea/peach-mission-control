from collections import Counter
from datetime import date

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import select

from app.db import get_session, init_db
from app.models import (
    ApplicationStage,
    JobApplication,
    Owner,
    Project,
    ProjectStatus,
    Task,
    TaskPriority,
    TaskStatus,
)

app = FastAPI(title="Peach Mission Control")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    with get_session() as session:
        tasks = session.exec(select(Task)).all()
        projects = session.exec(select(Project)).all()
        apps = session.exec(select(JobApplication)).all()

    task_status = Counter(t.status.value for t in tasks)
    app_stage = Counter(a.stage.value for a in apps)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "tasks": tasks,
            "projects": projects,
            "apps": apps,
            "task_status": task_status,
            "app_stage": app_stage,
        },
    )


@app.post("/tasks")
def create_task(
    title: str = Form(...),
    description: str = Form(""),
    priority: TaskPriority = Form(TaskPriority.medium),
    owner: Owner = Form(Owner.joint),
    project: str = Form("general"),
    due_date: str = Form(""),
) -> RedirectResponse:
    parsed_due = date.fromisoformat(due_date) if due_date else None
    task = Task(
        title=title,
        description=description,
        priority=priority,
        owner=owner,
        project=project,
        due_date=parsed_due,
    )
    with get_session() as session:
        session.add(task)
        session.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/tasks/{task_id}/status")
def update_task_status(task_id: int, status: TaskStatus = Form(...)) -> RedirectResponse:
    with get_session() as session:
        task = session.get(Task, task_id)
        if task:
            task.status = status
            session.add(task)
            session.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/projects")
def create_project(
    name: str = Form(...),
    goal: str = Form(""),
    status: ProjectStatus = Form(ProjectStatus.active),
) -> RedirectResponse:
    p = Project(name=name, goal=goal, status=status)
    with get_session() as session:
        session.add(p)
        session.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/applications")
def create_application(
    company: str = Form(...),
    role: str = Form(...),
    stage: ApplicationStage = Form(ApplicationStage.discovered),
    url: str = Form(""),
    notes: str = Form(""),
) -> RedirectResponse:
    a = JobApplication(company=company, role=role, stage=stage, url=url, notes=notes)
    with get_session() as session:
        session.add(a)
        session.commit()
    return RedirectResponse(url="/", status_code=303)
