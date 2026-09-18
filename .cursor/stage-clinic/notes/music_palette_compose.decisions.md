# Decisions — music_palette_compose

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | Zero-cue legal with theme assets? | | B1 draft incomplete |
| 2026-09-17 | L3 | MPC-B1 hollow cue_count=0 with assets → incomplete? | Wave 2 yes | `_music_palette_hollow_cues_incompleteness` in stage_completion; pytest |
| 2026-09-17 | L3 | MPC-B2 contract hard producer palettes vs plan? | Wave 2 skip — needs_you | leave open |
| 2026-09-17 | L3 | MPC-B3 consumers include sfx_prompt_craft? | Wave 2 yes | dependency data + bootstrap YAML |
| 2026-09-18 | L3 | MPC-B2 contract hard producer palettes vs plan? | Q1A: producer=sound_design_plan + harden body require SDP | dep override + refuse before LLM; pytest |
