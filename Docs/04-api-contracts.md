# API Contracts

## Conductor API

### `GET /health`
Returns version, DB status, queue depth, and reachable backends.

### `POST /jobs/enqueue`
Request body:
- `repo`
- `task_id`
- `task_type`
- `title`
- `body`
- `base_branch`

Response:
- `job_id`
- `status`

### `GET /jobs/{job_id}`
Returns:
- current status
- stage
- chosen candidate if available
- draft PR link if available
- latest reviewer status

### `POST /jobs/{job_id}/run`
Starts or resumes orchestration for a queued job.

### `POST /memory/query`
Request body:
- `repo`
- `query`
- optional `scopes`
- optional `alias_name`
- optional `pair_key`

Response:
- ranked memory hits
- frontier hits
- residual hits
- applied overlays

## Worker API

### `GET /health`
Return:
- version
- allowed repos
- busy flag
- current worktrees

### `POST /repo/prepare`
Input:
- `repo`
- `base_branch`
- `task_id`

Output:
- `worktree_path`
- `branch_name`

### `POST /repo/reset`
Input:
- `repo`
- `task_id`

### `POST /artifact/read_file`
Input:
- `repo`
- `task_id`
- `path`

Output:
- `content`

### `POST /artifact/write_file`
Input:
- `repo`
- `task_id`
- `path`
- `content`

### `POST /run/command`
Input:
- `repo`
- `task_id`
- `command_key`
- optional `args`

This endpoint must map `command_key` to a predefined allowlisted command.

### `POST /run/lint`
Input:
- `repo`
- `task_id`

### `POST /run/typecheck`
Input:
- `repo`
- `task_id`

### `POST /run/tests`
Input:
- `repo`
- `task_id`
- optional `tests`

### `POST /git/diff`
Input:
- `repo`
- `task_id`

Output:
- unified diff
- changed files

### `POST /git/commit`
Input:
- `repo`
- `task_id`
- `message`

### `POST /git/push`
Input:
- `repo`
- `task_id`

## oMLX client wrapper surface

Create a thin conductor wrapper that hides endpoint differences.

Methods:
- `chat(alias, messages, **kwargs)`
- `embed(alias, inputs)`
- `rerank(alias, query, documents)`
- `list_models(base_url)`

The wrapper should handle:
- base URL lookup by alias
- bearer auth
- timeout
- retries
- structured error conversion
