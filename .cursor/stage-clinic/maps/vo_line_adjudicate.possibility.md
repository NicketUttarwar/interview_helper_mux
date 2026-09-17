# Possibility Map — vo_line_adjudicate

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- delivery #54 | llm_full when on | primary adjudication JSON
- homunculus 0.1.0+ only; flag `analysis.gap_vo.adjudicate_before_synth` default true
- Local ML: N/A (OpenAI path in clinic)

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| no homunculus features | skip + force heal | IN_CODE | `has_homunculus_features` |
| adjudicate disabled | skip stub + heal | IN_CODE | |
| no/invalid gap | skip stub + heal | IN_CODE | |
| body lines need adjudicate | OpenAI batches; mutate gap | IN_CODE | `run_adjudicate_batches` |
| coverage floor fail | loud_fail unless fail_open | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| omit ledger | stamp skips on gap | IN_CODE | |
| unchanged lines | skip stub settled | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| G1 | not this stage's wait; resume mapping may pin here | IN_CODE | delivery_guardrails |
| brain 0.0.0 | skipped force heal | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | adjudication + allocation + heal | IN_CODE | |
| LLM fail | flow refuse | IN_CODE | |
| hollow skip stub | HV3 incompleteness risk if marked done wrong | IN_CODE | |

## 5. Side effects

- Writes adjudication, may gap_report, allocation plan — IN_CODE
- Invalidates vo_synthesize, edl_narrative_audit, edl — contract

## 6. Complexity traps

- OpenAI + intro compose + coverage floor — IN_CODE
- Dual SSOT gap vs adjudication — IN_CODE
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard layup+gap | matches entry | IN_CODE |
| lines min 0 | skip paths ok | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed/≤2 | refuse | IN_CODE | |
| hollow persist | incompleteness / HV3 | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto 0.2.0 + adjudicate=true | OpenAI; no human on stage | IN_CODE | |
| human stall? | No (G1 separate) | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| coverage fail_open | warning vs loud_fail | FULL_AUTO_REGRESSION_RISK | flag |
| partial-only fix risk | skip stubs must not hollow-done | IN_CODE | HV3 |

## Flags (§5.5)

- `analysis.gap_vo.adjudicate_before_synth` default true
- `adjudicate_fail_open` (cfg)

## TEST_GAP

- intro compose OpenAI failure honesty

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. fail_open default under Full-auto?

## discovery_status

`complete`
