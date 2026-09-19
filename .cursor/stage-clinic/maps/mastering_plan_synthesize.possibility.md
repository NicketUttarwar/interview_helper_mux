# Possibility Map — mastering_plan_synthesize

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process / Pass1 provisional plan | LLM optional OH-FS
- primary: `mastering/mastering_plan.json` (shared with confirm)
- module: `mastering_shape_runtime.py::run_mastering_plan_synthesize`
- hard: candidates.json | soft: agenda/dossier/gaps/episode_structure (forward soft)
- gate: none | thrash: research thin; plan authority A-03 | tests: A-03 / HM / heal pins

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| candidates present | LLM plan or first candidate → provisional plan | IN_CODE | `run_mastering_plan_synthesize` |
| no candidates | `forced_sparse_plan` | IN_CODE | |
| soft_gate off | Forced sparse `soft_gate_disabled` | IN_CODE | |
| hollow / invalid LLM | Soft_gate candidate path; `plan_status=degraded` | IN_CODE | `claim_plan_complete` |
| shape.llm off (default) | Soft_gate never claims complete | IN_CODE | A-03 |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| candidates done | Proceed | IN_CODE | |
| research thin | Admit refuse | IN_CODE | A-01 |
| soft gap/episode absent | OK Pass1 | IN_CODE | seed order |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No gate | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | write_plan + attach_shape_order | IN_CODE | |
| exception | forced_sparse | IN_CODE | |
| done-without-plan | write_plan always called on paths | IN_CODE | |
| authoritative complete | Only if shape.llm on + LLM accept | IN_CODE | `claim_plan_complete` |

## 5. Side effects

- Writes: mastering_plan.json (+ evidence packets) — `IN_CODE`
- Dual ownership with confirm (same path) — `IN_CODE` ownership ALLOW both stages
- Consumers: missing_framing, confirm, gap compose, delivery chain — contract + seed

## 6. Complexity traps

- Soft_gate vs LLM authority dual path — `IN_CODE` A-03
- consumers_bind default false — advisory plan — `IN_CODE` app.defaults
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard candidates | Enforced loosely (forced sparse if empty) | IN_CODE |
| soft gap_evaluations | Soft / after synthesize in seed | CODE_DOC_CONFLICT timing |
| consumers include missing_framing | Matches seed | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| default no LLM | Soft_gate degraded plan | IN_CODE | |
| LLM ≤2 fail | Soft_gate fallback; invoke contract explicitly requests `artifact=plan` | IN_CODE | flagship-synthesize |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | Always writes provisional degraded plan; no human | IN_CODE | soft_gate on, shape.llm off |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| landmine | Downstream may treat degraded plan as authoritative if bind flipped | FULL_AUTO_REGRESSION_RISK | consumers_bind |
| partial-only fix risk | Requiring complete plan_status before gaps would stall defaults | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

| flag | default | effect |
|------|---------|--------|
| soft_gate.enable | true | forced sparse if false |
| shape.llm.enabled | true | authoritative complete gate; plan response contract |
| soft_gate.consumers_bind | false | advisory |
| soft_gate.two_pass | true | confirm expected later |

## TEST_GAP

- Exception → forced sparse under seed
- consumers_bind true behavior (shadow)

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [x] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Keep consumers_bind false until shadow corpus — confirm inventory row?

## discovery_status

`complete`
