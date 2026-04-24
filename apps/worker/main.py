from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, status

from shared.config.settings import WorkerSettings
from shared.schemas.models import (
    GitCommitRequest,
    HealthResponse,
    ReadFileRequest,
    RepoPrepareRequest,
    RunCommandRequest,
    RunTestsRequest,
    WorkerRepoRequest,
    WriteFileRequest,
)
from shared.utils.auth import require_bearer

settings = WorkerSettings()
app = FastAPI(title="frontier-worker", version="0.1.0")


def _auth(authorization: str | None = Header(default=None)) -> None:
    require_bearer(settings.worker_token, authorization)


def _ensure_allowed_repo(repo: str) -> None:
    allowed = [Path(p).resolve() for p in settings.allowed_repos_list()]
    repo_path = Path(repo).resolve()
    if not any(repo_path == root or root in repo_path.parents for root in allowed):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="repo not allowed")


def _safe_repo_file_path(repo: str, rel_path: str) -> Path:
    repo_path = Path(repo).resolve()
    candidate = (repo_path / rel_path).resolve()
    if repo_path not in candidate.parents and candidate != repo_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="path escapes repo")
    return candidate


def _ensure_command_allowed(command_key: str) -> list[str]:
    allowlist = settings.command_allowlist()
    if command_key not in allowlist:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="command_key not allowlisted")
    return allowlist[command_key]


@app.get("/health", response_model=HealthResponse, dependencies=[Depends(_auth)])
def health() -> HealthResponse:
    return HealthResponse(details={"allowed_repos": settings.allowed_repos_list(), "busy": False, "current_worktrees": []})


@app.post("/repo/prepare", dependencies=[Depends(_auth)])
def repo_prepare(request: RepoPrepareRequest):
    _ensure_allowed_repo(request.repo)
    return {"worktree_path": f"/tmp/{request.task_id}", "branch_name": f"task/{request.task_id}"}


@app.post("/repo/reset", dependencies=[Depends(_auth)])
def repo_reset(request: WorkerRepoRequest):
    _ensure_allowed_repo(request.repo)
    return {"ok": True, "task_id": request.task_id}


@app.post("/artifact/read_file", dependencies=[Depends(_auth)])
def artifact_read_file(request: ReadFileRequest):
    _ensure_allowed_repo(request.repo)
    safe_path = _safe_repo_file_path(request.repo, request.path)
    content = safe_path.read_text() if safe_path.exists() else ""
    return {"content": content, "path": str(safe_path)}


@app.post("/artifact/write_file", dependencies=[Depends(_auth)])
def artifact_write_file(request: WriteFileRequest):
    _ensure_allowed_repo(request.repo)
    safe_path = _safe_repo_file_path(request.repo, request.path)
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.write_text(request.content)
    return {"ok": True, "path": str(safe_path), "bytes_written": len(request.content.encode("utf-8"))}


@app.post("/run/command", dependencies=[Depends(_auth)])
def run_command(request: RunCommandRequest):
    _ensure_allowed_repo(request.repo)
    template = _ensure_command_allowed(request.command_key)
    return {"ok": True, "command_key": request.command_key, "command": template + request.args, "stdout": "", "stderr": ""}


@app.post("/run/lint", dependencies=[Depends(_auth)])
def run_lint(request: WorkerRepoRequest):
    _ensure_allowed_repo(request.repo)
    _ensure_command_allowed("lint")
    return {"ok": True, "task_id": request.task_id, "tool": "lint"}


@app.post("/run/typecheck", dependencies=[Depends(_auth)])
def run_typecheck(request: WorkerRepoRequest):
    _ensure_allowed_repo(request.repo)
    _ensure_command_allowed("typecheck")
    return {"ok": True, "task_id": request.task_id, "tool": "typecheck"}


@app.post("/run/tests", dependencies=[Depends(_auth)])
def run_tests(request: RunTestsRequest):
    _ensure_allowed_repo(request.repo)
    _ensure_command_allowed("test")
    return {"ok": True, "task_id": request.task_id, "tests": request.tests}


@app.post("/git/diff", dependencies=[Depends(_auth)])
def git_diff(request: WorkerRepoRequest):
    _ensure_allowed_repo(request.repo)
    return {"diff": "", "changed_files": [], "task_id": request.task_id}


@app.post("/git/commit", dependencies=[Depends(_auth)])
def git_commit(request: GitCommitRequest):
    _ensure_allowed_repo(request.repo)
    return {"ok": True, "commit": "stub", "message": request.message}


@app.post("/git/push", dependencies=[Depends(_auth)])
def git_push(request: WorkerRepoRequest):
    _ensure_allowed_repo(request.repo)
    return {"ok": True, "remote": "origin", "task_id": request.task_id}
