# Target Spec — sound_design_vo_finalize

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| bridges measured | SDP adjust + heal | Completes |
| missing WAV | refuse; incomplete | Honest |
| no cues | skip + heal | Completes |
| no SDP | refuse → pin sound_design_plan | Honest |

## Rules set

- admit / adjusted|skip
- refuse / missing WAV|no SDP
- incomplete / refused sidecar

## Complexity subtraction

- Keep C-02 no hollow finalize

## Contract / dependency deltas (proposed)

- hard += sound_design_plan; review invalidates

## Non-goals

- Wave 1 patches

## Acceptance checks

- HV6; missing WAV no heal

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Keep refuse-without-heal on missing WAV | HV6 | 2 | yes |
| B2 | P1 | unambiguous | Contract hard += SDP | yaml | 2 | no |
| B3 | P1 | needs_you | Trim invalidates of vo_line_adjudicate? | intent | 7 | yes |

## Defaults inventory impact

- none new

## target_status

`draft`
