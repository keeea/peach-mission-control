import os

from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.db import engine, init_db
from app.main import app
from app.models import ApprovalRequest, Task

os.environ["PMC_AUTH_DISABLED"] = "0"
os.environ["PMC_ADMIN_USER"] = "admin"
os.environ["PMC_ADMIN_PASSWORD"] = "test-password"


def reset_db() -> None:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    init_db()


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
        assert "Search" in page.text
        assert "Details" in page.text
        assert 'data-dropzone="backlog"' in page.text


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
        assert create.json()["sort_order"] >= 1

        detail = client.get(f"/api/tasks/{task_id}")
        assert detail.status_code == 200
        assert detail.json()["title"] == "API created task"

        update = client.patch(
            f"/api/tasks/{task_id}",
            json={"status": "done", "title": "API created task updated"},
        )
        assert update.status_code == 200
        assert update.json()["status"] == "done"
        assert update.json()["title"] == "API created task updated"

        listed = client.get("/api/tasks")
        assert listed.status_code == 200
        assert listed.json()["items"][0]["title"] == "API created task updated"


def test_global_filters_flow_across_dashboard_kanban_and_reports() -> None:
    reset_db()
    with TestClient(app) as client:
        login(client)
        client.post(
            "/api/tasks",
            json={
                "title": "Alpha ship",
                "description": "priority scope",
                "priority": "high",
                "owner": "lan",
                "project": "alpha",
                "status": "blocked",
            },
        )
        client.post(
            "/api/tasks",
            json={
                "title": "Beta cleanup",
                "priority": "low",
                "owner": "peach",
                "project": "beta",
                "status": "done",
            },
        )

        filtered = client.get("/api/tasks", params={"project": "alpha", "owner": "lan"})
        assert filtered.status_code == 200
        assert filtered.json()["filters"] == {"project": "alpha", "owner": "lan"}
        assert len(filtered.json()["items"]) == 1
        assert filtered.json()["items"][0]["title"] == "Alpha ship"

        dashboard = client.get("/", params={"project": "alpha", "owner": "lan"})
        assert dashboard.status_code == 200
        assert "统一过滤语言" in dashboard.text
        assert "Alpha ship" in dashboard.text
        assert "Beta cleanup" not in dashboard.text

        kanban = client.get("/kanban", params={"project": "alpha", "owner": "lan"})
        assert kanban.status_code == 200
        assert "Execution board scope" in kanban.text
        assert "Alpha ship" in kanban.text
        assert "Beta cleanup" not in kanban.text

        report = client.get("/api/reports/weekly", params={"project": "alpha", "owner": "lan"})
        assert report.status_code == 200
        assert report.json()["filters"] == {"project": "alpha", "owner": "lan"}
        assert report.json()["tasks_touched"] == 1


def test_task_reorder_endpoint_persists_cross_column_move() -> None:
    reset_db()
    with TestClient(app) as client:
        login(client)
        first = client.post("/api/tasks", json={"title": "Task A", "status": "backlog"}).json()
        second = client.post("/api/tasks", json={"title": "Task B", "status": "backlog"}).json()

        reorder = client.post(
            "/api/tasks/reorder",
            json={
                "items": [
                    {"id": second["id"], "status": "in_progress", "sort_order": 1},
                    {"id": first["id"], "status": "backlog", "sort_order": 1},
                ]
            },
        )
        assert reorder.status_code == 200
        items = reorder.json()["items"]
        assert items[0]["status"] == "in_progress"
        assert items[0]["sort_order"] == 1

        second_detail = client.get(f"/api/tasks/{second['id']}")
        assert second_detail.json()["status"] == "in_progress"


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
        assert "sort_order" in csv_export.text


def test_auth_required_for_api() -> None:
    reset_db()
    with TestClient(app) as client:
        resp = client.get("/api/tasks")
        assert resp.status_code == 401


def test_models_are_registered() -> None:
    assert Task.__tablename__ == "task"
    assert ApprovalRequest.__tablename__ == "approvalrequest"
