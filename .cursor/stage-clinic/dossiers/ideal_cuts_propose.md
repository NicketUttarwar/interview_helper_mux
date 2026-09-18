# Stage clinic dossier — ideal_cuts_propose

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: remediation | L1_map: complete | L2_target: draft | L3_patch: done

# Wave 2 2026-09-17 — ICP-B2/B4 applied; ICP-B1 skipped (soft probes used via transcript_quality); ICP-B3 needs_you.

## §5.0 Evidence index card

- stage_id: `ideal_cuts_propose`
- seed_position: 12 (analysis)
- tier (contract claim): llm_full — verified vs body in L1 map
- primary_artifact_path (SSOT claim): understanding/ideal_cuts.json
- immediate upstream producers (from code — fill in L1): talking_points+transcript
- immediate downstream consumers (code + contract claim): materialize, boundary
- gate_adjacency: none
- LLM?: OpenAI ideal-cuts-propose.system.txt
- thrash_hotspot: listed
- test_gravity: solid (test_ideal_cuts) (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/ideal_cuts_propose.yaml`
- Map: `.cursor/stage-clinic/maps/ideal_cuts_propose.possibility.md`
- Target: `.cursor/stage-clinic/targets/ideal_cuts_propose.target.md`
- Notes: `.cursor/stage-clinic/notes/ideal_cuts_propose.decisions.md`
- Module (fill in L1): `src/interview_mux/stages/understanding.py::run_ideal_cuts_propose`
- Tests (fill in L1): solid (test_ideal_cuts)

## Pack completeness

discovery_status: complete  
Do not mark L1 complete without §5.8 gate (plan §5.8).
