# Possibility Map — interview_spine_build

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: deterministic (+ optional CLAP) — `IN_CODE`
- primary: `understanding/interview_spine.json` — `IN_CODE`
- gate adjacency: none — `IN_CODE`
- LLM: none; local CLAP optional — N/A internals

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | when enabled: transcript + complete SAP | IN_CODE | `run_interview_spine_build` |
| hard missing | FileNotFoundError / RuntimeError SAP incomplete | IN_CODE | |
| soft missing | wav from preclean or normalized | IN_CODE | |
| spine disabled | `heal_or_refuse_mark(force=True)` **refuses** — incompleteness still wants spine.json; stage never done | CODE_DOC_CONFLICT | probed HEAD |
| hollow | schema validate_interview_spine before write | IN_CODE | |
| semantic junk | schema may pass sparse windows | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | SAP incompleteness gated | IN_CODE | |
| can_skip_rebuild | lineage skip → heal_or_raise | IN_CODE | |
| producer invalidated | rebuild | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all | none | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | write spine → heal_or_raise | IN_CODE | |
| soft fail | diarization verify fail-open; CLAP unavailable warning continues | IN_CODE | |
| hard fail | validation SystemExit; missing inputs | IN_CODE | |
| done-without-primary | disabled path intends force-done without JSON but heal refuses | CODE_DOC_CONFLICT | |
| retry / heal | heal_or_raise | IN_CODE | |
| identical halt | UNKNOWN | UNKNOWN | |

## 5. Side effects

- Writes: interview_spine.json (+ optional CLAP sidecar under retrieval) — `IN_CODE`
- Invalidates: [] declared
- Consumers: speaker_roles/content/boundary soft attach — code attach_spine

## 6. Complexity traps

- OpenAI: none
- Local heavy ML: optional CLAP index — N/A internals
- Dual SSOT: disabled skip vs STAGE_ARTIFACT_DISK_PATHS primary

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard when spine_enabled | code gates on spine_enabled() | IN_CODE |
| soft wav paths | matches | IN_CODE |
| outputs spine.json | matches when enabled | IN_CODE |
| invalidates [] | true | IN_CODE |
| disabled completion | not honest on HEAD | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | N/A | IN_CODE | |

## 9. Full-auto / defaults path

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | `interview_spine.enabled=true` → builds spine (CLAP may warn) | IN_CODE | app.defaults |
| human stall? | No on defaults | IN_CODE | |
| If operator disables spine | seed stuck incomplete | CODE_DOC_CONFLICT | |
| partial-only fix risk | disabled-stub must not invent GUI wait | FULL_AUTO_REGRESSION_RISK | |

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions for operator

1. When `interview_spine.enabled=false`, should stage write an explicit skip stub primary or be removed from seed?

## discovery_status

`complete`
