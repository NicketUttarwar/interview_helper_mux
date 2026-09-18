# Target Spec — vo_synthesize

brain: 0.2.0 | target_status: applied

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| Chatterbox synth ok | WAVs + report + hard freeze + done | Completes |
| missing seated/G1 WAV | incomplete; never done-without-wav | Honest (B1 KEEP) |
| record-required (manual/partial) | gate needs_operator | Stall honest |
| record-required (Full-auto) | rewrite → synthesize; automation_pending | Completes (B3) |
| optional skip hollow | refuse seed | Honest (HV4) |

## Rules set

- admit / seated rendered + pairs ok + freeze
- refuse / freeze fail
- wait_for_gate / G1 record (non-Full-auto only)
- incomplete / missing WAV|G1|unsanitary
- Full-auto / rewrite record→synth then close via synth path

## Complexity subtraction

- TTS model quality out of clinic; keep host honesty

## Contract / dependency deltas (proposed)

- hard: add master/transitions.json — applied (B2)

## Non-goals

- Chatterbox quality tuning

## Acceptance checks

- done-without-wav impossible; HV4/HV5; hard freeze; VS-B3 Full-auto rewrite pins

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK | L3 |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|-----|
| B1 | P0 | unambiguous | Keep done-without-wav refuse | incompleteness | 2,6 | yes (KEEP) | documented KEEP |
| B2 | P0 | unambiguous | Contract hard += transitions | yaml | 2 | no | applied |
| B3 | P0 | needs_you→answered | Full-auto record-line → synth | intent | 3,5 | overridden | applied |

## Defaults inventory impact

- G1 optional + chatterbox_owned automation; Full-auto rewrites residual record lines
- optional skip landmine unchanged

## target_status

`applied` — Wave 2 CONTINUE: B1 KEEP documented; B2 prior; B3 rewrite applied
