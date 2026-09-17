# Possibility Map — assembly_preview

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- delivery #59 | process | binary `master/assembly_preview.wav`
- speech+VO only (no SFX) | heard_wav refuse
- Local ML: N/A

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| edl hard | required | IN_CODE | |
| unsourced glue / VO missing | RuntimeError heard_wav → vo_synthesize | IN_CODE | `assembly_preview_heard_wav_refuse` |
| no renderable clips | raise | IN_CODE | |
| heal VO source_path | may rewrite edl if reopen allow | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| assembly.wav exists | EDL heal may refuse (c13) | IN_CODE | timeline reopen gate |
| music deferred | agenda pins assembly_preview | IN_CODE | RC9 |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | preview wav + heal_or_refuse_mark | IN_CODE | |
| heard refuse | raise incomplete | IN_CODE | |
| empty clips | raise | IN_CODE | |

## 5. Side effects

- Writes assembly_preview.wav; may write edl heal — IN_CODE
- Invalidates [] — contract
- Consumers junction/mix claim — DOC_ONLY_UNVERIFIED vs music pin

## 6. Complexity traps

- Preview vs full mix dual audio SSOT — IN_CODE
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard edl+selection | selection not strictly read in run_preview | CODE_DOC_CONFLICT |
| soft ingest | used as speech source | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto | render preview unattended | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| missing VO wav | pin vo_synthesize | IN_CODE | |
| music before preview | agenda restarts to preview | IN_CODE | |

## Flags (§5.5)

- `mix.crossfade_ms_assembly_preview` default 80

## TEST_GAP

- hard selection unused
- reopen refuse after assembly exists

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [x] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Drop selection from hard inputs?

## discovery_status

`complete`
