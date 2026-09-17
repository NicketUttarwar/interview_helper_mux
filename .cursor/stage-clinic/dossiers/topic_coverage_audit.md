# Stage clinic dossier — topic_coverage_audit

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `topic_coverage_audit`
- seed_position: 36 (delivery)
- tier (contract claim): llm_full — verified vs body in map
- primary_artifact_path (SSOT claim): master/coverage_audit.json
- immediate upstream producers (from code — L1): delivery_brief_build (+ analysis complete)
- immediate downstream consumers (code + contract claim): narrative_arc_plan
- gate_adjacency: none
- LLM?: OpenAI OF-01 if det path unavailable
- thrash_hotspot: HG-4 voice_ref mis-pin
- test_gravity: thin–solid (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/topic_coverage_audit.yaml`
- Map: `.cursor/stage-clinic/maps/topic_coverage_audit.possibility.md`
- Target: `.cursor/stage-clinic/targets/topic_coverage_audit.target.md`
- Notes: `.cursor/stage-clinic/notes/topic_coverage_audit.decisions.md`
- Module (L1): `src/interview_mux/stages/analysis_extended.py::run_topic_coverage`
- Tests (L1): `tests/test_coherence_topic_coverage_volley.py, flow hardening`

## Pack completeness

discovery_status: complete

