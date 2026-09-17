# Stage clinic dossier — mastering_research_routing

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `mastering_research_routing`
- seed_position: 24 (analysis)
- tier (contract claim): process — optional OpenAI when research.llm.enabled
- primary_artifact_path (SSOT claim): mastering/research/routing.json
- immediate upstream producers (from code — fill in L1): sound_design_plan (contract hard, not enforced); many soft
- immediate downstream consumers (code + contract claim): mastering_research_waves / rollup / shape
- gate_adjacency: none
- LLM?: OpenAI/external only if mastering.research.llm.enabled (default false)
- thrash_hotspot: no
- test_gravity: thin

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/mastering_research_routing.yaml`
- Map: `.cursor/stage-clinic/maps/mastering_research_routing.possibility.md`
- Target: `.cursor/stage-clinic/targets/mastering_research_routing.target.md`
- Notes: `.cursor/stage-clinic/notes/mastering_research_routing.decisions.md`
- Module (fill in L1): `src/interview_mux/mastering_research.py` (`run_research_routing`)
- Tests (fill in L1): `tests/test_a03_mastering_llm_cutover.py`, `test_hm2_mastering_heal_pin.py`

## Pack completeness

discovery_status: complete  
§5.8 gate satisfied (index + body/rails + declared-vs-actual + flags + TEST_GAP).  
Open questions: LLM fail → stub vs refuse
