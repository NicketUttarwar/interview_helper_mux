# Target Spec — refinement_agenda

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| confirm phase | Always persist agenda; empty OK | Completes |
| gap unsanitary | Refuse agenda (dirty present) | Honest refuse |
| missing gap | Soft continue (RA-B1) | Completes |

## Rules set

- confirm phase in seed walk
- always persist; empty eligible OK
- cold_open may open class

## Complexity subtraction

- Demote gap_report to soft in contract

## Acceptance checks

- force heal; confirm ranking hole injection

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| RA-B1 | P1 | unambiguous | Demote gap_report to soft | YAML | 7 | no |
| RA-B2 | P2 | unambiguous | Block agenda when gap unsanitary — **Wave 2 applied** | honesty | 2,7 | yes |
| RA-B3 | P2 | unambiguous | Test confirm ranking hole injection | pytest | 5 | no |

## Defaults inventory impact

- refinement_passes.enabled landmine for Pass-2 no-op

## target_status

`done` — Wave 2 applied RA-B1 + RA-B2 + RA-B3
