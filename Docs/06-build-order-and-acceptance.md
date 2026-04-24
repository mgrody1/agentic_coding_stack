# Build Order and Acceptance Criteria

## Milestone 1 — skeleton
Deliver:
- conductor FastAPI app
- worker FastAPI app
- SQLite schema bootstrap
- oMLX client wrapper
- worker client wrapper
- health endpoints

Acceptance:
- all services start locally
- conductor sees all configured endpoints
- worker can report health
- DB initializes cleanly

## Milestone 2 — decision state + retrieval
Deliver:
- decision state assembly
- lexical retrieval
- embedding retrieval
- rerank pipeline

Acceptance:
- given a sample issue, conductor builds a decision state and returns ranked memory hits

## Milestone 3 — candidate generation + feasibility
Deliver:
- fixed role prompts
- CandidatePlan schema validation
- FeasibilityCertificate generation

Acceptance:
- conductor generates 6 candidates
- infeasible candidates are rejected with explicit reasons

## Milestone 4 — frontier + arbiter
Deliver:
- Pareto pruning
- simple Gram construction
- medoid selection
- arbiter choice/synthesis path

Acceptance:
- arbiter sees at most 3 candidates
- arbiter response validates against schema
- synthesized plans are recertified

## Milestone 5 — execution + review
Deliver:
- builder execution loop
- lint/type/test integration
- reviewer critique
- one repair cycle

Acceptance:
- selected plan can be implemented on a worktree
- diff and test outputs are captured
- reviewer can block or approve
- repair loop runs once

## Milestone 6 — draft PR + memory writes
Deliver:
- draft PR creation
- chosen-plan memory write
- frontier memory write
- residual write on surprise

Acceptance:
- system opens a draft PR with summary, risks, rollback note, test evidence, and reviewer objections/resolution
- memory records are stored cleanly

## Milestone 7 — localized memory overlays
Deliver:
- alias memory state
- pair memory state
- retrieval overlay logic

Acceptance:
- repeated role- or pair-specific patterns influence retrieval/prompt prefixing
- hard feasibility rules remain unchanged
