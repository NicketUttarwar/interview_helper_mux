# Stage clinic dossier — connector_fuse_pass_pre_ranking

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: remediation | L1_map: complete | L2_target: draft | L3_patch: done
# CFP-B1/B2 implemented 2026-09-17 (hard:[]; llm_full via ALL_LLM_STAGES).

## §5.0 Evidence index card

- stage_id: `connector_fuse_pass_pre_ranking`
- seed_position: 39 (delivery)
- tier (contract claim): llm_full (CFP-B2) — OpenAI economy seams
- primary_artifact_path (SSOT claim): analysis/connector_fuse_rounds.json
- immediate upstream producers (from code — L1): soft hitch+audit; body gates on manifest/enabled
- immediate downstream consumers (code + contract claim): full_master_ranking, nugget_corpus_mine, nugget_layup_compose
- gate_adjacency: none
- LLM?: OpenAI economy seam (same as fuse_pass)
- thrash_hotspot: yes — seam LLM / oscillation
- test_gravity: solid (via fuse suite) (excl. local-ML)

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/connector_fuse_pass_pre_ranking.yaml`
- Map: `.cursor/stage-clinic/maps/connector_fuse_pass_pre_ranking.possibility.md`
- Target: `.cursor/stage-clinic/targets/connector_fuse_pass_pre_ranking.target.md`
- Notes: `.cursor/stage-clinic/notes/connector_fuse_pass_pre_ranking.decisions.md`
- Module (L1): `stages/low_conf_fuse_stages.py::run_connector_fuse_pass_pre_ranking → segment_fuse`
- Tests (L1): `test_hs3_shared_fuse_writer.py; test_hs4_fuse_oscillation_pin.py; shared fuse suite`

## Pack completeness

discovery_status: complete
