# Possibility Map — transitions

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- delivery #52 | llm_full OF transitions | primary `master/transitions.json`
- module: `stages/selection.py::run_transitions`
- also writes synthetic framing / pair freeze / may mutate selection

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| hard missing | ADG/prestage refuse | IN_CODE | contract hard |
| selection present | prerepair order integrity | IN_CODE | `audit_and_report` |
| LLM persist | dedupe + spoken_copy_guard + stamp identity | IN_CODE | `persist_with_framing_dedupe` |
| hollow transitions | sufficiency min_rows 0 | IN_CODE | contract |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| air contract / layup | soft inputs in payload | IN_CODE | build_input |
| order change | `on_selection_order_changed` | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| G1 skipped/open | `stamp_transitions_pair_freeze` | IN_CODE | end of run |
| no stage gate wait | N/A | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean LLM | transitions.json + heal via flow | IN_CODE | `run_flow_llm_stage` |
| LLM ≤2 fail | flow refuse/incomplete | IN_CODE | |
| reverse-gap / opening filter | drop rows | IN_CODE | persist filter |
| soft fail hollow | UNKNOWN without flow detail | UNKNOWN | |

## 5. Side effects

- Writes transitions (+ synthetic plans, freezes, may selection) — IN_CODE
- Invalidates sound_design_plan, vo_line_adjudicate, vo_synthesize, edl — contract
- Forbidden: retired transitions_refine ghost — IN_CODE

## 6. Complexity traps

- OpenAI control + heavy post-filters — IN_CODE
- Dual SSOT transitions vs gap VO — IN_CODE
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard layup+selection+plan | body also requires content_brief in payload soft-fail? | CODE_DOC_CONFLICT if brief missing crashes |
| consumers include full_master_ranking | upstream-ish | CODE_DOC_CONFLICT |
| invalidates list | present | DOC_ONLY_UNVERIFIED vs ADG |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed/schema/≤2 | flow stage refuse | IN_CODE | |
| hollow persist | completeness / min_rows 0 risk | FULL_AUTO_REGRESSION_RISK | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto | OpenAI transitions; no human gate | IN_CODE | |
| human stall? | No on stage (G1 later) | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| empty transitions allowed | min_rows 0 — bridge later may pin | FULL_AUTO_REGRESSION_RISK | |
| partial-only fix risk | don't weaken spoken_copy_guard for partial | IN_CODE | |

## Flags (§5.5)

- G1 optional / skipped stamps pair freeze
- production prompt variant

## TEST_GAP

- hard brief missing vs contract soft
- ADG invalidate parity

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Should empty transitions be incompleteness under Full-auto?

## discovery_status

`complete`
