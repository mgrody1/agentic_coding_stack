# gpt-as-subagent

**English** · [简体中文](README.zh-CN.md)

[![Python](https://img.shields.io/badge/python-3.10--3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/protocol-MCP-purple)](https://modelcontextprotocol.io/)
[![Platforms](https://img.shields.io/badge/platforms-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey)](https://github.com/mgrody1/agentic_coding_stack)

> Run GPT as a **real sub-agent** inside Claude Code / Codex CLI — not just an LLM endpoint.
> The host agent keeps the main conversation, planning, judgment, and verification.
> GPT gets its own agent loop for execution-heavy work.
> Coding APIs use workspace-scoped writes and bounded trusted-host Bash; separate read-only APIs provide pure file analysis without command execution.

Ported from [PsChina/deepseek-as-subagent](https://github.com/PsChina/deepseek-as-subagent) (MIT).

### Full coding delegation

```text
       Claude / Codex (main agent)
         ├─ ordinary coding → delegate_to_gpt
         └─ coding task whose direction may change
                            → start_gpt → job_id
                                          ├─ send_gpt_message(job_id, ...)
                                          ├─ get_gpt_status(job_id)
                                          ├─ cancel_gpt(job_id)
                                          └─ get_gpt_result(job_id)
         ▼
       GPT coding sub-agent
         │  Read / Write / Edit / Bash / Glob / Grep / NotebookEdit
         │  autonomously reads, modifies, runs, and tests in the workspace
         ▼
       Result returns to the host
       Host verifies representative changes / tests
```

Coding Bash runs on the trusted host with `cwd=workspace`; it is bounded and
credential-isolated, but it is not an OS sandbox.

### Read-only analysis delegation

```text
       Claude / Codex (main agent)
         ├─ ordinary read-only analysis → delegate_to_gpt_readonly
         └─ read-only analysis whose direction may change
                            → start_gpt_readonly → job_id
                                                   ├─ send_gpt_message(job_id, ...)
                                                   ├─ get_gpt_status(job_id)
                                                   ├─ cancel_gpt(job_id)
                                                   └─ get_gpt_result(job_id)
         ▼
       GPT read-only sub-agent
         │  Read / Glob / Grep
         │  autonomously reads, searches, reviews, and performs static analysis
         ▼
       Analysis returns to the host
       Host verifies the conclusion
```

## Quick start

```bash
git clone https://github.com/mgrody1/agentic_coding_stack.git
cd agentic_coding_stack/gpt-as-subagent
# Inspect install.sh and requirements.lock, then:
./install.sh
```

Python 3.10–3.12 must already be installed. The installer never pipes a remote
bootstrap script into a shell. It installs the exact, hash-verified dependency
set in `requirements.lock`, registers the MCP server with Claude Code, deploys
protected generation copies of the skill + `/gpt` slash command. It does not
modify shell startup files. Helper deployment is best-effort after the core MCP
registration commits; a foreign destination is preserved and reported.

After install, edit `~/.gpt-mcp/config.json` to paste your GPT API
key on POSIX, or set `GPT_API_KEY` on Windows (get one at
[platform.openai.com](https://platform.openai.com/api-keys)). Then
run `claude` and try `/gpt inspect this workspace and summarize its structure`.

To upgrade, fetch and inspect an explicit tag or commit, then re-run the local
installer. Coding always uses `trusted_host`; read-only APIs need neither Bash
nor Docker/Podman. For
Codex or other MCP clients, see [Install](#install) below.

## How is this different from a plain GPT API wrapper?

A plain API wrapper exposes GPT as a **single LLM call**. The host has to read every file itself and feed content into the prompt, so GPT only saves the "thinking" cost, not the "reading/writing" cost.

This project gives GPT **its own agent loop**: tool dispatch, file I/O,
optional command execution for coding, and multi-turn reasoning against the
configured workspace. The host hands off a complete logical unit and gets a
result back. Token savings are end-to-end.

## What's in the box

- **MCP server** (Python, stdio transport)
- **Coding and read-only delegation**: `delegate_to_gpt` / `delegate_to_gpt_readonly`
- **Steerable background jobs**: `start_gpt` / `start_gpt_readonly` plus shared controls
- **Flash / Pro model routing**: host chooses a stable profile; users control the actual provider model IDs in config
- **Local GPT agent loop** (`agent_loop.py`) with OpenAI-compatible function calling
- **Fixed capability APIs**: coding gets Read / Write / Edit / Bash / Glob / Grep / NotebookEdit; read-only gets Read / Glob / Grep
- **Bash execution**: bounded credential-isolated trusted-host commands through the tool-child boundary
- **Workspace path boundary** for file tools, with outbound symlinks rejected
- **Cross-process execution lease** so two MCP servers cannot run GPT concurrently against the same workspace
- **Crash-safe mutation journal for Write / Edit / NotebookEdit** with recovery query, file verification, and exact acknowledgement before another delegation; trusted-host Bash changes are not journaled
- **Explicit network retry policy** with OpenAI SDK internal retries disabled to avoid nested retry amplification in proxy/TLS-timeout environments
- **Claude Code skill + `/gpt` command** for delegation policy and forced delegation

## Compatibility

The four delegation entry points accept one additive optional argument,
`model="flash" | "pro"`. Existing calls that omit it remain valid and now default
to the Flash profile. Background-job and recovery tools remain additive.
Mutation-capable legacy hosts must adopt the recovery query/verify/ack handshake
before starting another delegation; read-only use needs no change.
Clients should not parse health/error text byte-for-byte because diagnostics are now more specific. Provider calls still
use OpenAI's [Chat Completions API](https://platform.openai.com/docs/api-reference/chat/create).
Local Python module signatures are implementation details rather than a stable
public API.

## Install

### Claude Code (default)

```bash
git clone https://github.com/mgrody1/agentic_coding_stack.git
cd agentic_coding_stack/gpt-as-subagent
./install.sh
```

Then edit `~/.gpt-mcp/config.json` on POSIX, or set
`GPT_API_KEY` on Windows.

### Codex CLI

```bash
git clone https://github.com/mgrody1/agentic_coding_stack.git
cd agentic_coding_stack/gpt-as-subagent
bash adapters/codex/install.sh
```

See [adapters/codex/README.md](adapters/codex/README.md) for the Codex-specific install, delegation policy, and background-job workflow.

The Claude and Codex installers build a fresh isolated runtime, validate its
configuration and MCP protocol, and only then switch the host registration.
They keep the active generation plus one previous generation for recovery. Any
manual runtime must stay outside a delegated workspace when file-mutation tools
are enabled; unsafe layouts are rejected at startup.
Both installers serialize install/uninstall transactions. A hard-killed
installer intentionally leaves an empty fail-closed lock that must be removed
only after confirming no installer is running.

### Cursor / Cline / Claude Desktop / other MCP clients

The MCP server itself is client-agnostic. Install `requirements.lock` with
`pip --require-hashes`, install this project with dependency resolution disabled,
then point your client's MCP config at the generated `gpt-mcp` entrypoint.

## Usage

Choose capability for the task's **entire expected lifecycle** first. Use
read-only only when every expected step is static file analysis with Read, Glob,
and Grep—no command execution. If any step might need Bash, tests, builds,
lint, Git, program execution, dependency work, workspace mutation, or is not
clearly read-only, choose coding.

### Simple delegation

Use a synchronous API when the task can run to completion without mid-flight
intervention. The MCP request remains open until GPT finishes:

- `delegate_to_gpt(task, context, model="flash")` for coding, Bash, tests,
  or any task that might write the workspace.
- `delegate_to_gpt_readonly(task, context, model="flash")` for static file
  analysis only.

`model` is optional and accepts only `flash` or `pro`. Omit it for normal work;
select `pro` explicitly for difficult debugging, architecture-level reasoning,
or when Flash has already proved insufficient. The host never passes a provider
model ID directly.

### Steerable background delegation

For longer tasks that may need new instructions or cancellation, choose the
matching background API, then use the same controls for either job type:

```text
start_gpt(task, context, model="flash") / start_gpt_readonly(task, context, model="flash") -> job_id
send_gpt_message(job_id, message)
get_gpt_status(job_id)
cancel_gpt(job_id)
get_gpt_result(job_id)
```

Either `start_*` API returns quickly while the GPT agent continues in a
background worker. Steering changes only the task instruction: it cannot change
the job's fixed tools, Bash availability, or selected model profile. Cancellation
wakes retry backoff and promptly terminates an in-flight provider or local-tool
subprocess.

If a readonly job later needs a command or workspace mutation, cancel or finish
it, then create a new coding job with `start_gpt`; steering cannot upgrade
the existing readonly job.

If a steering message arrives after GPT has planned tool calls but before a not-yet-executed tool runs, the stale tool call is skipped and GPT re-plans from the new parent instruction.

Only **one GPT execution per canonical workspace** may run at a time, including executions started by separate MCP server processes. This lease coordinates GPT MCP executions only; it cannot prevent the host agent, IDE, user, or another local process from changing the workspace. While a coding background job is running, the host should steer, query, or cancel that job rather than independently mutate the same workspace, then resume host-side edits after the job reaches a terminal state. Background job IDs and results are session-scoped; collect the result before closing the host session.

### Mutation recovery

Mutations committed through `Write`, `Edit`, and `NotebookEdit` are journaled
before commit. Trusted-host Bash runs outside this transaction journal and may
modify workspace files directly; those changes are not represented by
`get_gpt_recovery`. After an interrupted coding run in which Bash may have
executed, inspect the workspace independently before continuing or retrying work.
After a result reports journaled mutations—or after cancellation, disconnection,
or MCP restart—run:

```text
get_gpt_recovery()
# verify every reported file
acknowledge_gpt_mutations(transaction_ids)
```

New delegation fails closed until the exact reviewed IDs are acknowledged.
Recovery works without a valid GPT API credential and never deletes or
rolls back workspace files.

### Claude Code helpers

- `delegate_to_gpt` / `delegate_to_gpt_readonly` — Claude selects the
  matching fixed capability and Flash/Pro profile
- `/gpt <task>` — force synchronous coding delegation
- `GPT_MODE=off claude` — start one session with GPT disabled

## When delegation actually saves money

The delegation decision should happen **before the host reads large amounts of source**. If the host reads first and then delegates, both agents pay the repository-reading cost.

Sweet spot:
- ✅ Multi-file implementation / mechanical refactors / test generation
- ✅ Large data + simple processing (log scan, file conversion, ETL)
- ✅ Tasks that may benefit from a cheap independent execution loop
- ❌ Tiny edits where orchestration overhead dominates
- ❌ Cross-domain architecture / ambiguous root-cause analysis / security-sensitive judgment

## Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│  Claude Code / Codex CLI (main agent)                           │
│    ↓ stdio (MCP protocol, local)                                │
│  gpt-as-subagent (Python MCP process)                           │
│    ├─ synchronous delegate                                      │
│    └─ steerable background job manager                          │
│         ↓                                                       │
│       GPT agent loop + selected fixed-capability tools          │
│    ↓ HTTPS                                                      │
│  api.openai.com                                                 │
└─────────────────────────────────────────────────────────────────┘
```

No third-party proxy or cloud relay is introduced by this project. Delegated prompts and tool/file outputs selected by the agent are sent to the configured OpenAI-compatible API, so only delegate data that endpoint is permitted to receive.

## Configuration

`~/.gpt-mcp/config.json`:

```json
{
  "api_key": "sk-...",
  "flash": "gpt-5.6-luna",
  "flash_reasoning_effort": "high",
  "pro": "gpt-5.6-luna",
  "pro_reasoning_effort": "high",
  "_reasoning_effort_options": ["none", "low", "high", "max"],
  "max_turns": 50,
  "max_run_seconds": 18000,
  "allowed_tools": ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "NotebookEdit"]
}
```

`flash` and `pro` are the provider model IDs behind the two stable MCP routing
profiles. You can change these strings when OpenAI publishes a new model
revision, or when a compatible endpoint uses different model names, without
changing how Claude/Codex calls the MCP tools. The public tool argument remains
only `model="flash"` or `model="pro"`.

`flash_reasoning_effort` and `pro_reasoning_effort` accept `none`, `low`, `high`,
or `max`. On turns without tools, `low`, `high` and `max` are sent as
`reasoning_effort` and `none` omits the field. Turns that include function tools
always send `reasoning_effort: "none"`. `_reasoning_effort_options` is only an
in-file hint and is ignored at runtime. If an effort field is absent, gpt-mcp
omits `reasoning_effort` on tool-free turns so the provider's default applies.
New installer-generated configs explicitly set both slots to `high`.

For upgrade compatibility, a legacy single `model` field is still accepted when
`flash` and `pro` are absent; its value is used for both slots. Do not combine
legacy `model` with the new `flash` / `pro` fields.

`allowed_tools` is retained for configuration compatibility and validation. It
does not select capabilities for a delegation: each MCP API applies its own
fixed profile after configuration is loaded.

`max_run_seconds` is the wall-clock limit for one delegated run. Its default is
18,000 seconds (5 hours), it may be increased explicitly, and its absolute
accepted maximum is 172,800 seconds (48 hours). Individual provider requests
remain bounded to 180 seconds within that run budget.
For synchronous delegation, the MCP client's tool timeout must be at least the
configured run limit plus cleanup grace; Codex installs with an 18,060-second
default (five hours plus 60 seconds).

**Workspace root** auto-follows the directory where you launch the host client.
To lock it to a fixed path regardless of cwd, add `"workspace": "/abs/path"`
to the config. It is the file-tool path boundary and the working directory for
coding Bash; it is not an OS sandbox for trusted-host Bash.

`delegate_to_gpt` and `start_gpt` always use full coding tools and
bounded `trusted_host` Bash. `delegate_to_gpt_readonly` and
`start_gpt_readonly` always use only Read/Glob/Grep and never expose Bash.
The selected API—not a task argument or model request—freezes that capability
for the job lifetime.
See [SECURITY.md](SECURITY.md) for boundaries and platform limitations.

Override at runtime with env vars: `GPT_API_KEY`, `GPT_WORKSPACE`, `GPT_MODE=off`.

## Uninstall

Claude Code: `./uninstall.sh`. Codex: `bash adapters/codex/uninstall.sh`.

Each uninstaller removes only its owned host registration. Neither deletes your
projects, GPT config/API key, logs, or account.

## License

MIT