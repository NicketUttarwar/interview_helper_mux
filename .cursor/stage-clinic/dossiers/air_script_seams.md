# Stage clinic dossier — air_script_seams

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `air_script_seams`
- seed_position: 50 (delivery)
- tier (contract claim): llm_full — **body is deterministic Pass B** (CODE_DOC_CONFLICT)
- primary_artifact_path (SSOT claim): mastering/mastering_plan.json
- immediate upstream producers (from code — L1): air_script_compose (+ layup/gap softs)
- immediate downstream consumers: transitions, air_contract_sanitize, edl (contract)
- gate_adjacency: none (soft seat freeze can no-op compose_pass_b)
- LLM?: no OpenAI in Pass B / sonic hunt (port-manifest non_llm)
- thrash_hotspot: yes — VO contract drift stamp + restore plan
- test_gravity: solid (`test_air_script.py`, HV1 vo contract)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails
- [x] §5.2 Declared-vs-actual matrix
- [x] §5.3 Schemas / prompts (OpenAI N/A; local ML N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/air_script_seams.yaml`
- Map: `.cursor/stage-clinic/maps/air_script_seams.possibility.md`
- Target: `.cursor/stage-clinic/targets/air_script_seams.target.md`
- Notes: `.cursor/stage-clinic/notes/air_script_seams.decisions.md`
- Module (L1): `src/interview_mux/air_script.py::run_air_script_seams`
- Tests (L1): `tests/test_air_script.py`, `tests/test_hv1_vo_contract_ladder_spin.py`

## Pack completeness

discovery_status: complete
