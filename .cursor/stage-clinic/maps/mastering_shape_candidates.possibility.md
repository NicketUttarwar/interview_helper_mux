# Possibility Map — mastering_shape_candidates

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process / LLM optional OH-S2
- primary: `mastering/shape/candidates.json`
- module: `mastering_shape_runtime.py::run_mastering_shape_candidates`
- hard: agenda.json | soft: dossier/gaps/selection
- gate: none | thrash: research thin | tests: thin

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| agenda present | Heuristic or LLM candidates; heal | IN_CODE | `run_mastering_shape_candidates` |
| soft_gate off | Empty candidates stub + skipped | IN_CODE | `_persist_shape_candidates_skip` |
| empty LLM candidates | Heuristic with `llm_failed` | IN_CODE | `_heuristic_candidates` |
| no modes | Forced sparse survivor cand | IN_CODE | `_heuristic_candidates` |
| hollow | HM-1 | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| agenda done | Read modes | IN_CODE | |
| research thin | Admit refuse | IN_CODE | A-01 |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No gate | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| defaults heuristic | ≥1 candidate; heal | IN_CODE | |
| LLM success | LLM candidates | IN_CODE | prompt shape-l2-candidates ≤2 |
| exception | Forced sparse cand; heal | IN_CODE | |
| diversity | Skipped by default (`skip_diversity: true`) | IN_CODE | |

## 5. Side effects

- Writes: candidates.json; optional diversity_report if not skip — `IN_CODE`
- Consumers: `mastering_plan_synthesize` — `IN_CODE`

## 6. Complexity traps

- OpenAI optional; fail-open always produces survivors — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard agenda | Soft-read with fallback modes | IN_CODE |
| outputs candidates (+ diversity/packets) | Diversity optional | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A default | Heuristic | IN_CODE | shape.llm false |
| LLM fail | Heuristic heal | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | Completes with heuristic candidates | IN_CODE | |
| human stall? | No (except research thin) | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| partial-only fix risk | Requiring LLM candidates without fallback stalls Full-auto | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

- same soft_gate / shape.llm as agenda

## TEST_GAP

- Forced sparse path when agenda empty
- diversity enable path

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [ ] 7 Cross-stage

## Open questions

1. (none blocking)

## discovery_status

`complete`
