# Stage clinic dossier — ideal_cuts_materialize

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `ideal_cuts_materialize`
- seed_position: 13 (analysis)
- tier (contract claim): process — verified process body (no OpenAI)
- primary_artifact_path (SSOT claim): understanding/ideal_cuts_materialized.json
- immediate upstream producers (from code — fill in L1): ideal_cuts_propose (`understanding/ideal_cuts.json`); soft transcript/wav
- immediate downstream consumers (code + contract claim): boundary_detection, segment_classification, ranking seed consumers
- gate_adjacency: none
- LLM?: no
- thrash_hotspot: no (boundary co-SSOT risk)
- test_gravity: solid (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/ideal_cuts_materialize.yaml`
- Map: `.cursor/stage-clinic/maps/ideal_cuts_materialize.possibility.md`
- Target: `.cursor/stage-clinic/targets/ideal_cuts_materialize.target.md`
- Notes: `.cursor/stage-clinic/notes/ideal_cuts_materialize.decisions.md`
- Module (fill in L1): `src/interview_mux/ideal_cuts.py` (`run_ideal_cuts_materialize`)
- Tests (fill in L1): `tests/test_ideal_cuts.py` (+ ownership/parity)

## Pack completeness

discovery_status: complete  
§5.8 gate satisfied (index + body/rails + declared-vs-actual + flags + TEST_GAP).  
Open questions: missing ideal_cuts soft-vs-hard
