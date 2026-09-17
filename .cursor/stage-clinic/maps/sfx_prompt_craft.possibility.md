# Possibility Map — sfx_prompt_craft

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | primary: sfx_prompts.json | seed #62
- module: `sound_design_stages.run_sfx_prompt_craft`
- gate: G1.5 (`g1_5_require_prompt_approval=true` defaults) | spend_block_stages
- LLM OpenAI | thrash: duplicate merge fixed | tests: solid

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| sound_design.enabled=false | `_mark_skipped` | IN_CODE | |
| SDP missing | `default_sound_design_plan()` — soft hollow | IN_CODE | `_load_sound_design_plan` |
| soft packets missing | Proceed thin | IN_CODE | build_input |
| prompts list missing | ValueError on persist | IN_CODE | persist |
| MUSIC_REQUIRES_ASSEMBLY | Seed incomplete without assembly | IN_CODE | stage_completion |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| palette/SDP cues updated | Re-craft replaces prompts (no list-merge) | IN_CODE | write_validated merge_from_disk=False |
| SDP duration repair | `_repair_sdp_asset_durations` | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| G1.5 required + not approved | Blocks mmaudio (`can_run_sfx_generation`) | IN_CODE | sfx_prompt_review |
| first_try + QA green | `maybe_auto_approve_prompt_review` | IN_CODE | first_try.enabled=true default |
| QA warnings | No auto-approve — **human/driver** | IN_CODE | FULL_AUTO_REGRESSION_RISK |
| Not in PARTIAL_MUST_ACT | Partial may still stall on G1.5 GUI | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | validated prompts + optional auto-approve | IN_CODE | |
| LLM fail ≤2 | stage error | IN_CODE | |
| re-craft | replace prompts (no duplicate concat) | IN_CODE | |

## 5. Side effects

- Writes sfx_prompts.json; may rewrite SDP durations — `IN_CODE`
- run_meta sfx_prompt_review — `IN_CODE`

## 6. Complexity traps

- Contract consumers: [sfx_prompt_craft] self — `CODE_DOC_CONFLICT`
- G1.5 default true + first_try auto only if warnings empty — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| consumers self | Should be mmaudio_sfx | CODE_DOC_CONFLICT |
| soft: [] | Many soft volley packets | CODE_DOC_CONFLICT |
| hard SDP from plan | Soft default SDP | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| OpenAI ≤2 fail | Hard error | IN_CODE | |
| thin prompts | Schema/lint may fail or warn | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + first_try + green QA | Auto-approve → mmaudio | IN_CODE | |
| Full-auto + QA warnings | Stall until approve (GUI) or driver | IN_CODE | FULL_AUTO_REGRESSION_RISK |
| Product seed walk alone | Does not call approve API | IN_CODE | landmine |
| tools/full_auto_driver | `approve_sfx_prompts()` on block | IN_CODE | driver-only |
| human stall? | Yes when G1.5 pending | IN_CODE | |
| GUI-only? | Approve panel when required | IN_CODE | |
| partial-only fix risk | Disabling G1.5 for Full-auto only is OK if documented | | |

## Flags (§5.5)

| flag | default | effect |
|------|---------|--------|
| g1_5_require_prompt_approval | **true** | Blocks mmaudio until approved |
| first_try.enabled | true | Auto-approve if QA green |
| sound_design.enabled | true | skip stage |

## TEST_GAP

- Full-auto product path without driver when QA warnings present
- Contract consumer typo xcheck

## DoD threats

- [x] 1  [x] 2  [x] 3 Stalls  [x] 4  [x] 5  [ ] 6  [x] 7

## Open questions

1. Should Full-auto auto-approve G1.5 even with soft warnings?

## discovery_status

`complete`
