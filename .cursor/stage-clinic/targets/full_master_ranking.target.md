# Target Spec — full_master_ranking

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| QC pass + inputs | selection ordered≥1; heal | Completes |
| empty ordered | refuse / incomplete | Honest |
| QC fail strict | Hard stop (document) | Fail loud |
| last envelope salvage | Prefer recover over hollow | Completes |

## Rules set

- require ordered≥1
- QC gate documented
- lattice seal; story_health warn fail-open
- salvage last envelope

## Complexity subtraction

- Keep specialists; avoid new operator waits

## Acceptance checks

- persistable selection; HR lattice; QC strict path

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| FMR-B1 | P0 | unambiguous | Fix contract hard to match checker | YAML | 2 | no |
| FMR-B2 | P1 | needs_you | Full-auto QC-fail policy (strict vs soft) | gates defaults | 3,5 | yes |

## Defaults inventory impact

- `narrative_qc.strict=true` landmine

## target_status

`draft`
