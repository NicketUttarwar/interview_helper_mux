# Stage clinic dossier — mastering_research_rollup

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `mastering_research_rollup`
- seed_position: 26 (analysis)
- tier (contract claim): process — verified vs body in map
- primary_artifact_path (SSOT claim): mastering/research/rollup.json + research_dossier.json
- immediate upstream producers (from code — L1): waves (+ re-runs routing/waves)
- immediate downstream consumers (code + contract claim): shape agenda/candidates/synthesize/confirm; RESEARCH_CONSUMER includes gaps
- gate_adjacency: none
- LLM?: OpenAI routing only if mastering.research.llm.enabled (default false)
- thrash_hotspot: yes (A-01 thin/stale latch)
- test_gravity: thin–solid (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/mastering_research_rollup.yaml`
- Map: `.cursor/stage-clinic/maps/mastering_research_rollup.possibility.md`
- Target: `.cursor/stage-clinic/targets/mastering_research_rollup.target.md`
- Notes: `.cursor/stage-clinic/notes/mastering_research_rollup.decisions.md`
- Module (L1): `src/interview_mux/mastering_research.py::run_mastering_research_rollup`
- Tests (L1): `tests/test_research_thin_latch.py, test_hm2_mastering_heal_pin.py`

## Pack completeness

discovery_status: complete

