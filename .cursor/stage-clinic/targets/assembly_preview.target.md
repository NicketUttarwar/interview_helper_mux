# Target Spec — assembly_preview

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| edl+WAVs | preview.wav + heal | Completes |
| missing VO source | refuse → vo_synthesize | Honest |
| post-assembly edl heal | reopen gate | Fail-closed when sealed |

## Rules set

- admit / wav exists
- refuse / heard_wav
- incomplete / missing wav

## Complexity subtraction

- Keep speech+VO only

## Contract / dependency deltas (proposed)

- hard selection optional/soft

## Non-goals

- Wave 1 patches

## Acceptance checks

- heard_wav; heal mark; music pin

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Keep heard_wav refuse | tests | 2,6 | yes |
| B2 | P1 | unambiguous | Contract selection hard→soft | yaml | 2 | no |

## Defaults inventory impact

- crossfade_ms_assembly_preview; music_deferred pin

## target_status

`draft`
