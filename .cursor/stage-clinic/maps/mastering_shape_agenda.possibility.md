# Possibility Map — mastering_shape_agenda

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process / LLM optional OH-S0
- primary: `mastering/shape/agenda.json` (+ `eval_rubric.json`)
- module: `mastering_shape_runtime.py::run_mastering_shape_agenda`
- hard: rollup.json; soft: dossier, briefs, gaps (often absent at Pass1)
- gate: none | thrash: via research thin refuse | tests: thin (HM-1, A-03)

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| soft_gate enable | Heuristic or LLM agenda+rubric; heal | IN_CODE | `run_mastering_shape_agenda` |
| soft_gate disabled | Schema stub skip; heal | IN_CODE | `_persist_shape_agenda_skip` |
| rollup thin / shape-core thin | Seed admit refused (consumer) | IN_CODE | `_research_thin_late_refuse` |
| hollow agenda | HM-1 incompleteness | IN_CODE | schema validator |
| LLM malformed | Fallback heuristic `llm_failed` | IN_CODE | `_heuristic_agenda_and_rubric` |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| rollup done + ready | Proceed | IN_CODE | |
| rollup stale thin | Refuse resume rollup | IN_CODE | A-01 |
| gap soft inputs absent | Heuristic still works | IN_CODE | Pass1 before missing_framing |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No gate | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean heuristic (defaults) | Agenda+rubric; heal | IN_CODE | `shape_llm_enabled` false |
| shape.llm on success | LLM agenda; rubric LLM or heuristic | IN_CODE | two `invoke_mastering_prompt` ≤2 each |
| exception | Degraded stub agenda; heal | IN_CODE | except branch |
| done-without-primary | HM-1 refuse | IN_CODE | |

## 5. Side effects

- Writes: agenda.json, eval_rubric.json; evidence packets via `compile_shape_evidence` when payload built — `IN_CODE`
- Consumers: `mastering_shape_candidates` — `IN_CODE`

## 6. Complexity traps

- OpenAI as optional control when `mastering.shape.llm.enabled` (default **false**)
- Fail-open stubs always heal — risk of weak agendas — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard rollup | Enforced via incompleteness rails more than body assert | IN_CODE |
| soft gap_evaluations | Soft / often absent Pass1 | IN_CODE |
| outputs agenda (+ rubric/packets) | Rubric always written when soft_gate on | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A default (shape.llm false) | Heuristic | IN_CODE | app.defaults |
| malformed / schema / ≤2 exhaust | Heuristic fallback + heal | IN_CODE | |
| hollow persist | Schema + HM-1 | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | soft_gate on, shape.llm off → heuristic agenda; no human | IN_CODE | `soft_gate.enable=true` |
| human stall? | No (unless research thin blocks admit) | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| landmine | Research thin refuse blocks unattended Shape | IN_CODE | A-01 |
| partial-only fix risk | Enabling shape.llm-only without fail-open would stall Full-auto | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

| flag | default | effect |
|------|---------|--------|
| `mastering.shape.soft_gate.enable` | true | skip stub if false |
| `mastering.shape.llm.enabled` | false | OpenAI vs heuristic |
| soft_gate max_mode_candidates / skip_diversity / prefer_talking_points | 2 / true / true | heuristic knobs |

## TEST_GAP

- Exception stub heal under seed admit
- soft_gate disabled path

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Should rubric LLM failure be incomplete instead of heuristic heal?

## discovery_status

`complete`
