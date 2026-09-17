# Stage clinic dossier — narrative_arc_plan

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `narrative_arc_plan`
- seed_position: 37 (delivery)
- tier (contract claim): llm_full — verified vs body in map
- primary_artifact_path (SSOT claim): master/narrative_plan.json
- immediate upstream producers (from code — L1): topic_coverage_audit (+ content_brief via stage_input_checks)
- immediate downstream consumers (code + contract claim): chapter_close_hitch, full_master_ranking, air_script_compose, transitions
- gate_adjacency: none
- LLM?: OpenAI OF-ish narrative-arc-plan (or det talking_points)
- thrash_hotspot: no (hitch may rewrite plan later)
- test_gravity: thin–solid (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/narrative_arc_plan.yaml`
- Map: `.cursor/stage-clinic/maps/narrative_arc_plan.possibility.md`
- Target: `.cursor/stage-clinic/targets/narrative_arc_plan.target.md`
- Notes: `.cursor/stage-clinic/notes/narrative_arc_plan.decisions.md`
- Module (L1): `stages/analysis_extended.py::run_narrative_arc`
- Tests (L1): `fixtures/llm_envelopes/narrative_arc_*; test_llm_envelope_fixtures; parity/homunculus`

## Pack completeness

discovery_status: complete
