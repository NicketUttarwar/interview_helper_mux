# Target Spec — mastering_plan_synthesize

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| soft_gate on, llm off | Provisional degraded plan always written | Completes |
| no candidates | forced_sparse | Completes |
| shape.llm on success | may claim complete | Completes |
| consumers_bind false | Downstream treats advisory | Completes |

## Rules set

- admit / after candidates
- incomplete / A-01 thin
- refuse / never claim soft_gate complete (A-03)
- auto_resolve_default / N/A

## Complexity subtraction

- None until bind shadow passes

## Contract deltas

- Soft gap_evaluations timing note (after synthesize)

## Non-goals

- Flipping consumers_bind true without inventory

## Acceptance checks

- A-03 claim_plan_complete soft_gate→degraded; write always

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Preserve soft_gate never complete | A-03 tests | 2,6 | no |
| B2 | P1 | needs_you | consumers_bind flip criteria | inventory | 5,6 | yes |

## Defaults inventory impact

- soft_gate.consumers_bind=false; two_pass=true

## target_status

`draft`
