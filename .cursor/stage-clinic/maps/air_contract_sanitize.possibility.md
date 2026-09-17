# Possibility Map — air_contract_sanitize

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- delivery #51 | process | `commit_air_contract` then heal + soft seat freeze
- primary mastering_plan (+ omit_ledger)
- module: `artifact_sanitize/air_script.py::run_air_contract_sanitize`

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| hard plan missing | commit fails / refuse | IN_CODE | `commit_air_contract` |
| reentry skipped | RuntimeError (no fake write) | IN_CODE | skipped==reentry |
| sanitize !ok | RuntimeError sanitize_refused | IN_CODE | |
| unsanitary after | heal refuse → raise | IN_CODE | `heal_or_refuse_mark` |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| seams wrote plan | sanitize seats/gap bind | IN_CODE | |
| producer pin air_contract_unsanitary | self | IN_CODE | PRODUCER_PIN_TABLE |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| no G* | N/A | IN_CODE | |
| post success | `stamp_soft_seat_freeze` (fail-closed) | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | commit + heal marked + soft freeze | IN_CODE | |
| reentry / !ok / heal refuse | raise | IN_CODE | |
| soft freeze stamp fail | raise | IN_CODE | |

## 5. Side effects

- Writes mastering_plan + omit_ledger — IN_CODE
- Soft seat freeze meta — IN_CODE
- Consumers transitions/vo/edl — contract

## 6. Complexity traps

- Nested reentry guard footgun (commented) — IN_CODE
- Dual SSOT plan+omit — IN_CODE
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| process / hard plan | matches | IN_CODE |
| lifecycle llm_execute | no LLM | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto | must succeed sanitize or hard-stop | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| dirty done | incompleteness `air_contract_unsanitary` | IN_CODE | HF-4 |
| partial-only fix risk | never mark done unsanitary | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

- seat freeze constitution (Pillar B)

## TEST_GAP

- reentry skip path under concurrent writers

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. none blocking

## discovery_status

`complete`
