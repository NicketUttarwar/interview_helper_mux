# Episode structure catalog

**Status:** shipped (Plan 2). Deterministic composer writes `understanding/episode_structure.json`.

**Related:** [sound-design.md](./sound-design.md) · [sonic-context.md](./sonic-context.md) · [soundscape-policy.md](./soundscape-policy.md) · [interview-scenario-atlas.md](../prompts/_shared/interview-scenario-atlas.md) · [local-llm-tier.md](./local-llm-tier.md) (Plan 1 LX-03 compact digest)

---

## Intent

Orient each run into a **sparse** slot plan. Components are **candidates**, not a mandatory checklist. Missing payoff/outro/cold-open is valid.

Pipeline stage: `episode_structure_compose` (analysis) + delivery **refresh** before `sound_design_plan`. **Not** on `QUALITY_LOCAL_ALLOWLIST` — no local/OpenAI authorship of the structure artifact.

---

## Non-negotiable rules

| Rule | Meaning |
|------|---------|
| No rigid component set | Default gates `allow`/`prefer`; almost never hard `must` |
| Orient without breaking | Preserve Q→A / rebuttal integrity; prefer bridges / gap VO |
| Main-audio single-use | Each `segment_id` ≤1× in delivery timeline |
| Hook-reel exception | Cold-open tease may repeat once (`repeat_allowed: true`) |
| Gap VO additive | Do not duplicate dialogue to fill holes |
| Deterministic composer | Packs + scoring only |

Assembler precedence: **operator overrides > trauma/hard bans > soundscape policy > atlas posture > format presets > genre/style presets > defaults**.

---

## Decision grammar

Every emitted slot: `component_id`, `class` (`standard`|`dynamic`), `gate` (`must`|`prefer`|`allow`|`forbid`), optional `speech_job`, `music_transition`, `asset_role`, `placement`, `priority`, `bound_segment_ids`, `repeat_allowed`.

### Music transition verbs

`into_speech`, `after_speech`, `under_speech`, `between_islands`, `around_vo`, `motif_callback`, `bed_morph`, `silence_as_transition`, `resolve_swell`, `tension_hold`.

---

## A. Standard components (skeleton — not mandatory)

| id | Intent | Default music | Typical gate |
|----|--------|---------------|--------------|
| `STD_cold_open_slot` | Pre-thesis attention | `into_speech` / silence | prefer → omit OK |
| `STD_orientation` | Who / why / stakes | soft after / dry | prefer → omit OK |
| `STD_act_body` | Interview mass (unique segments) | `under_speech` | prefer |
| `STD_chapter_hinge` | Section reset | chapter stinger | allow |
| `STD_comprehension_bridge` | Survive reorder | `around_vo` | allow |
| `STD_payoff_close` | End on clarity | `resolve_swell` | allow — **not required** |
| `STD_outro_button` | Clean landing | after-speech | allow — **not required** |
| `STD_lufs_master` | Loudness (mastering stage) | n/a | must (stage), not speech slot |

---

## B–G. Dynamic families

| Family | Example ids | Purpose |
|--------|-------------|---------|
| **B Openings** | `DYN_mid_quote_cold_open`, `DYN_teaser_montage`, `DYN_content_warning_pad` | Attention without trauma/triumph mistakes |
| **C Arc** | `DYN_tension_hold`, `DYN_breakthrough`, `DYN_nostalgia_bed` | Emotional pacing |
| **D Transitions** | `DYN_topic_shift_spoken`, `DYN_rebuttal_pair_lock`, `DYN_montage_glue` | Clip/topic glue |
| **E Host/VO** | `DYN_reaction`, `DYN_chapter_hook`, `DYN_missing_setup` | Production craft + G1 |
| **F Beds** | pastoral/urban/lab/intimate accents via music verbs | Palette vocabulary |
| **G Packs** | YAML under `episode-structure-packs/` | Gate reweights |

Pack examples: **debate** prefers rebuttal lock / forbids triumph sting; **trauma_adjacent** forces content warning / forbids cold-open montage; **media_profile** prefers mid-quote cold open.

---

## Artifact

Path: `understanding/episode_structure.json`  
Schema: [episode_structure.schema.json](./json-schemas/episode_structure.schema.json)

Compact digest (≤ ~800 tokens) is stored on `compact_digest` and written beside the artifact for LX-03 / `extra_digest_paths`: axes, emitted component_ids + gates, `segment_order`, high-profile STD omits, hook_reel flag.

---

## Pipeline

| When | Action |
|------|--------|
| Analysis | `episode_structure_compose` after `soundscape_policy_build` |
| Delivery | `refresh_episode_structure` inside `sound_design_plan` `build_input` (with cue refresh) |

Config: `structure.*` — see [config-keys.md](./config-keys.md#structure).
