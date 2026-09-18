# Stage clinic dossier — source_acoustic_profile

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `source_acoustic_profile`
- seed_position: 6 (analysis)
- tier (contract claim): deterministic — verified vs body in L1 map
- primary_artifact_path (SSOT claim): understanding/source_acoustic_profile.json
- immediate upstream producers (from code — fill in L1): ingest+transcribe
- immediate downstream consumers (code + contract claim): spine, sonic, palettes
- gate_adjacency: none
- LLM?: no
- thrash_hotspot: false (FORCE_DONE_GUARDED = hollow-force guard only; SAP-B5 Q2B)
- test_gravity: solid (test_source_acoustic_profile) (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/source_acoustic_profile.yaml`
- Map: `.cursor/stage-clinic/maps/source_acoustic_profile.possibility.md`
- Target: `.cursor/stage-clinic/targets/source_acoustic_profile.target.md`
- Notes: `.cursor/stage-clinic/notes/source_acoustic_profile.decisions.md`
- Module (fill in L1): `src/interview_mux/stages/understanding.py::run_source_acoustic_profile`
- Tests (fill in L1): solid (test_source_acoustic_profile)

## Pack completeness

discovery_status: complete  
Do not mark L1 complete without §5.8 gate (plan §5.8).
