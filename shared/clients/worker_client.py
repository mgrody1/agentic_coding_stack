"""Worker HTTP wrapper used by conductor orchestration flows."""

from __future__ import annotations

from typing import Any

import httpx


class WorkerClient:
    def __init__(self, base_url: str, token: str, timeout_seconds: float = 20.0, http_client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client = http_client or httpx.Client(timeout=timeout_seconds)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(
            f"{self.base_url}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {self.token}"},
        )
        response.raise_for_status()
        return response.json()

    def health(self) -> dict[str, Any]:
        response = self.client.get(
            f"{self.base_url}/health",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        response.raise_for_status()
        return response.json()

    def prepare_repo(self, repo: str, task_id: str, base_branch: str) -> dict[str, Any]:
        return self._post("/repo/prepare", {"repo": repo, "task_id": task_id, "base_branch": base_branch})

    def reset_repo(self, repo: str, task_id: str) -> dict[str, Any]:
        return self._post("/repo/reset", {"repo": repo, "task_id": task_id})

    def run_command(self, repo: str, task_id: str, command_key: str, args: list[str]) -> dict[str, Any]:
        return self._post("/run/command", {"repo": repo, "task_id": task_id, "command_key": command_key, "args": args})

    def read_file(self, repo: str, task_id: str, path: str) -> dict[str, Any]:
        return self._post("/artifact/read_file", {"repo": repo, "task_id": task_id, "path": path})

    def write_file(self, repo: str, task_id: str, path: str, content: str) -> dict[str, Any]:
        return self._post("/artifact/write_file", {"repo": repo, "task_id": task_id, "path": path, "content": content})

    def run_lint(self, repo: str, task_id: str) -> dict[str, Any]:
        return self._post("/run/lint", {"repo": repo, "task_id": task_id})

    def run_typecheck(self, repo: str, task_id: str) -> dict[str, Any]:
        return self._post("/run/typecheck", {"repo": repo, "task_id": task_id})

    def run_tests(self, repo: str, task_id: str, tests: list[str]) -> dict[str, Any]:
        return self._post("/run/tests", {"repo": repo, "task_id": task_id, "tests": tests})

    def git_diff(self, repo: str, task_id: str) -> dict[str, Any]:
        return self._post("/git/diff", {"repo": repo, "task_id": task_id})
