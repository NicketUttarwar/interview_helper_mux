# Possibility Map — edl

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- delivery #58 | process | primary `master/edl.json`
- module: `stages/assembly.py::run_edl`
- Local TTS quality N/A; host may resynth during EDL — honesty via incompleteness

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| narrative audit fail | SystemExit before build | IN_CODE | |
| hard brief/coverage/selection/audit/transitions | contract; body soft-fills some | CODE_DOC_CONFLICT soft vs hard |
| bridge incomplete | F4 soft=False; may warn/incompleteness | IN_CODE | `ensure_seam_glue` |
| vo unsanitary | incompleteness pin vo_synthesize | IN_CODE | stage_completion edl |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| layup freshness / authority | assert refuse | IN_CODE | |
| order lock bump | selection mutate | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A stage gate | | IN_CODE | |
| G1 still open | should be incomplete upstream | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | edl.json + transition wav paths | IN_CODE | |
| audit fail | hard stop | IN_CODE | |
| resync VO/transitions | may synth again | IN_CODE | |
| soft-complete glue | forbidden (F4) | IN_CODE | |

## 5. Side effects

- Writes edl.json; may rewrite selection/gap/transitions; synth WAVs — IN_CODE
- Invalidates [] declared — DOC_ONLY_UNVERIFIED
- Consumers assembly_preview/mix/… — contract

## 6. Complexity traps

- Heavy repair+synth inside EDL — IN_CODE
- Dual SSOT with vo_synthesize — IN_CODE
- Local heavy ML: TTS quality N/A; host honesty yes

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard many | body also needs gap/layup practically | IN_CODE soft path |
| SDP producer sound_design_palettes | delivery uses sound_design_plan | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A OpenAI | | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto | build EDL unattended if upstream green | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | No (NLE edits optional soft) | IN_CODE | |
| glue incomplete | refuse soft-complete | IN_CODE | |
| partial-only fix risk | don't soft-pass glue for partial | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

- F4 bridge soft=False fixed in body

## TEST_GAP

- contract SDP producer name
- budget refuse paths

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [x] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Fix soft SDP producer attribution in contract?

## discovery_status

`complete`
