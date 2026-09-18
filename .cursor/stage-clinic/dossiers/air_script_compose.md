# Stage clinic dossier — air_script_compose

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: remediation | L1_map: complete | L2_target: draft | L3_patch: done

## §5.0 Evidence index card

- stage_id: `air_script_compose`
- seed_position: 42 (delivery)
- tier (contract claim): process (ASC-B1) — matches deterministic Pass A
- primary_artifact_path (SSOT claim): mastering/mastering_plan.json
- immediate upstream producers (from code — L1): full_master_ranking / selection_order_sanitize
- immediate downstream consumers (code + contract claim): nugget_corpus_mine, air_script_seams, edl
- gate_adjacency: none
- LLM?: none for Pass A
- thrash_hotspot: automation fail_closed (enable=false skip latch ASC-B2 done)
- test_gravity: solid (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/air_script_compose.yaml`
- Map: `.cursor/stage-clinic/maps/air_script_compose.possibility.md`
- Target: `.cursor/stage-clinic/targets/air_script_compose.target.md`
- Notes: `.cursor/stage-clinic/notes/air_script_compose.decisions.md`
- Module (L1): `air_script.py::run_air_script_compose → compose_pass_a`
- Tests (L1): `test_air_script.py; test_hr3_pass_a_hollow_seats_pin.py`

## Pack completeness

discovery_status: complete
