# Target Spec — delivery_brief_build

brain: 0.2.0 | target_status: draft | L3: B1+B2 applied

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| enabled | Deterministic brief done | Completes |
| disabled | Skip stub done | Completes |
| gap_report missing | refuse/incomplete | Honest |

## Rules set

- admit / after gap compose
- incomplete / validator fail
- auto_resolve_default / N/A

## Complexity subtraction

- Circular contract consumer claim on gap_framing_compose

## Acceptance checks

- HG-2 stub; validator required fields

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P2 | unambiguous | Drop circular consumer from contract regen | yaml | 7 | no |
| B2 | P2 | unambiguous | Test hard missing gap_report | pytest | 2 | no |

## Defaults inventory impact

- analysis.delivery_brief.enabled=true

## target_status

`draft`
