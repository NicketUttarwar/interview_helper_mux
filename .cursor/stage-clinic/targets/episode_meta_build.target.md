# Target Spec — episode_meta_build

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| selection+LLM | real title/description | Completes |
| LLM fail | refuse incomplete | Honest |
| empty selection | refuse or incomplete | No Untitled lie |

## Rules set

- incomplete Untitled / empty description
- refuse LLM exhaust
- hard-require selection (align contract)

## Complexity subtraction

- Drop Untitled soft-success or mark advisory

## Acceptance checks

- ≤2 attempts; no hollow done; denylist

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | needs_you | Untitled fallback policy | product | 2,4 | yes |
| B2 | P1 | unambiguous | Align hard selection | contract+body | 7 | no |
| B3 | P2 | unambiguous | Stop transcript→meta ADG invalidate | ADG | 7 | no |

## Defaults inventory impact

- none

## target_status

`draft`
