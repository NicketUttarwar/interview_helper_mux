# Target Spec — vo_line_adjudicate

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| 0.2.0 + enabled | adjudicate/intro + heal | Completes |
| disabled / no gap | skip stub + heal (not hollow) | Completes honest |
| coverage fail | loud_fail unless intentional fail_open | Honest |
| LLM exhaust | refuse | Honest |

## Rules set

- admit / adjudication or skip stub with reason
- refuse / LLM|coverage
- incomplete / hollow stub without reason

## Complexity subtraction

- Keep skip stubs explicit

## Non-goals

- Wave 1 patches; Chatterbox quality

## Acceptance checks

- HV3 hollow-done; brain skip path

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Keep HV3 hollow-done refuse | tests | 2 | yes |
| B2 | P1 | needs_you | fail_open vs loud_fail Full-auto | intent | 2,5 | yes |

## Defaults inventory impact

- adjudicate_before_synth=true; fail_open landmine

## target_status

`draft`
