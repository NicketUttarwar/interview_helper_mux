# Possibility Map — episode_meta_build

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | primary: publish/episode_meta.json | seed #68
- module: `podcast_publish.run_episode_meta_build` → `llm_simple.run_llm_stage_simple`
- OpenAI **in clinic** | gate: none

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| selection missing | Soft empty chapters still LLM | IN_CODE | `_build_meta_input` |
| LLM empty | Fallback title Untitled Episode / thesis | IN_CODE | `_persist_meta` |
| hollow title | Persist always non-empty string | IN_CODE | honesty threat |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| invalidated by master_transcript ADG | Over-invalidate — meta doesn't read transcript | CODE_DOC_CONFLICT | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | Ship walk unattended | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | episode_meta.json | IN_CODE | |
| LLM ≤2 fail | StageError | IN_CODE | |
| soft-accept fallback | Untitled possible | IN_CODE | FULL_AUTO_REGRESSION_RISK |

## 5. Side effects

- publish/episode_meta.json only — `IN_CODE`

## 6. Complexity traps

- LLM-as-title with Untitled papering — `IN_CODE`

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard selection | Soft-read in body | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed / schema | retry ≤2 | IN_CODE | |
| exhausted | hard fail | IN_CODE | |
| hollow Untitled | may mark done | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| OpenAI up | Completes | IN_CODE | |
| OpenAI down | Hard stall | IN_CODE | |
| Untitled shipable | Yes today | IN_CODE | quality risk |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |

## Flags (§5.5)

- models.stages.episode_meta_build.tier=flagship; podcast.enabled

## TEST_GAP

- empty selection; Untitled acceptance; packet denylist

## DoD threats

- [ ] 1  [x] 2  [ ] 3  [x] 4  [x] 5  [ ] 6  [x] 7

## Open questions

1. Refuse Untitled vs allow?

## discovery_status

`complete`
