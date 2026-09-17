# Possibility Map — sonic_context_build

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: deterministic | primary `understanding/sonic_context.json` | gate: none | LLM: no | seed 22

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| contract hard connector_fuse_audit | stage_input_checks hard: content_brief + manifest | `CODE_DOC_CONFLICT` | contract vs `stage_input_checks._check_sonic_context_build` |
| soft missing | `build_sonic_context` uses `{}` fallbacks | `IN_CODE` | `sonic_context.py:build_sonic_context` |
| hollow inputs | May write thin but schema-validated doc | `IN_CODE` | write_validated_artifact + HM-4 |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | Seed after fuse; checks want brief+manifest | `CODE_DOC_CONFLICT` | — |
| invalidated | Contract invalidates none (others invalidate this) | `IN_CODE` | — |

## 3. Partial-accel gate posture

N/A

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | build + validate write + heal | `IN_CODE` | `sonic_context_stages.py:10-32` |
| soft fail | Unlikely — deterministic | `IN_CODE` | — |
| hard fail | Schema validation refuse | `IN_CODE` | HM-4 `_sonic_context_incompleteness` |
| done-without-primary | Blocked by HM-4 | `IN_CODE` | stage_completion L423-453 |
| retry / heal | heal_or_refuse after valid write | `IN_CODE` | L32 |

## 5. Side effects

- Writes: sonic_context.json only
- Consumers: palettes, soundscape, episode structure, SDP, mix family

## 6. Complexity traps

- Declared hard edge mismatch (fuse vs brief)
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard fuse audit | Checks brief+manifest | `CODE_DOC_CONFLICT` |
| soft many incl narrative_plan | Optional reads | `IN_CODE` |
| deterministic tier | Matches | `IN_CODE` |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A (no external LLM) | Deterministic | `IN_CODE` | — |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | Unattended deterministic build | `IN_CODE` | run_sonic_context_build |
| human stall? | No | `IN_CODE` | — |
| GUI-only? | No | `IN_CODE` | — |
| hard-require fuse if contract followed | Could stall if fuse skipped hollow | `FULL_AUTO_REGRESSION_RISK` | align contract to checks |

### §5.5 Flags

- (none stage-local beyond blacklist of specialists)

### §5.6 TEST_GAP

- `test_sonic_context.py`, `test_hm4_sonic_hollow.py` (~14)
- Gaps: contract vs input_checks parity test

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

Top footgun: CODE_DOC_CONFLICT on hard inputs (fuse audit vs brief/manifest) — rails disagree.

## Open questions for operator

1. Should hard prerequisite be fuse audit (contract) or brief+manifest (input_checks)? Recommend code: brief+manifest; fix contract.

## discovery_status

`complete`
