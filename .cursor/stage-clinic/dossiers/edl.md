# Stage clinic dossier — edl

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `edl`
- seed_position: 58 (delivery)
- tier (contract claim): process — verified
- primary_artifact_path (SSOT claim): master/edl.json
- immediate upstream producers (from code — L1): selection, transitions, narrative audit, gap/layup/air
- immediate downstream consumers: assembly_preview, mix, ship path
- gate_adjacency: none (G1/vo honesty enforced via incompleteness)
- LLM?: no (may call synth helpers)
- thrash_hotspot: yes — bridge glue, VO resync, order drift, vo_unsanitary
- test_gravity: solid (endc, r6 budget, assembly heal, soft_pass refuse)

## Evidence checklist (§5.1–5.6)

- [x] §5.1–5.6 all

## Links

- Contract: `docs/cross-cutting/stage-contracts/edl.yaml`
- Map: `.cursor/stage-clinic/maps/edl.possibility.md`
- Target: `.cursor/stage-clinic/targets/edl.target.md`
- Notes: `.cursor/stage-clinic/notes/edl.decisions.md`
- Module (L1): `src/interview_mux/stages/assembly.py::run_edl`
- Tests (L1): `tests/test_endc_glue_before_edl.py`, `tests/test_soft_pass_pre_edl_refuse.py`, `tests/test_r6_edl_budget.py`

## Pack completeness

discovery_status: complete
