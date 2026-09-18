# Stage clinic dossier — mastering_research_rollup

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: remediation | L1_map: complete | L2_target: draft | L3_patch: done
# MRRoll-B1/B3 implemented 2026-09-17; MRRoll-B2 needs_you open.

## §5.0 Evidence index card

- stage_id: `mastering_research_rollup`
- seed_position: 26 (analysis)
- tier (contract claim): process
- primary_artifact_path (SSOT claim): mastering/research/rollup.json (+ identical research_dossier.json)
- immediate upstream: waves (re-probed in body)
- immediate downstream: Shape/gap via RESEARCH_CONSUMER_STAGES (A-01 thin refuse)
- gate_adjacency: none
- LLM?: optional routing only if research.llm.enabled (default false)
- thrash_hotspot: A-01 shape-core thin latch
- test_gravity: solid (thin latch + HM-1)

## Evidence checklist (§5.1–5.6)

- [x] §5.1–5.6 pack complete (see map)

## Links

- Contract: `docs/cross-cutting/stage-contracts/mastering_research_rollup.yaml`
- Map: `.cursor/stage-clinic/maps/mastering_research_rollup.possibility.md`
- Target: `.cursor/stage-clinic/targets/mastering_research_rollup.target.md`
- Notes: `.cursor/stage-clinic/notes/mastering_research_rollup.decisions.md`
- Module: `src/interview_mux/mastering_research.py` (`_persist_research_dossier`)
- Tests: `tests/test_research_thin_latch.py`, `test_hm1_schema_hollow.py`, `test_narrative_excellence.py`

## Pack completeness

discovery_status: complete  
Open questions: MRRoll-B2 contract consumers vs RESEARCH_CONSUMER
