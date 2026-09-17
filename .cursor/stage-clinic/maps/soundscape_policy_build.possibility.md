# Possibility Map — soundscape_policy_build

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process / deterministic
- primary: `understanding/soundscape_policy.json`
- module: `soundscape_policy.py::run_soundscape_policy_build`
- hard: delivery_brief.json
- gate: none | LLM: none | thrash: density/fail_closed downstream | tests: test_soundscape_policy.py solid

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| enabled + brief | build_policy; validate; write; heal | IN_CODE | run |
| enabled + brief missing | RuntimeError | IN_CODE | explicit raise |
| disabled | skip stub; heal | IN_CODE | `persist_soundscape_skip_stub` |
| invalid policy | ValueError | IN_CODE | `validate_soundscape_policy` |
| hollow | Completeness rails | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| brief done | Proceed | IN_CODE | |
| soft sonic/acoustic absent | Density from available sources | IN_CODE | `_density_from_sources` |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No gate | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | policy + heal | IN_CODE | |
| hard fail | Raise (fail_closed defaults true) | IN_CODE | soundscape.fail_closed |
| invent obligation gate | May adjust slots | IN_CODE | `_apply_invent_obligation_gate` |

## 5. Side effects

- Writes soundscape_policy.json — `IN_CODE`
- Consumers: sound_design_plan, music_palette, sfx_prompt — contract
- Downstream MusicGen/MMAudio **host** uses policy; model quality N/A

## 6. Complexity traps

- Deterministic density + operator overrides + invent gate — `IN_CODE`
- Local heavy ML: N/A (policy only; later stages invoke MMAudio/MusicGen)

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard delivery_brief | Matches body raise | IN_CODE |
| sufficiency required fields | Matches validator | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | — | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | soundscape.enabled=true, fail_closed=true → completes or hard fails honestly | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | Overrides optional | IN_CODE | `save_operator_overrides` |
| landmine | fail_closed + thin brief density could hard-stop unattended | IN_CODE | DoD progression |
| partial-only fix risk | Softening fail_closed only for partial | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

| flag | default | effect |
|------|---------|--------|
| soundscape.enabled | true | stub if false |
| soundscape.fail_closed | true | raise vs soft |
| soundscape.strict_slots | true | occupancy |
| min_density.* | see defaults | invent obligations |

## TEST_GAP

- Brief missing RuntimeError under pipeline admit
- invent_obligation_status edge

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [x] 6 Ship bar  [ ] 7 Cross-stage

## Open questions

1. Prefer incomplete vs hard raise when density invent blocked under Full-auto?

## discovery_status

`complete`
