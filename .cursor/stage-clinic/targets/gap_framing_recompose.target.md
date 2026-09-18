# Target Spec — gap_framing_recompose

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| layup authority | Republish only; accept sidecar; heal | Completes |
| seat freeze | Skip stub done | Completes |
| gap unsanitary | Refuse done | Honest |
| legacy activate | Retired → skip-copy | Completes |

## Rules set

- no OpenAI on default
- never mark done if gap unsanitary
- seat freeze → skip stub

## Complexity subtraction

- Prefer authority path; fix contract lifecycle/consumers

## Acceptance checks

- authority path; freeze sticky; unsanitary refuse

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| GFR-B1 | P0 | unambiguous | Fix contract outputs/consumers/lifecycle | YAML | 7 | no |
| GFR-B2 | P1 | unambiguous | Remove duplicate seat-gate / dead docstring | code | 1 | no |
| GFR-B3 | P1 | unambiguous | Retire legacy activate path — **Wave 2 applied** | intent | 5,7 | yes |
| GFR-B4 | P2 | unambiguous | Pytest authority path | pytest | 2 | no |

## Defaults inventory impact

- authoritative_gap_report=true landmine if flipped mid-run

## target_status

`done` — Wave 2 applied GFR-B1/B2/B3/B4
