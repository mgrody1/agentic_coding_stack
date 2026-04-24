"""Thin oMLX client wrapper with alias endpoint routing."""

from __future__ import annotations

from typing import Any

import httpx

from shared.config.settings import ConductorSettings


class OMLXClientError(RuntimeError):
    pass


class OMLXClient:
    def __init__(self, settings: ConductorSettings, http_client: httpx.Client | None = None):
        self.settings = settings
        self.endpoints = settings.omlx_endpoints().model_dump()
        self.aliases = settings.alias_map().model_dump()
        self.client = http_client or httpx.Client(timeout=settings.request_timeout_seconds)

    def _base_url_for_alias(self, alias: str) -> str:
        mapped = alias.replace("-", "_")
        if mapped not in self.endpoints:
            raise OMLXClientError(f"Unknown alias: {alias}")
        return self.endpoints[mapped]

    def _post(self, alias: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        base_url = self._base_url_for_alias(alias)
        headers = {"Authorization": f"Bearer {self.settings.api_token}"}
        last_error: Exception | None = None
        for _ in range(self.settings.retry_count + 1):
            try:
                response = self.client.post(f"{base_url}{path}", json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # explicit conversion boundary
                last_error = exc
        raise OMLXClientError(f"oMLX request failed for alias={alias}: {last_error}")

    def chat(self, alias: str, messages: list[dict[str, str]], **kwargs: Any) -> dict[str, Any]:
        payload = {"model": alias, "messages": messages, **kwargs}
        return self._post(alias=alias, path="/chat/completions", payload=payload)

    def embed(self, alias: str, inputs: list[str]) -> list[list[float]]:
        payload = {"model": alias, "input": inputs}
        response = self._post(alias=alias, path="/embeddings", payload=payload)
        return [item["embedding"] for item in response.get("data", [])]

    def rerank(self, alias: str, query: str, documents: list[str]) -> list[dict[str, Any]]:
        payload = {"model": alias, "query": query, "documents": documents}
        response = self._post(alias=alias, path="/rerank", payload=payload)
        return response.get("results", [])

    def list_models(self, base_url: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.settings.api_token}"}
        response = self.client.get(f"{base_url}/models", headers=headers)
        response.raise_for_status()
        return response.json()
