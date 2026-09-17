# Possibility Map — framing_posture_decide

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | primary `understanding/framing_posture_decision.json` | gate adjacency: **G-Framing advisory** (gate authority later at missing_framing) | OpenAI `framing/framing-posture-decide.system.txt` | seed 17

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | Contract hard=`[]`; soft topology/speakers | `IN_CODE` | contract + `build_framing_posture_input` |
| hard missing | N/A hard | `IN_CODE` | — |
| soft missing | LLM/monologue still runs with sparse packet | `IN_CODE` | framing_posture.py |
| hollow | Stubs via allow/monologue builders | `IN_CODE` | `build_allow_stub_decision` / `build_monologue_decision` |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | Soft topology preferred; not hard | `IN_CODE` | — |
| producer invalidated | Contract invalidates none | `IN_CODE` | — |
| epoch drift | N/A | `IN_CODE` | — |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| gate open / waiting | Stage itself does not wait; G-Framing waits later at missing_framing | `IN_CODE` | operator-gates.md claim + gap_vo_gates |
| gate answered | Advisory only; operator Yes/No sticky | `DOC_ONLY_UNVERIFIED` / `IN_CODE` | docs + gap fill |
| illegal skip | Homunculus auto-Yes later; stage may stub | `IN_CODE` | `has_homunculus_features` skip |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | LLM advisory persist + `apply_host_gate` | `IN_CODE` | `framing_posture_decide.py:61-70` |
| soft fail | feature disabled / no homunculus → allow stub + heal | `IN_CODE` | L33-38 |
| hard fail | LLM StageError | `IN_CODE` | analysis_stage |
| monologue skip | Deterministic monologue + host gate | `IN_CODE` | L41-50 |
| done-without-primary | Stubs always persist decision doc | `IN_CODE` | `_persist_allow_stub_and_mark` |
| retry / heal | ≤2 + heal_or_refuse | `IN_CODE` | — |
| identical halt | Unlikely | `UNKNOWN` | — |

## 5. Side effects

- Writes: framing_posture_decision.json
- Side: `apply_host_gate` may `ensure_gap_fill_skipped` for native_only monologue (`IN_CODE` framing_posture.py:218-240)
- Consumers: missing_framing / gap compose (advisory)

## 6. Complexity traps

- Advisory LLM vs host enforce for native_only
- Gate coupling is **later** — StageInfo says advisory
- Local heavy ML: N/A (Chatterbox later — out of clinic)

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard [] | Matches | `IN_CODE` |
| llm_full | Body can skip LLM entirely | `CODE_DOC_CONFLICT` (tier vs control flow) |
| consumers missing_framing… | Advisory consumers | `IN_CODE` |
| StageInfo brain note 0.1.0+ | Brain clinic is 0.2.0; features via has_homunculus_features | `IN_CODE` |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed/schema | LLM path fail/retry | `IN_CODE` | run_analysis_llm_stage |
| hollow | Validators on write_validated_artifact | `IN_CODE` | persist_framing_decision |
| N/A | Stub/monologue paths skip OpenAI | `IN_CODE` | L33-50 |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | Runs advisory LLM (0.2.0); G-Framing auto-Yes later via homunculus even if `auto_accept_defaults=false` | `IN_CODE` | gap_fill defaults + operator-gates |
| human stall required? | Not at this stage; G-Framing may stall in partial | `IN_CODE` | — |
| GUI-only? | No for this stage | `IN_CODE` | — |
| auto-accept must fire | Later gate — do not add stall here | `FULL_AUTO_REGRESSION_RISK` | — |
| partial-only fix risk | Making advisory blocking would break Full-auto | `FULL_AUTO_REGRESSION_RISK` | — |

### §5.5 Flags

- `analysis.framing_posture.enabled` default true (code defaults; absent in app.defaults)
- `host_enforce` default true
- `analysis.gap_fill.auto_accept_defaults` default false (homunculus still auto-Yes)

### §5.6 TEST_GAP

- `tests/test_framing_posture_decide.py`, `test_hu2_framing_posture_stub.py` (~16 files)
- Gaps: advisory vs sticky operator No interaction (later stage)

## DoD threats

- [ ] 1 Progression  [x] 2 Honesty  [x] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

Top footgun: confusing advisory done with G-Framing resolution — stalls belong at missing_framing, not here.

## Open questions for operator

1. None for L1.

## discovery_status

`complete`
