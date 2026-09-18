# Target Spec — gap_report_sanitize

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| sanitary land | heal | Completes |
| unsanitary | refuse | Honest |
| missing report | stub then sanitize (or incomplete if decided) | Documented |

## Rules set

- W1 only; refuse unsanitary
- hash-change invalidate VO/EDL markers
- never require plan

## Complexity subtraction

- Fix contract hard/consumers/invalidates claims

## Acceptance checks

- precision invalidation; hollow seed sanitary

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| GRS-B1 | P0 | unambiguous | Fix contract hard+consumers | YAML | 7 | no |
| GRS-B2 | P1 | answered | Empty stub incomplete when framing Yes | honesty | 2,6 | yes (accepted) | applied |
| GRS-B3 | P2 | unambiguous | Document invalidate cascade in contract | YAML | 7 | no |

## Defaults inventory impact

- none new

## target_status

`draft` — Wave 2 CONTINUE: GRS-B2 applied (empty stub incomplete framing Yes)
