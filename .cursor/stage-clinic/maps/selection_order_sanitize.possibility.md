# Possibility Map — selection_order_sanitize

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process | seed **#41** | primary shared `master/selection.json`
- module: `artifact_sanitize/selection.py::run_selection_order_sanitize`
- hard: selection.json | OpenAI: N/A | Local heavy ML: N/A

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| selection present | sanitize + commit + heal | IN_CODE | `run_selection_order_sanitize` |
| selection missing | RuntimeError | IN_CODE | |
| soft missing | Continues | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| ranking done | Proceed | IN_CODE | |
| dirty-done | HR-4 refuse mark | IN_CODE | tests |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No gate | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| result.ok | heal_or_raise | IN_CODE | |
| not ok | raise sanitize_refused | IN_CODE | |
| done-without-sanitary | incompleteness | IN_CODE | |

## 5. Side effects

- Mutates selection via air-order bus; sanitize audit — `IN_CODE`
- Contract invalidates `[]` — order-change lifecycle via commit `IN_CODE`

## 6. Complexity traps

- Dual writer with ranking/junction — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard selection | Matches | IN_CODE |
| primary selection | Co-writer ownership | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A (no external LLM) | — | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | Sanitize+commit+heal; no human | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| landmine | Refuse loops if upstream lattice broken | IN_CODE | |
| partial-only fix risk | Ask operator on refuse; skip stage | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

- none stage-specific

## TEST_GAP

- Contract schema null vs selection schema polish

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. None critical.

## discovery_status

`complete`
