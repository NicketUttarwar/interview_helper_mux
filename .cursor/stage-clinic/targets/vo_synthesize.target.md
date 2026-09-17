# Target Spec — vo_synthesize

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| Chatterbox synth ok | WAVs + report + hard freeze + done | Completes |
| missing seated/G1 WAV | incomplete; never done-without-wav | Honest |
| record-required | gate needs_operator | Stall honest |
| optional skip hollow | refuse seed | Honest (HV4) |

## Rules set

- admit / seated rendered + pairs ok + freeze
- refuse / freeze fail
- wait_for_gate / G1 record
- incomplete / missing WAV|G1|unsanitary

## Complexity subtraction

- TTS model quality out of clinic; keep host honesty

## Contract / dependency deltas (proposed)

- hard: add master/transitions.json

## Non-goals

- Chatterbox quality tuning; Wave 1 patches

## Acceptance checks

- done-without-wav impossible; HV4/HV5; hard freeze

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Keep done-without-wav refuse | incompleteness | 2,6 | yes |
| B2 | P0 | unambiguous | Contract hard += transitions | yaml | 2 | no |
| B3 | P0 | needs_you | Full-auto record-line policy | intent | 3,5 | yes |

## Defaults inventory impact

- G1 optional + chatterbox_owned automation; optional skip landmine

## target_status

`draft`
