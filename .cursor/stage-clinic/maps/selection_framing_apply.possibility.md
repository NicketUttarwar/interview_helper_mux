# Possibility Map — selection_framing_apply

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: deterministic | delivery #49 | primary `understanding/selection_framing_apply.json`
- module: `refinement_passes.py::run_selection_framing_apply`
- hard: selection + gap_report | LLM: none | Local ML: N/A

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| selection missing | refuse stub `missing_selection` | IN_CODE | `persist_apply_refuse_stub` |
| invalid selection | refuse stub | IN_CODE | |
| seat freeze / gate error | skip stub + `_heal_pass2` | IN_CODE | `gate_seat_mutation` |
| gap present | rebase/drop/clone/orientation/layup | IN_CODE | gap helpers |
| hollow/refuse sidecar | pass2 incompleteness | IN_CODE | `_pass2_*` |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| framing-covered segs | exclude from ordered if validate ok | IN_CODE | `ranking_exclude_segment_ids` |
| hard validate fails | skip selection write | IN_CODE | `validate_framing_ranking` |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| no G* | N/A | IN_CODE | |
| seat freeze | no-op stub+heal | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | APPLY applied + `_finish_pass2` | IN_CODE | |
| post sanitize | optional `commit_selection_mutation` | IN_CODE | |
| refuse | incompleteness / not seed-complete | IN_CODE | |

## 5. Side effects

- Writes APPLY_REL; may mutate `master/selection.json` + `gap_report.json` — IN_CODE
- Contract lists draft/refinement outputs — CODE_DOC_CONFLICT vs body
- Invalidates [] declared — DOC_ONLY_UNVERIFIED

## 6. Complexity traps

- Selection+gap dual mutation — IN_CODE
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard selection+gap | matches checks | IN_CODE |
| llm_execute lifecycle | no LLM | CODE_DOC_CONFLICT |
| extra draft outputs | not primary body writes | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A no OpenAI | | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | deterministic; no human | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| seat freeze | stub+heal | IN_CODE | |
| partial-only fix risk | freeze must not require GUI | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

- seat freeze meta (Pillar B)

## TEST_GAP

- Contract output list vs writes; refuse vs heal honesty

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Align contract lifecycle/outputs with non-LLM body?

## discovery_status

`complete`
