# Target Spec — master_transcript_build

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| wav+edl+cues | transcript pack | Completes |
| empty cues | refuse incomplete | Honest fail |

## Rules set

- incomplete empty cues/VTT
- refuse missing wav/edl

## Complexity subtraction

- Align schema sufficiency with HPUB-3
- Clarify inline rebuild from publish as intentional or single producer

## Acceptance checks

- HPUB-3 hollow refuse
- ADG invalidate consumers

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P1 | unambiguous | Contract sufficiency min≥1 | schema/YAML | 2 | no |
| B2 | P2 | needs_you | Dual producer publish inline rebuild | ownership | 7 | no |

## Defaults inventory impact

- none

## target_status

`draft`
