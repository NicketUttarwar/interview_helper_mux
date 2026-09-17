# Target Spec — transitions

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| LLM ok | guarded transitions persist | Completes |
| LLM exhaust | refuse/incomplete | Honest |
| G1 open/skip | pair freeze stamp | Continues to VO/G1 |
| empty ok? | prefer incompleteness if air needs bridges | needs_you |

## Rules set

- admit / schema+guard ok
- refuse / LLM fail
- incomplete / hollow that breaks edl glue
- precise invalidate / declared list

## Complexity subtraction

- Keep post-filters; avoid dual writers

## Non-goals

- Wave 1 patches; no refine ghost revive

## Acceptance checks

- spoken_copy_guard; pair freeze; no thrash on order repair

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | needs_you | Empty transitions honesty under Full-auto | intent | 2,5 | yes |
| B2 | P1 | unambiguous | Align hard inputs with payload needs | contract | 2 | no |
| B3 | P1 | unambiguous | ADG invalidates match contract | ADG test | 7 | no |

## Defaults inventory impact

- G1 skip → pair freeze landmine for vo_synthesize

## target_status

`draft`
