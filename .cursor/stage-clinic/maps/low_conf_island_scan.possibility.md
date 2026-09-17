# Possibility Map — low_conf_island_scan

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process | primary `analysis/low_conf_islands.json` | StageInfo required_outputs empty | OpenAI: none (StageInfo llm deps empty) | seed 20 | thrash: island/fuse family

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | Contract hard vernacular resplit_report; body scans from transcript/manifest | `CODE_DOC_CONFLICT` | `low_conf_fuse_stages.py:run_low_conf_island_scan` + low_conf_islands |
| soft missing | Still scans | `IN_CODE` | — |
| enabled=false | **Log skip and return — no write, no heal** | `IN_CODE` | L40-46 |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | After vernacular | `IN_CODE` | — |
| invalidated | By resplit profile claim | `DOC_ONLY_UNVERIFIED` | — |

## 3. Partial-accel gate posture

N/A

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | islands + ranking + must_keep; heal if outputs present | `IN_CODE` | L48-89 |
| soft fail | high_value scan fail-open | `IN_CODE` | L62-68 |
| hard fail | Rare in scan | `UNKNOWN` | — |
| disabled skip | No heal → stage may remain pending forever | `IN_CODE` | L40-46 **BUG** |
| done-without-primary | Guarded by `_heal_island_stage` + stage_outputs_present | `IN_CODE` | L26-33, agenda L790-793 |

## 5. Side effects

- Writes: low_conf_islands, density_ranking, must_keep, high_value sidecars
- May mark segments high_value on manifest
- Consumers: connector_fuse_pass, ranking

## 6. Complexity traps

- Density ladder complexity; HV fail-open
- Heal gated on outputs present (good) but disabled path forgets skip artifact
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard vernacular report | Not hard-checked in stage wrapper | `CODE_DOC_CONFLICT` |
| process + llm_execute lifecycle | No LLM | `CODE_DOC_CONFLICT` |
| StageInfo required () | Custom outputs_present | `IN_CODE` |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A (no external LLM) | Process / deterministic ranking | `IN_CODE` | StageInfo deps empty |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | `analysis.low_conf_selection.enabled=true` → runs | `IN_CODE` | app.defaults |
| human stall? | No when enabled | `IN_CODE` | — |
| disabled=true landmine | Pending forever — Full-auto stall | `IN_CODE` | L40-46 |
| GUI-only? | No | `IN_CODE` | — |
| partial-only fix risk | Disabling without skip-artifact hurts Full-auto | `FULL_AUTO_REGRESSION_RISK` | — |

### §5.5 Flags

- `analysis.low_conf_selection.enabled` default true
- top_percentile 0.1, enforcement_mode authoritative
- high_value_speech_islands.enabled true

### §5.6 TEST_GAP

- Thin-solid (`test_low_conf_fuse_selection.py`, `test_hs1_island_fuse_reentry.py` ~7)
- **TEST_GAP:** disabled path must persist skip + heal

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [x] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

Top footgun: `enabled=false` returns without skip artifact/heal → seed walk stall.

## Open questions for operator

1. Confirm disabled should mean honest skip-done (like fuse `persist_fuse_skip`) — recommended yes.

## discovery_status

`complete`
