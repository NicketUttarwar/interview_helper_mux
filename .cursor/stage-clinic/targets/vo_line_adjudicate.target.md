# Target Spec — vo_line_adjudicate

brain: 0.2.0 | target_status: applied

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| 0.2.0 + enabled | adjudicate/intro + heal | Completes |
| disabled / no gap | skip stub + heal (not hollow) | Completes honest (B1 KEEP HV3) |
| coverage fail | warn + continue when fail_open (default true) | Completes with warning (B2) |
| LLM exhaust | refuse | Honest |

## Rules set

- admit / adjudication or skip stub with reason
- refuse / LLM exhaust
- warn+continue / coverage shortfall when fail_open
- incomplete / hollow stub without reason

## Complexity subtraction

- Keep skip stubs explicit

## Non-goals

- Chatterbox quality

## Acceptance checks

- HV3 hollow-done; fail_open default true pin

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK | L3 |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|-----|
| B1 | P0 | unambiguous | Keep HV3 hollow-done refuse | tests | 2 | yes (KEEP) | documented KEEP |
| B2 | P1 | needs_you→answered | fail_open=true product default | intent | 2,5 | overridden | applied |

## Defaults inventory impact

- `analysis.gap_vo.adjudicate_before_synth=true`
- `analysis.gap_vo.adjudicate_fail_open=true` (shipped)

## target_status

`applied` — Wave 2 CONTINUE: B1 KEEP HV3; B2 fail_open default true
