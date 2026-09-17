# Target Spec — selection_order_sanitize

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| sanitary land | commit + heal | Completes |
| unsanitary | refuse mark; raise | Honest |
| missing selection | hard fail | Honest |

## Rules set

- admit only sanitary
- write_committed only
- no LLM

## Complexity subtraction

- Keep deterministic sanitize

## Acceptance checks

- HR-4 dirty-done; heal_or_raise

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| SOS-B1 | P2 | unambiguous | Contract schema null vs selection schema | YAML | 2 | no |

## Defaults inventory impact

- none

## target_status

`draft`
