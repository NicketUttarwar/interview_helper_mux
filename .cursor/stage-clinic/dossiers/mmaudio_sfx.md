# Stage clinic dossier — mmaudio_sfx

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `mmaudio_sfx`
- seed_position: 63 (delivery)
- tier (contract claim): process — body MusicGen-first + MMAudio; lifecycle wrongly lists llm_execute
- primary_artifact_path (SSOT claim): sound_design/mmaudio_qa.json (+ WAVs)
- immediate upstream producers (from code — L1): SDP, sfx_prompts, assembly_preview; G1.5 approved
- immediate downstream consumers: mix
- gate_adjacency: G1.5; post_listen / block_mix_on_mmaudio_qa_fail; music listen optional
- LLM?: no stage OpenAI; local MusicGen/MMAudio
- thrash_hotspot: yes — music limbo / lease / identical musicgen_theme_failed
- test_gravity: solid host tests (excl. model invoke)

## Evidence checklist (§5.1–5.6)

- [x] §5.1–5.6 complete for host honesty; local ML internals N/A

## Links

- Contract: `docs/cross-cutting/stage-contracts/mmaudio_sfx.yaml`
- Map: `.cursor/stage-clinic/maps/mmaudio_sfx.possibility.md`
- Target: `.cursor/stage-clinic/targets/mmaudio_sfx.target.md`
- Notes: `.cursor/stage-clinic/notes/mmaudio_sfx.decisions.md`
- Module (L1): `stages/sfx_mmaudio.py` + `mmaudio_asset_qa.run_mmaudio_asset_qa` + musicgen_runner
- Tests (L1): test_sfx_mmaudio*, test_mmaudio_asset_qa, thrash suites

## Pack completeness

discovery_status: complete
