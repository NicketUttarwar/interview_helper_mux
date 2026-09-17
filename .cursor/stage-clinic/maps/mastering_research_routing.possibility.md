# Possibility Map — mastering_research_routing

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process | primary `mastering/research/routing.json` | StageInfo required () | OpenAI only if `mastering.research.llm.enabled` | seed 24

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| contract hard SDP | Body does not hard-require SDP before stub/LLM | `CODE_DOC_CONFLICT` | `mastering_research.py:run_research_routing` |
| soft many | Optional packet ingredients | `IN_CODE` | `_routing_user_payload` / soft list |
| llm disabled (default) | Sequential stub routing + heal | `IN_CODE` | L307-308 |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | After palettes in seed | `IN_CODE` | — |
| soft delivery artifacts | Often absent mid-analysis — OK | `IN_CODE` | soft list includes edl/master |

## 3. Partial-accel gate posture

N/A

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success LLM | invoke_mastering_prompt max_attempts=2; write routing; heal | `IN_CODE` | L286-301 |
| LLM exception / null arts | **Swallow → stub with llm_failed=True; still heal** | `IN_CODE` | L302-305 |
| llm disabled | Stub llm_failed=False; heal | `IN_CODE` | L307-308 |
| hard refuse | None on LLM fail | `IN_CODE` | bare `except Exception: pass` |

## 5. Side effects

- Writes: mastering/research/routing.json
- Consumers: research waves / rollup / shape
- Mode advisory default (does not skip fields authoritatively)

## 6. Complexity traps

- Soft-lie success on LLM failure (stub)
- research.llm.enabled false by default — process path
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard SDP | Not enforced | `CODE_DOC_CONFLICT` |
| process tier | Optional OpenAI | `CODE_DOC_CONFLICT` |
| StageInfo required () | heal after any routing write | `IN_CODE` |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed/schema | Falls to stub | `IN_CODE` | L302-305 |
| retry exhausted | max_attempts=2 then stub | `IN_CODE` | L295 |
| hollow persist | Stub still done | `IN_CODE` | **Honesty threat** |
| N/A default | research.llm.enabled=false | `IN_CODE` | mastering_plan_loader.research_llm_enabled |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | Stub routing (llm off); continues unattended | `IN_CODE` | research.llm.enabled=false |
| human stall? | No | `IN_CODE` | — |
| GUI-only? | No | `IN_CODE` | — |
| enabling research LLM without refuse-on-fail | Hollow-ish routing under variance | `FULL_AUTO_REGRESSION_RISK` | L302-305 |
| routing.mode advisory | Safe default | `IN_CODE` | app.defaults |

### §5.5 Flags

- mastering.research.llm.enabled **false**
- mastering.research.routing.mode advisory
- default_disposition required; max_deep_fields 12

### §5.6 TEST_GAP

- Thin (~5 files) incl. a03 / hm2
- Gaps: LLM fail → stub honesty when llm.enabled=true

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

Top footgun: when research LLM is on, exceptions soft-succeed via stub still marked done.

## Open questions for operator

1. When `research.llm.enabled=true`, should exhausted LLM refuse instead of stub-heal?

## discovery_status

`complete`
