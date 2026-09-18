# Possibility Map — talking_points_compose

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full OpenAI — `IN_CODE`
- primary: `understanding/talking_points.json` — `IN_CODE`
- gate adjacency: none — `IN_CODE`
- LLM: `understanding/talking-points-compose.system.txt`

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | contract hard transcript+content_brief; body requires brief before LLM (TPC-B1) | IN_CODE | `_talking_points_base_payload` + pre-LLM gate |
| hard missing | RuntimeError — no thin OpenAI packet | IN_CODE | |
| ideal_cuts disabled | writes stub talking_points + heal_or_refuse_mark force | IN_CODE | `ideal_cuts_cfg().enable` |
| hollow | schema strategy_summary + min talking_points | IN_CODE | |
| long text | shard merge_talking_points_artifacts | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | after content_context | IN_CODE | |
| disabled path | still marks via force heal if incompleteness clear | IN_CODE | stub has required keys |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all | none | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | persist + spread_talking_point_time_hints → mark | IN_CODE | |
| soft fail | not fail_open_partial | IN_CODE | |
| hard fail | StageError ≤2; empty shard parts raise | IN_CODE | |
| hollow persist | schema validate | IN_CODE | |
| disabled stub | intentional placeholder | IN_CODE | defaults enable true |

## 5. Side effects

- Writes: talking_points.json — `IN_CODE`
- Consumers: ideal_cuts_propose/materialize, mastering shape, nuggets — contract

## 6. Complexity traps

- OpenAI sharding
- Disable stub complexity when ideal_cuts off

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard transcript+brief | brief required before LLM (TPC-B1) | IN_CODE |
| soft speakers+probes | optional | IN_CODE |
| outputs talking_points schema | matches | IN_CODE |
| invalidates [] | true | IN_CODE |

## 8. External service variance (OpenAI)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed/schema/retry | same llm_simple ≤2 then raise | IN_CODE | |
| hollow persist | blocked | IN_CODE | |
| N/A when disabled | stub host path | IN_CODE | |

## 9. Full-auto / defaults path

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto defaults | `analysis.ideal_cuts.enable=true` → real OpenAI compose | IN_CODE | app.defaults |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| partial-only fix risk | None | IN_CODE | |

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [ ] 7 Cross-stage

## Open questions for operator

1. _(none)_

## discovery_status

`complete`
