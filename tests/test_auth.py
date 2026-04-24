from fastapi.testclient import TestClient

import apps.conductor.main as conductor_main


def test_conductor_jobs_requires_auth():
    client = TestClient(conductor_main.app)
    payload = {
        "repo": "r",
        "task_id": "t",
        "task_type": "issue",
        "title": "title",
        "body": "body",
        "base_branch": "main",
    }
    unauthorized = client.post("/jobs", json=payload)
    assert unauthorized.status_code == 401

    authorized = client.post("/jobs", json=payload, headers={"Authorization": "Bearer replace_me"})
    assert authorized.status_code == 200
