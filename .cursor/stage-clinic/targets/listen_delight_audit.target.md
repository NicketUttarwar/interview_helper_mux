# Target Spec — listen_delight_audit

brain: 0.2.0 | target_status: applied | L3: B1/B2 KEEP (notes); B3 remutate cap applied

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| pass | audit + heal | Completes |
| fail + fail_early=false | persist; continue; ship recheck | Continues |
| fail + fail_early=true | remutate ≤N then loud_fail | Hard stop |
| remutate budget exhausted | sticky exhaust; pick-best; refuse | No thrash |
| aspirational | advisory unless catastrophic | Soft |

## Rules set

- admit / passed or advisory persist
- refuse / loud_fail when blocking or remutate budget exhausted under authoritative
- incomplete / remutate applied needing rewind (attempt ≤ N)
- auto_resolve_default / fail_early=false under Full-auto
- remutate terminate / after N attempts: ship-best then refuse (no infinite thrash)
- **B1 KEEP:** `fail_early_at_audit_stage=false`
- **B2 KEEP:** authoritative ship re-run at `master_finalize`

## Complexity subtraction

- Keep ship authority at master_finalize

## Contract / dependency deltas (proposed)

- Note remutate side effects despite invalidates [] — applied via remutate_note on contract

## Non-goals

- Wave 1 patches; floor tuning as product

## Acceptance checks

- fail_early default; authoritative ship path; remutate exhaust at N=3 from defaults

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK | status |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|--------|
| B1 | P0 | answered | KEEP fail_early=false default | notes only | 5,6 | n/a kept | applied |
| B2 | P0 | answered | KEEP authoritative ship re-run | notes only | 6 | n/a kept | applied |
| B3 | P1 | needs_you→answered | Remutate cap then ship-best/refuse; contract remutate honesty | intent | 1,7 | overridden | applied |

## Defaults inventory impact

- listen_delight.mode=authoritative; fail_early=false; floors; aspirational
- listen_delight.max_remutate_attempts=**3** (finite remutate budget)

## target_status

`applied` — B1/B2 KEEP (notes); B3 remutate cap applied
