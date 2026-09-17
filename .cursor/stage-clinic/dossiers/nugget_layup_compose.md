# Stage clinic dossier — nugget_layup_compose

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `nugget_layup_compose`
- seed_position: 45 (delivery)
- tier (contract claim): llm_full — verified vs body in map
- primary_artifact_path (SSOT claim): understanding/nugget_layup_plan.json
- immediate upstream producers (from code — L1): corpus + selection + IP audit
- immediate downstream consumers (code + contract claim): gap_report_sanitize, gap_framing_recompose, transitions, vo_*
- gate_adjacency: none (G1 optional after publishes gap_report)
- LLM?: OpenAI nugget-layup-compose OF-03b
- thrash_hotspot: yes — QC floors / shard / CTA / dual SSOT gap_report
- test_gravity: solid (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/nugget_layup_compose.yaml`
- Map: `.cursor/stage-clinic/maps/nugget_layup_compose.possibility.md`
- Target: `.cursor/stage-clinic/targets/nugget_layup_compose.target.md`
- Notes: `.cursor/stage-clinic/notes/nugget_layup_compose.decisions.md`
- Module (L1): `stages/analysis_extended.py::run_nugget_layup_compose`
- Tests (L1): `test_nugget_layup.py; test_artifact_sanitize_layup.py; test_f3_*; test_layup_authority_*; media_ip/hg5/homunculus`

## Pack completeness

discovery_status: complete
