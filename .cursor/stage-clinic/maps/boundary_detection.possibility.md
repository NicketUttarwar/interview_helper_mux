# Possibility Map — boundary_detection

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | primary `segments/boundaries.json` | gate: none | OpenAI prompt `segmentation/boundary-detection.system.txt` | seed 14

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | LLM path builds transcript/speakers/brief (+ soft enrichments) | `IN_CODE` | `segmentation.py:run_boundaries` L115-153 |
| hard missing | Contract hard: brief/speakers/ideal_cuts_materialized; body reads without preflight refuse (rail may block) | `CODE_DOC_CONFLICT` | contract vs `build_input` |
| soft missing | talking_points/ideal_cuts/SAP optional | `IN_CODE` | L122-129 |
| soft stale | No hash gate | `UNKNOWN` | — |
| hollow `{}` / `[]` | Post `_assert_boundary_quality` may reject/repair | `IN_CODE` | `segmentation.py:_assert_boundary_quality` |
| schema-valid semantic junk | Coarse metrics → reject/repair or raise via quality assert | `IN_CODE` | `evaluate_boundary_quality` |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | Ideal-cuts bind may skip LLM if quality OK | `IN_CODE` | L57-87 |
| producer invalidated | Contract invalidates classification/reanchor/sonic/palettes/… | `DOC_ONLY_UNVERIFIED` | contract YAML — verify profiles |
| epoch / delivery drift | N/A | `IN_CODE` | — |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| gate open / waiting | N/A | `IN_CODE` | — |
| gate answered | N/A | `IN_CODE` | — |
| illegal skip | Skip LLM when bound+quality — intentional | `IN_CODE` | L57-106 |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | LLM persist + edge confidence + quality assert | `IN_CODE` | L157-176 |
| soft fail | Edge confidence fail-open log | `IN_CODE` | L170-175 |
| hard fail | LLM StageError / quality reject | `IN_CODE` | analysis_stage + `_assert_boundary_quality` |
| partial persist | Staging via `make_stage_persist` | `IN_CODE` | L155 |
| done-without-primary | Skip path heals only if boundaries already present | `IN_CODE` | L69-70 |
| retry / heal loop | Homunculus ≤2 volleys (analysis.max_volley_retries=2) | `IN_CODE` | app.defaults |
| identical halt | Cross-cutting | `UNKNOWN` | — |

## 5. Side effects

- Writes: `segments/boundaries.json` (+ edge confidence mutations)
- Forbidden: should not clobber ideal-cuts publisher without quality reject path
- Invalidates (claim): segment_classification, content_brief_reanchor, sonic, palettes, missing_framing, optimal_questions
- Consumers: classification, reanchor, resplit, …

## 6. Complexity traps

- OpenAI owns segmentation when bind skipped/coarse
- Dual SSOT with ideal_cuts_materialize publisher stamp
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard: brief, speakers, ideal_cuts_materialized | Body assumes present; ideal_cuts used for skip not always required for LLM payload | `CODE_DOC_CONFLICT` |
| soft list | Mostly matches build_input | `IN_CODE` |
| outputs boundaries | Matches | `IN_CODE` |
| invalidates list | Claim — verify execution profiles | `DOC_ONLY_UNVERIFIED` |
| remediation | volley_retry matches LLM | `IN_CODE` |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed JSON | analysis LLM reject/retry ≤2 | `IN_CODE` | `run_analysis_llm_stage` |
| schema fail | persist/validate path | `IN_CODE` | make_stage_persist |
| retry exhausted | StageError / incomplete | `IN_CODE` | max_volley_retries=2 |
| hollow persist | Quality assert / sufficiency min_rows | `IN_CODE` | contract + `_assert_boundary_quality` |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults happy path | Often skip LLM if ideal-cuts bound quality OK (`skip_boundary_llm_when_bound=true`) else OpenAI | `IN_CODE` | L57-76 |
| human stall required? | No | `IN_CODE` | — |
| GUI-only? | No | `IN_CODE` | — |
| auto-accept | N/A | `IN_CODE` | — |
| partial-only fix risk | Forcing always-LLM would slow Full-auto; forcing always-skip risks coarse maps | `FULL_AUTO_REGRESSION_RISK` | — |

### §5.5 Flags

- `analysis.ideal_cuts.skip_boundary_llm_when_bound` default true
- `segmentation.reject_coarse_fallback` (via segmentation_cfg)
- `analysis.max_volley_retries` = 2

### §5.6 TEST_GAP

- Solid (~35 files) incl. `test_boundary_detection_spine_input.py`
- Gaps: soft-stale brief; Full-auto skip vs coarse bind oscillation

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

Top footgun: ideal-cuts bind skip vs coarse fallthrough — wrong skip stamps done on sparse boundaries.

## Open questions for operator

1. None blocking — skip/LLM split looks intentional.

## discovery_status

`complete`
