# Possibility Map — mmaudio_sfx

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process (claim) | MusicGen-first host | seed #63
- primary: mmaudio_qa.json + sound_design/assets + master/sfx
- modules: sfx_mmaudio + mmaudio_asset_qa + musicgen_runner
- hard: SDP, prompts, assembly_preview (`_check_mmaudio_sfx`) + G1.5
- thrash: HIGH | tests: solid host

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| hard missing | StageInputIssue | IN_CODE | `_check_mmaudio_sfx` |
| G1.5 not approved | RuntimeError require_sfx_generation | IN_CODE | |
| theme WAVs missing | incompleteness / heal_mmaudio_qa_wav_parity | IN_CODE | |
| plan_hash unchanged | `_should_skip_generation` | IN_CODE | |
| hollow QA | seed incomplete until artifact_status complete | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| prompts/SDP change | regen | IN_CODE | |
| music epoch sealed | thrash_hardening blocks MusicGen re-entry | IN_CODE | |
| mix heal | ensure_mmaudio_qa_before_mix | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| G1.5 pending | Block generation | IN_CODE | |
| post_listen block_mix | May block mix after fail | IN_CODE | post_listen_gate_mode=block_mix |
| music listen (g1_5_require_music_listen) | default false | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| success | WAVs + QA pass | IN_CODE | |
| ladder exhaust + fail_closed_on_stub | stamp music_omitted (no creative stub) | IN_CODE | musicgen_runner |
| placeholder allow | first_try_allow_placeholder_mix false default | IN_CODE | |
| identical | musicgen_theme_failed | IN_CODE | |
| hard without omit | Loud fail / unavailable | IN_CODE | |

## 5. Side effects

- WAVs, mmaudio_qa.json, operator/music_omitted.json, run_meta sfx_generation_meta — `IN_CODE`

## 6. Complexity traps

- Local heavy ML: invokes MusicGen ladder then optional MMAudio (`mmaudio_backup_on_stub` default false); **internals N/A** — host omit honesty in clinic
- GUI StageInfo understates MusicGen-first — `CODE_DOC_CONFLICT`
- Contract lifecycle llm_execute — `CODE_DOC_CONFLICT`
- sufficiency min_rows:0 vs creative_delivery — `CODE_DOC_CONFLICT`

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard SDP+prompts | + assembly_preview hard | CODE_DOC_CONFLICT |
| tier process + llm_execute | No LLM | CODE_DOC_CONFLICT |
| consumers mix | Correct | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A OpenAI stage | Local gen only | IN_CODE | |
| semantic QA external if configured | UNKNOWN | | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Happy | prompts approved → stems → QA → mix | IN_CODE | |
| omit all beds | music_omitted honest; mix completeness excludes omitted | IN_CODE | |
| block_mix_on_mmaudio_qa_fail=true | Failed QA stalls mix | IN_CODE | FULL_AUTO_REGRESSION_RISK |
| G1.5 stall upstream | Same as sfx_prompt_craft | IN_CODE | |
| human stall? | G1.5 / post_listen / music listen if on | IN_CODE | |
| GUI-only? | Listen/approve panels | IN_CODE | |
| partial-only fix risk | Softening QA block for Full-auto only OK if inventory | | |

## Flags (§5.5)

| flag | default | effect |
|------|---------|--------|
| musicgen.fail_closed_on_stub | true | omit not stub |
| mmaudio_backup_on_stub | false | no MMAudio backup |
| block_mix_on_mmaudio_qa_fail | true | mix blocked |
| one_regen_on_fail | true | one regen |
| first_try_allow_placeholder_mix | false | no placeholders |

## TEST_GAP

- contract lifecycle honesty; StageInfo MusicGen-first label

## DoD threats

- [x] 1–7 all live (omit vs ship, thrash, stalls)

## Open questions

1. Omit-all themes: Full-auto ship-legal if later delight sonic_weave fails?

## discovery_status

`complete`
