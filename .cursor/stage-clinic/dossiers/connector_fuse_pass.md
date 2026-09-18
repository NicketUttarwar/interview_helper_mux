# Stage clinic dossier — connector_fuse_pass

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: remediation | L1_map: complete | L2_target: draft | L3_patch: done
# CFP-B1–B4 implemented 2026-09-17; CFP-B5/B6 needs_you open.

## §5.0 Evidence index card

- stage_id: `connector_fuse_pass`
- seed_position: 21 (analysis)
- tier (contract claim): llm_full (OpenAI economy seams)
- primary_artifact_path (SSOT claim): analysis/connector_fuse_audit.json
- immediate upstream producers (from code — fill in L1): low_conf_island_scan; manifest
- immediate downstream consumers (code + contract claim): pre_ranking, topic/narrative, ranking, nuggets, transitions, edl (claim)
- gate_adjacency: none (junction_heal has reopen gate)
- LLM?: OpenAI/external (economy seam adjudicate)
- thrash_hotspot: yes
- test_gravity: solid

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/connector_fuse_pass.yaml`
- Map: `.cursor/stage-clinic/maps/connector_fuse_pass.possibility.md`
- Target: `.cursor/stage-clinic/targets/connector_fuse_pass.target.md`
- Notes: `.cursor/stage-clinic/notes/connector_fuse_pass.decisions.md`
- Module (fill in L1): `src/interview_mux/stages/low_conf_fuse_stages.py` + `segment_fuse.py`
- Tests (fill in L1): `tests/test_low_conf_fuse_selection.py`, `test_hs3_shared_fuse_writer.py`, `test_hs4_fuse_oscillation_pin.py`

## Pack completeness

discovery_status: complete  
§5.8 gate satisfied (index + body/rails + declared-vs-actual + flags + TEST_GAP).  
Open questions: CFP-B5 (incomplete_thought_only / no seam GUI); CFP-B6 (invalidates fan-out)
