from fastapi.testclient import TestClient

from apps.conductor.main import app as conductor_app
from apps.worker.main import app as worker_app


def test_conductor_health_requires_auth():
    client = TestClient(conductor_app)
    unauthorized = client.get("/health")
    assert unauthorized.status_code == 401

    response = client.get("/health", headers={"Authorization": "Bearer replace_me"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_worker_health_requires_auth():
    client = TestClient(worker_app)
    unauthorized = client.get("/health")
    assert unauthorized.status_code == 401

    response = client.get("/health", headers={"Authorization": "Bearer replace_me"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
