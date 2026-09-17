# Possibility Map — audio_probe_build

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process / local probe platform — `IN_CODE`
- primary: `analysis/run_golden_facts.json` — `IN_CODE`
- gate adjacency: after G0 build in seed order; not a gate — `IN_CODE`
- LLM: local packs possible; clinic = host honesty only

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | requires `transcript/full.json` when enabled | IN_CODE | `run_audio_probe_build` |
| hard missing | required check raises (unless disabled early return) | IN_CODE | |
| soft missing | normalized soft; proceeds without wav | IN_CODE | fail-open source_wav |
| soft stale | soft claims master/edl etc unused by build | CODE_DOC_CONFLICT | contract soft list |
| hollow | disabled/fail_open writes empty probe artifacts then heal | IN_CODE | `empty_probe_artifacts` |
| semantic junk | empty zones still done | IN_CODE | fail_open default true |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | transcript required | IN_CODE | |
| producer invalidated | rebuild | IN_CODE | |
| epoch drift | N/A | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| gate open | seed walks after review_build; G0 may still be open depending on driver | IN_CODE | ANALYSIS_ORDER |
| gate answered | N/A for this stage | IN_CODE | |
| illegal skip | disabled flag writes empties + heal_or_raise | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | write 5 artifacts → heal_or_raise | IN_CODE | |
| soft fail | fail_open=true → empty artifacts + heal | IN_CODE | defaults |
| hard fail | fail_open=false re-raises | IN_CODE | |
| partial persist | write fail can return without heal if fail_open | IN_CODE | write except return |
| done-without-primary | heal after empty golden_facts still marks if primary exists | IN_CODE | honesty: hollow-but-present |
| retry / heal | heal_or_raise flush pending (HC-3 comment) | IN_CODE | |
| identical halt | UNKNOWN | UNKNOWN | |

## 5. Side effects

- Writes: golden_facts, protected_zones, speaker_flows, probe_report, audio_tags_by_flow — `IN_CODE`
- Forbidden writes risk: ownership producers list `transcribe` / `vernacular_segment_sanitize` for some paths but `write_mode=operational` allows any writer — `CODE_DOC_CONFLICT` (misleading producers)
- Invalidates: [] declared
- Consumers: vernacular sanitize, low_conf, boundary, classification — contract

## 6. Complexity traps

- OpenAI: none
- Dual SSOT: ownership producers vs actual writer stage
- Local heavy ML: probe packs / prefer_mlx — N/A internals; host fail_open in clinic

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard full.json | when enabled | IN_CODE |
| soft master/edl/topology/… | not read by build | CODE_DOC_CONFLICT |
| outputs 5 paths | matches | IN_CODE |
| invalidates [] | true | IN_CODE |
| remediation volley_retry | host | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A (no external LLM) | N/A | IN_CODE | |

## 9. Full-auto / defaults path

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults happy path | enabled + fail_open + shadow enforcement → always completes with some JSON | IN_CODE | `app.defaults.json` audio_probes |
| human stall required? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| auto-accept | N/A | IN_CODE | |
| partial-only fix risk | Tightening fail_open affects Full-auto | FULL_AUTO_REGRESSION_RISK | |

## DoD threats

- [ ] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions for operator

1. Is shadow+fail_open empty golden_facts an acceptable Full-auto outcome, or should fail_open refuse?

## discovery_status

`complete`
