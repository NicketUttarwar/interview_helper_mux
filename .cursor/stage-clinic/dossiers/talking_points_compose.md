# Stage clinic dossier — talking_points_compose

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: remediation | L1_map: complete | L2_target: draft | L3_patch: done

# TPC-B1 implemented 2026-09-17 — content_brief required before LLM; disabled stub exempt.

## §5.0 Evidence index card

- stage_id: `talking_points_compose`
- seed_position: 11 (analysis)
- tier (contract claim): llm_full — verified vs body in L1 map
- primary_artifact_path (SSOT claim): understanding/talking_points.json
- immediate upstream producers (from code — fill in L1): transcript+brief
- immediate downstream consumers (code + contract claim): ideal_cuts_propose
- gate_adjacency: none
- LLM?: OpenAI talking-points-compose.system.txt
- thrash_hotspot: listed
- test_gravity: via ideal_cuts tests (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/talking_points_compose.yaml`
- Map: `.cursor/stage-clinic/maps/talking_points_compose.possibility.md`
- Target: `.cursor/stage-clinic/targets/talking_points_compose.target.md`
- Notes: `.cursor/stage-clinic/notes/talking_points_compose.decisions.md`
- Module (fill in L1): `src/interview_mux/stages/understanding.py::run_talking_points_compose`
- Tests (fill in L1): via ideal_cuts tests

## Pack completeness

discovery_status: complete  
Do not mark L1 complete without §5.8 gate (plan §5.8).
