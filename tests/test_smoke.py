import os

from fastapi.testclient import TestClient

from app.main import app

os.environ["PMC_ADMIN_USER"] = "admin"
os.environ["PMC_ADMIN_PASSWORD"] = "test-password"


def test_dashboard_requires_login() -> None:
    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)
    assert response.status_code == 303


def test_login_page_loads() -> None:
    with TestClient(app) as client:
        response = client.get("/login")
    assert response.status_code == 200
    assert "Peach Mission Control" in response.text
