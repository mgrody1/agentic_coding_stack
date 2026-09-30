# Codex adapter

Use GLM as a delegated execution agent while Codex owns the conversation,
planning, judgment, and final verification.

## Install

Python 3.10–3.12 and a current Codex CLI are supported:

```bash
bash adapters/codex/install.sh
```

Python must already be installed; the adapter never bootstraps Python or `uv`
from a remote script. The installer is transactional:

1. selects an installed Python 3.12, 3.11, or 3.10;
2. builds a fresh, non-editable generation under
   `~/.glm-mcp/codex-venvs/`;
3. installs the exact distributions and hashes in `requirements.lock` without
   upgrading `pip`, then runs a real MCP stdio initialize/list-tools/ping smoke test;
4. creates a private, workspace-write-enabled GLM config when absent;
5. round-trip edits `~/.codex/config.toml`, preserving comments and custom
   settings;
6. verifies the Codex registration and rolls the config back on failure;
7. prunes only adapter-owned generations, retaining the active generation and
   the newest previous generation for recovery.

An existing `mcp_servers.glm` entry is replaced only when it has this
adapter's ownership marker or its command is a strict direct generation under
`~/.glm-mcp/codex-venvs/`. A project path that merely contains a familiar
name is foreign and refused. Inspect it first, then use `--force-replace` only
when replacing it is intentional:

```bash
bash adapters/codex/install.sh --force-replace
```

Normal upgrades preserve the adapter's documented approval, allowlist, and
timeout policy. They fail closed if the existing launch table contains args,
cwd, inline environment, unknown launch fields, or non-allowlisted forwarded
environment variables; use `--force-replace` only after inspecting that state.
That flag is a trust-boundary reset: it rebuilds a clean server table and does
not preserve those launch customizations.
It validates an existing GLM runtime config before touching Codex. New
installs enable coding Bash on the trusted host; read-only delegation needs no
container runtime.
Fresh registrations use:

- `default_tools_approval_mode = "writes"`;
- `startup_timeout_sec = 20`;
- `tool_timeout_sec = 18060` (5-hour run plus 60 seconds for safe cleanup);
- an exact eleven-tool MCP allowlist, including both readonly delegation APIs
  and durable recovery query/ack.

Read-only MCP tools (`ping`, status) carry protocol annotations and do not need
write approval. Delegation/control/cancellation are conservatively annotated as
mutating. Result retrieval and recovery query perform local bookkeeping writes;
the fresh config explicitly approves those plus exact recovery acknowledgement.

If `~/.glm-mcp/config.json` still contains the API-key placeholder, edit it
before delegating on POSIX. On Windows, leave the placeholder and set
`GLM_API_KEY` in the environment instead. The default GLM capability
set is `Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`, and `NotebookEdit`, so
delegated coding tasks can modify the workspace and run bounded commands
immediately after installation. Use the explicit read-only APIs for static
file analysis; see [../../SECURITY.md](../../SECURITY.md).

Verify:

```bash
codex mcp get glm
codex
```

Then ask Codex to call the GLM `ping` tool. `ping` validates registration
and configuration loading; it does not spend GLM API tokens or prove API
credentials can complete a model request.

## Delegation policy

The MCP server publishes host instructions during initialization. Their first
~512 characters are self-contained for clients that truncate server
instructions. They tell Codex to:

- delegate self-contained, execution-heavy work;
- decide before reading large amounts of repository source when practical;
- keep architecture, ambiguous root-cause analysis, security-sensitive
  judgment, and tiny edits in the host;
- pass all context explicitly because GLM cannot see the parent chat or
  repository instruction files;
- query recovery, verify files, and acknowledge exact transaction IDs after mutations;
- verify delegated changes and tests.

`instructions.md` can be copied into a project `AGENTS.md` when a stronger,
project-specific policy is desired.

## Delegation APIs

Use coding delegation for changes, builds, tests, lint, Git, dependencies, or
anything that could write the workspace:

