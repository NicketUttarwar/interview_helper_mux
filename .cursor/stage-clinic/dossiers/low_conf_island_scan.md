# Stage clinic dossier — low_conf_island_scan

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `low_conf_island_scan`
- seed_position: 20 (analysis)
- tier (contract claim): process — verified
- primary_artifact_path (SSOT claim): analysis/low_conf_islands.json
- immediate upstream producers (from code — fill in L1): vernacular resplit (contract); manifest/transcript soft
- immediate downstream consumers (code + contract claim): connector_fuse_pass, full_master_ranking
- gate_adjacency: none
- LLM?: no
- thrash_hotspot: yes (island/fuse family)
- test_gravity: thin→solid

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/low_conf_island_scan.yaml`
- Map: `.cursor/stage-clinic/maps/low_conf_island_scan.possibility.md`
- Target: `.cursor/stage-clinic/targets/low_conf_island_scan.target.md`
- Notes: `.cursor/stage-clinic/notes/low_conf_island_scan.decisions.md`
- Module (fill in L1): `src/interview_mux/stages/low_conf_fuse_stages.py` + `low_conf_islands.py`
- Tests (fill in L1): `tests/test_low_conf_fuse_selection.py`, `test_hs1_island_fuse_reentry.py`

## Pack completeness

discovery_status: complete  
§5.8 gate satisfied (index + body/rails + declared-vs-actual + flags + TEST_GAP).  
Open questions: disabled path skip-done?
