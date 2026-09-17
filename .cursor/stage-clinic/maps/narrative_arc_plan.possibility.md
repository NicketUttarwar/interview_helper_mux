# Possibility Map — narrative_arc_plan

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | seed **#37** delivery | primary `master/narrative_plan.json`
- module: `stages/analysis_extended.py::run_narrative_arc`
- hard (code): coverage_audit + content_brief | soft contract-only: plan/topology/structure…
- dual path: `try_deterministic_narrative` else OpenAI `selection/narrative-arc-plan.system.txt`
- gate: none | Local heavy ML: N/A

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| det path TP+ideal_cuts | Write plan; heal force; skip LLM | IN_CODE | `try_deterministic_narrative` |
| else LLM | `run_flow_llm_stage` | IN_CODE | `run_narrative_arc` |
| coverage/brief missing | stage_input refuse | IN_CODE | `_check_narrative_arc_plan` |
| contract hard=coverage only | Code also requires brief | CODE_DOC_CONFLICT | contract vs checker |
| hollow chapters&lt;1 | incompleteness / sufficiency | IN_CODE | `_gaps_narrative_plan` / contract |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| topic_coverage done | Proceed | IN_CODE | DELIVERY_ORDER |
| hitch later rewrites plan | QC/narrative mutate downstream | IN_CODE | chapter_close_hitch ALLOW |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No gate | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean det/LLM | narrative_plan + heal | IN_CODE | |
| LLM fail ≤2 | flow stage refuse | IN_CODE | llm_simple |
| soft fail | treat as refuse | UNKNOWN | |
| done-without-chapters | heal refuse | IN_CODE | completeness |

## 5. Side effects

- Writes: `master/narrative_plan.json`; operational QC may also be hitch-owned — `IN_CODE` ownership
- Invalidates: hitch, pre_ranking, ranking, transitions — ADG `IN_CODE`
- Consumers claim lists upstream Shape stages — `DOC_ONLY_UNVERIFIED` stale

## 6. Complexity traps

- Det vs OpenAI dual SSOT — `IN_CODE`
- Hitch remints narrative refs later — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard coverage_audit | + content_brief required | CODE_DOC_CONFLICT |
| soft content_brief | Hard in checker | CODE_DOC_CONFLICT |
| primary narrative_plan | Matches | IN_CODE |
| consumers Shape stages | Stale vs seed order | DOC_ONLY_UNVERIFIED |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| det path | N/A OpenAI | IN_CODE | |
| malformed/≤2 | refuse | IN_CODE | llm_simple |
| hollow persist | Completeness | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | Prefer det (`deterministic_narrative`); else OpenAI; no human | IN_CODE | talking_points_authority |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| landmine | Empty chapters hollow; disable det raises LLM thrash | IN_CODE | |
| partial-only fix risk | Forcing LLM-only | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

- `talking_points.authority.deterministic_narrative` (default true)
- ideal_cuts enable for det path

## TEST_GAP

- Dedicated body tests thin vs coverage det path
- Contract hard-list vs `_check_narrative_arc_plan`

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Align contract hard with checker (coverage+brief)?
2. QC writer SSOT: narrative_arc_plan vs chapter_close_hitch?

## discovery_status

`complete`
