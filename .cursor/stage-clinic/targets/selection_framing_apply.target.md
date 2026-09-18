# Target Spec — selection_framing_apply

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| ok inputs | apply + heal | Completes |
| seat freeze | skip stub + heal | Continues |
| missing selection | refuse; incomplete | Honest |

## Rules set

- admit / applied
- refuse / missing_selection
- incomplete / pass2 hollow|refuse

## Complexity subtraction

- Keep deterministic

## Contract / dependency deltas (proposed)

- Drop llm_execute; trim unused outputs

## Non-goals

- Wave 1 product patches

## Acceptance checks

- Freeze→heal; validate before selection write

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P1 | unambiguous | Contract match body | xcheck | 2,7 | no |
| B2 | P1 | unambiguous | Refuse never seed-complete | stage_completion | 2 | no |

## Defaults inventory impact

- none

## target_status

`draft` — Wave 2 applied SFA-B1/B2
