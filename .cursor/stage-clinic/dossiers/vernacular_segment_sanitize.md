# Stage clinic dossier — vernacular_segment_sanitize

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: not_started | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `vernacular_segment_sanitize`
- seed_position: 19 (analysis)
- tier (contract claim): process — verified
- primary_artifact_path (SSOT claim): vernacular/resplit_report.json (HS-5)
- immediate upstream producers (from code — fill in L1): manifest + protected_zones (contract claims boundaries hard)
- immediate downstream consumers (code + contract claim): low_conf_island_scan, connector_fuse_pass, ranking
- gate_adjacency: none
- LLM?: no
- thrash_hotspot: no
- test_gravity: solid

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (entry, writes, incompleteness, heal, dispatch, invalidation)
- [x] §5.2 Declared-vs-actual matrix (contract/ADG/ownership)
- [x] §5.3 Schemas / StageInfo / OpenAI prompts (local ML = one-line N/A)
- [x] §5.4 Gates / GUI / partial
- [x] §5.5 Config flags + defaults
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/vernacular_segment_sanitize.yaml`
- Map: `.cursor/stage-clinic/maps/vernacular_segment_sanitize.possibility.md`
- Target: `.cursor/stage-clinic/targets/vernacular_segment_sanitize.target.md`
- Notes: `.cursor/stage-clinic/notes/vernacular_segment_sanitize.decisions.md`
- Module (fill in L1): `src/interview_mux/stages/audio_probes.py` (`run_vernacular_segment_sanitize`)
- Tests (fill in L1): `tests/test_hs5_vernacular_hollow.py`, `test_i4_vernacular_manifest_ownership.py`

## Pack completeness

discovery_status: complete  
§5.8 gate satisfied (index + body/rails + declared-vs-actual + flags + TEST_GAP).  
Open questions: 
