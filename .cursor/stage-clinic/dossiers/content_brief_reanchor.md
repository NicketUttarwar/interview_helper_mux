# Stage clinic dossier — content_brief_reanchor

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `content_brief_reanchor`
- seed_position: 16 (analysis)
- tier (contract claim): llm_full — verified
- primary_artifact_path (SSOT claim): understanding/content_brief.json
- immediate upstream producers (from code — fill in L1): segment_classification; prior content_context brief
- immediate downstream consumers (code + contract claim): boundary_topic_resplit, sonic, palettes, missing_framing
- gate_adjacency: none
- LLM?: OpenAI/external (prompt: understanding/content-brief-reanchor.system.txt)
- thrash_hotspot: no
- test_gravity: solid

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/content_brief_reanchor.yaml`
- Map: `.cursor/stage-clinic/maps/content_brief_reanchor.possibility.md`
- Target: `.cursor/stage-clinic/targets/content_brief_reanchor.target.md`
- Notes: `.cursor/stage-clinic/notes/content_brief_reanchor.decisions.md`
- Module (fill in L1): `src/interview_mux/stages/understanding.py` (`run_content_brief_reanchor`)
- Tests (fill in L1): `tests/test_content_brief_reanchor.py`, `test_content_brief_segment_sync.py`

## Pack completeness

discovery_status: complete  
§5.8 gate satisfied (index + body/rails + declared-vs-actual + flags + TEST_GAP).  
Open questions: 
