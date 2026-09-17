# Possibility Map — vernacular_segment_sanitize

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process | primary claim `vernacular/resplit_report.json` | StageInfo required_outputs **empty** | gate: none | LLM: no | seed 19

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | Contract hard boundaries; body keys off manifest + zones | `CODE_DOC_CONFLICT` | `audio_probes.py:run_vernacular_segment_sanitize` |
| no zones / empty zones / no manifest | Skip report + heal (HS-5 honest skip) | `IN_CODE` | L249-301 |
| corrupt manifest | fail_open skip (default true) | `IN_CODE` | L271-284 |
| hard missing boundaries | Body does not hard-require boundaries file | `CODE_DOC_CONFLICT` | vs contract hard |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | After resplit/classification | `IN_CODE` | — |
| producer invalidated | Contract invalidates low_conf + fuse | `DOC_ONLY_UNVERIFIED` | contract |
| epoch drift | N/A | `IN_CODE` | — |

## 3. Partial-accel gate posture

N/A (`IN_CODE`)

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | N-way resplit; rewrite manifest + report + must_keep + zones | `IN_CODE` | L305-436 |
| soft fail | fail_open on sanitize/write errors | `IN_CODE` | L308-329, L373-383 |
| hard fail | fail_open=false raises | `IN_CODE` | L316-317 |
| write fail after mutate | return without heal if fail_open | `IN_CODE` | L373-383 |
| done honesty | `_heal_vernacular_done` + HS-5 incompleteness | `IN_CODE` | stage_completion `_vernacular_segment_sanitize_incompleteness` |
| identical halt | Unlikely | `UNKNOWN` | — |

## 5. Side effects

- Writes: resplit_report, manifest, vernacular_must_keep, protected_zones
- Does **not** mutate run_golden_facts (ownership)
- Consumers: low_conf, fuse, ranking

## 6. Complexity traps

- Fail-open default masks errors
- Manifest co-ownership with classification/fuse
- Local heavy ML: N/A (zones from probes earlier)

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard boundaries | Soft in body | `CODE_DOC_CONFLICT` |
| outputs include protected_zones | Matches write | `IN_CODE` |
| StageInfo required_outputs () | Completeness via HS-5 custom | `CODE_DOC_CONFLICT` |
| remediation volley_retry | Process — N/A | `CODE_DOC_CONFLICT` |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A (no external LLM) | Process | `IN_CODE` | — |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | fail_open=true; skip or resplit unattended | `IN_CODE` | audio_probes cfg |
| human stall? | No | `IN_CODE` | — |
| GUI-only? | No | `IN_CODE` | — |
| fail_open=false as “fix” | Would hard-stop Full-auto on probe gaps | `FULL_AUTO_REGRESSION_RISK` | — |

### §5.5 Flags

- `audio_probes.fail_open` default true
- sanitize.min_child_ms default 800
- enforcement_mode_for_ctx shadow vs authoritative

### §5.6 TEST_GAP

- `test_hs5_vernacular_hollow.py`, `test_i4_vernacular_manifest_ownership.py` (~15)
- Gaps: write-fail mid-path without heal under Full-auto

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

Top footgun: fail_open skip/heal after partial write failure — or StageInfo empty required vs HS-5.

## Open questions for operator

1. None.

## discovery_status

`complete`
