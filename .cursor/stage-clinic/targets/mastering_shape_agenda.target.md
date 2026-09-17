# Target Spec — mastering_shape_agenda

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| soft_gate on, llm off | Heuristic agenda+rubric done | Completes |
| soft_gate off | Schema skip stub done | Completes |
| research thin | incomplete/refuse admit | Blocks until rollup ready |
| LLM fail (if enabled) | Heuristic fallback done | Completes |

## Rules set

- admit / soft_gate path or skip stub
- incomplete / HM-1 + A-01
- refuse / N/A require LLM under defaults

## Complexity subtraction

- Dual LLM calls (agenda+rubric) when llm off path unused — leave until llm default flips

## Non-goals

- Turning shape.llm on by default

## Acceptance checks

- Heuristic happy path; skip stub; thin refuse

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P1 | needs_you | Rubric LLM fail → incomplete vs heuristic? | intent | 2,4 | yes if incomplete under defaults |
| B2 | P2 | unambiguous | soft_gate-disabled stub covered by test | pytest | 2 | no |

## Defaults inventory impact

- soft_gate.enable=true; shape.llm=false

## target_status

`draft`
