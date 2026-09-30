"""Stable MCP host instructions, separated to keep the server entrypoint small."""

HOST_INSTRUCTIONS = """
Recovery records cover Write/Edit/NotebookEdit commits; trusted-host Bash changes
are not transaction-journaled. After any result with reported mutations—or
cancellation, disconnection, or restart—call `get_glm_recovery`, verify the
reported files, then call `acknowledge_glm_mutations(transaction_ids)` with
the exact reviewed IDs. If coding Bash may have run before an interruption,
inspect the workspace independently before continuing.
After every delegation, verify delegated output against the requested acceptance
criteria before relying on it.

API reference:
- `ping()`: check that the MCP server is available.
- `delegate_to_glm(task, context="", model="flash")`: wait for full coding to
  finish; it cannot be steered, queried, or cancelled while running.
- `delegate_to_glm_readonly(task, context="", model="flash")`: wait for
  file-only analysis with Read/Glob/Grep; it has no Bash or mutation tools and
  cannot be controlled while running.
- `start_glm(task, context="", model="flash")` /
  `start_glm_readonly(task, context="", model="flash")`: start a coding or
  read-only background job and return `job_id`.
- `get_glm_status(job_id)`: read a background job's state.
- `send_glm_message(job_id, message)`: add or correct its task instruction.
- `cancel_glm(job_id)`: cancel a background job.
- `get_glm_result(job_id)`: return its final result, or not-ready state.
- `get_glm_recovery()`: list unacknowledged mutations from coding work.
- `acknowledge_glm_mutations(transaction_ids)`: acknowledge exact reviewed IDs.
`task` states the goal and acceptance criteria; optional `context` supplies paths,
constraints, and project conventions. `model` is exactly `flash` or `pro`: omit it
for Flash. A background job keeps the model chosen at start; steering cannot change
it. `job_id` comes from `start_*`.

Model routing guidance:
- `flash`: default general-purpose subagent, roughly Sonnet/Terra-tier. Use it for
  normal coding, review, investigation, refactoring, and routine multi-file work.
- `pro`: stronger difficult-task subagent, roughly Opus/Sol-tier. Use it for complex
  debugging, architecture, difficult multi-file reasoning, or when Flash was
  insufficient.
Do not select Pro merely because it is available; prefer Flash unless the task
clearly benefits from the stronger tier.

Selection: use `delegate_*` when the host can wait for completion. With
`model="pro"`, `delegate_*` starts a background job and returns its `job_id`,
because Pro usually outlasts host tool timeouts (60 s in Claude Desktop); poll
`get_glm_result`. `GLM_PRO_SYNC=1` makes Pro wait instead. Use `start_*`
when it needs steering, status, or cancellation. Use readonly only for pure
reading/search/review of existing files or text when no task step needs a command;
use coding for everything else or uncertainty. The API freezes the capability for
the job. Steering cannot enable Bash or mutation tools: if a readonly job later
needs either, cancel or finish it and create a new coding job.

GLM cannot see host chat or project instructions; pass needed context
explicitly. One OS lease permits one GLM execution per canonical workspace,
but it cannot prevent the host, IDE, or other processes from editing that workspace.
While a coding background job is running, the host should steer, query, or cancel
that job instead of independently mutating the same workspace; resume host-side
edits after the job reaches a terminal state. Background jobs/results are
process-local. New delegation fails closed while recovery records remain.
""".strip()
