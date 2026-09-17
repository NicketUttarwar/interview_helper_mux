# Stage clinic dossier — audio_probe_build

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `audio_probe_build`
- seed_position: 5 (analysis)
- tier (contract claim): process — verified vs body in L1 map
- primary_artifact_path (SSOT claim): analysis/run_golden_facts.json
- immediate upstream producers (from code — fill in L1): transcript/full.json
- immediate downstream consumers (code + contract claim): vernacular, low_conf, boundary
- gate_adjacency: none
- LLM?: local packs N/A
- thrash_hotspot: no
- test_gravity: solid (test_audio_probes) (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/audio_probe_build.yaml`
- Map: `.cursor/stage-clinic/maps/audio_probe_build.possibility.md`
- Target: `.cursor/stage-clinic/targets/audio_probe_build.target.md`
- Notes: `.cursor/stage-clinic/notes/audio_probe_build.decisions.md`
- Module (fill in L1): `src/interview_mux/stages/audio_probes.py`
- Tests (fill in L1): solid (test_audio_probes)

## Pack completeness

discovery_status: complete  
Do not mark L1 complete without §5.8 gate (plan §5.8).
