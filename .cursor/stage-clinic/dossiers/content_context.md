# Stage clinic dossier — content_context

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: remediation | L1_map: complete | L2_target: draft | L3_patch: done

# CC-B2 + CC-B1 implemented 2026-09-18 (Q1A harden topology before LLM).

## §5.0 Evidence index card

- stage_id: `content_context`
- seed_position: 10 (analysis)
- tier (contract claim): llm_full — verified vs body in L1 map
- primary_artifact_path (SSOT claim): understanding/content_brief.json
- immediate upstream producers (from code — fill in L1): speakers+transcript+topology claim
- immediate downstream consumers (code + contract claim): talking_points, cuts
- gate_adjacency: none
- LLM?: OpenAI content-context.system.txt
- thrash_hotspot: listed
- test_gravity: thin/solid mixed (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/content_context.yaml`
- Map: `.cursor/stage-clinic/maps/content_context.possibility.md`
- Target: `.cursor/stage-clinic/targets/content_context.target.md`
- Notes: `.cursor/stage-clinic/notes/content_context.decisions.md`
- Module (fill in L1): `src/interview_mux/stages/understanding.py::run_content_context`
- Tests (fill in L1): thin/solid mixed

## Pack completeness

discovery_status: complete  
Do not mark L1 complete without §5.8 gate (plan §5.8).
