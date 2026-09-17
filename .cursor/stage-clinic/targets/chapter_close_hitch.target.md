# Target Spec — chapter_close_hitch

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| enabled + narrative | One-shot latch after remap/inner walk | Completes |
| disabled / no plan | Skip-commit latch + heal | Completes |
| layup adopt fail | Incomplete; no hollow done | Honest |
| post Phase A reopen | Remap-only | Continues |

## Rules set

- one-shot latch; refuse done on adopt fail
- skip-commit when disabled/no plan
- precise invalidate hitch profiles only

## Complexity subtraction

- Drop llm_execute from contract lifecycle claim

## Acceptance checks

- latch status; restage caps; no GUI wait

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| CCH-B1 | P0 | unambiguous | Drop llm_execute from contract lifecycle | YAML | 2 | no |
| CCH-B2 | P1 | needs_you | narrative_plan write authority hitch vs narrative | ownership | 7 | yes |

## Defaults inventory impact

- `mastering.chapter_close_hitch.enabled=true` landmine if mid-run disable

## target_status

`draft`
