# Possibility Map — episode_cover_prompt_craft

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | primary: cover_prompt.json | seed #69
- dual run_prompt_envelope draft+finalize; harvest fallback F7

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| meta soft | Harvest motifs | IN_CODE | |
| LLM reject | `_cover_craft_fallback` still writes | IN_CODE | fail-open |
| empty prompt after harvest | UNKNOWN edge | UNKNOWN | |

## 2–3. Freshness / gates

- No gate; ship walk — `IN_CODE`

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| LLM ok | validated prompt | IN_CODE | |
| LLM fail | harvest + heal_or_raise | IN_CODE | |
| exception | still attempts persist | IN_CODE | |

## 5–6. Side effects / traps

- cover_prompt.json only; dual-volley cost intentional — `IN_CODE`

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard meta | Soft harvest | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| draft fail | ignored; finalize | IN_CODE | |
| finalize fail | harvest | IN_CODE | |
| validate_prompt reject | harvest | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Always produces a prompt | LLM or harvest | IN_CODE | no stall |
| human stall? | No | IN_CODE | |
| OpenAI outage | Still progresses via harvest | IN_CODE | |

## Flags (§5.5)

- podcast.cover_image.prompt_max_chars; load_cover_theme; flagship models

## TEST_GAP

- finalize fail + empty harvest motifs

## DoD threats

- [ ] 1  [x] 2  [ ] 3  [x] 4  [ ] 5  [ ] 6  [ ] 7

## Open questions

1. Require validate_prompt==[] before done?

## discovery_status

`complete`
