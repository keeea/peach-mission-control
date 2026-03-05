import os

from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.db import engine
from app.main import app
from app.models import ApprovalRequest, Task

os.environ["PMC_ADMIN_USER"] = "admin"
os.environ["PMC_ADMIN_PASSWORD"] = "test-password"


def reset_db() -> None:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


def login(client: TestClient) -> None:
    response = client.post(
        "/login",
        data={"username": "admin", "password": "test-password"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_create_task_and_kanban_flow() -> None:
    reset_db()
    with TestClient(app) as client:
        login(client)
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

        page = client.get("/kanban")
        assert page.status_code == 200
        assert "Build DS portfolio website" in page.text


def test_task_api_crud_flow() -> None:
    reset_db()
    with TestClient(app) as client:
        login(client)

        create = client.post(
            "/api/tasks",
            json={
                "title": "API created task",
                "description": "from chat",
                "priority": "medium",
                "owner": "peach",
                "project": "automation",
                "status": "backlog",
            },
        )
        assert create.status_code == 201
        task_id = create.json()["id"]

        update = client.patch(f"/api/tasks/{task_id}", json={"status": "done"})
        assert update.status_code == 200
        assert update.json()["status"] == "done"

        listed = client.get("/api/tasks")
        assert listed.status_code == 200
        assert listed.json()["items"][0]["title"] == "API created task"


def test_approval_queue_and_report_endpoints() -> None:
    reset_db()
    with TestClient(app) as client:
        login(client)
        create = client.post(
            "/api/approvals",
            json={
                "title": "Send outbound email",
                "action_type": "external_email",
                "payload": {"to": "x@example.com"},
                "requested_by": "peach",
            },
        )
        assert create.status_code == 201
        approval_id = create.json()["id"]

        review = client.patch(
            f"/api/approvals/{approval_id}",
            params={"decision": "approved", "note": "safe to send"},
        )
        assert review.status_code == 200
        assert review.json()["status"] == "approved"

        approvals = client.get("/api/approvals")
        assert approvals.status_code == 200
        assert approvals.json()["items"][0]["action_type"] == "external_email"

        weekly_api = client.get("/api/reports/weekly")
        assert weekly_api.status_code == 200
        assert "tasks_touched" in weekly_api.json()


def test_export_endpoints() -> None:
    reset_db()
    with TestClient(app) as client:
        login(client)
        client.post("/api/tasks", json={"title": "Export me"})

        json_export = client.get("/api/export/tasks.json")
        assert json_export.status_code == 200
        assert json_export.json()["items"][0]["title"] == "Export me"

        csv_export = client.get("/api/export/tasks.csv")
        assert csv_export.status_code == 200
        assert "text/csv" in csv_export.headers["content-type"]
        assert "Export me" in csv_export.text


def test_auth_required_for_api() -> None:
    reset_db()
    with TestClient(app) as client:
        resp = client.get("/api/tasks")
        assert resp.status_code == 401


def test_models_are_registered() -> None:
    assert Task.__tablename__ == "task"
    assert ApprovalRequest.__tablename__ == "approvalrequest"
