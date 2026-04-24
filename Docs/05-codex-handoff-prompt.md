# Codex Handoff Prompt

You are implementing a local-first multi-Mac development system called `frontier-dev`.

Read the docs in this bundle and follow them strictly.

## Architectural rules you must not violate

1. oMLX is runtime only. Do not put planning or durable memory logic inside oMLX wrappers.
2. Workers execute code only. Do not let workers decide policy or write durable memory.
3. Keep memory structured. Do not default to storing transcripts or chain-of-thought-like logs.
4. Use fixed candidate roles and fixed objective dimensions in v1.
5. Feasibility is a hard gate, not a score.
6. Frontier construction is:
   - validate
   - feasibility gate
   - Pareto prune
   - dedupe
   - Gram
   - medoid select
   - arbiter
7. Arbiter sees only the filtered frontier in v1, not the whole candidate pool.
8. Draft PR only. No auto-merge.
9. Do not depend on SSH.
10. Minimize knobs. Prefer fixed vocabularies, fixed schemas, and deterministic code paths.

## What to build first

Implement in this exact order:
1. shared Pydantic schemas
2. worker FastAPI skeleton
3. conductor FastAPI skeleton
4. SQLite models and migrations
5. oMLX client wrapper
6. worker client wrapper
7. decision-state assembly
8. memory retrieval pipeline
9. candidate generation
10. feasibility certificates
11. frontier pruning
12. arbiter selection
13. execution loop
14. reviewer loop
15. PR writer
16. frontier/residual memory writes
17. alias/pair memory overlays

## Repo layout to create

```text
frontier-dev/
  apps/
    conductor/
      main.py
      config.py
      db.py
      models.py
      routes/
        health.py
        jobs.py
        memory.py
      services/
        omlx_client.py
        worker_client.py
        decision_state.py
        memory.py
        candidate_generator.py
        feasibility.py
        frontier.py
        arbiter.py
        executor.py
        reviewer.py
        pr_writer.py
        residuals.py
    worker/
      main.py
      config.py
      repo_registry.py
      git_ops.py
      runner.py
      routes.py
  shared/
    schemas.py
    enums.py
    utils.py
  prompts/
    builder/
      minimal_patch.txt
      test_first.txt
      rollback_first.txt
      refactor_first.txt
      architecture_clean.txt
      perf_aware.txt
    reviewer.txt
    arbiter.txt
  docs/
    (copy or adapt from this bundle)
```

## Coding style

- Use Python 3.11+
- Use Pydantic for all wire schemas
- Use small focused modules
- Keep side effects isolated
- Make behavior explicit over clever
- Add docstrings to service entry points
- Add type hints throughout

## First milestone acceptance

Milestone 1 is done only when:
- conductor starts
- worker starts
- SQLite initializes
- `GET /health` works on both
- conductor can call configured oMLX aliases
- conductor can call worker endpoints
