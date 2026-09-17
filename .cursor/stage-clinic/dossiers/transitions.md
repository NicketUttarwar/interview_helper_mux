# Stage clinic dossier — transitions

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `transitions`
- seed_position: 52 (delivery)
- tier (contract claim): llm_full — verified (`run_flow_llm_stage`)
- primary_artifact_path (SSOT claim): master/transitions.json
- immediate upstream producers (from code — L1): nugget_layup + selection + mastering_plan (contract hard); body soft-reads many
- immediate downstream consumers: sound_design_plan, vo_*, edl (contract invalidates)
- gate_adjacency: none on stage; may stamp pair freeze when G1 skipped/open
- LLM?: OpenAI — `assembly/transitions.system.txt`
- thrash_hotspot: yes — selection prerepair + pair freeze + bridge incompleteness pins
- test_gravity: solid (bridge/glue/endc/major thrash)

## Evidence checklist (§5.1–5.6)

- [x] §5.1–5.6 all

## Links

- Contract: `docs/cross-cutting/stage-contracts/transitions.yaml`
- Map: `.cursor/stage-clinic/maps/transitions.possibility.md`
- Target: `.cursor/stage-clinic/targets/transitions.target.md`
- Notes: `.cursor/stage-clinic/notes/transitions.decisions.md`
- Module (L1): `src/interview_mux/stages/selection.py::run_transitions`
- Tests (L1): `tests/test_endc_glue_before_edl.py`, `tests/test_f4_bridge_glue.py`, thrash suites

## Pack completeness

discovery_status: complete
