# Architecture

## Machine roles

### M4 Pro mini
Runs:
- conductor service
- scheduler
- GitHub webhook receiver
- memory service
- SQLite database
- local oMLX aliases for embeddings and rerank

### Mac Studio M2 128GB
Runs:
- oMLX `builder`
- optional oMLX `scout`
- worker service
- primary repo worktrees
- lint, typecheck, and test execution

### MBP M3 Max 128GB
Runs:
- oMLX `reviewer`
- optional `review-scout`
- worker service
- optional second execution sandbox
- screenshot / UI review support later if needed

### Mac Studio M3 Ultra 512GB
Runs:
- oMLX `arbiter`
- optional `architect` later
- heavy-context planning, arbitration, synthesis

## Service boundaries

### oMLX responsibilities
- model serving
- aliases
- TTL / loading
- embeddings
- rerank
- cache behavior
- OpenAI-compatible API surface

### Conductor responsibilities
- job intake
- decision-state assembly
- memory retrieval
- candidate generation workflow
- feasibility filtering
- frontier pruning
- arbiter calls
- builder/reviewer orchestration
- PR opening and updates
- memory writes
- regret / residual updates

### Worker responsibilities
- prepare worktree
- read and write files
- run approved commands
- produce diffs
- commit and push branches
- report results

Workers must not decide policy, select plans, or write durable memory directly.

## Networking

Use Tailscale-only HTTP in v1.

Recommended endpoints:
- conductor: `http://mini:8710`
- worker (M2): `http://m2studio:8720`
- worker (MBP): `http://mbp:8720`
- oMLX (mini): `http://mini:8000/v1`
- oMLX (M2): `http://m2studio:8000/v1`
- oMLX (MBP): `http://mbp:8000/v1`
- oMLX (Ultra): `http://ultra:8000/v1`

All services require bearer auth and stay private to the tailnet.

## Model aliases

### Mini
- `mem-embed`
- `mem-rerank`

### M2
- `builder`
- optional `scout`

### MBP
- `reviewer`
- optional `review-scout`

### Ultra
- `arbiter`

## Core workflow

1. Job enters conductor.
2. Conductor assembles `DecisionState`.
3. Memory retrieval runs.
4. Builder generates fixed-role candidates.
5. Feasibility filters drop invalid plans.
6. Frontier pruning keeps a small feasible set.
7. Arbiter selects or synthesizes from that set.
8. Builder implements selected plan on a worktree.
9. Reviewer critiques the diff independently.
10. Builder repairs if blocked.
11. Conductor opens/updates a draft PR.
12. Memory writes occur.
13. Later outcomes update residual/regret memory.
