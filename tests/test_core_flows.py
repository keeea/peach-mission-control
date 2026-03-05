from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.db import engine
from app.main import app
from app.models import JobApplication, Project, Task


def reset_db() -> None:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


def test_create_task_flow() -> None:
    reset_db()
    with TestClient(app) as client:
        response = client.post(
            "/tasks",
            data={
                "title": "Build DS portfolio website",
                "description": "Ship V1 personal site",
                "priority": "high",
                "owner": "joint",
                "project": "portfolio",
                "due_date": "2026-03-15",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        page = client.get("/")
        assert page.status_code == 200
        assert "Build DS portfolio website" in page.text


def test_update_task_status_flow() -> None:
    reset_db()
    with TestClient(app) as client:
        client.post(
            "/tasks",
            data={"title": "Prepare ML interview notes"},
            follow_redirects=False,
        )

        with engine.connect() as conn:
            task_id = conn.execute(Task.__table__.select()).fetchone()[0]

        update = client.post(
            f"/tasks/{task_id}/status",
            data={"status": "in_progress"},
            follow_redirects=False,
        )
        assert update.status_code == 303

        page = client.get("/")
        assert "in_progress" in page.text


def test_create_project_flow() -> None:
    reset_db()
    with TestClient(app) as client:
        response = client.post(
            "/projects",
            data={
                "name": "AI Pivot Plan",
                "goal": "Land DS role in advanced tech",
                "status": "active",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        page = client.get("/")
        assert page.status_code == 200
        assert "AI Pivot Plan" in page.text


def test_create_job_application_flow() -> None:
    reset_db()
    with TestClient(app) as client:
        response = client.post(
            "/applications",
            data={
                "company": "OpenAI",
                "role": "Applied Scientist",
                "stage": "applied",
                "url": "https://example.com/job",
                "notes": "Tailored resume submitted",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        page = client.get("/")
        assert page.status_code == 200
        assert "Applied Scientist" in page.text


def test_models_are_registered() -> None:
    # Sanity check to ensure table models stay importable/registered.
    assert Task.__tablename__ == "task"
    assert Project.__tablename__ == "project"
    assert JobApplication.__tablename__ == "jobapplication"
