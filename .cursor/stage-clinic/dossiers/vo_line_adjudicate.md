# Stage clinic dossier — vo_line_adjudicate

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: remediation | L1_map: complete | L2_target: draft | L3_patch: done
# Wave 2 2026-09-17 — no product patch; B1/B2 skipped (FULL_AUTO_REGRESSION_RISK; B2 also needs_you).

## §5.0 Evidence index card

- stage_id: `vo_line_adjudicate`
- seed_position: 54 (delivery)
- tier (contract claim): llm_full — verified when adjudicate enabled + homunculus
- primary_artifact_path (SSOT claim): understanding/vo_line_adjudication.json
- immediate upstream producers (from code — L1): nugget_layup + gap_report (hard); omit_ledger soft
- immediate downstream consumers: vo_synthesize (invalidates edl_narrative/edl)
- gate_adjacency: G1 adjacency (not owned); brain 0.2.0 required
- LLM?: OpenAI batched adjudicate (+ intro compose path)
- thrash_hotspot: yes — hollow skip stubs / coverage floor / g1_vo_open resume
- test_gravity: solid (`test_vo_line_adjudicate.py`, HV3/HV5)

## Evidence checklist (§5.1–5.6)

- [x] §5.1–5.6 all

## Links

- Contract: `docs/cross-cutting/stage-contracts/vo_line_adjudicate.yaml`
- Map: `.cursor/stage-clinic/maps/vo_line_adjudicate.possibility.md`
- Target: `.cursor/stage-clinic/targets/vo_line_adjudicate.target.md`
- Notes: `.cursor/stage-clinic/notes/vo_line_adjudicate.decisions.md`
- Module (L1): `stages/vo_line_adjudicate.py` → `vo_line_adjudicate.py::run_vo_line_adjudicate_stage`
- Tests (L1): `tests/test_vo_line_adjudicate.py`, `tests/test_hv3_adjudicate_hollow_done.py`

## Pack completeness

discovery_status: complete
