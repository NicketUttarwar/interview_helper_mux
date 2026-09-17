# Possibility Map — music_palette_compose

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | OpenAI cue placement | **delivery** seed #61
- primary: `sound_design/music_palette_compose.json`
- module: `stages/music_palette_compose.py::run_music_palette_compose`
- hard (contract): SDP from sound_design_palettes | body: SDP soft/optional + `_default_cues`
- gate: none | music epoch: MUSIC_REQUIRES_ASSEMBLY incompleteness
- thrash: low | tests: solid (host)

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| SDP present + assets | LLM arrange cues; persist compose + rewrite SDP cues | IN_CODE | `run_music_palette_compose` / `persist` |
| SDP missing/empty | Soft `_optional_json` → `_default_cues` / sparse | IN_CODE | build_input |
| no assembly_preview | Seed incompleteness — theme/SFX wait | IN_CODE | `stage_completion` MUSIC_REQUIRES_ASSEMBLY |
| LLM empty cues | Deterministic fallback cues | IN_CODE | `persist` raw_cues fallback |
| zero cues + assets exist | May still write cue_count 0 | IN_CODE | honesty threat |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| assembly_preview done | Music epoch admits | IN_CODE | agenda MUSIC_REQUIRES_ASSEMBLY |
| listen_delight advisory done | Soft context only | IN_CODE | optional read |
| STRUCTURAL_DELIVERY clear | Cleared with delivery ladders | IN_CODE | profiles |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No journey gate on stage | IN_CODE | |
| Not in spend_block_stages | Spend block starts at sfx_prompt_craft | IN_CODE | llm_flow_hardening |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | compose JSON + SDP cue seat + bookend seed | IN_CODE | |
| bookend seed fail | Warning; continues | IN_CODE | soft |
| LLM/schema fail | flow stage refuse | IN_CODE | run_flow_llm_stage |
| done-without-primary | Guardrails fight; possible if mark_done alone | UNKNOWN | |

## 5. Side effects

- Writes: music_palette_compose.json; mutates understanding/sound_design_plan.json cues — `IN_CODE`
- Ownership: ALLOW compose + musicgen_candidates operational row — `IN_CODE`
- Invalidates: contract [] — real clears via structural delivery — `IN_CODE`
- Local MusicGen: **not this stage** (placement only)

## 6. Complexity traps

- Dual write compose JSON + SDP — `IN_CODE`
- Contract consumers omit sfx_prompt_craft — `CODE_DOC_CONFLICT`
- Local heavy ML: N/A (OpenAI only)

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard SDP from palettes | Body soft-loads SDP; plan stage also writes | CODE_DOC_CONFLICT |
| soft episode_structure | Code leans narrative_plan chapters | CODE_DOC_CONFLICT |
| consumers mmaudio+mix | Also sfx_prompt_craft via SDP | CODE_DOC_CONFLICT |
| sufficiency ≥1 cue | Fallback may emit 0 | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed / ≤2 | flow refuse or fallback cues | IN_CODE | |
| hollow cue_count=0 | Persist may succeed — seed risk | IN_CODE | FULL_AUTO_REGRESSION_RISK |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | After assembly_preview: OpenAI compose → continue | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| landmine | Empty SDP/assets → sparse music epoch → mix/omit later | IN_CODE | |
| partial-only fix risk | Forcing hard SDP refuse helps Full-auto | IN_CODE | |

## Flags (§5.5)

| flag | default | effect |
|------|---------|--------|
| sound_design.enabled | true | skip path if false |
| mix.underbed_arrangement.* | enabled | arrangement config |
| identity timeout | 480 | budget |

## TEST_GAP

- hard-input refuse when assets>0 and cue_count=0
- contract producer palettes vs plan body

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Is zero-cue compose ship-legal when SDP has theme assets?

## discovery_status

`complete`
