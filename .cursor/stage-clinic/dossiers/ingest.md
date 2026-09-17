# Stage clinic dossier — ingest

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `ingest`
- seed_position: 2 (analysis)
- tier (contract claim): process — verified vs body in L1 map
- primary_artifact_path (SSOT claim): ingest/normalized.wav
- immediate upstream producers (from code — fill in L1): preclean isolated optional / input_audio
- immediate downstream consumers (code + contract claim): transcribe, probes, SAP…
- gate_adjacency: none
- LLM?: no
- thrash_hotspot: no
- test_gravity: solid (test_source_loudness, pipeline) (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/ingest.yaml`
- Map: `.cursor/stage-clinic/maps/ingest.possibility.md`
- Target: `.cursor/stage-clinic/targets/ingest.target.md`
- Notes: `.cursor/stage-clinic/notes/ingest.decisions.md`
- Module (fill in L1): `src/interview_mux/stages/ingest.py`
- Tests (fill in L1): solid (test_source_loudness, pipeline)

## Pack completeness

discovery_status: complete  
Do not mark L1 complete without §5.8 gate (plan §5.8).
