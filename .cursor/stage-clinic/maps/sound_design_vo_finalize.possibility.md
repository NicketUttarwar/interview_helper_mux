# Possibility Map — sound_design_vo_finalize

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- delivery #56 | deterministic | sidecar finalize JSON; may rewrite SDP durations
- Local ML: N/A

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| no SDP | refuse sidecar `no_sound_design_plan` (no heal) | IN_CODE | |
| no vo_bridge cues | skip sidecar + heal | IN_CODE | |
| vo_bridge missing WAV | refuse sidecar; **no heal** | IN_CODE | C-02 |
| adjust ok | write SDP bytes + heal | IN_CODE | |
| SDP validate fail after adjust | skip sidecar; may patch sonic; **no heal** | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| vo_synthesize WAVs | measured_duration_ms | IN_CODE | |
| opening repairs | fail-open before | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| adjusted | heal | IN_CODE | |
| refuse missing WAV | incompleteness | IN_CODE | `_sound_design_vo_finalize_incompleteness` |
| skip no cues | heal | IN_CODE | |

## 5. Side effects

- Writes finalize sidecar; may overwrite SDP file directly — IN_CODE
- Invalidates vo_line_adjudicate, vo_synthesize, edl_* — contract (aggressive)

## 6. Complexity traps

- Direct SDP file write vs ownership — IN_CODE
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard vo_synthesize.json | also needs SDP | CODE_DOC_CONFLICT |
| sufficiency skipped/refused fields | matches sidecar shape | IN_CODE |
| invalidates vo_line_adjudicate | surprising upstream | CODE_DOC_CONFLICT / risk |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto | adjust or skip/refuse honest | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| refuse missing WAV | pins vo_synthesize | IN_CODE | |
| hollow done | HV6 refuse | IN_CODE | |

## Flags (§5.5)

- none stage-local beyond SDP presence

## TEST_GAP

- SDP validate-fail path heal honesty
- invalidate list necessity

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Should invalidates drop vo_line_adjudicate?

## discovery_status

`complete`
