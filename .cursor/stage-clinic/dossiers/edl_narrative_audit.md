# Stage clinic dossier — edl_narrative_audit

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `edl_narrative_audit`
- seed_position: 57 (delivery)
- tier (contract claim): llm_full — verified
- primary_artifact_path (SSOT claim): master/edl_narrative_audit.json
- immediate upstream producers (from code — L1): vo_synthesize heard + SDP soft; contract hard only SDP (understates)
- immediate downstream consumers: edl (verdict=fail blocks)
- gate_adjacency: none (heard_wav may pin vo_synthesize)
- LLM?: OpenAI — `selection/edl-narrative-audit.system.txt`
- thrash_hotspot: yes — HE-1 heard_wav; remutate; thrash cap in agenda
- test_gravity: solid (`test_he1_audit_heard_wav.py`)

## Evidence checklist (§5.1–5.6)

- [x] §5.1–5.6 all

## Links

- Contract: `docs/cross-cutting/stage-contracts/edl_narrative_audit.yaml`
- Map: `.cursor/stage-clinic/maps/edl_narrative_audit.possibility.md`
- Target: `.cursor/stage-clinic/targets/edl_narrative_audit.target.md`
- Notes: `.cursor/stage-clinic/notes/edl_narrative_audit.decisions.md`
- Module (L1): `src/interview_mux/stages/edl_narrative_audit.py::run_edl_narrative_audit`
- Tests (L1): `tests/test_he1_audit_heard_wav.py`, remutate suites

## Pack completeness

discovery_status: complete
