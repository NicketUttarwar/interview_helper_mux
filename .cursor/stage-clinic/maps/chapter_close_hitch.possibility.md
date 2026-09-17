# Possibility Map — chapter_close_hitch

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process | seed **#38** | primary `mastering/chapter_close_hitch.json`
- module: `chapter_close_hitch.py::run_chapter_close_hitch`
- hard: narrative_plan OR frozen intent_plan | OpenAI: none
- Local heavy ML: N/A (optional cut_edge_refine on normalized.wav — signal edge only)
- thrash: inner restage / hitch_layup_adopt_failed

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| narrative present | Recut/remap/inner walk → latch | IN_CODE | `run_chapter_close_hitch` |
| intent_plan only | Resume OK | IN_CODE | `_check_chapter_close_hitch` |
| neither | skip latch reason=no_narrative_plan + heal | IN_CODE | hitch body |
| soft missing | Opportunistic | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| narrative done | Proceed | IN_CODE | |
| Phase A/assembly reopen | Remap-only profiles | IN_CODE | hitch restage |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No operator gate; homunculus cannot skip until latch | IN_CODE | `homunculus/agenda.py` |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | committed latch + heal force | IN_CODE | |
| disabled | skip-commit + heal | IN_CODE | hitch_cfg enabled |
| layup adopt fail | raise + incompleteness | IN_CODE | `_hitch_layup_adopt_incompleteness` |
| reuse | policy none | IN_CODE | |

## 5. Side effects

- Writes: latch, intent/remap/keepers/omit/vo snapshots, boundaries, may rewrite narrative_plan (stage_key spoof) — `IN_CODE`
- Invalidates: pre_ranking, ranking (+ bounded restage unmark) — ADG `IN_CODE`

## 6. Complexity traps

- Inner walk thrash — `IN_CODE`
- Narrative rewrite ownership conflict — `IN_CODE`
- Lifecycle lists llm_execute but StageInfo none — `CODE_DOC_CONFLICT`
- Local heavy ML: N/A (edge refine boundary only)

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| tier process | Matches deterministic body | IN_CODE |
| lifecycle llm_execute | No LLM | CODE_DOC_CONFLICT |
| hard narrative_plan | Or intent_plan | IN_CODE |
| primary latch | Matches | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A (no external LLM) | — | IN_CODE | StageInfo none |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | enabled=true → recut→inner walk→latch; unattended | IN_CODE | `mastering.chapter_close_hitch.enabled` |
| human stall? | No (unless adopt-fail incomplete loop) | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| landmine | Inner restage thrash; narrative ALLOW co-write | IN_CODE | |
| partial-only fix risk | Operator approve-before-recut | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

- `mastering.chapter_close_hitch.enabled` default true
- max_cut_ms / listen_restage once

## TEST_GAP

- Solid hitch suite; confirm lifecycle honesty not tested as contract lint

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [x] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Keep hitch as ALLOW writer of `master/narrative_plan.json` / QC?

## discovery_status

`complete`
