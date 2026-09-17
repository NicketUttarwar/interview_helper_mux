# Stage clinic dossier — boundary_topic_resplit

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `boundary_topic_resplit`
- seed_position: 18 (analysis)
- tier (contract claim): llm_full — often no LLM (skip/deterministic)
- primary_artifact_path (SSOT claim): segments/boundaries.json
- immediate upstream producers (from code — fill in L1): content_brief_reanchor; boundaries/manifest soft
- immediate downstream consumers (code + contract claim): segment_classification (unlink), vernacular, low_conf, fuse, sonic…
- gate_adjacency: none
- LLM?: OpenAI/external optional (segmentation/boundary-detection-refine.system.txt)
- thrash_hotspot: yes
- test_gravity: solid

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/boundary_topic_resplit.yaml`
- Map: `.cursor/stage-clinic/maps/boundary_topic_resplit.possibility.md`
- Target: `.cursor/stage-clinic/targets/boundary_topic_resplit.target.md`
- Notes: `.cursor/stage-clinic/notes/boundary_topic_resplit.decisions.md`
- Module (fill in L1): `src/interview_mux/stages/segmentation.py` (`run_boundary_topic_resplit`)
- Tests (fill in L1): `tests/test_boundary_topic_resplit.py`, `test_hs2_resplit_self_archive.py`

## Pack completeness

discovery_status: complete  
§5.8 gate satisfied (index + body/rails + declared-vs-actual + flags + TEST_GAP).  
Open questions: hollow-done without boundaries intentional?
