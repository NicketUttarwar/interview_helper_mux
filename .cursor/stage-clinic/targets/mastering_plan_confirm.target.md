# Target Spec — mastering_plan_confirm

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| soft_gate on | Pass2 confirmed plan; heal | Completes |
| soft_gate off | Must incomplete or forced confirm — **not silent return** | Honest progress |
| provisional only | confirm-hollow incomplete | Re-runs confirm |
| LLM fail | Heuristic confirm degraded | Completes |

## Rules set

- admit / after gap evals
- incomplete / confirm-hollow + soft_gate-off no-op
- refuse / marking done on provisional

## Complexity subtraction

- Silent soft_gate-off return

## Acceptance checks

- soft_gate-off cannot leave hollow done; HM-1 leftover

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | soft_gate-off: write forced confirmed sparse OR refuse incomplete | pytest | 2,5 | no |
| B2 | P1 | needs_you | Contract consumers list circular cleanup | yaml | 7 | no |

## Defaults inventory impact

- soft_gate.enable=false: Wave 2 MPC-B1 writes forced confirmed sparse (no silent no-op)

## target_status

`draft` — Wave 2 applied MPC-B1; B2 still `needs_you`
