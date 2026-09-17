# Possibility Map — episode_structure_compose

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process / deterministic
- primary: `understanding/episode_structure.json` + compact.txt
- module: `episode_structure.py::run_episode_structure_compose`
- hard: soundscape_policy.json | soft: brief/gaps/plan/selection
- gate: none | LLM: none (LX-03 compact template only) | thrash: boundary quality assert
- tests: test_episode_structure.py solid
- role: last shared analysis stage (`shared_analysis_chain_complete`)

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| enabled + policy | build + persist + heal; maybe finalize analysis | IN_CODE | run |
| disabled | skip stub + heal | IN_CODE | `persist_structure_skip_stub` |
| boundary quality fail | Hard-stop via `_assert_boundary_quality` | IN_CODE | |
| soft segments thin | Slot plan omits; integrity flags | IN_CODE | `build_episode_structure` |
| hollow | Validators | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| soundscape done | Proceed | IN_CODE | |
| soft gap/plan | Used if present | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No gate | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | structure + compact; heal; analysis_complete candidate | IN_CODE | `maybe_finalize_shared_analysis` |
| boundary assert fail | Raise | IN_CODE | |
| gap compose not done + not skipped | analysis_complete withheld | IN_CODE | `maybe_finalize_shared_analysis` |

## 5. Side effects

- Writes episode_structure.json + compact.txt — `IN_CODE`
- May stamp analysis_complete.json — `IN_CODE`
- Consumers: narrative/ranking/EDL soft — contract (also listed as soft into synthesize — forward)

## 6. Complexity traps

- Pack YAML axes scoring — deterministic complexity — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard soundscape_policy | Matches | IN_CODE |
| consumers include synthesize | Soft forward edge; seed order structure after synthesize | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | — | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | structure.enabled=true → completes; handoff to delivery | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| landmine | Boundary quality hard-stop mid Full-auto | IN_CODE | |
| partial-only fix risk | None | IN_CODE | |

## Flags (§5.5)

| flag | default | effect |
|------|---------|--------|
| structure.enabled | true | stub if false |
| structure.strict_slots | false | occupancy |
| structure.hook_reel_enabled | true | hook pick |
| require_payoff/outro | false | sparse OK |

## TEST_GAP

- Boundary assert failure path under compose
- analysis_complete gating when gap skipped vs not

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. (none)

## discovery_status

`complete`
