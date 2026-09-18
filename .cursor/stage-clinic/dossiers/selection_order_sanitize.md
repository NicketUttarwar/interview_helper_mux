# Stage clinic dossier — selection_order_sanitize

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: remediation | L1_map: complete | L2_target: draft | L3_patch: done

## §5.0 Evidence index card

- stage_id: `selection_order_sanitize`
- seed_position: 41 (delivery)
- tier (contract claim): process — verified vs body in map
- primary_artifact_path (SSOT claim): master/selection.json
- immediate upstream producers (from code — L1): full_master_ranking
- immediate downstream consumers (code + contract claim): air_script_compose, nugget_*, transitions, edl
- gate_adjacency: none
- LLM?: none
- thrash_hotspot: no (refuse if unsanitary)
- test_gravity: solid (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/selection_order_sanitize.yaml`
- Map: `.cursor/stage-clinic/maps/selection_order_sanitize.possibility.md`
- Target: `.cursor/stage-clinic/targets/selection_order_sanitize.target.md`
- Notes: `.cursor/stage-clinic/notes/selection_order_sanitize.decisions.md`
- Module (L1): `artifact_sanitize/selection.py::run_selection_order_sanitize`
- Tests (L1): `test_artifact_sanitize_selection.py; test_hr4_ranking_sanitize_dirty_done.py; test_sanitize_authority_thrash.py`

## Pack completeness

discovery_status: complete
