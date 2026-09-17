# Possibility Map — nugget_corpus_mine

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | seed **#43** | primary `understanding/nugget_corpus.json`
- module: `analysis_extended.py::run_nugget_corpus_mine`
- contract hard plan+selection unused as PRESTAGE — `CODE_DOC_CONFLICT`
- OpenAI ≤2 | Local heavy ML: N/A
- QC side output claimed by contract but ownership = layup — `CODE_DOC_CONFLICT`

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| enabled + soft packet | LLM corpus | IN_CODE | `build_corpus_mine_input` |
| disabled | empty nuggets + force heal | IN_CODE | `run_nugget_corpus_mine` |
| empty order | still LLM with empty segments | IN_CODE | |
| contract hard plan | Not enforced | CODE_DOC_CONFLICT | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| after air_script/selection | Seed order | IN_CODE | |
| invalidate from fuse/ranking | ADG | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No gate | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean LLM | corpus + auto_complete | IN_CODE | run_flow_llm_stage |
| LLM fail ≤2 | StageError refuse | IN_CODE | not fail-open |
| CTA strip | strip_never_touch_nuggets | IN_CODE | |

## 5. Side effects

- Writes corpus only (mandatory) — `IN_CODE`
- Invalidates layup/recompose/transitions/vo/edl — ADG `IN_CODE`

## 6. Complexity traps

- Empty enabled corpus still done (sufficiency min_rows:0) — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard plan+selection | Soft admit | CODE_DOC_CONFLICT |
| output nugget_layup_qc | Ownership = layup | CODE_DOC_CONFLICT |
| primary corpus | Matches | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed/≤2 | StageError | IN_CODE | llm_simple |
| hollow | schema fail | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | enabled=true → LLM → heal; no human | IN_CODE | analysis.nugget_layup.enabled |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| landmine | Empty corpus done; soft hard-inputs | IN_CODE | |
| partial-only fix risk | Force hard plan PRESTAGE | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

- `analysis.nugget_layup.enabled` default true

## TEST_GAP

- Disabled stub honesty; missing plan PRESTAGE not required

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Empty enabled corpus incomplete or allowed?
2. Drop QC from contract outputs?

## discovery_status

`complete`
