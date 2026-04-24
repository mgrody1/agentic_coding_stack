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
