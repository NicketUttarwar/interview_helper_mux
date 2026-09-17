# Target Spec — boundary_topic_resplit

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| ideal_cuts bound | Skip + heal (current) | Continue |
| no overload | Cycle stamp + heal | Continue |
| no boundaries at start | Incomplete/refuse — not raw hollow done | Seed walk retries producer |
| wrote-then-lost | Refuse hollow (current HS-2) | Keep |

## Rules set (prefer deterministic)

- admit / overload + boundaries present
- refuse / wrote-then-lost OR missing boundaries (replace mark_done_raw)
- wait_for_gate / N/A
- incomplete / missing boundaries
- precise invalidate / keep bounded unlink of classification/reanchor (no wide clear_from)
- auto_resolve_default / N/A

## Complexity subtraction list

- Remove `_mark_done_raw` hollow skip for missing boundaries

## Contract / dependency deltas (proposed; not applied)

- Align hard brief enforcement with body or demote contract hard→soft with explicit skip rule

## Non-goals

- Widening invalidation fanout
- Always forcing LLM refine

## Acceptance checks

- Missing boundaries → not `.stage_done`
- HS-2 still refuses wrote-then-lost
- Full-auto ideal_cuts skip path unchanged

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| B1 | P1 | unambiguous | Replace hollow mark_done_raw with incomplete/refuse | test_hs2 + new unit | 1,2 | no |
| B2 | P3 | needs_you | Operator: is empty-boundaries skip ever desired? | answer before changing skip UX | 2 | yes if wrong |

## Defaults inventory impact

- Stage-local landmine: hollow skip — remove after B1

## target_status

`draft`
