# Target Spec — mastering_shape_agenda

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| soft_gate on, llm off | Heuristic agenda+rubric done | Completes |
| soft_gate off | Schema skip stub done | Completes |
| research thin | incomplete/refuse admit | Blocks until rollup ready |
| LLM fail (if enabled) | Incomplete/refuse (CSP-05) | Blocks until LLM ok or llm off |

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
| B1 | P1 | confirmed | Rubric LLM fail → incomplete (Q2A CSP-05; reverses 2B) | `test_msa_b1_rubric_llm_fail_incomplete` | 2,4 | low (shape.llm default false) |
| B2 | P2 | unambiguous | soft_gate-disabled stub covered by test | pytest | 2 | no |

## Defaults inventory impact

- soft_gate.enable=true; shape.llm=false (heuristic path unchanged)

## target_status

`draft` — Wave 2 MSA-B2 + Q2A CSP-05 rubric LLM fail incomplete
