# Agentic Coding Stack (Frontier Dev)

Local-first multi-Mac orchestration scaffold built milestone-by-milestone.

## Current implementation status

Implemented and stabilized:
- **Milestone 1**: shared schemas/config, conductor and worker FastAPI skeletons, SQLite models/bootstrap, oMLX/worker wrappers, health endpoints.
- **Milestone 2**: decision-state assembly and retrieval pipeline (SQLite FTS lexical + oMLX embedding + oMLX rerank).
- **Milestone 3**: fixed-role candidate generation (6 builder roles), schema validation, feasibility certificates and gating.
- **Milestone 4**: frontier pruning (Pareto non-dominated, dedupe, Gram similarity, medoids `k<=3`), arbiter decision contract, synthesis recertification.
- **Milestone 5**: execution/review loop for one selected candidate with explicit stage machine, one repair cycle max, and structured artifact capture.
- **Milestone 6**: draft PR payload composition and deterministic memory writes for chosen/frontier/residual records with rule-based surprise detection.

Not implemented yet:
- **Milestone 7+** localized alias/pair overlays and overlay-aware retrieval/prompting.

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
