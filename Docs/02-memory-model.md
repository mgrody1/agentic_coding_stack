# Memory Model

## Principle

Memory is not a giant transcript. It is a layered, structured system.

## Layers

### 1. Global macro memory (authoritative)
Examples:
- architecture invariants
- migration policy
- security rules
- deployment rules
- repo constitution
- high-level coding standards

### 2. Global meso memory (authoritative or semi-authoritative)
Examples:
- auth subsystem recurring regressions
- billing-specific conventions
- frontend review norms
- CI pitfalls in a package

### 3. Global micro memory (task-local factual context)
Examples:
- exact files
- exact tests
- current failing output
- exact logs
- directly related past diffs

### 4. Alias-local mesostatic memory (advisory)
One small compressed state per alias:
- builder
- reviewer
- arbiter

Store:
- recurrent blind spots
- recurrent strengths
- retrieval boosts and penalties
- escalation triggers
- compressed strategy notes

This memory influences retrieval ranking and prompt prefixing, but cannot override hard constraints.

### 5. Pair-local mesostatic memory (advisory)
Start with:
- `builder ↔ reviewer`

Store:
- disagreement patterns
- complementarity patterns
- common failure modes
- when reviewer tends to catch what builder misses

### 6. Frontier memory
Stores a small number of feasible, non-dominated alternatives not chosen.

### 7. Residual memory
Stores surprises:
- expected tests pass but they fail
- reviewer finds a major issue the builder missed
- chosen path later underperforms an unchosen feasible alternative

## Write policy

Always write:
- chosen candidate
- feasibility certificate
- compact decision state summary

Write 1–2 alternatives only if they are:
- feasible
- non-dominated
- materially distinct
- reusable
- not redundant with existing frontier memory

Write residual memory only on surprise.

Write alias/pair memory only when a pattern is stable across repeated runs.

## Candidate coordinate system

Every plan is rotated into a fixed structured representation before comparison or storage.

`CandidatePlan -> [macro, meso, micro, objective, certificate]`

### Macro vector (6 fixed axes in {-1, 0, +1})
1. local patch ↔ cross-cutting change
2. immediate fix ↔ platform/refactor move
3. easy rollback ↔ hard rollback
4. isolated ↔ coupled
5. evidence-backed ↔ speculative
6. exploit-known-pattern ↔ novel-design

### Meso taxonomy (fixed)
- auth
- billing
- api
- schema_data
- frontend
- ci_build
- infra
- security
- observability
- docs_devex
- shared_lib
- tooling

### Micro footprint
- files
- tests
- migration yes/no
- config yes/no
- endpoint yes/no
- env var yes/no

### Objective vector (fixed 5 dimensions)
- correctness_confidence
- reversibility
- locality
- maintainability
- delivery_speed

Keep this as a vector. Do not scalarize in v1.

## Frontier construction

1. Validate candidate JSON.
2. Certify feasibility.
3. Drop infeasible candidates.
4. Pareto-prune on objective vectors.
5. Deduplicate near-identical candidates.
6. Build a simple Gram matrix over survivors.
7. Keep at most 3 medoids.
8. Send only those to the arbiter.
