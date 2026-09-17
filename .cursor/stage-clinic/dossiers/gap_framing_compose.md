# Stage clinic dossier — gap_framing_compose

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `gap_framing_compose`
- seed_position: 32 (analysis)
- tier (contract claim): llm_full — verified vs body in map
- primary_artifact_path (SSOT claim): understanding/gap_report.json
- immediate upstream producers (from code — L1): missing_framing + mastering_plan
- immediate downstream consumers (code + contract claim): delivery_brief_build + VO/ranking chain
- gate_adjacency: G1 optional later (not this stage)
- LLM?: OpenAI OA-08
- thrash_hotspot: yes (layup no-op, high_gap fill)
- test_gravity: solid (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/gap_framing_compose.yaml`
- Map: `.cursor/stage-clinic/maps/gap_framing_compose.possibility.md`
- Target: `.cursor/stage-clinic/targets/gap_framing_compose.target.md`
- Notes: `.cursor/stage-clinic/notes/gap_framing_compose.decisions.md`
- Module (L1): `src/interview_mux/pipeline.py::_run_gap_framing_compose_stage → gaps.run_gap_framing_compose`
- Tests (L1): `tests/test_gap_framing_gates.py, test_hg2_gap_tail_hollow.py`

## Pack completeness

discovery_status: complete

