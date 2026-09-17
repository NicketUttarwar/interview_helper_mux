# Possibility Map — edl_narrative_audit

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- delivery #57 | llm_full | primary audit JSON | audit_mode heard_wav_flow
- HE-1: incomplete unless vo_synthesize seed-complete + VO coverage heard
- Local ML: N/A (OpenAI semantic audit)

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| contract hard SDP | soft-read if missing in payload | CODE_DOC_CONFLICT | build_input optional |
| vo not complete | incompleteness HE-1 | IN_CODE | `_edl_narrative_audit_heard_wav_*` |
| verdict=fail persisted | incompleteness blocks edl | IN_CODE | stage_completion |
| findings min 0 | allow empty | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| vo_coverage wav_stale/missing | payload + incompleteness | IN_CODE | `compact_vo_coverage` |
| repair loop | `maybe_repair_after_narrative_audit` | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | | IN_CODE | |
| thrash cap | agenda may pin away | IN_CODE | homunculus agenda |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean LLM | audit + optional remutate repair | IN_CODE | |
| LLM fail | flow refuse | IN_CODE | |
| fail verdict | edl SystemExit / incompleteness | IN_CODE | |

## 5. Side effects

- Writes edl_narrative_audit.json; may remutate artifacts via repair — IN_CODE
- Invalidates vo_synthesize, edl — contract (upstream pin risk)
- consumers self — CODE_DOC_CONFLICT

## 6. Complexity traps

- OpenAI + repair remutate thrash — IN_CODE
- Dual SSOT audit vs VO coverage — IN_CODE
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard SDP only | body needs brief/selection/coverage etc soft | CODE_DOC_CONFLICT |
| consumers self | odd | CODE_DOC_CONFLICT |
| invalidates vo_synthesize | can thrash | FULL_AUTO_REGRESSION_RISK |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed/≤2 | refuse | IN_CODE | |
| hollow fail verdict | blocks edl | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto | OpenAI audit after WAVs; no human | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| heard_wav incomplete | pin vo_synthesize | IN_CODE | |
| fail→remutate thrash | agenda cap | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

- none unique; repair loop config UNKNOWN

## TEST_GAP

- contract hard inputs vs payload
- invalidate vo_synthesize necessity

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [x] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Should hard inputs include vo_synthesize seed?

## discovery_status

`complete`
