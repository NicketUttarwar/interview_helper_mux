# Stage clinic dossier — vo_synthesize

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `vo_synthesize`
- seed_position: 55 (delivery)
- tier (contract claim): process — verified
- primary_artifact_path (SSOT claim): mastering/vo_synthesize.json
- immediate upstream producers (from code — L1): transitions + gap (+ adjudicate); contract hard only gap_report (understates)
- immediate downstream consumers: sound_design_vo_finalize, edl_narrative_audit, edl
- gate_adjacency: **G1**
- LLM?: no OpenAI; local Chatterbox/TTS = **one-line N/A for model quality** — clinic still owns done-without-wav honesty
- thrash_hotspot: yes — G1 open, pair missing, seated VO, hard seat freeze, rewind blocks
- test_gravity: solid (HV4/HV5, vo bind, thrash, end-* VO)

## Evidence checklist (§5.1–5.6)

- [x] §5.1–5.6 all

## Links

- Contract: `docs/cross-cutting/stage-contracts/vo_synthesize.yaml`
- Map: `.cursor/stage-clinic/maps/vo_synthesize.possibility.md`
- Target: `.cursor/stage-clinic/targets/vo_synthesize.target.md`
- Notes: `.cursor/stage-clinic/notes/vo_synthesize.decisions.md`
- Module (L1): `src/interview_mux/stages/vo_synthesize.py::run_vo_synthesize`
- Tests (L1): `tests/test_hv4_g1_skip_hollow_vo_seed.py`, `tests/test_hv5_g1_needs_operator.py`, vo bind suites

## Pack completeness

discovery_status: complete
