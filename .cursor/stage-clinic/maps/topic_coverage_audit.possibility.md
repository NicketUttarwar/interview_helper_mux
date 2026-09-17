# Possibility Map — topic_coverage_audit

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | OF-01 | **delivery** seed #36
- primary: `master/coverage_audit.json`
- module: `stages/analysis_extended.py::run_topic_coverage`
- hard: delivery_brief.json | soft: brief/topology/gaps/spine/manifest
- gate: none | thrash: voice_ref mis-pin redirected to missing_framing | tests: coherence + flow hardening
- dual path: deterministic talking-points coverage preferred; else OpenAI

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| deterministic coverage available | Write audit; heal; skip LLM | IN_CODE | `try_deterministic_coverage` |
| else LLM path | run_flow_llm_stage OF-01 | IN_CODE | |
| hard brief missing | Prestage/ADG refuse | IN_CODE | contract |
| hollow audit | Completeness / schema | IN_CODE | `validate_coverage_audit` |
| coherence activated without report | maybe_run_coherence_analysis first | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| analysis_complete / delivery ready | `assert_delivery_ready` in pipeline | IN_CODE | pipeline topic_coverage entry |
| delivery_brief done | Proceed | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No gate on stage | IN_CODE | |
| G-VoiceRef open | Must not pin this stage — pin missing_framing | IN_CODE | HG-4 / stage_completion |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean det/LLM | coverage_audit; heal; post specialists; post_coverage coherence | IN_CODE | |
| LLM fail | Flow stage error / heal refuse | IN_CODE | |
| soft fail | Unknown without reading flow stage — treat as refuse | UNKNOWN | |

## 5. Side effects

- Writes master/coverage_audit.json — `IN_CODE`
- Invalidates narrative/fuse/ranking/nugget/transitions (contract propagation) — claim; verify ADG — `DOC_ONLY_UNVERIFIED` until ADG confirm
- Consumers: narrative_arc_plan etc. — contract

## 6. Complexity traps

- Deterministic vs OpenAI dual SSOT — `IN_CODE`
- Coherence side calls — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard delivery_brief | Matches payload attach | IN_CODE |
| sufficiency topics≥1 | Deterministic may still emit topics | IN_CODE |
| invalidates list | Present in YAML; confirm runtime | DOC_ONLY_UNVERIFIED |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| det path | N/A OpenAI | IN_CODE | |
| LLM malformed/≤2 | flow stage refuse | IN_CODE | |
| hollow persist | Completeness | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | Prefer det; else OpenAI; no human | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| landmine | Delivery-ready assert if analysis incomplete | IN_CODE | |
| voice_ref mis-heal | Redirected away from this stage | IN_CODE | HG-4 |
| partial-only fix risk | None | IN_CODE | |

## Flags (§5.5)

- talking_points / ideal_cuts enable (det path)
- coherence duration gate activation

## TEST_GAP

- Contract invalidates propagation vs ADG runtime
- LLM path hollow after det unavailable

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Confirm ADG transitive_invalidate matches contract list for coverage_audit?

## discovery_status

`complete`
