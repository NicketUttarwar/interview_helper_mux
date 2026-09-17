# Stage clinic dossier — speaker_roles

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `speaker_roles`
- seed_position: 8 (analysis)
- tier (contract claim): llm_full — verified vs body in L1 map
- primary_artifact_path (SSOT claim): understanding/speakers.json
- immediate upstream producers (from code — fill in L1): transcript (+spine claim)
- immediate downstream consumers (code + contract claim): topology, content_context
- gate_adjacency: post-G0
- LLM?: OpenAI speaker-roles.system.txt
- thrash_hotspot: yes (recovery)
- test_gravity: solid (hu3, llm_flow) (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/speaker_roles.yaml`
- Map: `.cursor/stage-clinic/maps/speaker_roles.possibility.md`
- Target: `.cursor/stage-clinic/targets/speaker_roles.target.md`
- Notes: `.cursor/stage-clinic/notes/speaker_roles.decisions.md`
- Module (fill in L1): `src/interview_mux/stages/understanding.py::run_speaker_roles`
- Tests (fill in L1): solid (hu3, llm_flow)

## Pack completeness

discovery_status: complete  
Do not mark L1 complete without §5.8 gate (plan §5.8).
