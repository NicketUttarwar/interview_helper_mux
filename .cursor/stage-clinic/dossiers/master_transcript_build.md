# Stage clinic dossier — master_transcript_build

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `master_transcript_build`
- seed_position: 67 (delivery)
- tier (contract claim): process — deterministic assemble
- primary_artifact_path (SSOT claim): master/transcript.json (+ .vtt/.txt)
- immediate upstream producers (from code — L1): master.wav, edl; sidecars via assemble_master_cues
- immediate downstream consumers: podcast_publish (VTT); ADG also invalidates episode_meta_build
- gate_adjacency: G-Publish (arms ship UI; stage itself ungated)
- LLM?: no (local STT internals N/A — sidecar remap host only)
- thrash_hotspot: no
- test_gravity: solid — test_hpub3_hollow_transcript, test_asset_transcripts

## Evidence checklist (§5.1–5.6)

- [x] Complete

## Links

- Contract: `docs/cross-cutting/stage-contracts/master_transcript_build.yaml`
- Map: `.cursor/stage-clinic/maps/master_transcript_build.possibility.md`
- Target: `.cursor/stage-clinic/targets/master_transcript_build.target.md`
- Notes: `.cursor/stage-clinic/notes/master_transcript_build.decisions.md`
- Module (L1): `asset_transcripts.run_master_transcript_build`
- Tests (L1): test_hpub3_hollow_transcript.py, test_asset_transcripts.py

## Pack completeness

discovery_status: complete
