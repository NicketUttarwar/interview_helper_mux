# Possibility Map — refinement_agenda

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: deterministic | seed **#47** | primary `understanding/refinement_agenda.json`
- module: `refinement_agenda.py::run_refinement_agenda` — pipeline **phase=confirm**
- contract hard gap_report never required — `CODE_DOC_CONFLICT`
- OpenAI: N/A | Local heavy ML: N/A

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| any tape | Always write agenda from character+policy | IN_CODE | |
| gap_report missing | Still writes | CODE_DOC_CONFLICT | vs YAML hard |
| empty eligible | Force heal | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| after sanitize | Seed adjacency | IN_CODE | |
| coverage may append ranking hole | confirm phase | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No operator modal | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | agenda + heal force | IN_CODE | |
| refinement_passes.enabled false | Pass-2 no-ops downstream | IN_CODE | |

## 5. Side effects

- Writes agenda; operational cascade/ensemble/plan ownership rows may be other writers — `IN_CODE` ownership
- Invalidates `[]`

## 6. Complexity traps

- Ignore gap sanitary claim — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard gap_report | Unused | CODE_DOC_CONFLICT |
| primary agenda | Matches | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | — | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | Write eligible classes → force heal; no human | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| landmine | Empty eligible done; ignore gap hard claim | IN_CODE | |
| partial-only fix risk | Operator approve agenda; require gap hard | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

- `analysis.refinement_passes.enabled`; policy packs; simple_tape_override

## TEST_GAP

- Confirm-phase ranking injection; enabled=false path

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Refuse agenda when gap unsanitary?

## discovery_status

`complete`
