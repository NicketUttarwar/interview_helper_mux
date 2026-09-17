# Target Spec — nugget_layup_compose

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| happy | plan+gap_report co-publish; QC pass; heal | Completes |
| QC fail | refuse done | Honest |
| mid-shard crash | incomplete (not hollow done) | Honest |
| disabled | stub + heal | Completes |

## Rules set

- selection sanitary first
- plan+gap_report co-publish
- shards merge then heal
- CTA via selection bus only

## Complexity subtraction

- Keep authoritative_gap_report default; no G1 wait here

## Acceptance checks

- QC; shard heal; CTA commit; HG heal pins

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| NLC-B1 | P0 | unambiguous | Incompleteness if mid-shard crash | stage_completion | 2 | no |
| NLC-B2 | P1 | needs_you | Compose-time hard nugget-air floor? | floors | 5,6 | yes |
| NLC-B3 | P1 | unambiguous | Contract hard=selection+corpus; audit soft if shadow | YAML | 7 | no |

## Defaults inventory impact

- nugget_layup floors / authoritative_gap_report landmines

## target_status

`draft`
