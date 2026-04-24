# Frontier Dev Codex Bundle

This bundle is a low-knob, Codex-ready handoff for building a local-first multi-Mac development system on top of oMLX.

## What this bundle contains

- `01-architecture.md` — system topology and hard boundaries
- `02-memory-model.md` — global vs localized memory, frontier memory, residual memory
- `03-implementation-spec.md` — the full implementation spec
- `04-api-contracts.md` — conductor and worker API contracts
- `05-codex-handoff-prompt.md` — a direct prompt to give Codex
- `06-build-order-and-acceptance.md` — exact milestone sequence and acceptance criteria
- `07-config-examples.md` — example `.codex/config.toml`, `AGENTS.md`, and service config
- `08-schema-examples.md` — CandidatePlan, FeasibilityCertificate, and memory records

## Design stance

This system is intentionally:
- deterministic around probabilistic models
- low-knob
- frontier-based rather than swarm-based
- safe by default: draft PRs, no auto-merge
- structured in memory rather than transcript-heavy

## V1 boundaries

Do not implement in v1:
- auto-merge to `main`
- SSH-dependent execution
- learned planning metrics
- full Fisher pullback geometry
- arbitrary tuning dashboards
- vector DB dependencies unless SQLite retrieval is clearly too small

## Operational shape

- oMLX = inference/runtime only
- Conductor = planner, memory, orchestration, PR flow
- Workers = local git + test execution only
- Human = final approver
