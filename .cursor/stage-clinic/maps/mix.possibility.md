# Possibility Map — mix

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process | primary: master/assembly.wav | seed #64
- module: `assembly.run_mix` → `sound_design.mix` + `enforce_mix_completeness`
- hard actual: ingest audio, selection, **edl**, **SDP**, seat/VO agreement, theme bookends, mmaudio QA when required
- thrash: **PRIMARY** with junction_snip_qa | tests: solid

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| edl/SDP/selection missing | StageInputIssue | IN_CODE | `_check_mix` |
| live incomplete-cut criticals | Loud refuse; pin junction | IN_CODE | `refuse_mix_if_live_incomplete_cuts` |
| junction_recut_precedes_mix | Seed/runtime flip: junction before mix | IN_CODE | agenda/runtime/air_order |
| VO script≠WAV | Heal transitions then refuse | IN_CODE | `_vo_script_wav_agreement_issues` |
| theme bookends not ready | assert_theme_bookends_ready_for_mix | IN_CODE | |
| mmaudio QA missing | ensure_mmaudio_qa_before_mix escalate | IN_CODE | |
| hollow assembly mtime-only | `_mix_unseated_incompleteness` / mix_outputs_seated | IN_CODE | |
| music_omitted assets | Excluded from missing-SFX | IN_CODE | mix_completeness / sound_design |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| EDL order change | invalidate_mix_on_order_change default false | IN_CODE | |
| junction remaster_mix_only | Unmark/re-run mix without wipe EDL | IN_CODE | junction_snip_qa |
| spend artifacts incomplete | require_spend_artifacts_complete | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| post_listen block_mix | May stall before mix | IN_CODE | sync_post_listen_gate_state |
| g_listen after remaster | Pending; finalize blocks if mode=block | IN_CODE | `_set_g_listen_pending_after_remaster` |
| No PARTIAL_MUST_ACT on mix | Partial may still hit g_listen | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | assembly.wav + coverage/QC sidecars; optional delight refresh | IN_CODE | |
| completeness mode=block | SFX placeholder hard (soft_fail_sfx_placeholder=false); VO often warn (hard_fail_missing_blocking_vo=false) | IN_CODE | completeness_gate |
| remux | intelligibility / bed_presence / underbed_ab cycles | IN_CODE | |
| PublishabilityBlocked | Hard pre_mix | IN_CODE | |
| empty speech | hard_fail_empty_speech | IN_CODE | |
| identical incomplete_cut | Ping-pong if junction cannot precede | IN_CODE | FULL_AUTO_REGRESSION_RISK |
| inner junction remaster | Bypasses incomplete-cut refuse | IN_CODE | `_junction_snip_qa_inner` |

## 5. Side effects

- Writes: assembly.wav, music_cue_coverage, bed_presence_qc, underbed_ab_qc, listen_critic, listenability_contract; may rewrite EDL listenability — `IN_CODE`
- Invalidates: contract []; structural profiles clear mix — `IN_CODE`
- Consumers: junction, finalize — `IN_CODE`

## 6. Complexity traps

- Contract soft edl vs hard `_check_mix` — `CODE_DOC_CONFLICT`
- Completeness VO soft / SFX hard asymmetry — `IN_CODE`
- Local heavy ML: N/A (consumes MusicGen/MMAudio stems; host only)
- Dual thrash with junction — `IN_CODE`

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard ingest+selection | + edl + SDP hard | CODE_DOC_CONFLICT |
| edl soft correctness | Required in `_check_mix` | CODE_DOC_CONFLICT |
| junction soft | Live incomplete cuts hard-refuse | CODE_DOC_CONFLICT |
| llm_execute lifecycle | No LLM | CODE_DOC_CONFLICT |
| invalidates [] | Remaster/thrash clears via profiles | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A OpenAI | Deterministic host mix | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Happy music epoch complete | Mix seats → junction | IN_CODE | |
| incomplete cuts live | Junction-first then mix | IN_CODE | junction_recut_precedes_mix |
| g_listen_mode=block after remaster | Stalls finalize until clear; product Full-auto seed does not auto-clear | IN_CODE | FULL_AUTO_REGRESSION_RISK |
| tools/full_auto_driver | clear_g_listen skipped/continued | IN_CODE | driver-only |
| completeness / bed fail_closed | Hard stop remux exhaust | IN_CODE | |
| human stall? | g_listen / post_listen | IN_CODE | |
| GUI-only? | G-Listen continue/skip | IN_CODE | |
| partial-only fix risk | Auto-clear g_listen only in Full-auto — must not weaken Partial must-act elsewhere | | yes if mis-scoped |

## Flags (§5.5)

| flag | default | effect |
|------|---------|--------|
| completeness_gate.mode | block | Hard completeness |
| hard_fail_missing_blocking_vo | false | VO warn path |
| soft_fail_sfx_placeholder | false | SFX hard |
| bed_presence_qc.fail_closed | true | Hard beds |
| intelligibility remux max | 2 | Remux loops |
| g_listen_mode | **block** | Finalize stall |
| post_listen_gate_mode | block_mix | Pre-mix stall |
| timeout | 600 | |

## TEST_GAP

- Contract hard/soft vs `_check_mix` parity test
- Product Full-auto (no driver) g_listen after remaster
- VO soft vs SFX hard under creative_delivery matrix

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [x] 3 Stalls  [ ] 4  [x] 5 Defaults  [x] 6 Ship  [x] 7 Cross-stage

## Open questions

1. Keep VO soft / SFX hard under creative_delivery?
2. Product Full-auto: auto-clear g_listen or change default mode?

## discovery_status

`complete`
