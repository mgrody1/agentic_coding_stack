# Claude Code Adapter

This is the **default** adapter — the root `install.sh` installs it
automatically. This README documents what gets installed.

## What it adds to Claude Code

| File | Purpose |
|---|---|
| `~/.claude.json` entry `mcpServers.glm` | MCP server registration |
| `~/.claude/skills/delegate-to-glm/` (symlink) | Teaches Claude when to delegate |
| `~/.claude/commands/glm.md` (symlink) | `/glm <task>` slash command for explicit delegation |
| `~/.glm-mcp/config.json` | GLM API key + model settings (workspace auto-follows `claude` cwd) |

The skill and command symlinks target installer-owned copies under
`~/.glm-mcp/claude-helpers/`, so moving or deleting the checkout does not
break an installed Claude setup. Re-run the installer to publish repo updates.
The installer never edits shell startup files.

## Delegation capabilities

Use `delegate_to_glm` or `start_glm` for coding: they always expose
Read, Write, Edit, Bash, Glob, Grep, and NotebookEdit. Bash runs on the trusted
host with `cwd=workspace`; it is bounded and credential-isolated, but not an OS
sandbox.

Use `delegate_to_glm_readonly` or `start_glm_readonly` for static
file analysis. They always expose only Read, Glob, and Grep—no Bash and no
workspace mutation. Both `start_*` APIs return a `job_id` controlled by the
same `send_glm_message`, status, cancel, and result APIs. The selected API
fixes its capability for the whole job, including after steering.

## Install

From repo root:
```bash
./install.sh
```

Idempotent — safe to re-run after pulling repo updates.

## Uninstall

```bash
./uninstall.sh
```

Removes the MCP registration, skill, and slash command. Does **not** touch
your `~/.glm-mcp/config.json` (preserves your API key). An alias left by an
older release must be removed manually from your shell startup file.

## Per-feature control

| Feature | How to disable |
|---|---|
| Auto-delegation in main conversation | Tell Claude "do it yourself, don't delegate" |
| Whole session, no GLM | Run `GLM_MODE=off claude` |
| Permanently | `./uninstall.sh` |

## Files in this adapter (relative to repo root)

- `../../skills/delegate-to-glm/SKILL.md` — delegation decision rules
- `../../commands/glm.md` — `/glm` slash command
- `../../install.sh` — installer that wires this adapter into `~/.claude/`
- `../../uninstall.sh` — removes everything this adapter added
