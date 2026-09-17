# Possibility Map — segment_classification

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | primary `segments/manifest.json` | gate: none | OpenAI `segmentation/segment-classification.system.txt` | seed 15 | thrash hotspot: yes (resplit coupling)

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | Boundaries required (contract); payload via `build_classification_payload` | `IN_CODE` | `segmentation.py:run_classification` |
| hard missing | LLM/payload fail or rail issue | `IN_CODE` | stage rails |
| soft missing | speakers/brief/etc optional in soft list | `IN_CODE` | contract soft |
| hollow boundaries | Deterministic path may no-op → LLM; empty segments fail sufficiency | `IN_CODE` | `try_deterministic_classification` L753 |
| schema-valid junk | Post stamp speakers + topic bootstrap | `IN_CODE` | L785-947 |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | After boundaries | `IN_CODE` | seed order |
| producer invalidated | Resplit unlinks `.stage_done/segment_classification` | `IN_CODE` | `run_boundary_topic_resplit` L592-595 |
| epoch drift | N/A | `IN_CODE` | — |

## 3. Partial-accel gate posture

N/A — no gate (`IN_CODE`)

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | Deterministic ideal-cuts path OR LLM (± shards) + heal | `IN_CODE` | L753-770, L837-928 |
| soft fail | Speech sidecar sync fail-open | `IN_CODE` | L774-779 |
| hard fail | Batched incomplete raises RuntimeError | `IN_CODE` | L917-923 |
| partial persist | Staging manifest | `IN_CODE` | make_stage_persist |
| done-without-primary | Deterministic only if segments non-empty | `IN_CODE` | L754 |
| retry / heal | analysis LLM ≤2; heal_or_raise on batch complete | `IN_CODE` | L926-928 |
| identical halt | Cross-cutting | `UNKNOWN` | — |

## 5. Side effects

- Writes: `segments/manifest.json`; may refresh ideal_cuts selection seed
- Invalidates (claim): reanchor, sonic, palettes, missing_framing, optimal_questions
- Consumers: reanchor, vernacular, low_conf, fuse, sonic, …

## 6. Complexity traps

- OpenAI classification vs deterministic ideal-cuts bind (`skip_classification_llm_when_bound`)
- Proactive sharding when obligation > threshold
- Dual path SSOT with talking_points authority
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard boundaries | Matches intent | `IN_CODE` |
| soft includes master/edl.json | Unusual soft — body may ignore | `CODE_DOC_CONFLICT` |
| outputs manifest | Matches | `IN_CODE` |
| remediation | Matches LLM | `IN_CODE` |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed / schema | StageError / validate | `IN_CODE` | llm_simple / persist |
| retry exhausted | Fail stage | `IN_CODE` | ≤2 |
| hollow persist | sufficiency min segments | `IN_CODE` | contract |
| N/A | Deterministic path skips OpenAI | `IN_CODE` | L753-770 |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | Prefer deterministic when ideal-cuts bound; else OpenAI (±shards) | `IN_CODE` | ideal_cuts skip_classification_llm + run_classification |
| human stall? | No | `IN_CODE` | — |
| GUI-only? | No | `IN_CODE` | — |
| partial-only fix risk | Adding operator review here would regress Full-auto | `FULL_AUTO_REGRESSION_RISK` | — |

### §5.5 Flags

- `analysis.ideal_cuts.skip_classification_llm_when_bound` default true
- classification_context_cfg shard thresholds
- specialists post-stage enabled default true

### §5.6 TEST_GAP

- Solid (~50 files) incl. `test_classification_obligation.py`, `test_llm_output_resilience_segment.py`
- Gaps: shard mid-fail recovery honesty; soft edl presence

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

Top footgun: resplit clears done marker → re-entry thrash with incomplete batch hard-fail.

## Open questions for operator

1. None.

## discovery_status

`complete`
