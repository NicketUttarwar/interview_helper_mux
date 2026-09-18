# Target Spec — junction_snip_qa

brain: 0.2.0 | target_status: applied

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| post-mix clean | commitment==live assembly; no critical incomplete | Completes |
| live incomplete before mix | Recut-first; then mix | Progresses |
| remaster budget / osc exhaust | classified pin + refuse terminate when critical residuals; **no** `needs_operator` hang | Terminates honest / ladders then refuse |
| feel LLM fail | soft_pass or one remaster then settle | ≤2 attempts |

## Rules set

- never seed-complete without commitment seal
- never mix with live incomplete criticals
- refuse oscillation identical applied_sig
- precise invalidate assembly on remaster only
- auto_resolve g_listen Full-auto (shared with mix)
- **B3:** budget/osc exhaust → classified remediation / refuse terminate — **NO** `needs_operator` hang (operator rebind 2026-09-17)

## Complexity subtraction

- Rename advisory→authoritative or document dual meaning
- Cap feel-driven remaster; prefer deterministic detect for criticals

## Acceptance checks

- junction_recut_precedes_mix golden
- commitment incompleteness
- e2e_soft does not clear critical incomplete
- oscillation halt terminates without needs_operator
- `junction_budget_exhaust_hard_pin` sets classified flags only

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Mode label vs blocking semantics docs/config | rename or doc | 2 | no |
| B2 | P0 | unambiguous | Thrash golden mix⇄junction | tests | 1 | no |
| B3 | P0 | answered | classified refuse on osc/budget (no needs_operator) | hard_pin + markers + pytest | 3 | applied |
| B4 | P1 | unambiguous | Contract selection hard vs `_check` | align | 7 | no |

Wave 2 (2026-09-17): applied B1/B2/B4. CONTINUE rebind: B3 classified refuse (code).

## Defaults inventory impact

- junction mode advisory; max_remaster_rounds=2; commitment_blocks_finalize — landmines with g_listen
- B3: Full-auto osc/budget → classified refuse terminate (no human stall)

## target_status

`applied` — B1/B2/B3/B4 closed
