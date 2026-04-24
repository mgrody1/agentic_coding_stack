# Config Examples

## Example `.codex/config.toml`

```toml
model = "gpt-5.4"
approval_policy = "on-request"
sandbox_mode = "workspace-write"

[profiles.frontier_dev]
model = "gpt-5.4"
approval_policy = "on-request"
sandbox_mode = "workspace-write"

[mcp_servers.frontier_dev]
command = "python"
args = ["-m", "frontier_dev_mcp"]
```

Keep project-specific settings in `.codex/config.toml` if you trust the repo.

## Example `AGENTS.md`

```md
# AGENTS.md

## Purpose
This repo implements a low-knob frontier-based development orchestrator.

## Hard rules
- Do not move planning logic into worker services.
- Do not move durable memory writes into oMLX wrappers.
- Keep feasibility as a hard gate.
- Keep objective evaluation vector-valued in v1.
- Default to draft PRs only.

## Working style
- Prefer explicit code over framework magic.
- Keep modules small and typed.
- Add or update tests when behavior changes.
- Explain architectural changes in PR notes.
```

## Example environment variables

### Conductor
```bash
FRONTIER_DB_URL=sqlite:///./frontier.db
FRONTIER_GITHUB_TOKEN=...
FRONTIER_OMLX_BUILDER_URL=http://m2studio:8000/v1
FRONTIER_OMLX_REVIEWER_URL=http://mbp:8000/v1
FRONTIER_OMLX_ARBITER_URL=http://ultra:8000/v1
FRONTIER_OMLX_EMBED_URL=http://mini:8000/v1
FRONTIER_OMLX_RERANK_URL=http://mini:8000/v1
FRONTIER_WORKER_M2_URL=http://m2studio:8720
FRONTIER_WORKER_MBP_URL=http://mbp:8720
FRONTIER_API_TOKEN=replace_me
```

### Worker
```bash
FRONTIER_WORKER_TOKEN=replace_me
FRONTIER_ALLOWED_REPOS=/Users/you/src/repo1,/Users/you/src/repo2
FRONTIER_ALLOWED_COMMANDS_JSON=/Users/you/frontier/allowed_commands.json
```

## Example command allowlist
```json
{
  "lint": ["pnpm", "lint"],
  "typecheck": ["pnpm", "typecheck"],
  "test": ["pnpm", "test"],
  "test_changed": ["pnpm", "test", "--", "{tests}"]
}
```
