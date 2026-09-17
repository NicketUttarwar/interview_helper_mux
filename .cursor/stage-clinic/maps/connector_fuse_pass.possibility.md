# Possibility Map — connector_fuse_pass

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process (contract) but OpenAI economy seam LLM `IN_CODE` | primary `analysis/connector_fuse_audit.json` | StageInfo required () | seed 21 | thrash hotspot: yes

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | Contract hard low_conf_islands; fuse_pass checks manifest | `CODE_DOC_CONFLICT` | `segment_fuse.py:run_connector_fuse_pass` |
| missing manifest | persist_fuse_skip missing_manifest | `IN_CODE` | segment_fuse ~1855 |
| soft missing | Continues | `IN_CODE` | — |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | After low_conf | `IN_CODE` | — |
| reentry | HS-1 heal after write; oscillation pins in tests | `IN_CODE` | low_conf_fuse_stages + hs4 |

## 3. Partial-accel gate posture

N/A (junction_heal reopen gate is separate path)

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | Seam LLM loops to fixed point; audit + maybe rewrite manifest | `IN_CODE` | fuse_pass |
| disabled | Inner persist_fuse_skip + heal if outputs | `IN_CODE` | segment_fuse L1851-1852; wrapper still calls fuse_pass |
| soft fail | deterministic_fallback_on_llm_fail default true | `IN_CODE` | connector_fuse cfg |
| hard fail | LLM exhaustion / apply errors | `IN_CODE` | — |
| heal | `_heal_island_stage(fuse_writer_stage(pass_id))` | `IN_CODE` | L126 |
| oscillation | Caps / locked seams | `IN_CODE` | fuse + tests |

## 5. Side effects

- Writes: audit, seam packets/verdicts, manifest rewrite, locked seams
- Invalidates (claim): pre_ranking, topic/narrative, ranking, nuggets, transitions, edl
- Dual pass_id post_sanitize vs pre_ranking vs junction_heal

## 6. Complexity traps

- Economy OpenAI over every adjacent pair — control plane
- Multi-round fuse until fixed_point
- Manifest co-ownership
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| tier process | Uses OpenAI seams | `CODE_DOC_CONFLICT` |
| hard low_conf_islands | Soft in fuse_pass (enabled/manifest checks) | `CODE_DOC_CONFLICT` |
| StageInfo llm deps openai | Matches fuse | `IN_CODE` |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed/schema | fallback when configured | `IN_CODE` | deterministic_fallback_on_llm_fail |
| retry ≤2 | Per volley policy | `IN_CODE` | llm tier economy |
| hollow audit | skip_reason docs still count as output | `IN_CODE` | persist_fuse_skip |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | enabled=true; incomplete_thought_only; unattended | `IN_CODE` | app.defaults connector_fuse |
| human stall? | No | `IN_CODE` | — |
| GUI-only? | No | `IN_CODE` | — |
| partial-only fix risk | Adding operator seam approval would stall Full-auto | `FULL_AUTO_REGRESSION_RISK` | — |

### §5.5 Flags

- analysis.connector_fuse.* (enabled, incomplete_thought_only, max_fuses 0=unlimited, llm_tier economy, …)

### §5.6 TEST_GAP

- Solid fuse selection / hs3/hs4 (~20)
- Gaps: wrapper logs skip without return (benign because inner handles)

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

Top footgun: seam LLM thrash / oscillation rewriting manifest and invalidating delivery consumers.

## Open questions for operator

1. None.

## discovery_status

`complete`
