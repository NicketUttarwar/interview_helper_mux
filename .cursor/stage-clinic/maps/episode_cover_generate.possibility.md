# Possibility Map — episode_cover_generate

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier claim process vs OpenAI Images+Vision — `CODE_DOC_CONFLICT`
- primary: cover.jpg | seed #71 | cascade: 3-candidate + vision + show fallback

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| rejected/empty prompt | harvest then generate or show fallback | IN_CODE | |
| show art missing | FileNotFoundError hard | IN_CODE | `_copy_show_fallback` |
| cover.jpg missing after done | HPUB-2 incompleteness | IN_CODE | |

## 2–3. Freshness / gates

- No gate — `IN_CODE`

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | cover.jpg + pick + meta; mark_done | IN_CODE | |
| vision fail | local_fallback_pick | IN_CODE | |
| all fail + show_fallback | show art + mark_done | IN_CODE | fail-open |
| candidates dir write | publish/cover_candidates/** — ownership ALLOW? | UNKNOWN | authority risk |

## 5–6. Side effects / traps

- Cost always-on under defaults (candidate_count=3, max_rebatch=1) — `IN_CODE`
- Doc cascade verified in code — `IN_CODE`

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| tier process | OpenAI images+vision | CODE_DOC_CONFLICT |
| hard prompt | Soft harvest | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| image API fail | rebatch≤1 then show fallback | IN_CODE | |
| vision fail | local_fallback_pick | IN_CODE | |
| hollow done without jpg | HPUB-2 unmarks | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Always completes cover | LLM or show art | IN_CODE | no human |
| OpenAI spend | Always under defaults | IN_CODE | |
| min size 1400 | Enforced at publish more than generate | IN_CODE | |
| human stall? | No | IN_CODE | |

## Flags (§5.5)

- podcast.cover_image.*; vision_pick.*; models.episode_cover_vision_pick

## TEST_GAP

- ownership cover_candidates; min size at generate

## DoD threats

- [ ] 1  [x] 2  [ ] 3  [x] 4  [x] 5  [ ] 6  [x] 7

## Open questions

1. ALLOW cover_candidates or write outside staging?

## discovery_status

`complete`
