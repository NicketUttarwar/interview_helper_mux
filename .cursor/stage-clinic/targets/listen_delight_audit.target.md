# Target Spec — listen_delight_audit

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| pass | audit + heal | Completes |
| fail + fail_early=false | persist; continue; ship recheck | Continues |
| fail + fail_early=true | remutate ≤cap then loud_fail | Hard stop |
| aspirational | advisory unless catastrophic | Soft |

## Rules set

- admit / passed or advisory persist
- refuse / loud_fail when blocking
- incomplete / remutate applied needing rewind
- auto_resolve_default / fail_early=false under Full-auto

## Complexity subtraction

- Keep ship authority at master_finalize

## Contract / dependency deltas (proposed)

- Note remutate side effects despite invalidates []

## Non-goals

- Wave 1 patches; floor tuning as product

## Acceptance checks

- fail_early default; authoritative ship path; remutate exhaust

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Keep fail_early=false default | config | 5,6 | yes |
| B2 | P0 | unambiguous | Keep authoritative ship re-run | master_finalize | 6 | yes |
| B3 | P1 | needs_you | Remutate cap / contract invalidates honesty | intent | 1,7 | yes |

## Defaults inventory impact

- listen_delight.mode=authoritative; fail_early=false; floors; aspirational

## target_status

`draft`
