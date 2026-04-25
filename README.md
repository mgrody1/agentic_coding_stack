# Agentic Coding Stack (Frontier Dev)

Local-first multi-Mac orchestration scaffold built milestone-by-milestone.

## Current implementation status

Implemented orchestration shape:
- **Milestone 1**: shared schemas/config, conductor and worker FastAPI skeletons, SQLite models/bootstrap, oMLX/worker wrappers, health endpoints.
- **Milestone 2**: decision-state assembly and retrieval pipeline (SQLite FTS lexical + oMLX embedding + oMLX rerank).
- **Milestone 3**: fixed-role candidate generation (6 builder roles), schema validation, feasibility certificates and gating.
- **Milestone 4**: frontier pruning (Pareto non-dominated, dedupe, Gram similarity, medoids `k<=3`), arbiter decision contract, synthesis recertification.
- **Milestone 5**: execution/review loop for one selected candidate with explicit stage machine, one repair cycle max, and structured artifact capture.
- **Milestone 6**: draft PR payload composition and deterministic memory writes with explicit package semantics:
  - `completed` execution: draft payload + canonical memory persistence (`chosen_memory`, `frontier_memory`, `residual_memory` as applicable).
  - `blocked` / `failed` execution: draft payload only (no canonical `chosen_memory` persistence).
  - in-progress execution statuses: package request is rejected.

Implemented in Milestone 7A:
- localized alias-local and pair-local overlay state records.
- overlay-aware retrieval filtering/ranking by active alias/pair and repo/task context.
- overlay-aware candidate prompt assembly with explicit precedence:
  - global constraints > global memory > alias-local overlay > pair-local overlay.

Implemented in Milestone 7B:
- bounded one-shot conductor-driven repair loop using worker-safe read/write/reset primitives.
- repair result states: `repaired_and_passed`, `repaired_but_still_blocked`, `repair_failed`.
- explicit repair diff artifact requirement and deterministic terminal status on repair failure.

Implemented in Milestone 8:
- explicit idempotency/replay handling for execute/package routes.
- structured low-cardinality telemetry events with stable cause codes.
- JSON round-trip hardening for persisted execution/package/overlay payloads.
- operator-facing diagnostics for replayed/blocked/failed execution and package outcomes.

Not implemented yet:
- **Milestone 9+** richer autonomous planning controls and extended orchestration hardening.

Implemented in Milestone 9:
- bounded operator controls for cancel, retry, and resume-from-checkpoint.
- explicit separation of replay vs retry vs resume semantics in API behavior.
- telemetry summary endpoint with low-cardinality grouped buckets.
- invariant report endpoint for execution/package/memory/telemetry consistency checks.

## Worker realism boundary (current)

- Worker endpoints are intentionally policy-free execution primitives (repo/file/command/git actions only).
- Repair is conductor-driven and bounded to exactly one real modification attempt using worker file primitives. Worker remains policy-free.
- This repository therefore demonstrates orchestration contracts and state transitions, but not a production-grade self-healing implementation path.

## Remaining blockers before realistic end-to-end loop

- PR flow remains draft-payload composition only; no live provider-side PR mutation/orchestration.
- Milestone 10 should harden policy/governance controls around operator actions and long-lived workflows.

## Architecture boundaries

- oMLX is runtime/model serving only.
- Conductor owns orchestration, memory retrieval/writes, frontier selection, and arbiter coordination.
- Workers execute repo/file/command/git actions only (policy-free).
- Objective vectors remain vector-valued (no weighted scalar collapse).
- No SSH dependency.

## Services

### Conductor (`apps/conductor/main.py`)
- `GET /health`
- `POST /jobs`
- `GET /jobs/{id}`
- `POST /jobs/{id}/execute`
- `GET /jobs/{id}/execution-state`
- `POST /jobs/{id}/package`
- `POST /decision-state/build`
- `POST /memory/query`
- `POST /memory/ingest`
- `POST /candidates/generate`
- `POST /frontier/build`
- `POST /arbiter/decide`

### Worker (`apps/worker/main.py`)
- `GET /health`
- `POST /repo/prepare`
- `POST /repo/reset`
- `POST /artifact/read_file`
- `POST /artifact/write_file`
- `POST /run/command`
- `POST /run/lint`
- `POST /run/typecheck`
- `POST /run/tests`
- `POST /git/diff`
- `POST /git/commit`
- `POST /git/push`

## Security and safety currently enforced

- Bearer auth required for all conductor and worker endpoints.
- Worker repo allowlist enforcement.
- Worker command allowlist enforcement.
- Worker path traversal protection for file read/write.

## Development notes

Environment variables (key examples):
- `FRONTIER_API_TOKEN`
- `FRONTIER_WORKER_TOKEN`
- `FRONTIER_DB_URL`
- `FRONTIER_ALLOWED_REPOS`
- `FRONTIER_ALLOWED_COMMANDS_JSON`
- `FRONTIER_OMLX_*_URL`

## Tests

Tests are under `tests/` and cover schema/config, client wrappers, health/auth checks, candidate/feasibility/frontier/arbiter behavior, retrieval ingestion, and worker safety rejections.
