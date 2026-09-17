# Possibility Map — air_script_compose

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier contract llm_full vs deterministic Pass A — `CODE_DOC_CONFLICT` | seed **#42**
- primary `mastering/mastering_plan.json` (air_script Pass A)
- module: `air_script.py::run_air_script_compose` → `compose_pass_a`
- OpenAI: N/A Pass A | Local heavy ML: N/A
- StageInfo openai () ; not ALL_LLM_STAGES

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| selection ordered | Pass A beats on plan | IN_CODE | `compose_pass_a` |
| plan missing | load `{}` soft | IN_CODE | |
| contract hard selection | Soft-ish in body | CODE_DOC_CONFLICT | mild |
| enable=false | early return **without heal** | IN_CODE | `run_air_script_compose` L1644 |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| sanitize/ranking done | Proceed | IN_CODE | |
| Pass A omit commit | may mutate selection | IN_CODE | commit_selection_or_refuse |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No gate | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | plan.air_script pass_a + heal | IN_CODE | |
| fail_open Manual | warn continue | IN_CODE | air_script_cfg |
| automation | fail_open forced false | IN_CODE | |
| selection_commit_refused | incompleteness | IN_CODE | |
| HR-3 hollow seats | Pass A markable without VO seats | IN_CODE | |

## 5. Side effects

- Mutates mastering_plan air_script; omit_ledger; maybe selection commit — `IN_CODE`
- Contract invalidates `[]`

## 6. Complexity traps

- Disabled unmarked stall — `IN_CODE`
- Automation fail_closed — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| tier llm_full | Deterministic Pass A | CODE_DOC_CONFLICT |
| primary mastering_plan | Matches | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A (no external LLM Pass A) | — | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | enable=true → Pass A → heal; fail_closed under automation | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| landmine | enable=false unmarked; fail_closed; omit commit refuse | IN_CODE | |
| partial-only fix risk | Reintroduce LLM Pass A; require VO seats at Pass A | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

- `mastering.air_script.enable` default true
- fail_open automation override

## TEST_GAP

- Disabled path skip-done honesty unit

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [x] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Retier contract to process?
2. Disabled path should stamp skip-done?
3. May Pass A shrink selection via omit commit?

## discovery_status

`complete`
