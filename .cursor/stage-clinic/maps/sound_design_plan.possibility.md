# Possibility Map — sound_design_plan

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- delivery #53 | llm_full | primary SDP | hard transitions
- module: `sound_design_stages.py::run_sound_design_plan`
- `sound_design.enabled` default true; disable → force heal skip

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| enabled false | `_mark_skipped` force heal | IN_CODE | |
| transitions hard | LLM plan persist + fingerprint restamp | IN_CODE | `restamp_committed_artifact` |
| assets min 1 | sufficiency | IN_CODE | contract |
| invent unpaid / wrong producer | incompleteness | IN_CODE | stage_completion SDP |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| palettes-shaped file without delivery producer | refuse seed_complete | IN_CODE | agenda `_sdp_producer_stage` |
| order drift | reconcile fail-open before LLM | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | SDP + music_brief; compose_deferred cues | IN_CODE | |
| LLM fail | flow refuse | IN_CODE | |
| skip enabled=false | force heal | IN_CODE | |

## 5. Side effects

- Writes SDP + music_brief (+ compact txt contract) — IN_CODE
- Invalidates sfx_prompt_craft, vo_*, edl — contract
- Consumers list includes sound_design_palettes (analysis) — CODE_DOC_CONFLICT vs delivery order

## 6. Complexity traps

- OpenAI + motif + placeholder cues dual SSOT with later music_palette_compose — IN_CODE
- Local heavy ML: N/A (MusicGen later)

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard transitions | matches | IN_CODE |
| consumers palettes | early stage already ran | CODE_DOC_CONFLICT |
| assets≥1 | enforced | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed/≤2 | refuse | IN_CODE | |
| hollow assets | incompleteness / invent | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto enabled=true | OpenAI SDP; no human | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| enabled=false | skip heal — may starve music/sfx | FULL_AUTO_REGRESSION_RISK | |
| producer fingerprint | blocks skip-consume of palettes file | IN_CODE | |

## Flags (§5.5)

- `sound_design.enabled` default true
- `sound_design.early_palettes_llm=false` (upstream)

## TEST_GAP

- consumers list vs delivery walk
- invent obligation empty palettes+cues

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Update contract consumers to delivery-true set?

## discovery_status

`complete`
