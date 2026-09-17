# Stage clinic dossier — selection_framing_apply

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `selection_framing_apply`
- seed_position: 49 (delivery)
- tier (contract claim): deterministic — verified vs body
- primary_artifact_path (SSOT claim): understanding/selection_framing_apply.json
- immediate upstream producers (from code — L1): full_master_ranking (`master/selection.json`); gap stages (`understanding/gap_report.json`)
- immediate downstream consumers (code + contract claim): air/VO/EDL via mutated selection+gap; contract consumers []
- gate_adjacency: none (seat freeze can no-op)
- LLM?: no
- thrash_hotspot: no
- test_gravity: thin–solid (`test_hf5_pass2_gap_dirty`)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails
- [x] §5.2 Declared-vs-actual matrix
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/selection_framing_apply.yaml`
- Map: `.cursor/stage-clinic/maps/selection_framing_apply.possibility.md`
- Target: `.cursor/stage-clinic/targets/selection_framing_apply.target.md`
- Notes: `.cursor/stage-clinic/notes/selection_framing_apply.decisions.md`
- Module (L1): `src/interview_mux/refinement_passes.py::run_selection_framing_apply`
- Tests (L1): `tests/test_hf5_pass2_gap_dirty.py`

## Pack completeness

discovery_status: complete
