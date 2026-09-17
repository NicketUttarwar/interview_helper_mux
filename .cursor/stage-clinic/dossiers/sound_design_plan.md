# Stage clinic dossier — sound_design_plan

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `sound_design_plan`
- seed_position: 53 (delivery)
- tier (contract claim): llm_full — verified
- primary_artifact_path (SSOT claim): understanding/sound_design_plan.json
- immediate upstream producers (from code — L1): transitions (hard)
- immediate downstream consumers: vo_*, edl, music/sfx (contract + agenda SDP producer check)
- gate_adjacency: none
- LLM?: OpenAI — `sound_design/plan-flow1.system.txt`
- thrash_hotspot: yes — producer_stage fingerprint / invent / sdp_unsanitary
- test_gravity: solid (`test_sound_design_plan_build060`, sanitize SDP)

## Evidence checklist (§5.1–5.6)

- [x] §5.1–5.6 all

## Links

- Contract: `docs/cross-cutting/stage-contracts/sound_design_plan.yaml`
- Map: `.cursor/stage-clinic/maps/sound_design_plan.possibility.md`
- Target: `.cursor/stage-clinic/targets/sound_design_plan.target.md`
- Notes: `.cursor/stage-clinic/notes/sound_design_plan.decisions.md`
- Module (L1): `src/interview_mux/stages/sound_design_stages.py::run_sound_design_plan`
- Tests (L1): `tests/test_sound_design_plan_build060.py`, `tests/test_artifact_sanitize_sdp.py`

## Pack completeness

discovery_status: complete
