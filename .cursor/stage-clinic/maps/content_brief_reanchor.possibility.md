# Possibility Map — content_brief_reanchor

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | primary `understanding/content_brief.json` (overwrite) | gate: none | OpenAI `understanding/content-brief-reanchor.system.txt` | seed 16

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | Reads manifest + existing brief; LLM reanchors | `IN_CODE` | `understanding.py:run_content_brief_reanchor` L481-558 |
| hard missing | Persist raises if brief not complete after write | `IN_CODE` | L542-548 |
| soft missing | boundaries/speakers optional | `IN_CODE` | L491-507 |
| hollow brief in | May LLM-repair; post-status must be complete | `IN_CODE` | L542-548 |
| schema-valid junk | Completeness gate refuses hollow done | `IN_CODE` | `artifact_status_for_stage` |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | After classification | `IN_CODE` | seed order |
| producer invalidated | Resplit unlinks done marker | `IN_CODE` | segmentation.py L592-595 |
| epoch drift | N/A | `IN_CODE` | — |

## 3. Partial-accel gate posture

N/A (`IN_CODE`)

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | LLM persist + sync_fn + optional coherence post | `IN_CODE` | L551-564 |
| soft fail | Topic bootstrap / coherence fail-open-ish | `IN_CODE` | L471-478, L560-564 |
| hard fail | Incomplete brief RuntimeError; LLM StageError | `IN_CODE` | L546-548 |
| partial persist | Staging content_brief | `IN_CODE` | make_stage_persist |
| done-without-primary | Blocked by completeness raise | `IN_CODE` | L542-548 |
| retry / heal | ≤2 volleys | `IN_CODE` | defaults |
| identical halt | Cross-cutting | `UNKNOWN` | — |

## 5. Side effects

- Writes: `understanding/content_brief.json` (same path as content_context — intentional reanchor)
- Invalidates (claim): boundary_topic_resplit, sonic, palettes, missing_framing, optimal_questions
- Consumers: resplit, sonic, palettes, missing_framing

## 6. Complexity traps

- OpenAI rewrites brief SSOT shared with content_context
- Dual producer path on one artifact
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard manifest + brief | Matches | `IN_CODE` |
| outputs content_brief | Matches | `IN_CODE` |
| sufficiency thesis/topics | Matches completeness raise | `IN_CODE` |
| remediation | LLM retry | `IN_CODE` |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed/schema | Fail / retry ≤2 | `IN_CODE` | run_analysis_llm_stage |
| hollow persist | Explicit RuntimeError | `IN_CODE` | L546-548 |
| retry exhausted | Stage incomplete | `IN_CODE` | — |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | Unattended OpenAI reanchor | `IN_CODE` | run_content_brief_reanchor |
| human stall? | No | `IN_CODE` | — |
| GUI-only? | No | `IN_CODE` | — |
| partial-only fix risk | Softening completeness would hollow-poison Full-auto | `FULL_AUTO_REGRESSION_RISK` | — |

### §5.5 Flags

- prompt_variant production profile
- analysis.max_volley_retries=2

### §5.6 TEST_GAP

- Solid (`test_content_brief_reanchor.py`, `test_content_brief_segment_sync.py`, ~34 files)
- Gaps: resplit→reanchor oscillation caps

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

Top footgun: shared brief SSOT with content_context — failed LLM after overwrite attempt thrash.

## Open questions for operator

1. None.

## discovery_status

`complete`
