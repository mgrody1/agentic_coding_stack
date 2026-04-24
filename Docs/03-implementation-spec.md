# Implementation Spec

## Purpose

Build a local-first multi-Mac development system that:
- uses oMLX only as the model/runtime layer
- uses a separate conductor for orchestration
- generates diverse candidate plans
- filters them against macro, meso, and micro memory
- selects from a small feasible frontier
- implements code changes on worker machines
- runs independent review before opening draft PRs
- stores standard, frontier, and residual memory without turning memory into a giant transcript

## Non-goals

Do not implement in v1:
- auto-merge to `main`
- general autonomous merge bot behavior
- learned planning metrics
- RL or self-play loops
- dynamic role creation
- SSH-required execution
- vector DB dependency unless SQLite retrieval becomes a real bottleneck
- arbitrary tuning dashboards

## Hard architectural boundaries

### 1. oMLX is runtime, not planner
oMLX is responsible for:
- serving LLM/VLM/embedding/rerank models
- aliases
- model loading and unloading
- cache behavior
- API compatibility

The conductor is responsible for:
- memory retrieval and writes
- candidate generation flow
- feasibility filtering
- frontier pruning
- worker assignment
- PR creation
- outcome tracking

### 2. Workers execute code; they do not decide policy
Workers are responsible for:
- worktree creation
- file reads and writes
- repo commands
- git operations
- artifact collection

Workers must not:
- decide whether a change is acceptable
- select a plan
- write durable memory
- open PRs

### 3. Memory is structured, not conversational
Store:
- architecture rules
- recurring subsystem patterns
- prior successful strategies
- feasible alternatives not chosen
- surprises and regret updates

Do not store:
- raw full prompts by default
- every intermediate thought
- repeated summaries of the same repo fact

## Services

### Conductor service
Suggested stack:
- FastAPI
- Pydantic
- SQLAlchemy/SQLModel
- SQLite initially

Responsibilities:
- receive jobs from webhook / API / manual queue
- construct decision state
- retrieve memory
- generate candidate plans
- request feasibility checks
- prune frontier
- call arbiter
- dispatch implementation to workers
- request independent review
- write memory updates
- open / update draft PRs

### Worker service
Suggested stack:
- FastAPI
- subprocess
- path allowlists
- command allowlists
- launchd on macOS

Responsibilities:
- create worktrees
- reset/clean worktrees
- read and write files
- run repo-specific commands
- create commits
- push branches
- collect diffs and artifacts

### Memory service
Can be part of the conductor initially.

Responsibilities:
- embeddings via oMLX
- lexical retrieval via SQLite FTS5
- dense retrieval via cosine similarity
- rerank via oMLX
- memory write gating
- localized memory overlays

## Candidate generation

### Default generation policy
For each decision state:
1. Ask `builder` for 6 candidates using fixed role prompts.
2. Optionally ask `reviewer` for 1–2 more only if triggered.
3. Do not ask `arbiter` to bulk-generate by default.

### Fixed builder roles
- minimal_patch
- test_first
- rollback_first
- refactor_first
- architecture_clean
- perf_aware

### Reviewer candidate triggers
Use reviewer-generated alternatives only if:
- task crosses multiple subsystems
- frontend/UI significance is high
- builder candidates are too similar
- uncertainty is high
- previous similar tasks produced regressions

## Feasibility certification

Every candidate must receive a certificate.

Fields:
- macro_pass
- meso_pass
- micro_pass
- lint_plan_valid
- test_plan_valid
- rollback_plan_valid
- migration_policy_pass
- security_policy_pass
- scope_policy_pass
- notes

Feasibility is a gate, not a score.

## Frontier construction

Pipeline:
1. Validate candidate structure.
2. Build feasibility certificates.
3. Drop infeasible candidates.
4. Pareto-prune by objective vector.
5. Deduplicate near-identical candidates.
6. Build Gram matrix over survivors.
7. Select at most 3 medoids.
8. Send those to the arbiter.

### Pareto rule
A dominates B if A is at least as good on all objective dimensions and strictly better on at least one.

### Similarity rule
Use block-normalized concatenation of:
- macro vector
- meso vector
- micro vector
- objective vector

No learned weights in v1.

## Arbiter contract

Arbiter receives:
- compact decision-state summary
- frontier candidates only
- feasibility certificates
- objective vectors
- contrastive differences between frontier members

Arbiter may:
- choose one candidate
- propose a synthesis
- reject all

If a synthesis is proposed, convert it back into CandidatePlan format and recertify it before execution.

## Execution workflow

1. Job enters conductor.
2. Conductor assembles decision state.
3. Memory retrieval runs.
4. Candidate plans are generated.
5. Feasibility and frontier pruning run.
6. Arbiter chooses or synthesizes.
7. Selected plan is dispatched to builder worker.
8. Builder implements on a worktree branch.
9. Builder runs lint/type/tests.
10. Reviewer inspects issue + diff + changed files + test results.
11. Builder repairs if reviewer blocks.
12. Conductor opens or updates a draft PR.
13. Memory write occurs.
14. Outcome memory updates later.

## Security and operational rules

- All services stay on Tailscale/private network.
- Every service requires bearer auth.
- Workers only allow approved repo roots.
- Workers only allow approved commands.
- Conductor stores secrets outside the repo.
- GitHub integration uses minimal token scope.
