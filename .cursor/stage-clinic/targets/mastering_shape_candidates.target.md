# Target Spec — mastering_shape_candidates

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| defaults | ≥1 heuristic candidate done | Completes |
| LLM empty | Heuristic survivors | Completes |
| soft_gate off | Empty stub skipped done | Completes |

## Rules set

- admit / after agenda
- incomplete / HM-1 + A-01
- never block Full-auto waiting on LLM candidates

## Complexity subtraction

- Diversity path off by default — keep skip

## Acceptance checks

- Forced sparse when empty modes

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P2 | unambiguous | Test forced sparse survivor | pytest | 1 | no |
| B2 | P1 | needs_you | Require LLM candidates only if shape.llm on + no fallback? | intent | 4,5 | yes |

## Defaults inventory impact

- skip_diversity=true

## target_status

`draft`
