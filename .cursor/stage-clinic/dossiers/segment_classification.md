# Stage clinic dossier — segment_classification

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `segment_classification`
- seed_position: 15 (analysis)
- tier (contract claim): llm_full — verified (+ deterministic ideal-cuts path)
- primary_artifact_path (SSOT claim): segments/manifest.json
- immediate upstream producers (from code — fill in L1): boundary_detection (`segments/boundaries.json`)
- immediate downstream consumers (code + contract claim): content_brief_reanchor, vernacular, low_conf, fuse, sonic, palettes
- gate_adjacency: none
- LLM?: OpenAI/external (prompt: segmentation/segment-classification.system.txt)
- thrash_hotspot: yes (resplit unlink)
- test_gravity: solid

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/segment_classification.yaml`
- Map: `.cursor/stage-clinic/maps/segment_classification.possibility.md`
- Target: `.cursor/stage-clinic/targets/segment_classification.target.md`
- Notes: `.cursor/stage-clinic/notes/segment_classification.decisions.md`
- Module (fill in L1): `src/interview_mux/stages/segmentation.py` (`run_classification`)
- Tests (fill in L1): `tests/test_classification_obligation.py`, resilience suites

## Pack completeness

discovery_status: complete  
§5.8 gate satisfied (index + body/rails + declared-vs-actual + flags + TEST_GAP).  
Open questions: 
