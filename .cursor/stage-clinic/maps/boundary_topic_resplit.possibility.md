# Possibility Map — boundary_topic_resplit

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | primary `segments/boundaries.json` | gate: none | OpenAI refine prompt optional | seed 18 | thrash_hotspot: **yes**

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | Contract hard reanchored brief; soft boundaries/manifest | `IN_CODE` | contract + `run_boundary_topic_resplit` |
| hard missing | May still run with soft reads; skip paths | `CODE_DOC_CONFLICT` | L497-525 |
| no boundaries | Hollow `mark_done` raw if never wrote; refuse if wrote-then-lost (HS-2) | `IN_CODE` | L497-525 |
| no overload | Cycle stamp + edge confidence + heal | `IN_CODE` | L540-547 |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | After reanchor | `IN_CODE` | — |
| cycle_done | Skip re-invalidation unless fp flip + heal_n<2 | `IN_CODE` | L444-475 |
| ideal_cuts bound | Skip resplit (`skip_topic_resplit_when_bound`) | `IN_CODE` | L479-495 |

## 3. Partial-accel gate posture

N/A (`IN_CODE`)

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | LLM refine OR deterministic enrich; unlink class/reanchor done; bounded heal consumers | `IN_CODE` | L549-604+ |
| soft fail | Edge confidence fail-open | `IN_CODE` | L419-438 |
| hard fail | LLM StageError | `IN_CODE` | — |
| hollow done | Raw mark_done when no boundaries at start | `IN_CODE` | L516-525 |
| wrote-then-lost | Refuse hollow (return without done) | `IN_CODE` | L505-515 |
| retry / heal | heal_count cap 2 via run_meta | `IN_CODE` | L463 |
| identical halt | Cross-cutting thrash risk | `IN_CODE` | agenda/recovery |

## 5. Side effects

- Writes: boundaries (+ split_plan operational)
- Unlinks: `.stage_done/segment_classification`, `content_brief_reanchor`
- Invalidates consumers list via bounded profile
- Dual SSOT boundaries

## 6. Complexity traps

- Optional LLM vs deterministic enrich (`resegment_pass` policy)
- Self-archive / HS-2 hollow guards
- Multi-heal capped at 2
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard content_brief (reanchor) | Soft-read if missing in practice | `CODE_DOC_CONFLICT` |
| invalidates include classification + island/fuse | Matches unlink + profile intent | `IN_CODE` |
| llm_full | Often no LLM (skip / no overload / !resegment_pass) | `CODE_DOC_CONFLICT` |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| LLM path | refine system prompt ≤2 | `IN_CODE` | L561-568 |
| N/A | Skip/deterministic paths | `IN_CODE` | L479-547 |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | Often skip when ideal_cuts bound; else maybe LLM | `IN_CODE` | skip_topic_resplit_when_bound=true |
| human stall? | No | `IN_CODE` | — |
| GUI-only? | No | `IN_CODE` | — |
| partial-only fix risk | Widening clear_from would thrash Full-auto | `FULL_AUTO_REGRESSION_RISK` | — |

### §5.5 Flags

- `analysis.ideal_cuts.skip_topic_resplit_when_bound` true
- segmentation policy `resegment_pass`
- heal max 2 (run_meta)

### §5.6 TEST_GAP

- `test_boundary_topic_resplit.py`, `test_hs2_resplit_self_archive.py` (~16)
- Gaps: hollow skip when boundaries missing mid Full-auto seed

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

Top footgun: invalidation thrash (unlink classification/reanchor) + hollow raw mark_done when boundaries absent.

## Open questions for operator

1. Is hollow-done-without-boundaries intentional for seed gaps, or should it refuse?

## discovery_status

`complete`
