# Target Spec — edl

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| audit pass + inputs | edl.json | Completes |
| audit fail | hard stop | Honest |
| glue incomplete | incomplete/refuse soft-done | Honest F4 |
| vo unsanitary | pin vo_synthesize | Honest |

## Rules set

- admit / built edl
- refuse / audit fail|layup stale
- incomplete / glue|vo

## Complexity subtraction

- Prefer earlier synth honesty so EDL isn't second synth home — later wave

## Contract / dependency deltas (proposed)

- SDP soft producer → sound_design_plan

## Non-goals

- Wave 1 patches

## Acceptance checks

- F4; audit fail; vo pin

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Keep F4 no soft-complete glue | tests | 2,6 | yes |
| B2 | P1 | unambiguous | Contract SDP producer fix | yaml | 7 | no |

## Defaults inventory impact

- none new

## target_status

`draft`
