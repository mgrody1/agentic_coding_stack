from fastapi.testclient import TestClient

from apps.conductor.main import app as conductor_app
from apps.worker.main import app as worker_app


def test_conductor_health_smoke():
    client = TestClient(conductor_app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_worker_health_smoke():
    client = TestClient(worker_app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
