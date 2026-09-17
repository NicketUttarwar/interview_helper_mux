# Target Spec — episode_cover_prompt_craft

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| LLM ok | cover_prompt non-empty valid | Completes |
| LLM fail | harvest non-empty OR incomplete | Prefer progress with honest rejected flag |

## Rules set

- incomplete empty prompt
- keep fail-open harvest (F7) if prompt non-empty

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P1 | unambiguous | Assert non-empty prompt before done | incompleteness | 2 | no |
| B2 | P2 | unambiguous | Contract soft meta | YAML | 7 | no |

## Defaults inventory impact

- none

## target_status

`draft`
