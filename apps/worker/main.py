from __future__ import annotations

from fastapi import FastAPI

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

settings = WorkerSettings()
app = FastAPI(title="frontier-worker", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    repos = [path.strip() for path in settings.allowed_repos.split(",") if path.strip()]
    return HealthResponse(details={"allowed_repos": repos, "busy": False, "current_worktrees": []})


@app.post("/repo/prepare")
def repo_prepare(request: RepoPrepareRequest):
    return {"worktree_path": f"/tmp/{request.task_id}", "branch_name": f"task/{request.task_id}"}


@app.post("/repo/reset")
def repo_reset(request: WorkerRepoRequest):
    return {"ok": True, "task_id": request.task_id}


@app.post("/artifact/read_file")
def artifact_read_file(request: ReadFileRequest):
    return {"content": "", "path": request.path}


@app.post("/artifact/write_file")
def artifact_write_file(request: WriteFileRequest):
    return {"ok": True, "path": request.path, "bytes_written": len(request.content.encode("utf-8"))}


@app.post("/run/command")
def run_command(request: RunCommandRequest):
    return {"ok": True, "command_key": request.command_key, "args": request.args, "stdout": "", "stderr": ""}


@app.post("/run/lint")
def run_lint(request: WorkerRepoRequest):
    return {"ok": True, "task_id": request.task_id, "tool": "lint"}


@app.post("/run/typecheck")
def run_typecheck(request: WorkerRepoRequest):
    return {"ok": True, "task_id": request.task_id, "tool": "typecheck"}


@app.post("/run/tests")
def run_tests(request: RunTestsRequest):
    return {"ok": True, "task_id": request.task_id, "tests": request.tests}


@app.post("/git/diff")
def git_diff(request: WorkerRepoRequest):
    return {"diff": "", "changed_files": [], "task_id": request.task_id}


@app.post("/git/commit")
def git_commit(request: GitCommitRequest):
    return {"ok": True, "commit": "stub", "message": request.message}


@app.post("/git/push")
def git_push(request: WorkerRepoRequest):
    return {"ok": True, "remote": "origin", "task_id": request.task_id}
