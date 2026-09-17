# Stage clinic dossier — mastering_plan_synthesize

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `mastering_plan_synthesize`
- seed_position: 29 (analysis)
- tier (contract claim): process — verified vs body in map
- primary_artifact_path (SSOT claim): mastering/mastering_plan.json
- immediate upstream producers (from code — L1): mastering_shape_candidates
- immediate downstream consumers (code + contract claim): missing_framing, confirm, gap compose, delivery chain
- gate_adjacency: none
- LLM?: OpenAI OH-FS if shape.llm else soft_gate degraded
- thrash_hotspot: A-03 authority
- test_gravity: solid-ish A-03/HM (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/mastering_plan_synthesize.yaml`
- Map: `.cursor/stage-clinic/maps/mastering_plan_synthesize.possibility.md`
- Target: `.cursor/stage-clinic/targets/mastering_plan_synthesize.target.md`
- Notes: `.cursor/stage-clinic/notes/mastering_plan_synthesize.decisions.md`
- Module (L1): `src/interview_mux/mastering_shape_runtime.py::run_mastering_plan_synthesize`
- Tests (L1): `tests/test_a03_mastering_llm_cutover.py, test_hm3_soft_plan_bind.py`

## Pack completeness

discovery_status: complete

