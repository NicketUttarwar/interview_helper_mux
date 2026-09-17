# Target Spec — nugget_corpus_mine

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| enabled | LLM corpus ≤2; refuse hollow | Completes/honest |
| disabled | empty stub + warn + heal | Completes |
| LLM exhaust | incomplete | Honest |

## Rules set

- never write QC here
- strip never_touch
- disabled stub OK

## Complexity subtraction

- Demote plan to soft in contract

## Acceptance checks

- ownership QC; disabled heal; ≤2 refuse

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| NCM-B1 | P1 | unambiguous | Drop QC from contract outputs | YAML/ownership | 7 | no |
| NCM-B2 | P1 | needs_you | Empty enabled corpus incomplete? | sufficiency | 2,6 | yes |
| NCM-B3 | P2 | unambiguous | Demote mastering_plan to soft | YAML | 7 | no |

## Defaults inventory impact

- nugget_layup.enabled landmine if false mid-campaign

## target_status

`draft`
