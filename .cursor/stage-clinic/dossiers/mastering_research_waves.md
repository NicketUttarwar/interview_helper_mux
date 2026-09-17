# Stage clinic dossier — mastering_research_waves

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `mastering_research_waves`
- seed_position: 25 (analysis)
- tier (contract claim): process — verified vs body in map
- primary_artifact_path (SSOT claim): mastering/research/waves.json
- immediate upstream producers (from code — L1): mastering_research_routing (contract hard; body ignores)
- immediate downstream consumers (code + contract claim): mastering_research_rollup
- gate_adjacency: none
- LLM?: no
- thrash_hotspot: no
- test_gravity: thin (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/mastering_research_waves.yaml`
- Map: `.cursor/stage-clinic/maps/mastering_research_waves.possibility.md`
- Target: `.cursor/stage-clinic/targets/mastering_research_waves.target.md`
- Notes: `.cursor/stage-clinic/notes/mastering_research_waves.decisions.md`
- Module (L1): `src/interview_mux/mastering_research.py::run_mastering_research_waves`
- Tests (L1): `tests/test_hm1_schema_hollow.py, conformance`

## Pack completeness

discovery_status: complete

