# Stage clinic dossier — gap_report_sanitize

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `gap_report_sanitize`
- seed_position: 46 (delivery)
- tier (contract claim): process — verified vs body in map
- primary_artifact_path (SSOT claim): understanding/gap_report.json
- immediate upstream producers (from code — L1): nugget_layup_compose (gap_report); contract claims layup_plan hard
- immediate downstream consumers (code + contract claim): refinement_agenda, gap_framing_recompose, vo_*, edl
- gate_adjacency: none
- LLM?: none
- thrash_hotspot: empty stub sanitary+done
- test_gravity: solid (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/gap_report_sanitize.yaml`
- Map: `.cursor/stage-clinic/maps/gap_report_sanitize.possibility.md`
- Target: `.cursor/stage-clinic/targets/gap_report_sanitize.target.md`
- Notes: `.cursor/stage-clinic/notes/gap_report_sanitize.decisions.md`
- Module (L1): `artifact_sanitize/gap_report.py::run_gap_report_sanitize`
- Tests (L1): `test_hollow_seed_sanitary.py; test_precision_invalidation.py; sanitize thrash suites`

## Pack completeness

discovery_status: complete
