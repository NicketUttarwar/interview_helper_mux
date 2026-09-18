# Stage clinic dossier — mix

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: remediation | L1_map: complete | L2_target: draft | L3_patch: done

## §5.0 Evidence index card

- stage_id: `mix`
- seed_position: 64 (delivery)
- tier (contract claim): process — lifecycle lists llm_execute (false)
- primary_artifact_path (SSOT claim): master/assembly.wav
- immediate upstream producers (from code — L1): edl + SDP hard (`_check_mix`); selection+ingest; mmaudio/omit soft; theme bookends; VO script/WAV agreement
- immediate downstream consumers: junction_snip_qa, master_finalize; listen_delight may refresh
- gate_adjacency: pre_mix publishability; incomplete-cut refuse→junction; g_listen after remaster; post_listen
- LLM?: no (placement/critic host)
- thrash_hotspot: **yes** — mix⇄junction incomplete_cut; remux cycles
- test_gravity: solid — test_mix_*, f5/hx thrash, r5 seat

## Evidence checklist (§5.1–5.6)

- [x] §5.1 Body + rails (run_mix, refuse incomplete, completeness, remux)
- [x] §5.2 Contract vs `_check_mix` honesty
- [x] §5.3 StageInfo; local ML N/A (consumes stems)
- [x] §5.4 Gates / g_listen / post_listen
- [x] §5.5 Completeness + bed/intelligibility flags
- [x] §5.6 Tests + TEST_GAP

## Links

- Contract: `docs/cross-cutting/stage-contracts/mix.yaml`
- Map: `.cursor/stage-clinic/maps/mix.possibility.md`
- Target: `.cursor/stage-clinic/targets/mix.target.md`
- Notes: `.cursor/stage-clinic/notes/mix.decisions.md`
- Module (L1): `stages/assembly.py::run_mix` → `sound_design.mix` + `mix_completeness`
- Tests (L1): `tests/test_mix_*.py`, thrash/junction suites

## Pack completeness

discovery_status: complete
