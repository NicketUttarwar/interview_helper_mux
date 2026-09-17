# Stage clinic dossier — full_master_ranking

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `full_master_ranking`
- seed_position: 40 (delivery)
- tier (contract claim): llm_full — verified vs body in map
- primary_artifact_path (SSOT claim): master/selection.json
- immediate upstream producers (from code — L1): narrative_arc_plan + manifest + gap_report (code); contract also fuse_rounds+coverage
- immediate downstream consumers (code + contract claim): selection_order_sanitize, air_script_compose, nugget_*, transitions, edl
- gate_adjacency: none (soft narrative_qc, not G*)
- LLM?: OpenAI full-master-ranking.system.txt
- thrash_hotspot: yes — QC strict / empty ordered / Shape bind
- test_gravity: solid (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/full_master_ranking.yaml`
- Map: `.cursor/stage-clinic/maps/full_master_ranking.possibility.md`
- Target: `.cursor/stage-clinic/targets/full_master_ranking.target.md`
- Notes: `.cursor/stage-clinic/notes/full_master_ranking.decisions.md`
- Module (L1): `stages/selection.py::run_full_master_ranking`
- Tests (L1): `test_ranking_persist_continue.py; test_hr2/hr4; test_f1_selection_lattice.py; test_selection_pack.py`

## Pack completeness

discovery_status: complete
