# Target Spec — air_script_compose

brain: 0.2.0 | target_status: applied

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| enable + selection | Deterministic Pass A; heal | Completes |
| enable=false | Explicit skip latch + done | Completes |
| Pass A padding omits | Plan/ledger omit only; selection unchanged | Completes |
| hollow VO seats | OK at Pass A (HR-3) | Completes |

## Rules set

- deterministic Pass A; seats deferred to seams
- disabled → skip-done
- ASC-B3: air omits do not shrink `master/selection.json`
- automation fail_closed documented

## Complexity subtraction

- No LLM at Pass A

## Acceptance checks

- HR-3; enable false heal; ASC-B3 selection intact; fail_open automation

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| ASC-B1 | P0 | unambiguous | Contract tier process not llm_full | YAML | 2 | no |
| ASC-B2 | P0 | unambiguous | Disabled path heal/skip-done | air_script.py | 1,3 | yes |
| ASC-B3 | P2 | unambiguous | Pass A omits leave selection alone | compose_pass_a | 7 | no |

## Defaults inventory impact

- `mastering.air_script.enable=true`; automation fail_closed landmine
- ASC-B3: omit no longer mutates selection (air membership ≠ selection shrink)

## Wave 2 apply log

- ASC-B1 + ASC-B2 applied (CONTINUE CSP-01)
- ASC-B3 applied (1B): remove `commit_selection_or_refuse` from `compose_pass_a`; pin `test_asc_b3_pass_a_omits_leave_selection_unchanged`

## target_status

`applied`
