# Possibility Map — information_package_plan

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process | seed **#44** | primary `mastering/shape/information_packages_audit.json`
- module: `information_packages.py::run_information_package_plan`
- deterministic scoring; lifecycle llm_execute claim — `CODE_DOC_CONFLICT`
- Local heavy ML: N/A | OpenAI: N/A

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| corpus present | score → audit → patch plan | IN_CODE | |
| require_corpus + empty | candidates corpus_missing; still write+heal | CODE_DOC_CONFLICT | vs YAML hard |
| disabled | empty packages + episode_close | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| corpus done | Proceed | IN_CODE | |
| ADG layup←audit | Required edge | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No gate | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | heal_or_raise | IN_CODE | |
| commit_music_vo | mutates mastering_plan | IN_CODE | defaults mode |

## 5. Side effects

- Writes candidates+audit; patches mastering_plan — `IN_CODE`
- Contract invalidates `[]`

## 6. Complexity traps

- Default commit mode mutates plan for layup budget — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard corpus | Soft warn path | CODE_DOC_CONFLICT |
| lifecycle llm_execute | No LLM | CODE_DOC_CONFLICT |
| primary audit | Matches | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | — | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | enable=true; mode commit_music_vo; unattended | IN_CODE | app.defaults |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| landmine | Empty corpus still done; commit mutates plan | IN_CODE | |
| partial-only fix risk | Flip default to shadow-only | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

- `mastering.shape.information_packages.*` enable/mode/require_corpus/allow_regroup

## TEST_GAP

- Full-auto commit binding vs shadow; empty-corpus done honesty

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Empty corpus refuse mark_done when require_corpus?

## discovery_status

`complete`
