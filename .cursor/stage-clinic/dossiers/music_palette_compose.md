# Stage clinic dossier — music_palette_compose

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `music_palette_compose`
- seed_position: 61 (delivery)
- tier (contract claim): llm_full — verified OpenAI via `run_flow_llm_stage`
- primary_artifact_path (SSOT claim): sound_design/music_palette_compose.json
- immediate upstream producers (from code — L1): sound_design_plan / palettes (SDP soft in body); assembly_preview required for seed completeness; soft: edl/selection/delight/soundscape/delivery_brief
- immediate downstream consumers (code + contract claim): mmaudio_sfx, mix (via SDP cues); sfx_prompt_craft reads SDP
- gate_adjacency: none (music epoch waits assembly_preview)
- LLM?: OpenAI — sound_design/music-palette-compose.system.txt
- thrash_hotspot: low alone; music-epoch seal / MusicGen re-entry adjacent
- test_gravity: solid (excl. local-ML) — test_music_palette_compose.py, quality uplift

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/music_palette_compose.yaml`
- Map: `.cursor/stage-clinic/maps/music_palette_compose.possibility.md`
- Target: `.cursor/stage-clinic/targets/music_palette_compose.target.md`
- Notes: `.cursor/stage-clinic/notes/music_palette_compose.decisions.md`
- Module (L1): `src/interview_mux/stages/music_palette_compose.py::run_music_palette_compose`
- Tests (L1): `tests/test_music_palette_compose.py`, `test_music_quality_uplift.py`

## Pack completeness

discovery_status: complete
