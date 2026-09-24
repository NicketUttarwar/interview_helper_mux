# Possibility Map — full_master_ranking

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | seed **#40** | primary `master/selection.json`
- module: `stages/selection.py::run_full_master_ranking`
- hard (code): narrative_plan + manifest + gap_report | contract hard fuse_rounds+coverage → conflict
- OpenAI: `selection/full-master-ranking.system.txt` ≤2 | Local heavy ML: N/A
- gate: narrative_qc.strict (default true) soft gate — not operator G*

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| code hard present | LLM ranking → persist lattice | IN_CODE | `run_full_master_ranking` |
| contract fuse_rounds hard | Not in `_check_full_master_ranking` | CODE_DOC_CONFLICT | stage_input_checks |
| empty ordered_segment_ids | refuse persist | IN_CODE | `ranking_artifacts_persistable` |
| hollow gap soft | build_input soft-empty | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| pre_ranking/hitch done | Seed adjacency | IN_CODE | |
| envelope salvage | commit_persistable_ranking_from_last_envelope | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| narrative_qc fail + strict | SystemExit / hard stop | IN_CODE | gates narrative_qc |
| NLE overlay | Optional GUI; not required | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | selection + sides; heal | IN_CODE | |
| LLM fail | salvage envelope or refuse | IN_CODE | |
| story_health fail | warn (not hard block default) | IN_CODE | |
| incomplete_no_persistable | fail_key unattended | IN_CODE | breakpoints |

## 5. Side effects

- Writes: selection, rank_candidates, story_health, bridges, SDP, stt_lexicon, media_ip CTA — `IN_CODE`
- Invalidates: nuggets, transitions, SDP, vo_synth, edl — ADG `IN_CODE`

## 6. Complexity traps

- Shape/seed prefer_seed_over_ranking bind thrash — `IN_CODE`
- Dual SSOT with sanitize co-writer — `IN_CODE`
- Local heavy ML: N/A

## Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard narrative+manifest+gap | Matches `_check_full_master_ranking` (FMR-B1) | IN_CODE |
| primary selection | Matches | IN_CODE |
| CTA may write manifest children | `full_master_ranking` co-producer + `cta_child_materialize` | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed/≤2 | refuse / salvage | IN_CODE | |
| hollow empty ordered | no persist | IN_CODE | |
| order_reconcile LLM | fail-open path | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | QC pass → LLM → seal selection; no human | IN_CODE | |
| human stall? | No (QC fail is hard stop not GUI) | IN_CODE | |
| GUI-only? | NLE optional only | IN_CODE | |
| landmine | `narrative_qc.strict=true` | IN_CODE | gates.py |
| partial-only fix risk | GUI-required NLE; relax QC without repair | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

- narrative_qc.strict default true
- ideal_cuts prefer_seed_over_ranking / Shape bind

## TEST_GAP

- Contract hard-list vs checker alignment not linted

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [x] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [x] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Align contract hard with `_check_full_master_ranking`?
2. Full-auto policy if QC fail: keep strict vs soft?

## discovery_status

`complete`
