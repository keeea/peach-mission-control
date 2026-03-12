import os

from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.db import engine, init_db
from app.main import app

os.environ["PMC_AUTH_DISABLED"] = "0"
os.environ["PMC_ADMIN_USER"] = "admin"
os.environ["PMC_ADMIN_PASSWORD"] = "test-password"


def reset_db() -> None:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    init_db()


def test_dashboard_requires_login() -> None:
    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)
    assert response.status_code == 303


def test_login_page_loads() -> None:
    with TestClient(app) as client:
        response = client.get("/login")
    assert response.status_code == 200
    assert "Peach Mission Control" in response.text


def test_kanban_page_renders_toolbar_and_modal() -> None:
    reset_db()
    with TestClient(app) as client:
        client.post(
            "/login",
            data={"username": "admin", "password": "test-password"},
            follow_redirects=False,
        )
        client.post("/api/tasks", json={"title": "Smoke task", "project": "kanban"})
        response = client.get("/kanban")
    assert response.status_code == 200
    assert "task-search" in response.text
    assert "task-detail-dialog" in response.text
    assert "filter-owner" in response.text
    assert "Execution board scope" in response.text
