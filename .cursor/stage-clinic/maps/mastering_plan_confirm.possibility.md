# Possibility Map — mastering_plan_confirm

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process / Pass2 confirm | LLM optional OH-FS
- primary: `mastering/mastering_plan.json` (rewrite) + optional `shadow_diff.json`
- module: `mastering_shape_runtime.py::run_mastering_plan_confirm`
- hard: gap_evaluations.json | soft: prior plan, dossier, gaps report
- gate: none (after G-Framing path) | thrash: confirm-hollow if provisional left | tests: HM-1 leftover

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| soft_gate on + evals | LLM or heuristic Pass2; heal_or_raise | IN_CODE | `run_mastering_plan_confirm` |
| soft_gate **disabled** | **Early return; no write/heal** | IN_CODE | lines 759–760 |
| provisional plan only after synthesize | Confirm incompleteness until pass=confirmed | IN_CODE | `_mastering_plan_confirm_incompleteness` |
| LLM fail | Heuristic mode adjust from gap count; degraded status | IN_CODE | |
| exception | Keep provisional + degradation_reasons or forced sparse | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| missing_framing done | Proceed | IN_CODE | |
| research thin | Admit refuse | IN_CODE | A-01 |
| gap_report soft often absent | Shadow uses 0 VO density | IN_CODE | `_maybe_shadow_diff` |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No gate on confirm itself | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean confirm | plan pass=confirmed; heal | IN_CODE | |
| soft_gate off | No-op return — **done risk if marker stamped elsewhere** | IN_CODE | honesty threat |
| confirm-hollow | Incomplete until confirmed_mode/pass | IN_CODE | HM-1 leftover |
| shadow_compare | Writes shadow_diff when enabled (default true) | IN_CODE | |

## 5. Side effects

- Rewrites mastering_plan.json; may write shadow_diff.json — `IN_CODE`
- Dual writer with synthesize — `IN_CODE`

## 6. Complexity traps

- Soft_gate disabled silent return — `IN_CODE`
- LLM vs soft_gate authority — `IN_CODE` A-03
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard gap_evaluations | Soft-read in heuristic; hard via rails | IN_CODE |
| consumers include missing_framing | Circular vs seed (confirm after) | CODE_DOC_CONFLICT |
| outputs plan + shadow | Matches when soft_gate on | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| default no LLM | Heuristic confirm | IN_CODE | |
| LLM ≤2 fail | Heuristic; invoke contract explicitly requests `artifact=plan` | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | soft_gate on → confirm runs; no human | IN_CODE | |
| soft_gate disabled | Silent return — unattended may leave provisional forever | IN_CODE | landmine |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| partial-only fix risk | Marking done on soft_gate-off no-op | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

| flag | default | effect |
|------|---------|--------|
| soft_gate.enable | true | no-op if false |
| soft_gate.shadow_compare | true | shadow_diff |
| shape.llm.enabled | true | LLM confirm path; plan response contract |

## TEST_GAP

- soft_gate disabled early-return + stage_done honesty
- confirm-hollow refuse under seed

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. soft_gate-off confirm: refuse incomplete vs forced confirmed sparse?

## discovery_status

`complete`
