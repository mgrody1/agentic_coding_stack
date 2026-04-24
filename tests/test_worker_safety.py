from fastapi.testclient import TestClient

import apps.worker.main as worker_main


TOKEN_HEADER = {"Authorization": "Bearer replace_me"}


def test_worker_rejects_non_allowlisted_repo(tmp_path):
    allowed = tmp_path / "allowed"
    disallowed = tmp_path / "disallowed"
    allowed.mkdir()
    disallowed.mkdir()

    worker_main.settings.allowed_repos = str(allowed)
    client = TestClient(worker_main.app)

    response = client.post(
        "/repo/prepare",
        json={"repo": str(disallowed), "task_id": "t1", "base_branch": "main"},
        headers=TOKEN_HEADER,
    )
    assert response.status_code == 403


def test_worker_rejects_path_escape(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()

    worker_main.settings.allowed_repos = str(allowed)
    client = TestClient(worker_main.app)

    response = client.post(
        "/artifact/read_file",
        json={"repo": str(allowed), "task_id": "t1", "path": "../escape.txt"},
        headers=TOKEN_HEADER,
    )
    assert response.status_code == 400


def test_worker_rejects_unallowlisted_command(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()

    worker_main.settings.allowed_repos = str(allowed)
    worker_main.settings.allowed_commands_json = "/nonexistent.json"
    client = TestClient(worker_main.app)

    response = client.post(
        "/run/command",
        json={"repo": str(allowed), "task_id": "t1", "command_key": "rm_all", "args": []},
        headers=TOKEN_HEADER,
    )
    assert response.status_code == 403
