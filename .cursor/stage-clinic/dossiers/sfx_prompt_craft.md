# Stage clinic dossier — sfx_prompt_craft

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `sfx_prompt_craft`
- seed_position: 62 (delivery)
- tier (contract claim): llm_full — verified OpenAI
- primary_artifact_path (SSOT claim): sound_design/sfx_prompts.json
- immediate upstream producers (from code — L1): SDP (`_load_sound_design_plan`); soft acoustic/sonic/soundscape/delivery_brief
- immediate downstream consumers (code + contract claim): mmaudio_sfx (contract wrongly lists self)
- gate_adjacency: G1.5 prompt approval (`g1_5_require_prompt_approval` default **true**)
- LLM?: OpenAI sfx prompt craft
- thrash_hotspot: re-craft duplicate prompts (fixed merge_from_disk=False)
- test_gravity: solid — test_sound_design_stages, test_g1_5_prompt_review

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails
- [x] §5.2 Declared-vs-actual
- [x] §5.3 Schemas / OpenAI (local ML N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/sfx_prompt_craft.yaml`
- Map: `.cursor/stage-clinic/maps/sfx_prompt_craft.possibility.md`
- Target: `.cursor/stage-clinic/targets/sfx_prompt_craft.target.md`
- Notes: `.cursor/stage-clinic/notes/sfx_prompt_craft.decisions.md`
- Module (L1): `stages/sound_design_stages.py::run_sfx_prompt_craft`
- Tests (L1): `tests/test_sound_design_stages.py`, `test_g1_5_prompt_review.py`

## Pack completeness

discovery_status: complete
