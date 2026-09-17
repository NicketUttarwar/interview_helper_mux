# Possibility Map — delivery_brief_build

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process / deterministic
- primary: `understanding/delivery_brief.json`
- module: `delivery_brief.py::run_delivery_brief_build`
- hard: gap_report.json | soft: plan, briefs, selection (often absent)
- gate: none | LLM: none | thrash: no | tests: thin–solid (validators, HG-2 stubs)

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| feature enabled + gap_report | Build brief; heal | IN_CODE | `build_delivery_brief` / run |
| feature disabled | Schema skip stub; heal | IN_CODE | `persist_delivery_brief_skip_stub` |
| hard gap_report missing | Prestage/rails refuse (body assumes present for meaningful budgets) | IN_CODE | contract hard |
| soft selection absent | Duration estimates None; still builds | IN_CODE | |
| hollow brief | Completeness validators | IN_CODE | `validate_delivery_brief` |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| gap compose done | Proceed | IN_CODE | |
| plan overlay | `_overlay_mastering_plan` soft | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No gate | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | write + heal | IN_CODE | |
| hard fail | Uncaught build errors | IN_CODE | |
| done-without-primary | Heal path + validators | IN_CODE | |

## 5. Side effects

- Writes delivery_brief.json; may update analysis_memory profile — `IN_CODE`
- Consumers: soundscape, topic_coverage, ranking/mix — contract

## 6. Complexity traps

- Deterministic rules + mastering_plan overlay — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard gap_report | Matches ownership/ADG | IN_CODE |
| consumers include gap_framing_compose | Circular vs seed (compose before brief) | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A (no external LLM) | — | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | `analysis.delivery_brief.enabled=true` → completes | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | No (operator overrides exist but not required) | IN_CODE | |
| partial-only fix risk | None | IN_CODE | |

## Flags (§5.5)

| flag | default | effect |
|------|---------|--------|
| analysis.delivery_brief.enabled | true | stub if false |
| ideal/min/max ratios & duration caps | see app.defaults | budget math |

## TEST_GAP

- Hard missing gap_report under seed refuse
- Plan overlay when plan degraded

## DoD threats

- [ ] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. (none)

## discovery_status

`complete`
