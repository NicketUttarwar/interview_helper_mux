# Stage clinic dossier — boundary_detection

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `boundary_detection`
- seed_position: 14 (analysis)
- tier (contract claim): llm_full — verified OpenAI + ideal-cuts skip path
- primary_artifact_path (SSOT claim): segments/boundaries.json
- immediate upstream producers (from code — fill in L1): ideal_cuts_materialize; content_brief; speakers; transcript
- immediate downstream consumers (code + contract claim): segment_classification, content_brief_reanchor, sonic/palettes/missing_framing (claim)
- gate_adjacency: none
- LLM?: OpenAI/external (prompt: segmentation/boundary-detection.system.txt)
- thrash_hotspot: yes (bind skip vs coarse)
- test_gravity: solid

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/boundary_detection.yaml`
- Map: `.cursor/stage-clinic/maps/boundary_detection.possibility.md`
- Target: `.cursor/stage-clinic/targets/boundary_detection.target.md`
- Notes: `.cursor/stage-clinic/notes/boundary_detection.decisions.md`
- Module (fill in L1): `src/interview_mux/stages/segmentation.py` (`run_boundaries`)
- Tests (fill in L1): `tests/test_boundary_detection_spine_input.py` + many

## Pack completeness

discovery_status: complete  
§5.8 gate satisfied (index + body/rails + declared-vs-actual + flags + TEST_GAP).  
Open questions: 
