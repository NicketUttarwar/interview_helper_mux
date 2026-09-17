# Target Spec — junction_snip_qa

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| post-mix clean | commitment==live assembly; no critical incomplete | Completes |
| live incomplete before mix | Recut-first; then mix | Progresses |
| remaster budget exhaust | classified remediation / refuse — not infinite | Terminates |
| feel LLM fail | soft_pass or one remaster then settle | ≤2 attempts |

## Rules set

- never seed-complete without commitment seal
- never mix with live incomplete criticals
- refuse oscillation identical applied_sig
- precise invalidate assembly on remaster only
- auto_resolve g_listen Full-auto (needs_you — shared with mix)

## Complexity subtraction

- Rename advisory→authoritative or document dual meaning
- Cap feel-driven remaster; prefer deterministic detect for criticals

## Acceptance checks

- junction_recut_precedes_mix golden
- commitment incompleteness
- e2e_soft does not clear critical incomplete
- oscillation halt terminates

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Mode label vs blocking semantics docs/config | rename or doc | 2 | no |
| B2 | P0 | unambiguous | Thrash golden mix⇄junction | tests | 1 | no |
| B3 | P0 | needs_you | Full-auto osc/budget: remediation vs needs_operator | stall policy | 3 | yes |
| B4 | P1 | unambiguous | Contract selection hard vs `_check` | align | 7 | no |

## Defaults inventory impact

- junction mode advisory; max_remaster_rounds=2; commitment_blocks_finalize — landmines with g_listen

## target_status

`draft`
