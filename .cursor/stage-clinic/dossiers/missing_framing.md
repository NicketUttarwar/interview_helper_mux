# Stage clinic dossier — missing_framing

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `missing_framing`
- seed_position: 30 (analysis)
- tier (contract claim): llm_full — verified vs body in map
- primary_artifact_path (SSOT claim): understanding/gap_evaluations.json
- immediate upstream producers (from code — L1): mastering_plan_synthesize + boundaries/brief/manifest
- immediate downstream consumers (code + contract claim): mastering_plan_confirm, gap_framing_compose
- gate_adjacency: G-Framing (+ speaker/voiceref/delivery when Yes)
- LLM?: OpenAI OA-07
- thrash_hotspot: yes
- test_gravity: solid (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/missing_framing.yaml`
- Map: `.cursor/stage-clinic/maps/missing_framing.possibility.md`
- Target: `.cursor/stage-clinic/targets/missing_framing.target.md`
- Notes: `.cursor/stage-clinic/notes/missing_framing.decisions.md`
- Module (L1): `src/interview_mux/pipeline.py::_run_missing_framing_stage → stages/gaps.py::run_missing_framing`
- Tests (L1): `tests/test_hg3_missing_framing_batch.py, test_gap_framing_gates.py, test_gates.py`

## Pack completeness

discovery_status: complete

