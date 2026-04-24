"""Typed, explicit settings for conductor and worker services."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AliasMap(BaseModel):
    mem_embed: str = "mem-embed"
    mem_rerank: str = "mem-rerank"
    builder: str = "builder"
    reviewer: str = "reviewer"
    arbiter: str = "arbiter"


class OMLXEndpoints(BaseModel):
    mem_embed: str
    mem_rerank: str
    builder: str
    reviewer: str
    arbiter: str


class ConductorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FRONTIER_", extra="ignore")

    api_token: str = Field(default="replace_me")
    db_url: str = Field(default="sqlite:///./frontier.db")
    worker_m2_url: str = Field(default="http://m2studio:8720")
    worker_mbp_url: str = Field(default="http://mbp:8720")

    omlx_mem_embed_url: str = Field(default="http://mini:8000/v1")
    omlx_mem_rerank_url: str = Field(default="http://mini:8000/v1")
    omlx_builder_url: str = Field(default="http://m2studio:8000/v1")
    omlx_reviewer_url: str = Field(default="http://mbp:8000/v1")
    omlx_arbiter_url: str = Field(default="http://ultra:8000/v1")

    request_timeout_seconds: float = 20.0
    retry_count: int = 2

    def alias_map(self) -> AliasMap:
        return AliasMap()

    def omlx_endpoints(self) -> OMLXEndpoints:
        return OMLXEndpoints(
            mem_embed=self.omlx_mem_embed_url,
            mem_rerank=self.omlx_mem_rerank_url,
            builder=self.omlx_builder_url,
            reviewer=self.omlx_reviewer_url,
            arbiter=self.omlx_arbiter_url,
        )


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FRONTIER_", extra="ignore")

    worker_token: str = Field(default="replace_me")
    allowed_repos: str = Field(default="/tmp")
    allowed_commands_json: str = Field(default="")

    def allowed_repos_list(self) -> list[str]:
        return [path.strip() for path in self.allowed_repos.split(",") if path.strip()]

    def command_allowlist(self) -> dict[str, list[str]]:
        if not self.allowed_commands_json:
            return {
                "lint": ["echo", "lint"],
                "typecheck": ["echo", "typecheck"],
                "test": ["echo", "test"],
            }

        path = Path(self.allowed_commands_json)
        if not path.exists():
            return {}

        try:
            loaded = json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}

        if not isinstance(loaded, dict):
            return {}

        clean: dict[str, list[str]] = {}
        for key, value in loaded.items():
            if isinstance(key, str) and isinstance(value, list) and all(isinstance(v, str) for v in value):
                clean[key] = value
        return clean
