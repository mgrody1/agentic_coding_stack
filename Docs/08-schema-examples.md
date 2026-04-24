# Schema Examples

## CandidatePlan

```json
{
  "title": "minimal patch in auth middleware",
  "summary": "Patch token refresh edge case without schema changes",
  "role": "minimal_patch",
  "macro_vec": [-1, -1, 1, -1, 1, -1],
  "meso_tags": ["auth", "api"],
  "micro_targets": {
    "files": ["src/auth/middleware.ts", "tests/auth_refresh.test.ts"],
    "tests": ["tests/auth_refresh.test.ts"],
    "migration": false,
    "config": false,
    "endpoint": true,
    "env_var": false
  },
  "objective_vec": {
    "correctness_confidence": 0.82,
    "reversibility": 0.95,
    "locality": 0.93,
    "maintainability": 0.66,
    "delivery_speed": 0.91
  },
  "rollback_plan": "revert single commit",
  "test_plan": [
    "tests/auth_refresh.test.ts",
    "tests/api_session_expiry.test.ts"
  ],
  "implementation_outline": [
    "add guard for stale refresh token path",
    "preserve existing auth middleware contract",
    "add regression test"
  ],
  "risk_notes": [
    "touches auth session edge case",
    "verify no change to token issuance semantics"
  ]
}
```

## FeasibilityCertificate

```json
{
  "macro_pass": true,
  "meso_pass": true,
  "micro_pass": true,
  "lint_plan_valid": true,
  "test_plan_valid": true,
  "rollback_plan_valid": true,
  "migration_policy_pass": true,
  "security_policy_pass": true,
  "scope_policy_pass": true,
  "notes": [
    "No schema change",
    "Rollback is single-commit revert",
    "Tests cover touched auth path"
  ]
}
```

## AliasMemoryState

```json
{
  "alias_name": "builder",
  "scope": "repo_role",
  "repo": "example-repo",
  "recurrent_blind_spots": [
    "underweights rollback notes for schema-touching tasks"
  ],
  "recurrent_strengths": [
    "strong on small localized auth fixes"
  ],
  "retrieval_rank_boosts": [
    "rollback playbooks when migration=true"
  ],
  "retrieval_rank_penalties": [
    "broad refactor examples for hotfix tasks"
  ],
  "compressed_strategy_state": "Prefer low-scope rollback-safe options for hotfixes."
}
```

## PairMemoryState

```json
{
  "alias_a": "builder",
  "alias_b": "reviewer",
  "scope": "repo_pair",
  "repo": "example-repo",
  "disagreement_patterns": [
    "builder minimal-patch plans often omit migration notes",
    "reviewer frequently blocks cross-subsystem changes without rollback sections"
  ],
  "complementarity_patterns": [
    "reviewer catches auth edge-case tests the builder misses"
  ],
  "trusted_escalation_conditions": [
    "if migration=true and rollback_plan is short or vague, escalate"
  ],
  "common_failure_modes": [
    "tests pass locally but release note / migration risk is under-described"
  ],
  "compressed_pair_state": "When schema_data is involved, reviewer objections get high priority."
}
```

## FrontierMemory record

```json
{
  "chosen_candidate_id": "cand_003",
  "alternative_candidate_id": "cand_005",
  "relation_type": "feasible_unchosen",
  "contrastive_delta": "Alternative used refactor-first strategy; chosen plan stayed local and faster.",
  "win_conditions": "Prefer alternative if auth middleware requires a broader cleanup next sprint.",
  "objective_delta": {
    "correctness_confidence": 0.02,
    "reversibility": -0.11,
    "locality": -0.22,
    "maintainability": 0.18,
    "delivery_speed": -0.27
  }
}
```
