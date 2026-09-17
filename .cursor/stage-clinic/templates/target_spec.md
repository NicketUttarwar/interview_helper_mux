# Target Spec — {{STAGE_ID}}

brain: 0.2.0 | target_status: not_started  
Wave 2 may implement `unambiguous` rows without further operator input.
# After a real L2 write, set target_status to draft (or needs_you / approved).

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| | | |

## Rules set (prefer deterministic)

- admit /
- refuse /
- wait_for_gate /
- incomplete /
- precise invalidate /
- auto_resolve_default /

## Complexity subtraction list

- 

## Contract / dependency deltas (proposed; not applied)

- 

## Non-goals

- 

## Acceptance checks

- 

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| B1 | P0 | unambiguous | | | 1-6 | no |

## Defaults inventory impact

- Rows touched in `defaults_inventory.md`: none | list:

## target_status

`not_started` | `draft` | `needs_you` | `approved`