```text
delegate_to_glm(task, context)
```

This synchronous MCP request stays open until the run completes. The Codex
adapter's default tool timeout is 18,060 seconds: the 18,000-second (5-hour)
GLM run limit plus 60 seconds for safe child cleanup and result delivery.
`max_run_seconds` may be raised explicitly but is rejected above 172,800
seconds (48 hours). For a synchronous run above five hours, raise Codex's
`mcp_servers.glm.tool_timeout_sec` to at least `max_run_seconds + 60`; the
server-side 48-hour ceiling still applies. Use the coding background API for
work that needs steering:

```text
start_glm(task, context) -> job_id
send_glm_message(job_id, message)
get_glm_status(job_id)
cancel_glm(job_id)
get_glm_result(job_id)
```

For clearly read-only investigation—code reading/search, review, log analysis,
root-cause analysis, and call-graph tracing—use the fixed file-analysis profile:

```text
delegate_to_glm_readonly(task, context)
start_glm_readonly(task, context) -> job_id
```

The readonly APIs provide only Read, Glob, and Grep. They expose neither Bash
nor workspace mutation and work without Docker/Podman. Do not pass a mode,
backend, or permission argument; the selected API freezes the profile for the
job.

For either `start_*` API, use the same job controls:

```text
send_glm_message(job_id, message)
get_glm_status(job_id)
cancel_glm(job_id)
get_glm_result(job_id)
```

Steering is applied at model/tool safe points. Cancellation wakes retry backoff
and promptly terminates an in-flight provider or local-tool subprocess. A
cancellation accepted before terminal commit always wins that atomic commit; a
later request returns `cancel_accepted=false`.

An OS-backed lease permits one GLM execution per canonical workspace even
when several Codex/MCP processes exist. Different workspaces can run
independently. Background job state is held in the current MCP process only:
collect its result before closing or restarting the Codex task.

Every workspace mutation is journaled before commit. After a result reports
mutations, call `get_glm_recovery`, verify each file, then call
`acknowledge_glm_mutations` with the exact reviewed IDs. After cancellation,
disconnect, or restart, query recovery before retrying. New delegation is blocked
until pending records are acknowledged; recovery does not need a valid API key.

## Manual registration

Install into a supported environment and run the protocol smoke test:

```bash
python3.12 -m venv ~/.glm-mcp/manual-venv
~/.glm-mcp/manual-venv/bin/python -m pip install --only-binary=:all: --require-hashes -r requirements.lock
~/.glm-mcp/manual-venv/bin/python -m pip install --no-deps --no-build-isolation .
~/.glm-mcp/manual-venv/bin/python adapters/codex/mcp_smoke.py \
  ~/.glm-mcp/manual-venv/bin/glm-mcp
```

Keep the runtime outside any workspace that may enable `Write`, `Edit`, or
`NotebookEdit`. The server rejects mutation tools when its interpreter or
package is inside the delegated workspace, preventing that workspace from
replacing code imported by a privileged provider child.

Then adapt `config.toml.example` into `~/.codex/config.toml`. Direct TOML config
is recommended over a bare `codex mcp add` because the example includes
approval and timeout policy. Official Codex MCP settings are documented at
<https://developers.openai.com/codex/mcp>.

## Disable or uninstall

Disable delegation for one launch without changing configuration:

```bash
GLM_MODE=off codex
```

Remove only this adapter's owned Codex entry:

```bash
bash adapters/codex/uninstall.sh
```

The uninstaller preserves `~/.glm-mcp/config.json`, logs, and installed
generation environments. Successful installs automatically keep only the
active generation and the newest previous generation. The uninstaller refuses
to remove a foreign same-name server unless `--force` is explicitly supplied.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
bash -n adapters/codex/install.sh adapters/codex/uninstall.sh
```

The suite covers cancellation/finalization races, cross-process workspace
leases, MCP annotations and stdio protocol flow, TOML preservation/ownership/
rollback and safe default capabilities.
